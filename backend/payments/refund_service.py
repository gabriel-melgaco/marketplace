"""
Refund Service
Handles payment refunds via Stripe, including Transfer Reversals for sellers.

Design decisions:
- Refund is created on the PaymentIntent (not the Charge directly)
- For each dispatched PaymentSplit, a proportional Transfer Reversal is created
  so sellers absorb their share of the refund
- Order status is updated via OrderStateMachine (NEVER via direct assignment)
- Idempotency keys are deterministic to avoid duplicate refunds on retry
- All database operations are wrapped in @transaction.atomic

Transfer Reversal logic:
    For a full refund: reverse the full net_amount of each split
    For a partial refund: reverse proportional to refund_ratio
        reversal_amount = net_amount * (refund_amount / payment_amount)
"""

import stripe
import logging
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from decimal import Decimal, ROUND_HALF_UP

from .models import Payment, PaymentSplit

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


class RefundError(Exception):
    """Raised when refund processing fails"""
    pass


class RefundService:
    """Service for creating and managing refunds with Transfer Reversals"""

    @staticmethod
    @transaction.atomic
    def create_refund(payment, amount=None, reason=''):
        """
        Create a refund in Stripe and reverse seller transfers proportionally.

        Args:
            payment: Payment instance (must have status='succeeded')
            amount: Amount to refund as Decimal (None = full refund)
            reason: Human-readable reason for the refund

        Returns:
            Payment: Updated payment instance

        Raises:
            ValueError: If payment cannot be refunded or amount is invalid
            RefundError: If Stripe or reversal operations fail
        """
        # Validate payment can be refunded
        if payment.status != 'succeeded':
            raise ValueError('Only succeeded payments can be refunded')

        refund_amount = Decimal(str(amount)) if amount else payment.amount

        # Validate refund amount
        if refund_amount > payment.amount:
            raise ValueError(
                f'Refund amount ({refund_amount}) cannot exceed '
                f'payment amount ({payment.amount})'
            )

        if refund_amount <= 0:
            raise ValueError('Refund amount must be greater than zero')

        # Deterministic idempotency key for the Stripe Refund
        # Using payment.id + date ensures one refund attempt per day per payment
        idempotency_key = (
            f"re_{payment.id}_{timezone.now().date().isoformat()}"
        )

        logger.info(
            "Creating refund for payment",
            extra={
                'payment_id': payment.id,
                'order_id': str(payment.order.id),
                'refund_amount': float(refund_amount),
                'payment_amount': float(payment.amount),
                'reason': reason,
                'idempotency_key': idempotency_key,
            }
        )

        try:
            # Create refund in Stripe
            refund = stripe.Refund.create(
                payment_intent=payment.stripe_payment_intent_id,
                amount=int(float(refund_amount) * 100),  # Convert to cents
                reason='requested_by_customer',
                metadata={
                    'order_number': payment.order.order_number,
                    'payment_id': payment.id,
                    'refund_reason': reason,
                },
                idempotency_key=idempotency_key,
            )

            logger.info(
                "Stripe refund created",
                extra={
                    'refund_id': refund.id,
                    'payment_id': payment.id,
                    'amount_cents': refund.amount,
                    'status': refund.status,
                }
            )

        except stripe.error.IdempotencyError:
            # Refund already created — retrieve the existing refund
            logger.warning(
                "IdempotencyError creating refund — refund may already exist",
                extra={
                    'payment_id': payment.id,
                    'idempotency_key': idempotency_key,
                }
            )
            # Continue — we still need to update local records
            refund = None

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe error creating refund: {str(e)}",
                extra={
                    'payment_id': payment.id,
                    'error_type': type(e).__name__,
                    'error_code': getattr(e, 'code', None),
                },
                exc_info=True
            )
            raise RefundError(f'Erro ao criar reembolso: {str(e)}')

        # Update payment record
        payment.status = 'refunded'
        payment.refund_amount = refund_amount
        payment.refund_reason = reason
        payment.refunded_at = timezone.now()

        if not payment.metadata:
            payment.metadata = {}

        if refund:
            payment.metadata['refund_id'] = refund.id
            payment.metadata['refund_status'] = refund.status

        payment.metadata['refunded_at'] = timezone.now().isoformat()
        payment.save()

        # Update order status via OrderStateMachine — NEVER direct assignment
        order = payment.order
        try:
            from orders.services import PaymentCallbackService
            PaymentCallbackService.on_refund_processed(
                order=order,
                refund_amount=float(refund_amount),
                refund_reason=reason,
            )
        except Exception as e:
            logger.error(
                f"Failed to update order status after refund: {str(e)}",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                },
                exc_info=True
            )
            raise RefundError(f'Erro ao atualizar status do pedido: {str(e)}')

        # Create Transfer Reversals for each dispatched seller split
        RefundService._reverse_seller_transfers(
            payment=payment,
            refund_amount=refund_amount,
        )

        logger.info(
            "Payment refunded successfully",
            extra={
                'payment_id': payment.id,
                'order_id': str(order.id),
                'order_number': order.order_number,
                'refund_amount': float(refund_amount),
            }
        )

        return payment

    @staticmethod
    def _reverse_seller_transfers(payment, refund_amount: Decimal):
        """
        Create proportional Transfer Reversals for all dispatched PaymentSplits.

        For a partial refund, each seller's share is reversed proportionally:
            reversal_amount = split.net_amount * (refund_amount / payment.amount)

        For a full refund, the full net_amount of each split is reversed.

        Args:
            payment: Payment instance
            refund_amount: Amount being refunded as Decimal

        Note: Failures are logged but do not raise — manual reconciliation needed.
        """
        dispatched_splits = PaymentSplit.objects.filter(
            payment=payment,
            transfer_status='dispatched',
        ).exclude(stripe_transfer_id='')

        if not dispatched_splits.exists():
            logger.info(
                "No dispatched splits to reverse for refund",
                extra={'payment_id': payment.id}
            )
            return

        # Calculate refund ratio (0.0 to 1.0)
        refund_ratio = refund_amount / payment.amount

        today_str = timezone.now().date().isoformat()

        for split in dispatched_splits:
            reversal_amount_decimal = (split.net_amount * refund_ratio).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            reversal_amount_cents = int(reversal_amount_decimal * 100)

            if reversal_amount_cents <= 0:
                logger.info(
                    "Skipping reversal for split (zero amount)",
                    extra={
                        'split_id': split.id,
                        'seller_id': split.seller_id,
                    }
                )
                continue

            # Deterministic idempotency key for the Transfer Reversal
            idempotency_key = (
                f"rev_{split.stripe_transfer_id}_{today_str}"
            )

            logger.info(
                "Creating Transfer Reversal for refund",
                extra={
                    'payment_id': payment.id,
                    'split_id': split.id,
                    'transfer_id': split.stripe_transfer_id,
                    'reversal_amount_cents': reversal_amount_cents,
                    'seller_id': split.seller_id,
                    'refund_ratio': str(refund_ratio),
                    'idempotency_key': idempotency_key,
                }
            )

            try:
                stripe.Transfer.create_reversal(
                    split.stripe_transfer_id,
                    amount=reversal_amount_cents,
                    description=(
                        f"Reversal for refund on payment {payment.id} "
                        f"/ order {payment.order.order_number}"
                    ),
                    metadata={
                        'payment_id': str(payment.id),
                        'split_id': str(split.id),
                        'seller_id': str(split.seller_id),
                        'refund_reason': payment.refund_reason,
                        'refund_ratio': str(refund_ratio),
                    },
                    idempotency_key=idempotency_key,
                )

                logger.info(
                    "Transfer Reversal created successfully",
                    extra={
                        'transfer_id': split.stripe_transfer_id,
                        'reversed_cents': reversal_amount_cents,
                        'seller_id': split.seller_id,
                    }
                )

            except stripe.error.IdempotencyError:
                logger.warning(
                    "IdempotencyError — Transfer Reversal may already exist",
                    extra={
                        'idempotency_key': idempotency_key,
                        'split_id': split.id,
                    }
                )

            except stripe.error.StripeError as e:
                # Log error but do not abort — other sellers still need reversals
                logger.error(
                    f"Failed to create Transfer Reversal for split {split.id}: {str(e)}",
                    extra={
                        'split_id': split.id,
                        'transfer_id': split.stripe_transfer_id,
                        'seller_id': split.seller_id,
                        'error_type': type(e).__name__,
                        'error_code': getattr(e, 'code', None),
                    },
                    exc_info=True
                )
                # Mark split for manual reconciliation
                split.error_message = (
                    f"Transfer Reversal failed on refund: {str(e)}"
                )
                split.save(update_fields=['error_message', 'updated_at'])

    @staticmethod
    def retrieve_refund(refund_id):
        """
        Retrieve a refund from Stripe.

        Args:
            refund_id: Stripe Refund ID

        Returns:
            stripe.Refund object
        """
        try:
            refund = stripe.Refund.retrieve(refund_id)

            logger.debug(
                "Retrieved refund",
                extra={
                    'refund_id': refund_id,
                    'status': refund.status,
                }
            )

            return refund

        except stripe.error.StripeError as e:
            logger.error(
                f"Error retrieving refund: {str(e)}",
                extra={
                    'refund_id': refund_id,
                    'error_type': type(e).__name__,
                },
                exc_info=True
            )
            raise
