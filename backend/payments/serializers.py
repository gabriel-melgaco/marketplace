from rest_framework import serializers
from .models import Payment, PaymentWebhook, SellerPayout, PaymentSplit, Dispute, RefundRequest, RefundRequestHistory


class PaymentSplitSerializer(serializers.ModelSerializer):
    """Serializer de split de pagamento por vendedor"""
    seller_email = serializers.EmailField(source='seller.email', read_only=True)
    order_number = serializers.CharField(source='payment.order.order_number', read_only=True)

    class Meta:
        model = PaymentSplit
        fields = [
            'id', 'payment', 'order_number', 'seller', 'seller_email',
            'gross_amount', 'product_amount', 'shipping_amount',
            'platform_fee_amount', 'net_amount',
            'shipping_status', 'stripe_transfer_id', 'transfer_status',
            'error_message', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class DisputeSerializer(serializers.ModelSerializer):
    """Serializer de disputa/chargeback"""

    class Meta:
        model = Dispute
        fields = [
            'id', 'payment', 'stripe_dispute_id', 'stripe_charge_id',
            'amount', 'currency', 'reason', 'status',
            'reversal_attempted', 'reversal_amount',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer completo de pagamento"""
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    splits = PaymentSplitSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'order', 'order_number', 'user', 'user_email',
            'stripe_payment_intent_id', 'stripe_charge_id',
            'transfer_group', 'platform_fee_total',
            'amount', 'currency', 'status', 'payment_method',
            'description', 'failure_message', 'receipt_url',
            'refund_amount', 'refund_reason', 'refunded_at',
            'created_at', 'updated_at', 'paid_at',
            'splits',
        ]
        read_only_fields = [
            'stripe_payment_intent_id', 'stripe_charge_id',
            'transfer_group', 'platform_fee_total',
            'status', 'failure_message', 'receipt_url',
            'created_at', 'updated_at', 'paid_at', 'refunded_at',
            'splits',
        ]


class PaymentIntentCreateSerializer(serializers.Serializer):
    """Serializer para criar Payment Intent no Stripe"""
    order_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(
        choices=['credit_card', 'debit_card', 'pix', 'boleto']
    )
    save_payment_method = serializers.BooleanField(default=False)


class PaymentIntentBatchItemSerializer(serializers.Serializer):
    """Item de resultado no endpoint batch de criação de Payment Intents"""
    order_id = serializers.UUIDField()
    payment_id = serializers.IntegerField()
    client_secret = serializers.CharField()
    amount = serializers.FloatField()
    currency = serializers.CharField()
    payment_method = serializers.CharField()
    reused = serializers.BooleanField(default=False)


class PaymentIntentBatchErrorItemSerializer(serializers.Serializer):
    """Item de erro no endpoint batch de criação de Payment Intents"""
    order_id = serializers.UUIDField()
    error = serializers.CharField()
    detail = serializers.CharField(required=False, allow_blank=True)


class PaymentIntentBatchCreateSerializer(serializers.Serializer):
    """
    Serializer para criar Payment Intents em batch — um por Order.

    Utilizado quando POST /orders/ retorna múltiplos Orders (carrinho multi-vendedor).
    O buyer envia todos os order_ids de uma vez; a plataforma cria um PaymentIntent
    por Order e retorna todos os client_secrets para o frontend processar.
    """
    order_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=20,
        help_text=(
            'Lista de UUIDs dos Orders criados por POST /orders/. '
            'Um PaymentIntent será criado por Order.'
        ),
    )
    payment_method = serializers.ChoiceField(
        choices=['credit_card', 'debit_card', 'pix', 'boleto'],
        help_text='Método de pagamento (aplicado a todos os Orders da lista).',
    )


class PaymentIntentBatchResponseSerializer(serializers.Serializer):
    """Resposta do endpoint batch de criação de Payment Intents"""
    succeeded = PaymentIntentBatchItemSerializer(many=True)
    failed = PaymentIntentBatchErrorItemSerializer(many=True)


class PaymentConfirmSerializer(serializers.Serializer):
    """Serializer para confirmar pagamento"""
    payment_intent_id = serializers.CharField()
    payment_method_id = serializers.CharField(required=False)


class LegacyRefundSerializer(serializers.Serializer):
    """
    Serializer legado para o endpoint POST /api/payments/refund/ (DEPRECATED — retorna 410).
    Mantido apenas para o @extend_schema do endpoint depreciado.
    """
    payment_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    reason = serializers.CharField(required=False, allow_blank=True)


# Alias para compatibilidade com import no views.py legado
RefundSerializer = LegacyRefundSerializer


class RefundRequestHistorySerializer(serializers.ModelSerializer):
    """Audit trail de um RefundRequest"""
    changed_by_email = serializers.EmailField(
        source='changed_by.email', read_only=True, allow_null=True
    )

    class Meta:
        model = RefundRequestHistory
        fields = [
            'id', 'refund_request', 'from_status', 'to_status',
            'changed_by', 'changed_by_email', 'actor_type', 'notes', 'created_at',
        ]
        read_only_fields = fields


class RefundRequestSerializer(serializers.ModelSerializer):
    """Serializer completo de RefundRequest"""
    requested_by_email = serializers.EmailField(
        source='requested_by.email', read_only=True
    )
    decided_by_email = serializers.EmailField(
        source='decided_by.email', read_only=True, allow_null=True
    )
    order_number = serializers.CharField(
        source='order.order_number', read_only=True
    )
    refund_type_display = serializers.CharField(
        source='get_refund_type_display', read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display', read_only=True
    )
    history = RefundRequestHistorySerializer(many=True, read_only=True)

    class Meta:
        model = RefundRequest
        fields = [
            'id', 'payment', 'order', 'order_number',
            'requested_by', 'requested_by_email',
            'status', 'status_display',
            'refund_type', 'refund_type_display',
            'amount_requested', 'amount_approved',
            'reason_buyer', 'reason_seller', 'reason_platform',
            'evidence_urls', 'seller_evidence_urls',
            'seller_deadline', 'escalation_deadline',
            'decided_by', 'decided_by_email',
            'stripe_refund_id', 'metadata',
            'created_at', 'updated_at', 'resolved_at',
            'history',
        ]
        read_only_fields = [
            'id', 'status', 'status_display', 'amount_approved',
            'reason_seller', 'reason_platform',
            'seller_evidence_urls', 'seller_deadline', 'escalation_deadline',
            'decided_by', 'decided_by_email',
            'stripe_refund_id', 'metadata',
            'created_at', 'updated_at', 'resolved_at',
            'history', 'order_number', 'requested_by_email',
            'refund_type_display',
        ]


class RefundRequestCreateSerializer(serializers.Serializer):
    """Serializer para abertura de solicitação de reembolso"""
    payment_id = serializers.IntegerField()
    refund_type = serializers.ChoiceField(
        choices=RefundRequest.REFUND_TYPE_CHOICES
    )
    amount_requested = serializers.DecimalField(max_digits=10, decimal_places=2)
    reason_buyer = serializers.CharField(min_length=10, max_length=2000)
    evidence_urls = serializers.ListField(
        child=serializers.URLField(), required=False, default=list, max_length=10
    )


class RefundRequestApproveSerializer(serializers.Serializer):
    """Serializer para aprovação pelo vendedor"""
    amount_approved = serializers.DecimalField(max_digits=10, decimal_places=2)


class RefundRequestRejectSerializer(serializers.Serializer):
    """Serializer para rejeição pelo vendedor"""
    reason = serializers.CharField(min_length=10, max_length=2000)
    evidence_urls = serializers.ListField(
        child=serializers.URLField(), required=False, default=list, max_length=10
    )


class RefundRequestPlatformDecideSerializer(serializers.Serializer):
    """Serializer para decisão da plataforma (staff)"""
    approve = serializers.BooleanField()
    reason = serializers.CharField(min_length=10, max_length=2000)


class PaymentWebhookSerializer(serializers.ModelSerializer):
    """Serializer de webhook"""
    class Meta:
        model = PaymentWebhook
        fields = '__all__'


class SellerPayoutSerializer(serializers.ModelSerializer):
    """
    Serializer de repasse ao vendedor (legado — model SellerPayout).
    Mantido para compatibilidade. Endpoints /payouts/ e /balance/ usam PaymentSplitSerializer.
    """
    seller_email = serializers.EmailField(source='seller.email', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)

    class Meta:
        model = SellerPayout
        fields = [
            'id', 'seller', 'seller_email', 'order', 'order_number',
            'gross_amount', 'platform_fee', 'net_amount',
            'status', 'stripe_transfer_id',
            'created_at', 'scheduled_for', 'paid_at',
        ]
