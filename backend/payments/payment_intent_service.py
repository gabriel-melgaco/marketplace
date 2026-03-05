"""
Payment Intent Service
Handles creation and management of Stripe Payment Intents

Key design decisions:
- Idempotency key is DETERMINISTIC: f"pi_{order.id}_{order.order_number}"
  This ensures retries on the same order always hit the same PaymentIntent.
- transfer_group is set on creation: f"group_{order.id}"
  Required for Separate Charges and Transfers pattern.
- Seller readiness is validated BEFORE creating the PaymentIntent.
  If any seller cannot receive transfers, the payment is rejected.
- platform_fee_total is calculated server-side and stored on Payment.
"""

import stripe
import logging
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from decimal import Decimal

from .models import Payment

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


class SellerNotReadyError(Exception):
    """Raised when one or more sellers are not ready to receive transfers"""
    pass


class PaymentIntentService:
    """Service for creating and managing Stripe Payment Intents"""

    @staticmethod
    def _validate_sellers_ready(order):
        """
        Validate that all sellers in the order have active Stripe accounts
        capable of receiving transfers.

        Args:
            order: Order instance

        Raises:
            SellerNotReadyError: If any seller is not ready to receive payments
        """
        seller_ids = list(
            order.items.values_list('seller', flat=True).distinct()
        )

        if not seller_ids:
            raise SellerNotReadyError("Order has no items/sellers")

        from authentication.models import CustomUser
        unready_sellers = []

        for seller_id in seller_ids:
            try:
                seller = CustomUser.objects.get(pk=seller_id)
            except CustomUser.DoesNotExist:
                unready_sellers.append(f"seller_id={seller_id} (not found)")
                continue

            if not seller.stripe_account_id:
                unready_sellers.append(
                    f"{seller.email} (no Stripe account)"
                )
                continue

            # Check transfer capability via Stripe API
            # We check charges_enabled as a proxy for transfer readiness
            # In Separate Charges and Transfers, the destination account must
            # have transfers enabled.
            try:
                account = stripe.Account.retrieve(seller.stripe_account_id)
                if not account.get('charges_enabled', False):
                    unready_sellers.append(
                        f"{seller.email} (charges_enabled=False on account {seller.stripe_account_id})"
                    )
            except stripe.error.StripeError as e:
                logger.warning(
                    f"Could not verify seller {seller.email} account status: {str(e)}",
                    extra={
                        'seller_id': seller.id,
                        'stripe_account_id': seller.stripe_account_id,
                    }
                )
                unready_sellers.append(
                    f"{seller.email} (could not verify Stripe account: {str(e)})"
                )

        if unready_sellers:
            sellers_str = ', '.join(unready_sellers)
            raise SellerNotReadyError(
                f"The following sellers cannot receive payments: {sellers_str}"
            )

        logger.info(
            "All sellers validated as ready to receive transfers",
            extra={
                'order_id': str(order.id),
                'seller_count': len(seller_ids),
            }
        )

    @staticmethod
    @transaction.atomic
    def create_payment_intent(order, payment_method, user):
        """
        Create a Payment Intent in Stripe and corresponding Payment record.

        Args:
            order: Order instance
            payment_method: Payment method type ('credit_card', 'debit_card', 'pix', 'boleto')
            user: User making the payment

        Returns:
            tuple: (Payment instance, client_secret string)

        Raises:
            SellerNotReadyError: If any seller is not ready to receive transfers
            ValueError: If order already has an active payment
            stripe.error.StripeError: If Stripe API fails

        Design:
            - Idempotency key is deterministic: pi_{order.id}_{order.order_number}
            - transfer_group is set: group_{order.id}
            - platform_fee_total is calculated server-side
        """
        # Deterministic idempotency key — safe for retries
        idempotency_key = f"pi_{order.id}_{order.order_number}"
        transfer_group = f"group_{order.id}"

        logger.info(
            "Creating payment intent for order",
            extra={
                'order_id': str(order.id),
                'order_number': order.order_number,
                'user_id': user.id,
                'amount': float(order.total),
                'idempotency_key': idempotency_key,
                'transfer_group': transfer_group,
                'payment_method': payment_method,
            }
        )

        # Validate all sellers are ready to receive transfers BEFORE creating PI
        PaymentIntentService._validate_sellers_ready(order)

        # Calculate platform fee server-side
        from .services.transfer_dispatch_service import TransferDispatchService
        platform_fee_total = TransferDispatchService.calculate_total_platform_fee(order)

        try:
            # Determine payment method types based on method
            if payment_method in ['credit_card', 'debit_card']:
                payment_method_types = ['card']
            elif payment_method == 'boleto':
                payment_method_types = ['boleto']
            elif payment_method == 'pix':
                payment_method_types = ['pix']
            else:
                payment_method_types = ['card']

            # Create Payment Intent in Stripe
            # transfer_group links this charge to subsequent Transfers
            intent = stripe.PaymentIntent.create(
                amount=int(float(order.total) * 100),  # Convert to cents
                currency='brl',
                payment_method_types=payment_method_types,
                transfer_group=transfer_group,
                description=f'Pedido #{order.order_number}',
                metadata={
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'user_id': user.id,
                    'payment_method': payment_method,
                    'platform_fee_total': str(platform_fee_total),
                },
                idempotency_key=idempotency_key,
            )

            logger.info(
                "Stripe Payment Intent created",
                extra={
                    'payment_intent_id': intent.id,
                    'order_id': str(order.id),
                    'status': intent.status,
                    'transfer_group': transfer_group,
                }
            )

            # Create Payment record in database
            payment = Payment.objects.create(
                order=order,
                user=user,
                stripe_payment_intent_id=intent.id,
                amount=order.total,
                currency='brl',
                payment_method=payment_method,
                status='pending',
                transfer_group=transfer_group,
                platform_fee_total=platform_fee_total,
                description=f'Pagamento do pedido #{order.order_number}',
                idempotency_key=idempotency_key,
                metadata={
                    'payment_intent_status': intent.status,
                    'created_at_stripe': intent.created,
                }
            )

            logger.info(
                "Payment record created",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                    'payment_intent_id': intent.id,
                    'transfer_group': transfer_group,
                    'platform_fee_total': str(platform_fee_total),
                }
            )

            return payment, intent.client_secret

        except SellerNotReadyError:
            # Re-raise without wrapping — caller handles this specifically
            raise

        except stripe.error.IdempotencyError:
            # PaymentIntent already exists for this order — retrieve it
            logger.warning(
                "IdempotencyError: PaymentIntent already exists, retrieving",
                extra={'order_id': str(order.id), 'idempotency_key': idempotency_key}
            )
            # Return existing payment if it exists in DB
            try:
                existing_payment = Payment.objects.get(
                    order=order,
                    idempotency_key=idempotency_key
                )
                intent = stripe.PaymentIntent.retrieve(
                    existing_payment.stripe_payment_intent_id
                )
                return existing_payment, intent.client_secret
            except Payment.DoesNotExist:
                raise

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe error creating payment intent: {str(e)}",
                extra={
                    'order_id': str(order.id),
                    'error_type': type(e).__name__,
                    'error_code': getattr(e, 'code', None),
                },
                exc_info=True
            )
            raise Exception(f'Erro ao criar payment intent: {str(e)}')

        except Exception as e:
            logger.error(
                f"Unexpected error creating payment intent: {str(e)}",
                extra={'order_id': str(order.id)},
                exc_info=True
            )
            raise

    @staticmethod
    def retrieve_payment_intent(payment_intent_id):
        """
        Retrieve a Payment Intent from Stripe.

        Args:
            payment_intent_id: Stripe Payment Intent ID

        Returns:
            stripe.PaymentIntent object
        """
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            logger.debug(
                "Retrieved payment intent",
                extra={
                    'payment_intent_id': payment_intent_id,
                    'status': intent.status,
                }
            )

            return intent

        except stripe.error.StripeError as e:
            logger.error(
                f"Error retrieving payment intent: {str(e)}",
                extra={
                    'payment_intent_id': payment_intent_id,
                    'error_type': type(e).__name__,
                },
                exc_info=True
            )
            raise

    @staticmethod
    def cancel_payment_intent(payment_intent_id):
        """
        Cancel a Payment Intent in Stripe.

        Args:
            payment_intent_id: Stripe Payment Intent ID

        Returns:
            stripe.PaymentIntent object
        """
        try:
            intent = stripe.PaymentIntent.cancel(payment_intent_id)

            logger.info(
                "Payment intent cancelled",
                extra={
                    'payment_intent_id': payment_intent_id,
                    'status': intent.status,
                }
            )

            return intent

        except stripe.error.StripeError as e:
            logger.error(
                f"Error cancelling payment intent: {str(e)}",
                extra={
                    'payment_intent_id': payment_intent_id,
                    'error_type': type(e).__name__,
                },
                exc_info=True
            )
            raise
