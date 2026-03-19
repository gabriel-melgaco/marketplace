import uuid
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

    SHIPPING_STATUS_CHOICES = [
        ('held', 'Retido'),
        ('released', 'Liberado p/ Logística'),
        ('refunded', 'Reembolsado'),
    ]

    # Valores financeiros (em BRL)
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee_amount = models.DecimalField(max_digits=10, decimal_places=2)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Separação produto vs frete (nova fórmula de split)
    # product_amount: base de cálculo da comissão (somente produtos)
    # shipping_amount: frete retido integralmente pela plataforma (NÃO entra no Transfer)
    product_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Subtotal somente dos produtos (base da comissão)'
    )
    shipping_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Frete retido pela plataforma para cobrir débitos ME'
    )
    shipping_status = models.CharField(
        max_length=20,
        choices=SHIPPING_STATUS_CHOICES,
        default='held',
        help_text='Status do frete retido: held/released/refunded'
    )

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


class RefundRequest(models.Model):
    """
    Solicitação de reembolso não-unilateral.

    Fluxo padrão:
        requested → seller_reviewing → approved/rejected → stripe_refund_pending → refunded
    Fluxo auto-aprovado:
        requested → auto_approved → stripe_refund_pending → refunded
    Fluxo com escalada:
        seller_reviewing → escalated → platform_approved/platform_rejected
    """

    STATUS_CHOICES = [
        ('requested', 'Solicitado'),
        ('seller_reviewing', 'Em Análise pelo Vendedor'),
        ('auto_approved', 'Aprovado Automaticamente'),
        ('approved', 'Aprovado pelo Vendedor'),
        ('rejected', 'Rejeitado pelo Vendedor'),
        ('escalated', 'Escalado para Plataforma'),
        ('platform_approved', 'Aprovado pela Plataforma'),
        ('platform_rejected', 'Rejeitado pela Plataforma'),
        ('stripe_refund_pending', 'Reembolso Stripe Pendente'),
        ('refunded', 'Reembolsado'),
        ('withdrawn', 'Retirado pelo Comprador'),
        ('closed', 'Encerrado'),
    ]

    REFUND_TYPE_CHOICES = [
        ('remorse', 'Arrependimento'),
        ('defective', 'Produto com Defeito / Diferente'),
        ('not_received', 'Produto Não Recebido'),
        ('duplicate_charge', 'Cobrança Duplicada'),
        ('platform_decision', 'Decisão da Plataforma'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name='refund_requests',
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name='refund_requests',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='refund_requests_made',
    )

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='requested')
    refund_type = models.CharField(max_length=30, choices=REFUND_TYPE_CHOICES)

    amount_requested = models.DecimalField(max_digits=10, decimal_places=2)
    amount_approved = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    reason_buyer = models.TextField()
    reason_seller = models.TextField(blank=True)
    reason_platform = models.TextField(blank=True)

    evidence_urls = models.JSONField(default=list)
    seller_evidence_urls = models.JSONField(default=list)

    # Prazos
    seller_deadline = models.DateTimeField(null=True, blank=True)
    escalation_deadline = models.DateTimeField(null=True, blank=True)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='refund_requests_decided',
    )

    stripe_refund_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação de Reembolso'
        verbose_name_plural = 'Solicitações de Reembolso'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'seller_deadline']),
            models.Index(fields=['status', 'escalation_deadline']),
            models.Index(fields=['payment', 'status']),
        ]

    def __str__(self):
        return f'RefundRequest {self.id} — {self.status} — {self.order}'


class RefundRequestHistory(models.Model):
    """
    Audit trail de todas as transições de estado de um RefundRequest.
    Imutável: nunca editar ou apagar registros aqui.
    """

    ACTOR_TYPE_CHOICES = [
        ('buyer', 'Comprador'),
        ('seller', 'Vendedor'),
        ('system', 'Sistema'),
        ('platform', 'Plataforma'),
    ]

    refund_request = models.ForeignKey(
        RefundRequest,
        on_delete=models.CASCADE,
        related_name='history',
    )
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    actor_type = models.CharField(max_length=20, choices=ACTOR_TYPE_CHOICES)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Histórico de Solicitação de Reembolso'
        verbose_name_plural = 'Históricos de Solicitações de Reembolso'
        ordering = ['created_at']

    def __str__(self):
        return (
            f'RefundRequest {self.refund_request_id}: '
            f'{self.from_status} → {self.to_status}'
        )


class ScheduledTransfer(models.Model):
    """
    Intenção de repasse agendado para o vendedor.

    Criado quando a Order transiciona para 'delivered'.
    O Celery Beat processa os registros com scheduled_for <= now e status='pending',
    disparando os Transfers via Stripe.

    Regra: 1 ScheduledTransfer por Order (unique=True em order).
    """

    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('dispatched', 'Despachado'),
        ('failed', 'Falhou'),
    ]

    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name='scheduled_transfer',
    )

    payment = models.ForeignKey(
        'Payment',
        on_delete=models.PROTECT,
        related_name='scheduled_transfers',
    )

    scheduled_for = models.DateTimeField(
        help_text='Data/hora a partir da qual o repasse pode ser executado (delivered_at + PAYOUT_DAYS)'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
    )

    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Repasse Agendado'
        verbose_name_plural = 'Repasses Agendados'
        ordering = ['scheduled_for']
        indexes = [
            models.Index(fields=['status', 'scheduled_for']),
        ]

    def __str__(self):
        return (
            f'ScheduledTransfer order={self.order.order_number} '
            f'status={self.status} scheduled_for={self.scheduled_for.date()}'
        )


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
