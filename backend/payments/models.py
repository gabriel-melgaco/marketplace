from django.db import models
from django.conf import settings
from orders.models import Order


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
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payments'
    )

    # Stripe IDs
    stripe_payment_intent_id = models.CharField(max_length=255, unique=True)
    stripe_charge_id = models.CharField(max_length=255, blank=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True)

    # Stripe Connect - transfer group para Separate Charges and Transfers
    transfer_group = models.CharField(max_length=255, blank=True, db_index=True)

    # Informações do pagamento
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='BRL')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)

    # Comissão da plataforma (total calculado server-side)
    platform_fee_total = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

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


class PaymentSplit(models.Model):
    """
    Rastreia o split de pagamento por vendedor.
    Criado após payment_intent.succeeded, um registro por seller no pedido.
    """

    TRANSFER_STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('dispatched', 'Despachado'),
        ('failed', 'Falhou'),
    ]

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name='splits'
    )

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payment_splits'
    )

    # Valores financeiros (em BRL)
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee_amount = models.DecimalField(max_digits=10, decimal_places=2)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Stripe Transfer ID quando transfer for criada
    stripe_transfer_id = models.CharField(max_length=255, blank=True, db_index=True)

    # Status do repasse
    transfer_status = models.CharField(
        max_length=20,
        choices=TRANSFER_STATUS_CHOICES,
        default='pending'
    )

    # Metadata para auditoria
    error_message = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Split de Pagamento'
        verbose_name_plural = 'Splits de Pagamento'
        ordering = ['-created_at']
        unique_together = ['payment', 'seller']

    def __str__(self):
        return f'Split {self.seller.email} - Pagamento {self.payment.id} - {self.transfer_status}'


class Dispute(models.Model):
    """Chargeback/disputa recebido via Stripe webhook charge.dispute.created"""

    STATUS_CHOICES = [
        ('warning_needs_response', 'Precisa de Resposta (Warning)'),
        ('warning_under_review', 'Em Revisão (Warning)'),
        ('warning_closed', 'Fechado (Warning)'),
        ('needs_response', 'Precisa de Resposta'),
        ('under_review', 'Em Revisão'),
        ('charge_refunded', 'Charge Reembolsado'),
        ('won', 'Ganho'),
        ('lost', 'Perdido'),
    ]

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name='disputes'
    )

    stripe_dispute_id = models.CharField(max_length=255, unique=True)
    stripe_charge_id = models.CharField(max_length=255)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='BRL')
    reason = models.CharField(max_length=100)
    status = models.CharField(max_length=50)

    # Controle de reversão de transfers
    reversal_attempted = models.BooleanField(default=False)
    reversal_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Payload completo do Stripe para auditoria
    stripe_payload = models.JSONField(default=dict, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Disputa'
        verbose_name_plural = 'Disputas'
        ordering = ['-created_at']

    def __str__(self):
        return f'Disputa {self.stripe_dispute_id} - {self.status}'


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
    """Repasses para vendedores (legado - mantido para compatibilidade)"""

    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('processing', 'Processando'),
        ('completed', 'Concluído'),
        ('failed', 'Falhou'),
    ]

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
