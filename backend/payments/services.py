"""
Stripe Service (Legacy)
DEPRECATED: Use specialized services instead:
- PaymentIntentService for payment intents
- WebhookService for webhooks
- RefundService for refunds

This file is kept for backward compatibility.
"""

import stripe
import logging
from django.conf import settings
from django.utils import timezone

from .models import Payment, PaymentWebhook
from .payment_intent_service import PaymentIntentService
from .webhook_service import WebhookService
from .refund_service import RefundService

logger = logging.getLogger(__name__)

# Configurar Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeService:
    """
    Legacy Stripe Service

    DEPRECATED: This class delegates to specialized services.
    Use specialized services directly in new code.
    """

    @staticmethod
    def create_payment_intent(order, payment_method, user):
        """
        DEPRECATED: Use PaymentIntentService.create_payment_intent() instead

        Cria um Payment Intent no Stripe

        Args:
            order: Instância do Order
            payment_method: Tipo de pagamento ('credit_card', 'pix', etc)
            user: Usuário que está fazendo o pagamento

        Returns:
            tuple: (Payment instance, client_secret)
        """
        logger.warning(
            "StripeService.create_payment_intent is deprecated. "
            "Use PaymentIntentService.create_payment_intent instead."
        )
        return PaymentIntentService.create_payment_intent(order, payment_method, user)
    
    @staticmethod
    def confirm_payment(payment_intent_id):
        """
        DEPRECATED: Use PaymentIntentService.retrieve_payment_intent() instead

        WARNING: This method should NOT be used for confirming payments.
        Payment confirmation should ONLY happen via webhooks.

        This method now only RETRIEVES status from Stripe without updating.

        Args:
            payment_intent_id: ID do Payment Intent do Stripe

        Returns:
            Payment: Instância do Payment (sem alterações)
        """
        logger.warning(
            "StripeService.confirm_payment is deprecated and unsafe. "
            "Payment confirmation should only happen via webhooks. "
            "This method now only retrieves status."
        )

        try:
            # Retrieve payment intent from Stripe (READ ONLY)
            intent = PaymentIntentService.retrieve_payment_intent(payment_intent_id)

            # Get payment from database
            payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)

            logger.info(
                f"Payment status retrieved: {payment.status}",
                extra={
                    'payment_id': payment.id,
                    'stripe_status': intent.status,
                    'db_status': payment.status
                }
            )

            return payment

        except Payment.DoesNotExist:
            logger.error(f"Payment not found for intent: {payment_intent_id}")
            raise Exception('Pagamento não encontrado')

        except Exception as e:
            logger.error(f"Error retrieving payment: {str(e)}", exc_info=True)
            raise Exception(f'Erro ao buscar pagamento: {str(e)}')
    
    @staticmethod
    def create_refund(payment, amount=None, reason=''):
        """
        DEPRECATED: Use RefundService.create_refund() instead

        Cria um reembolso

        Args:
            payment: Instância do Payment
            amount: Valor a reembolsar (None = reembolso total)
            reason: Motivo do reembolso

        Returns:
            Payment: Instância do Payment atualizado
        """
        logger.warning(
            "StripeService.create_refund is deprecated. "
            "Use RefundService.create_refund instead."
        )
        return RefundService.create_refund(payment, amount, reason)
    
    @staticmethod
    def handle_webhook(payload, sig_header):
        """
        DEPRECATED: Use WebhookService.handle_webhook() instead

        Processa webhooks do Stripe com idempotência e validação

        Args:
            payload: Corpo da requisição (bytes)
            sig_header: Header de assinatura

        Returns:
            bool: True se processado com sucesso
        """
        logger.warning(
            "StripeService.handle_webhook is deprecated. "
            "Use WebhookService.handle_webhook instead."
        )
        return WebhookService.handle_webhook(payload, sig_header)
    
    @staticmethod
    def create_customer(user):
        """
        Cria um Customer no Stripe
        
        Args:
            user: Usuário
        
        Returns:
            str: ID do customer no Stripe
        """
        try:
            customer = stripe.Customer.create(
                email=user.email,
                name=user.get_full_name(),
                metadata={
                    'user_id': user.id
                }
            )
            return customer.id
            
        except stripe.error.StripeError as e:
            raise Exception(f'Erro ao criar customer: {str(e)}')