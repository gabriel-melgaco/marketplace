from rest_framework import serializers
from .models import Payment, PaymentWebhook, SellerPayout, PaymentSplit, Dispute


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


class PaymentConfirmSerializer(serializers.Serializer):
    """Serializer para confirmar pagamento"""
    payment_intent_id = serializers.CharField()
    payment_method_id = serializers.CharField(required=False)


class RefundSerializer(serializers.Serializer):
    """Serializer para solicitar reembolso"""
    payment_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    reason = serializers.CharField(required=False, allow_blank=True)


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
