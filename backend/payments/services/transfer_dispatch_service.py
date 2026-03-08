"""
Transfer Dispatch Service
Handles creation of Stripe Transfers to sellers after payment confirmation.

Architecture: Separate Charges and Transfers
- Platform owns the PaymentIntent on its own account
- After payment_intent.succeeded, creates individual Transfers to each seller
- MANDATORY: uses source_transaction=charge_id on every Transfer
- This links the Transfer to the original charge, enabling proper reporting and refunds

Split Calculation (shipping separation):
    product_amount  = sum(item.subtotal)        ← base da comissão (somente produtos)
    shipping_amount = sum(item.shipping_cost)   ← retido integralmente pela plataforma
    platform_fee    = product_amount * PLATFORM_FEE_PERCENTAGE / 100
    seller_net      = product_amount - platform_fee
    gross_amount    = product_amount + shipping_amount (mantido para compatibilidade)
    Transfer Stripe = seller_net (NUNCA inclui shipping)

Nota: o frete é retido no saldo Stripe da plataforma para cobrir débitos ME via API.
O Melhor Envio NÃO é uma Stripe Connected Account — não há Transfer para o ME.
"""

import stripe
import logging
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


class TransferDispatchError(Exception):
    """Raised when transfer dispatch fails for a seller"""
    pass


class TransferDispatchService:
    """Service for dispatching Stripe Transfers to sellers after payment confirmation"""

    @staticmethod
    def calculate_seller_split(order, seller, platform_fee_pct: Decimal):
        """
        Calculate split amounts for a specific seller separating product and shipping.

        Args:
            order: Order instance
            seller: CustomUser (seller) instance
            platform_fee_pct: Platform fee percentage as Decimal (e.g. Decimal('10'))

        Returns:
            tuple: (product_cents: int, shipping_cents: int, fee_cents: int, net_cents: int,
                    product_decimal: Decimal, shipping_decimal: Decimal,
                    fee_decimal: Decimal, net_decimal: Decimal)

        Formula:
            product_amount  = sum(item.subtotal)        — base da comissão
            shipping_amount = sum(item.shipping_cost)   — retido pela plataforma
            platform_fee    = product_amount * fee_pct / 100
            seller_net      = product_amount - platform_fee
            Transfer Stripe = seller_net  (NUNCA inclui shipping)
        """
        seller_items = order.items.filter(seller=seller)

        product_decimal = Decimal('0.00')
        shipping_decimal = Decimal('0.00')
        for item in seller_items:
            # item.subtotal = unit_price * quantity (auto-calculated on save)
            product_decimal += item.subtotal
            # Shipping is retained by the platform — never transferred to seller
            shipping_decimal += item.shipping_cost

        # Platform fee is applied only on product amount (not shipping)
        fee_decimal = (product_decimal * platform_fee_pct / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        net_decimal = product_decimal - fee_decimal

        # Convert to cents for Stripe (integer)
        product_cents = int(product_decimal * 100)
        shipping_cents = int(shipping_decimal * 100)
        fee_cents = int(fee_decimal * 100)
        net_cents = int(net_decimal * 100)

        logger.debug(
            "Seller split calculated",
            extra={
                'order_id': str(order.id),
                'seller_id': seller.id,
                'seller_email': seller.email,
                'product_cents': product_cents,
                'shipping_cents': shipping_cents,
                'fee_cents': fee_cents,
                'net_cents': net_cents,
                'platform_fee_pct': str(platform_fee_pct),
            }
        )

        return (
            product_cents, shipping_cents, fee_cents, net_cents,
            product_decimal, shipping_decimal, fee_decimal, net_decimal
        )

    @staticmethod
    @transaction.atomic
    def dispatch_transfers_for_order(order, payment, charge_id: str):
        """
        Create a Stripe Transfer for each seller in the order.

        Args:
            order: Order instance (with items prefetched if possible)
            payment: Payment model instance (must be in 'succeeded' status)
            charge_id: Stripe Charge ID from payment_intent.latest_charge
                       REQUIRED: used as source_transaction for the Transfer

        Returns:
            list[PaymentSplit]: Created/updated PaymentSplit records

        Raises:
            TransferDispatchError: If a critical failure occurs dispatching transfers

        Note:
            Failures for individual sellers are logged but the transaction continues
            so other sellers still receive their funds. The failed split is marked
            with transfer_status='failed' for later retry.
        """
        from payments.models import PaymentSplit

        if not charge_id:
            raise TransferDispatchError(
                f"charge_id is required to create Transfers. "
                f"Payment {payment.id} / Order {order.id}"
            )

        platform_fee_pct = Decimal(str(getattr(settings, 'PLATFORM_FEE_PERCENTAGE', 10)))

        # Get distinct sellers in this order
        sellers = list(
            order.items.select_related('seller')
            .values_list('seller', flat=True)
            .distinct()
        )

        if not sellers:
            logger.warning(
                "No sellers found in order, skipping transfer dispatch",
                extra={'order_id': str(order.id), 'payment_id': payment.id}
            )
            return []

        # Import here to avoid circular imports at module level
        from authentication.models import CustomUser

        splits_created = []

        for seller_id in sellers:
            seller = CustomUser.objects.get(pk=seller_id)

            # Calculate amounts for this seller (new formula: product/shipping separated)
            (
                product_cents, shipping_cents, fee_cents, net_cents,
                product_decimal, shipping_decimal, fee_decimal, net_decimal
            ) = TransferDispatchService.calculate_seller_split(
                order, seller, platform_fee_pct
            )

            # gross_amount kept for backward compatibility = product + shipping
            gross_decimal = product_decimal + shipping_decimal

            # Get or create PaymentSplit record (idempotent)
            split, created = PaymentSplit.objects.get_or_create(
                payment=payment,
                seller=seller,
                defaults={
                    'gross_amount': gross_decimal,
                    'product_amount': product_decimal,
                    'shipping_amount': shipping_decimal,
                    'platform_fee_amount': fee_decimal,
                    'net_amount': net_decimal,
                    'transfer_status': 'pending',
                }
            )

            # If split already dispatched successfully, skip
            if not created and split.transfer_status == 'dispatched':
                logger.info(
                    "PaymentSplit already dispatched, skipping",
                    extra={
                        'split_id': split.id,
                        'seller_id': seller.id,
                        'stripe_transfer_id': split.stripe_transfer_id,
                    }
                )
                splits_created.append(split)
                continue

            # Validate seller has a connected Stripe account
            if not seller.stripe_account_id:
                error_msg = (
                    f"Seller {seller.email} (id={seller.id}) has no stripe_account_id. "
                    f"Transfer skipped."
                )
                logger.error(
                    error_msg,
                    extra={
                        'order_id': str(order.id),
                        'seller_id': seller.id,
                        'payment_id': payment.id,
                    }
                )
                split.transfer_status = 'failed'
                split.error_message = error_msg
                split.save(update_fields=['transfer_status', 'error_message', 'updated_at'])
                splits_created.append(split)
                continue

            # Deterministic idempotency key:  tr_{order_id}_{seller_id}_{charge_id[:8]}
            idempotency_key = f"tr_{order.id}_{seller.id}_{charge_id[:8]}"

            logger.info(
                "Dispatching Stripe Transfer to seller",
                extra={
                    'order_id': str(order.id),
                    'seller_id': seller.id,
                    'seller_email': seller.email,
                    'stripe_account_id': seller.stripe_account_id,
                    'product_cents': product_cents,
                    'shipping_cents': shipping_cents,
                    'fee_cents': fee_cents,
                    'net_cents': net_cents,
                    'charge_id': charge_id,
                    'idempotency_key': idempotency_key,
                }
            )

            try:
                transfer = stripe.Transfer.create(
                    amount=net_cents,  # seller_net = product - fee (shipping EXCLUDED)
                    currency='brl',
                    destination=seller.stripe_account_id,
                    source_transaction=charge_id,
                    transfer_group=payment.transfer_group,
                    description=(
                        f"Repasse - Pedido {order.order_number} "
                        f"- Vendedor {seller.email}"
                    ),
                    metadata={
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'seller_id': str(seller.id),
                        'seller_email': seller.email,
                        'payment_id': str(payment.id),
                        'product_amount': str(product_decimal),
                        'shipping_amount': str(shipping_decimal),
                        'platform_fee': str(fee_decimal),
                        'net_amount': str(net_decimal),
                    },
                    idempotency_key=idempotency_key,
                )

                # Update split with transfer info
                split.stripe_transfer_id = transfer.id
                split.transfer_status = 'dispatched'
                split.error_message = ''
                split.save(update_fields=[
                    'stripe_transfer_id', 'transfer_status',
                    'error_message', 'updated_at'
                ])

                logger.info(
                    "Stripe Transfer created successfully",
                    extra={
                        'transfer_id': transfer.id,
                        'seller_id': seller.id,
                        'seller_email': seller.email,
                        'net_cents': net_cents,
                        'order_id': str(order.id),
                    }
                )

            except stripe.error.IdempotencyError:
                # Transfer already created with this key — retrieve and update split
                logger.warning(
                    "IdempotencyError for transfer — retrieving existing transfer",
                    extra={
                        'idempotency_key': idempotency_key,
                        'seller_id': seller.id,
                    }
                )
                # We cannot retrieve by idempotency key; mark as dispatched conservatively
                # The webhook handler for transfer.created will update if needed
                split.transfer_status = 'dispatched'
                split.error_message = 'IdempotencyError - transfer may already exist'
                split.save(update_fields=['transfer_status', 'error_message', 'updated_at'])

            except stripe.error.StripeError as e:
                error_msg = f"Stripe error creating transfer for seller {seller.id}: {str(e)}"
                logger.error(
                    error_msg,
                    extra={
                        'order_id': str(order.id),
                        'seller_id': seller.id,
                        'error_type': type(e).__name__,
                        'error_code': getattr(e, 'code', None),
                    },
                    exc_info=True
                )
                split.transfer_status = 'failed'
                split.error_message = str(e)
                split.save(update_fields=['transfer_status', 'error_message', 'updated_at'])
                # Continue processing other sellers — do not abort the whole transaction

            splits_created.append(split)

        logger.info(
            "Transfer dispatch completed for order",
            extra={
                'order_id': str(order.id),
                'payment_id': payment.id,
                'splits_total': len(splits_created),
                'splits_dispatched': sum(
                    1 for s in splits_created if s.transfer_status == 'dispatched'
                ),
                'splits_failed': sum(
                    1 for s in splits_created if s.transfer_status == 'failed'
                ),
            }
        )

        return splits_created

    @staticmethod
    def calculate_total_platform_fee(order) -> Decimal:
        """
        Calculate total platform fee across all sellers in the order.
        Used by PaymentIntentService to store platform_fee_total on Payment.

        Args:
            order: Order instance

        Returns:
            Decimal: Total platform fee in BRL
        """
        platform_fee_pct = Decimal(str(getattr(settings, 'PLATFORM_FEE_PERCENTAGE', 10)))

        sellers = list(
            order.items.values_list('seller', flat=True).distinct()
        )

        total_fee = Decimal('0.00')
        for seller_id in sellers:
            from authentication.models import CustomUser
            seller = CustomUser.objects.get(pk=seller_id)
            # New return: (product_cents, shipping_cents, fee_cents, net_cents,
            #              product_decimal, shipping_decimal, fee_decimal, net_decimal)
            _, _, _, _, _, _, fee_decimal, _ = TransferDispatchService.calculate_seller_split(
                order, seller, platform_fee_pct
            )
            total_fee += fee_decimal

        return total_fee
