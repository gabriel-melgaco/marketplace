"""
Payment Intent Service
Handles creation and management of Stripe Payment Intents
"""

import stripe
import uuid
import logging
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

from .models import Payment

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class PaymentIntentService:
    """Service for creating and managing Stripe Payment Intents"""

    @staticmethod
    def create_payment_intent(order, payment_method, user):
        """
        Create a Payment Intent in Stripe and corresponding Payment record

        Args:
            order: Order instance
            payment_method: Payment method type ('credit_card', 'pix', etc)
            user: User making the payment

        Returns:
            tuple: (Payment instance, client_secret string)

        Raises:
            ValueError: If order already has a paid payment
            stripe.error.StripeError: If Stripe API fails
        """
        # Generate idempotency key to prevent duplicate payment intents
        idempotency_key = f"pi_{order.id}_{uuid.uuid4().hex[:16]}"

        logger.info(
            f"Creating payment intent for order {order.order_number}",
            extra={
                'order_id': str(order.id),
                'user_id': user.id,
                'amount': float(order.total),
                'idempotency_key': idempotency_key
            }
        )

        try:
            # Determine payment method types based on method
            payment_method_types = ['card']
            if payment_method in ['credit_card', 'debit_card']:
                payment_method_types = ['card']
            elif payment_method == 'boleto':
                payment_method_types = ['boleto']

            # Create Payment Intent in Stripe
            intent = stripe.PaymentIntent.create(
                amount=int(float(order.total) * 100),  # Convert to cents
                currency='brl',
                payment_method_types=payment_method_types,
                description=f'Pedido #{order.order_number}',
                metadata={
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'user_id': user.id,
                    'payment_method': payment_method,
                },
                idempotency_key=idempotency_key
            )

            logger.info(
                f"Stripe Payment Intent created: {intent.id}",
                extra={
                    'payment_intent_id': intent.id,
                    'order_id': str(order.id),
                    'status': intent.status
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
                description=f'Pagamento do pedido #{order.order_number}',
                idempotency_key=idempotency_key,
                metadata={
                    'payment_intent_status': intent.status,
                    'created_at_stripe': intent.created,
                }
            )

            # NOTE: Order status is already 'pending_payment' from OrderCreationService
            # No need to update it here - state transitions are managed by OrderStateMachine

            logger.info(
                f"Payment record created: {payment.id}",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                    'payment_intent_id': intent.id
                }
            )

            return payment, intent.client_secret

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe error creating payment intent: {str(e)}",
                extra={
                    'order_id': str(order.id),
                    'error_type': type(e).__name__,
                    'error_code': getattr(e, 'code', None)
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
        Retrieve a Payment Intent from Stripe

        Args:
            payment_intent_id: Stripe Payment Intent ID

        Returns:
            stripe.PaymentIntent object

        Raises:
            stripe.error.StripeError: If retrieval fails
        """
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            logger.debug(
                f"Retrieved payment intent: {payment_intent_id}",
                extra={
                    'payment_intent_id': payment_intent_id,
                    'status': intent.status
                }
            )

            return intent

        except stripe.error.StripeError as e:
            logger.error(
                f"Error retrieving payment intent: {str(e)}",
                extra={
                    'payment_intent_id': payment_intent_id,
                    'error_type': type(e).__name__
                },
                exc_info=True
            )
            raise

    @staticmethod
    def cancel_payment_intent(payment_intent_id):
        """
        Cancel a Payment Intent in Stripe

        Args:
            payment_intent_id: Stripe Payment Intent ID

        Returns:
            stripe.PaymentIntent object

        Raises:
            stripe.error.StripeError: If cancellation fails
        """
        try:
            intent = stripe.PaymentIntent.cancel(payment_intent_id)

            logger.info(
                f"Payment intent cancelled: {payment_intent_id}",
                extra={
                    'payment_intent_id': payment_intent_id,
                    'status': intent.status
                }
            )

            return intent

        except stripe.error.StripeError as e:
            logger.error(
                f"Error cancelling payment intent: {str(e)}",
                extra={
                    'payment_intent_id': payment_intent_id,
                    'error_type': type(e).__name__
                },
                exc_info=True
            )
            raise
