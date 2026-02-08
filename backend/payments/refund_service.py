"""
Refund Service
Handles payment refunds via Stripe
"""

import stripe
import logging
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

from .models import Payment

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class RefundService:
    """Service for creating and managing refunds"""

    @staticmethod
    def create_refund(payment, amount=None, reason=''):
        """
        Create a refund in Stripe

        Args:
            payment: Payment instance
            amount: Amount to refund (None = full refund)
            reason: Reason for refund

        Returns:
            Payment: Updated payment instance

        Raises:
            ValueError: If payment cannot be refunded
            stripe.error.StripeError: If Stripe API fails
        """
        # Validate payment can be refunded
        if payment.status != 'succeeded':
            raise ValueError('Only succeeded payments can be refunded')

        if payment.status == 'refunded':
            raise ValueError('Payment already refunded')

        refund_amount = amount if amount else payment.amount

        # Validate refund amount
        if refund_amount > payment.amount:
            raise ValueError(
                f'Refund amount ({refund_amount}) cannot exceed payment amount ({payment.amount})'
            )

        logger.info(
            f"Creating refund for payment {payment.id}",
            extra={
                'payment_id': payment.id,
                'order_id': str(payment.order.id),
                'refund_amount': float(refund_amount),
                'reason': reason
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
                    'refund_reason': reason
                }
            )

            logger.info(
                f"Stripe refund created: {refund.id}",
                extra={
                    'refund_id': refund.id,
                    'payment_id': payment.id,
                    'amount': refund.amount
                }
            )

            # Update payment
            payment.status = 'refunded'
            payment.refund_amount = refund_amount
            payment.refund_reason = reason
            payment.refunded_at = timezone.now()

            # Store refund metadata
            if not payment.metadata:
                payment.metadata = {}

            payment.metadata['refund_id'] = refund.id
            payment.metadata['refund_status'] = refund.status
            payment.metadata['refunded_at'] = timezone.now().isoformat()

            payment.save()

            # Update order status
            order = payment.order
            order.status = 'refunded'
            order.save(update_fields=['status'])

            logger.info(
                f"Payment refunded successfully: {payment.id}",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'refund_amount': float(refund_amount)
                }
            )

            return payment

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe error creating refund: {str(e)}",
                extra={
                    'payment_id': payment.id,
                    'error_type': type(e).__name__,
                    'error_code': getattr(e, 'code', None)
                },
                exc_info=True
            )
            raise Exception(f'Erro ao criar reembolso: {str(e)}')

        except Exception as e:
            logger.error(
                f"Unexpected error creating refund: {str(e)}",
                extra={'payment_id': payment.id},
                exc_info=True
            )
            raise

    @staticmethod
    def retrieve_refund(refund_id):
        """
        Retrieve a refund from Stripe

        Args:
            refund_id: Stripe Refund ID

        Returns:
            stripe.Refund object

        Raises:
            stripe.error.StripeError: If retrieval fails
        """
        try:
            refund = stripe.Refund.retrieve(refund_id)

            logger.debug(
                f"Retrieved refund: {refund_id}",
                extra={
                    'refund_id': refund_id,
                    'status': refund.status
                }
            )

            return refund

        except stripe.error.StripeError as e:
            logger.error(
                f"Error retrieving refund: {str(e)}",
                extra={
                    'refund_id': refund_id,
                    'error_type': type(e).__name__
                },
                exc_info=True
            )
            raise
