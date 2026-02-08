from django.db import models
from orders.models import Order
from authentication.models import CustomUser


class Payment(models.Model):
    """Modelo de pagamento via Stripe"""
    
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('processing', 'Processando'),
        ('succeeded', 'Sucesso'),
        ('failed', 'Falhou'),
        ('cancelled', 'Cancelado'),
        ('refunded', 'Reembolsado'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('credit_card', 'Cartão de Crédito'),
        ('debit_card', 'Cartão de Débito'),
        ('pix', 'PIX'),
        ('boleto', 'Boleto'),
    ]
    
    # Relacionamentos
    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name='payment'
    )
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='payments'
    )
    
    # Stripe IDs
    stripe_payment_intent_id = models.CharField(max_length=255, unique=True)
    stripe_charge_id = models.CharField(max_length=255, blank=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True)

    # Informações do pagamento
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='BRL')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)

    # Idempotency and metadata
    idempotency_key = models.CharField(max_length=255, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Dados adicionais
    description = models.TextField(blank=True)
    failure_message = models.TextField(blank=True)
    receipt_url = models.URLField(blank=True)
    
    # Reembolso
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    refund_reason = models.TextField(blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Pagamento'
        verbose_name_plural = 'Pagamentos'
        ordering = ['-created_at']
    
    def __str__(self):
        return f'Pagamento {self.stripe_payment_intent_id} - {self.order.order_number}'


class PaymentWebhook(models.Model):
    """Log de webhooks recebidos do Stripe"""
    
    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhooks'
    )
    
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Webhook de Pagamento'
        verbose_name_plural = 'Webhooks de Pagamento'
        ordering = ['-created_at']
    
    def __str__(self):
        return f'{self.event_type} - {self.stripe_event_id}'


class SellerPayout(models.Model):
    """Repasses para vendedores"""
    
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('processing', 'Processando'),
        ('completed', 'Concluído'),
        ('failed', 'Falhou'),
    ]
    
    seller = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='payouts'
    )
    
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name='seller_payouts'
    )
    
    # Valores
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Stripe Connect (para repasses automáticos)
    stripe_transfer_id = models.CharField(max_length=255, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_for = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Repasse ao Vendedor'
        verbose_name_plural = 'Repasses aos Vendedores'
        ordering = ['-created_at']
    
    def __str__(self):
        return f'Repasse {self.seller.email} - {self.order.order_number}'