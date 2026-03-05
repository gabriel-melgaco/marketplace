"""
Payments Services Package

Exports:
- TransferDispatchService: dispatches Stripe Transfers to sellers
- StripeService: legacy service (deprecated, delegates to specialized services)
"""

from .transfer_dispatch_service import TransferDispatchService

# Legacy StripeService kept for backward compatibility with views.py
# DEPRECATED: Use specialized services directly in new code.
import stripe
import logging
from django.conf import settings

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeService:
    """
    Legacy Stripe Service.
    DEPRECATED: Use specialized services directly.
    """

    @staticmethod
    def create_payment_intent(order, payment_method, user):
        """DEPRECATED: Use PaymentIntentService.create_payment_intent() instead"""
        logger.warning(
            "StripeService.create_payment_intent is deprecated. "
            "Use PaymentIntentService.create_payment_intent instead."
        )
        from payments.payment_intent_service import PaymentIntentService
        return PaymentIntentService.create_payment_intent(order, payment_method, user)

    @staticmethod
    def confirm_payment(payment_intent_id):
        """DEPRECATED: Payment confirmation must happen via webhooks."""
        logger.warning(
            "StripeService.confirm_payment is deprecated and unsafe. "
            "Payment confirmation should only happen via webhooks."
        )
        from payments.payment_intent_service import PaymentIntentService
        from payments.models import Payment
        intent = PaymentIntentService.retrieve_payment_intent(payment_intent_id)
        payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)
        return payment

    @staticmethod
    def create_refund(payment, amount=None, reason=''):
        """DEPRECATED: Use RefundService.create_refund() instead"""
        logger.warning(
            "StripeService.create_refund is deprecated. "
            "Use RefundService.create_refund instead."
        )
        from payments.refund_service import RefundService
        return RefundService.create_refund(payment, amount, reason)

    @staticmethod
    def handle_webhook(payload, sig_header):
        """DEPRECATED: Use WebhookService.handle_webhook() instead"""
        logger.warning(
            "StripeService.handle_webhook is deprecated. "
            "Use WebhookService.handle_webhook instead."
        )
        from payments.webhook_service import WebhookService
        return WebhookService.handle_webhook(payload, sig_header)

    @staticmethod
    def create_customer(user):
        """Cria um Customer no Stripe"""
        try:
            customer = stripe.Customer.create(
                email=user.email,
                name=user.get_full_name(),
                metadata={'user_id': user.id}
            )
            return customer.id
        except stripe.error.StripeError as e:
            raise Exception(f'Erro ao criar customer: {str(e)}')


__all__ = ['TransferDispatchService', 'StripeService']
