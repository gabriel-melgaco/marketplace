import stripe
from django.conf import settings
from django.utils import timezone
from .models import Payment, PaymentWebhook
from orders.models import Order

# Configurar Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeService:
    """Serviço para integração com Stripe"""
    
    @staticmethod
    def create_payment_intent(order, payment_method, user):
        """
        Cria um Payment Intent no Stripe
        
        Args:
            order: Instância do Order
            payment_method: Tipo de pagamento ('credit_card', 'pix', etc)
            user: Usuário que está fazendo o pagamento
        
        Returns:
            Payment: Instância do Payment criado
        """
        try:
            # Criar Payment Intent no Stripe
            intent = stripe.PaymentIntent.create(
                amount=int(float(order.total) * 100),  # Stripe usa centavos
                currency='brl',
                payment_method_types=['card'] if payment_method in ['credit_card', 'debit_card'] else ['boleto'],
                description=f'Pedido #{order.order_number}',
                metadata={
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'user_id': user.id,
                }
            )
            
            # Criar registro de Payment no banco
            payment = Payment.objects.create(
                order=order,
                user=user,
                stripe_payment_intent_id=intent.id,
                amount=order.total,
                payment_method=payment_method,
                status='pending',
                description=f'Pagamento do pedido #{order.order_number}'
            )
            
            # Atualizar status do pedido
            order.status = 'payment_pending'
            order.save()
            
            return payment, intent.client_secret
            
        except stripe.error.StripeError as e:
            raise Exception(f'Erro ao criar payment intent: {str(e)}')
    
    @staticmethod
    def confirm_payment(payment_intent_id):
        """
        Confirma um pagamento
        
        Args:
            payment_intent_id: ID do Payment Intent do Stripe
        
        Returns:
            Payment: Instância do Payment atualizado
        """
        try:
            # Buscar payment intent no Stripe
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            
            # Buscar payment no banco
            payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)
            
            # Atualizar status baseado no intent
            if intent.status == 'succeeded':
                payment.status = 'succeeded'
                payment.paid_at = timezone.now()
                payment.stripe_charge_id = intent.charges.data[0].id if intent.charges.data else ''
                payment.receipt_url = intent.charges.data[0].receipt_url if intent.charges.data else ''
                
                # Atualizar status do pedido
                payment.order.status = 'payment_confirmed'
                payment.order.save()
                
            elif intent.status == 'processing':
                payment.status = 'processing'
            elif intent.status == 'canceled':
                payment.status = 'cancelled'
            else:
                payment.status = 'failed'
                payment.failure_message = intent.last_payment_error.message if intent.last_payment_error else ''
            
            payment.save()
            return payment
            
        except Payment.DoesNotExist:
            raise Exception('Pagamento não encontrado')
        except stripe.error.StripeError as e:
            raise Exception(f'Erro ao confirmar pagamento: {str(e)}')
    
    @staticmethod
    def create_refund(payment, amount=None, reason=''):
        """
        Cria um reembolso
        
        Args:
            payment: Instância do Payment
            amount: Valor a reembolsar (None = reembolso total)
            reason: Motivo do reembolso
        
        Returns:
            Payment: Instância do Payment atualizado
        """
        try:
            refund_amount = amount if amount else payment.amount
            
            # Criar reembolso no Stripe
            refund = stripe.Refund.create(
                payment_intent=payment.stripe_payment_intent_id,
                amount=int(float(refund_amount) * 100),  # Centavos
                reason='requested_by_customer',
                metadata={
                    'order_number': payment.order.order_number,
                    'reason': reason
                }
            )
            
            # Atualizar payment
            payment.status = 'refunded'
            payment.refund_amount = refund_amount
            payment.refund_reason = reason
            payment.refunded_at = timezone.now()
            payment.save()
            
            # Atualizar pedido
            payment.order.status = 'refunded'
            payment.order.save()
            
            return payment
            
        except stripe.error.StripeError as e:
            raise Exception(f'Erro ao criar reembolso: {str(e)}')
    
    @staticmethod
    def handle_webhook(payload, sig_header):
        """
        Processa webhooks do Stripe
        
        Args:
            payload: Corpo da requisição
            sig_header: Header de assinatura
        
        Returns:
            bool: True se processado com sucesso
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            
            # Criar registro do webhook
            webhook = PaymentWebhook.objects.create(
                stripe_event_id=event.id,
                event_type=event.type,
                payload=event.data.object
            )
            
            # Processar evento
            if event.type == 'payment_intent.succeeded':
                payment_intent = event.data.object
                payment = Payment.objects.get(
                    stripe_payment_intent_id=payment_intent.id
                )
                payment.status = 'succeeded'
                payment.paid_at = timezone.now()
                payment.save()
                
                payment.order.status = 'payment_confirmed'
                payment.order.save()
                
                webhook.payment = payment
                webhook.processed = True
                webhook.processed_at = timezone.now()
                webhook.save()
                
            elif event.type == 'payment_intent.payment_failed':
                payment_intent = event.data.object
                payment = Payment.objects.get(
                    stripe_payment_intent_id=payment_intent.id
                )
                payment.status = 'failed'
                payment.failure_message = payment_intent.last_payment_error.message if payment_intent.last_payment_error else ''
                payment.save()
                
                webhook.payment = payment
                webhook.processed = True
                webhook.processed_at = timezone.now()
                webhook.save()
            
            return True
            
        except Exception as e:
            if 'webhook' in locals():
                webhook.error_message = str(e)
                webhook.save()
            raise Exception(f'Erro ao processar webhook: {str(e)}')
    
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