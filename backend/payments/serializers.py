from rest_framework import serializers
from .models import Payment, PaymentWebhook, SellerPayout


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer completo de pagamento"""
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'order', 'order_number', 'user', 'user_email',
            'stripe_payment_intent_id', 'stripe_charge_id',
            'amount', 'currency', 'status', 'payment_method',
            'description', 'failure_message', 'receipt_url',
            'refund_amount', 'refund_reason', 'refunded_at',
            'created_at', 'updated_at', 'paid_at'
        ]
        read_only_fields = [
            'stripe_payment_intent_id', 'stripe_charge_id',
            'status', 'failure_message', 'receipt_url',
            'created_at', 'updated_at', 'paid_at', 'refunded_at'
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
    """Serializer de repasse ao vendedor"""
    seller_email = serializers.EmailField(source='seller.email', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    
    class Meta:
        model = SellerPayout
        fields = [
            'id', 'seller', 'seller_email', 'order', 'order_number',
            'gross_amount', 'platform_fee', 'net_amount',
            'status', 'stripe_transfer_id',
            'created_at', 'scheduled_for', 'paid_at'
        ]