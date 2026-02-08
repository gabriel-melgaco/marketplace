"""
Webhook Service
Handles Stripe webhook events with idempotency and validation
"""

import stripe
import logging
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from decimal import Decimal

from .models import Payment, PaymentWebhook

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class PaymentAmountMismatchError(Exception):
    """Raised when payment amount doesn't match expected amount"""
    pass


class WebhookService:
    """Service for processing Stripe webhooks with idempotency"""

    @staticmethod
    def verify_webhook_signature(payload, sig_header):
        """
        Verify Stripe webhook signature

        Args:
            payload: Raw request body (bytes)
            sig_header: Stripe-Signature header value

        Returns:
            stripe.Event object

        Raises:
            ValueError: If signature is invalid
            stripe.error.SignatureVerificationError: If verification fails
        """
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET

        if not webhook_secret:
            logger.error("STRIPE_WEBHOOK_SECRET not configured")
            raise ValueError("Webhook secret not configured")

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )

            logger.debug(
                f"Webhook signature verified: {event.type}",
                extra={
                    'event_id': event.id,
                    'event_type': event.type
                }
            )

            return event

        except stripe.error.SignatureVerificationError as e:
            logger.error(
                f"Webhook signature verification failed: {str(e)}",
                extra={'signature_header': sig_header[:50]},
                exc_info=True
            )
            raise

    @staticmethod
    def validate_payment_amount(payment_intent, payment):
        """
        Validate that payment intent amount matches payment record

        Args:
            payment_intent: Stripe PaymentIntent object
            payment: Payment model instance

        Raises:
            PaymentAmountMismatchError: If amounts don't match
        """
        expected_amount_cents = int(float(payment.amount) * 100)
        actual_amount_cents = payment_intent.amount

        if expected_amount_cents != actual_amount_cents:
            error_msg = (
                f"Payment amount mismatch for payment {payment.id}. "
                f"Expected: {expected_amount_cents} cents, "
                f"Got: {actual_amount_cents} cents"
            )

            logger.error(
                error_msg,
                extra={
                    'payment_id': payment.id,
                    'order_id': str(payment.order.id),
                    'expected_amount': expected_amount_cents,
                    'actual_amount': actual_amount_cents,
                    'payment_intent_id': payment_intent.id
                }
            )

            raise PaymentAmountMismatchError(error_msg)

        logger.debug(
            f"Payment amount validated: {expected_amount_cents} cents",
            extra={
                'payment_id': payment.id,
                'payment_intent_id': payment_intent.id
            }
        )

    @staticmethod
    def handle_webhook(payload, sig_header):
        """
        Process Stripe webhook with idempotency

        Args:
            payload: Raw request body (bytes)
            sig_header: Stripe-Signature header value

        Returns:
            bool: True if processed successfully

        Raises:
            Exception: If processing fails
        """
        # Verify webhook signature
        event = WebhookService.verify_webhook_signature(payload, sig_header)

        logger.info(
            f"Processing webhook event: {event.type}",
            extra={
                'event_id': event.id,
                'event_type': event.type
            }
        )

        # Check if event already processed (idempotency)
        webhook, created = PaymentWebhook.objects.get_or_create(
            stripe_event_id=event.id,
            defaults={
                'event_type': event.type,
                'payload': event.data.object
            }
        )

        if not created and webhook.processed:
            logger.info(
                f"Webhook event already processed: {event.id}",
                extra={
                    'event_id': event.id,
                    'processed_at': webhook.processed_at.isoformat()
                }
            )
            return True  # Already processed, return success

        # Process event within atomic transaction
        try:
            with transaction.atomic():
                # Route to appropriate handler
                if event.type == 'payment_intent.succeeded':
                    WebhookService._handle_payment_succeeded(event, webhook)

                elif event.type == 'payment_intent.payment_failed':
                    WebhookService._handle_payment_failed(event, webhook)

                elif event.type == 'payment_intent.canceled':
                    WebhookService._handle_payment_canceled(event, webhook)

                else:
                    logger.warning(
                        f"Unhandled webhook event type: {event.type}",
                        extra={'event_id': event.id}
                    )
                    # Mark as processed even if unhandled
                    webhook.processed = True
                    webhook.processed_at = timezone.now()
                    webhook.save(update_fields=['processed', 'processed_at'])
                    return True

                # Mark webhook as processed
                webhook.processed = True
                webhook.processed_at = timezone.now()
                webhook.save(update_fields=['processed', 'processed_at'])

            logger.info(
                f"Webhook event processed successfully: {event.id}",
                extra={
                    'event_id': event.id,
                    'event_type': event.type
                }
            )

            return True

        except Payment.DoesNotExist:
            error_msg = f"Payment not found for payment_intent_id in event {event.id}"
            logger.error(error_msg, extra={'event_id': event.id})

            webhook.error_message = error_msg
            webhook.save(update_fields=['error_message'])
            raise

        except Exception as e:
            error_msg = f"Error processing webhook {event.id}: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    'event_id': event.id,
                    'event_type': event.type
                },
                exc_info=True
            )

            webhook.error_message = str(e)
            webhook.save(update_fields=['error_message'])
            raise

    @staticmethod
    def _handle_payment_succeeded(event, webhook):
        """Handle payment_intent.succeeded event"""
        payment_intent = event.data.object

        logger.info(
            f"Handling payment_intent.succeeded: {payment_intent.id}",
            extra={
                'payment_intent_id': payment_intent.id,
                'amount': payment_intent.amount
            }
        )

        # Get payment record
        payment = Payment.objects.select_for_update().get(
            stripe_payment_intent_id=payment_intent.id
        )

        # Validate amount
        WebhookService.validate_payment_amount(payment_intent, payment)

        # Update payment status
        payment.status = 'succeeded'
        payment.paid_at = timezone.now()

        # Extract charge information
        if payment_intent.charges and payment_intent.charges.data:
            charge = payment_intent.charges.data[0]
            payment.stripe_charge_id = charge.id
            payment.receipt_url = charge.receipt_url

        # Store metadata
        payment.metadata['webhook_processed_at'] = timezone.now().isoformat()
        payment.metadata['payment_intent_status'] = payment_intent.status

        payment.save()

        # Link webhook to payment
        webhook.payment = payment
        webhook.save(update_fields=['payment'])

        # Update order status using callback service (decoupled)
        order = payment.order
        try:
            from orders.services import PaymentCallbackService
            PaymentCallbackService.on_payment_succeeded(
                order=order,
                payment_intent_id=payment_intent.id,
                metadata={
                    'payment_id': payment.id,
                    'webhook_processed_at': timezone.now().isoformat()
                }
            )
        except Exception as e:
            logger.error(
                f"Failed to update order status via callback: {str(e)}",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                },
                exc_info=True
            )
            # Re-raise to ensure webhook is marked as failed
            raise

        logger.info(
            f"Payment succeeded: {payment.id}",
            extra={
                'payment_id': payment.id,
                'order_id': str(order.id),
                'order_number': order.order_number
            }
        )

    @staticmethod
    def _handle_payment_failed(event, webhook):
        """Handle payment_intent.payment_failed event"""
        payment_intent = event.data.object

        logger.info(
            f"Handling payment_intent.payment_failed: {payment_intent.id}",
            extra={'payment_intent_id': payment_intent.id}
        )

        # Get payment record
        payment = Payment.objects.select_for_update().get(
            stripe_payment_intent_id=payment_intent.id
        )

        # Update payment status
        payment.status = 'failed'

        # Extract failure message
        failure_message = ''
        if payment_intent.last_payment_error:
            failure_message = payment_intent.last_payment_error.message
            payment.failure_message = failure_message

        # Store metadata
        payment.metadata['webhook_processed_at'] = timezone.now().isoformat()
        payment.metadata['payment_intent_status'] = payment_intent.status
        if payment_intent.last_payment_error:
            payment.metadata['error_code'] = payment_intent.last_payment_error.code

        payment.save()

        # Link webhook to payment
        webhook.payment = payment
        webhook.save(update_fields=['payment'])

        # Update order status using callback service (decoupled)
        order = payment.order
        try:
            from orders.services import PaymentCallbackService
            PaymentCallbackService.on_payment_failed(
                order=order,
                payment_intent_id=payment_intent.id,
                failure_message=failure_message
            )
        except Exception as e:
            logger.error(
                f"Failed to update order status via callback: {str(e)}",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                },
                exc_info=True
            )
            # Re-raise to ensure webhook is marked as failed
            raise

        logger.warning(
            f"Payment failed: {payment.id}",
            extra={
                'payment_id': payment.id,
                'order_id': str(payment.order.id),
                'failure_reason': payment.failure_message
            }
        )

    @staticmethod
    def _handle_payment_canceled(event, webhook):
        """Handle payment_intent.canceled event"""
        payment_intent = event.data.object

        logger.info(
            f"Handling payment_intent.canceled: {payment_intent.id}",
            extra={'payment_intent_id': payment_intent.id}
        )

        # Get payment record
        payment = Payment.objects.select_for_update().get(
            stripe_payment_intent_id=payment_intent.id
        )

        # Update payment status
        payment.status = 'cancelled'

        # Store metadata
        cancellation_reason = payment_intent.cancellation_reason or 'Payment canceled'
        payment.metadata['webhook_processed_at'] = timezone.now().isoformat()
        payment.metadata['payment_intent_status'] = payment_intent.status
        payment.metadata['cancellation_reason'] = cancellation_reason

        payment.save()

        # Link webhook to payment
        webhook.payment = payment
        webhook.save(update_fields=['payment'])

        # Update order status using callback service (decoupled)
        order = payment.order
        try:
            from orders.services import PaymentCallbackService
            PaymentCallbackService.on_payment_canceled(
                order=order,
                payment_intent_id=payment_intent.id,
                cancellation_reason=cancellation_reason
            )
        except Exception as e:
            logger.error(
                f"Failed to update order status via callback: {str(e)}",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                },
                exc_info=True
            )
            # Re-raise to ensure webhook is marked as failed
            raise

        logger.info(
            f"Payment cancelled: {payment.id}",
            extra={
                'payment_id': payment.id,
                'order_id': str(order.id),
                'order_number': order.order_number
            }
        )
