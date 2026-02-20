from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import (
    ShippingQuote, Shipment, ShipmentTracking, Address,
    OrderDelivery, InPersonDelivery, DeliveryStatusLog, DeliveryMethod,
)
from django.utils import timezone


# =================== Address Serializers ===================
class AddressSerializer(serializers.ModelSerializer):
    """Serializer completo de endereço"""
    
    class Meta:
        model = Address
        fields = [
            'id', 'address_type', 'nickname', 'recipient_name',
            'recipient_phone', 'zipcode', 'street', 'number',
            'complement', 'neighborhood', 'city', 'state',
            'country', 'is_default', 'is_active', 'is_shipping_address',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class AddressCreateSerializer(serializers.ModelSerializer):
    """Serializer para criar endereço"""

    class Meta:
        model = Address
        fields = [
            'address_type', 'nickname', 'recipient_name',
            'recipient_phone', 'zipcode', 'street', 'number',
            'complement', 'neighborhood', 'city', 'state',
            'is_default', 'is_shipping_address'
        ]

    def validate(self, data):
        user = self.context['request'].user
        address_type = data.get('address_type')

        # 🔒 Regra de negócio: shipping => is_shipping_address = True
        if address_type == 'shipping':
            data['is_shipping_address'] = True
        else:
            data['is_shipping_address'] = False

        # Shipping permite múltiplos; outros tipos são únicos
        if address_type != 'shipping' and Address.objects.filter(
            user=user,
            address_type=address_type,
            is_active=True
        ).exists():
            raise serializers.ValidationError({
                "address_type": "Você já possui um endereço deste tipo cadastrado."
            })

        return data



# =================== Shipping Quote Serializers ===================
class ShippingQuoteRequestSerializer(serializers.Serializer):
    """
    Serializer para solicitar cotação de frete
    ATUALIZADO: Agora usa shipping_address_id em vez de destination_zipcode
    """
    shipping_address_id = serializers.IntegerField(
        required=True,
        help_text="ID do endereço de entrega salvo do usuário"
    )
    
    def validate_shipping_address_id(self, value):
        """Valida se o endereço existe e pertence ao usuário"""
        user = self.context['request'].user
        
        if not Address.objects.filter(
            id=value, 
            user=user, 
            is_active=True
        ).exists():
            raise serializers.ValidationError(
                "Endereço não encontrado ou não pertence ao usuário"
            )
        
        return value
    
    def validate(self, data):
        """Valida se o carrinho tem itens"""
        user = self.context['request'].user
        
        try:
            cart = user.cart
            if not cart.items.exists():
                raise serializers.ValidationError("Carrinho está vazio.")
        except:
            raise serializers.ValidationError("Carrinho não encontrado.")
        
        return data


class ShippingServiceSerializer(serializers.Serializer):
    """Serializer de um serviço de frete"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    company = serializers.CharField()
    company_picture = serializers.URLField(required=False, allow_blank=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    delivery_time = serializers.IntegerField()
    currency = serializers.CharField()


class SellerShippingQuoteSerializer(serializers.Serializer):
    """Serializer de cotação por vendedor"""
    seller_id = serializers.IntegerField()
    seller_name = serializers.CharField()
    seller_city = serializers.CharField(required=False)
    seller_state = serializers.CharField(required=False)
    services = ShippingServiceSerializer(many=True)
    total_value = serializers.DecimalField(max_digits=10, decimal_places=2)
    items_count = serializers.IntegerField()
    error = serializers.CharField(required=False)


class ShippingQuoteResponseSerializer(serializers.Serializer):
    """Serializer de resposta de cotação agrupada por vendedor"""
    quotes_by_seller = serializers.DictField(
        child=SellerShippingQuoteSerializer()
    )
    shipping_address = AddressSerializer()
    shipping_address_id = serializers.IntegerField()
    total_items = serializers.IntegerField()
    total_value = serializers.DecimalField(max_digits=10, decimal_places=2)


class ShippingQuoteSerializer(serializers.ModelSerializer):
    """Serializer de cotação de frete salva"""
    services = serializers.SerializerMethodField()
    seller_name = serializers.CharField(source='seller.get_full_name', read_only=True, required=False)
    
    class Meta:
        model = ShippingQuote
        fields = [
            'id', 'seller', 'seller_name', 'origin_zipcode', 'origin_address',
            'destination_zipcode', 'destination_address',
            'weight', 'height', 'width', 'length', 'declared_value',
            'services', 'created_at', 'expires_at'
        ]
    
    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_services(self, obj):
        """Retorna lista de serviços de frete disponíveis formatados"""
        services = []
        
        # O quotes_data pode vir em diferentes formatos
        quotes_list = obj.quotes_data
        if isinstance(quotes_list, dict):
            quotes_list = quotes_list.get('services', [])
        
        for quote in quotes_list:
            if isinstance(quote, dict) and 'error' not in quote:
                services.append({
                    'id': quote.get('id'),
                    'name': quote.get('name'),
                    'company': quote.get('company', {}).get('name') if isinstance(quote.get('company'), dict) else quote.get('company'),
                    'company_picture': quote.get('company', {}).get('picture') if isinstance(quote.get('company'), dict) else '',
                    'price': float(quote.get('price', 0)),
                    'discount': float(quote.get('discount', 0)),
                    'delivery_time': quote.get('delivery_time'),
                    'currency': quote.get('currency', 'BRL'),
                })
        
        return services


# =================== Shipment Serializers ===================
class ShipmentTrackingSerializer(serializers.ModelSerializer):
    """Serializer de rastreamento"""
    
    class Meta:
        model = ShipmentTracking
        fields = ['id', 'status', 'description', 'location', 'occurred_at', 'created_at']


class ShipmentSerializer(serializers.ModelSerializer):
    """Serializer completo de envio"""
    tracking_history = ShipmentTrackingSerializer(many=True, read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    
    class Meta:
        model = Shipment
        fields = [
            'id', 'order', 'order_number',
            'melhorenvio_order_id', 'melhorenvio_tracking_code',
            'carrier_name', 'carrier_service',
            'shipping_cost', 'insurance_value',
            'status', 'tracking_url',
            'weight', 'height', 'width', 'length',
            'origin_address', 'destination_address',
            'label_url', 'label_generated_at',
            'estimated_delivery_date',
            'created_at', 'updated_at', 'posted_at', 'delivered_at',
            'tracking_history'
        ]


class ShipmentCreateSerializer(serializers.Serializer):
    """Serializer para criar envio"""
    order_id = serializers.UUIDField()
    shipping_service_id = serializers.IntegerField()
    
    def validate_order_id(self, value):
        """Valida se o pedido existe e não tem envio"""
        from orders.models import Order
        
        try:
            order = Order.objects.get(id=value)
            if hasattr(order, 'shipment'):
                raise serializers.ValidationError("Este pedido já possui um envio cadastrado.")
        except Order.DoesNotExist:
            raise serializers.ValidationError("Pedido não encontrado.")
        
        return value


class ShipmentLabelSerializer(serializers.Serializer):
    """Serializer para gerar etiqueta"""
    shipment_id = serializers.IntegerField()


# =================== CEP Lookup Serializer ===================
class CEPLookupSerializer(serializers.Serializer):
    """Serializer para buscar endereço por CEP"""
    zipcode = serializers.CharField(max_length=9)

    def validate_zipcode(self, value):
        """Remove caracteres não numéricos do CEP"""
        cleaned = ''.join(filter(str.isdigit, value))
        if len(cleaned) != 8:
            raise serializers.ValidationError("CEP deve conter 8 dígitos.")
        return cleaned


# =================== In-Person Delivery Serializers ===================
class InPersonDeliverySerializer(serializers.ModelSerializer):
    """Serializer completo para entrega presencial"""

    seller_name = serializers.CharField(source='seller.get_full_name', read_only=True)
    buyer_name = serializers.CharField(source='buyer.get_full_name', read_only=True)
    is_fully_confirmed = serializers.BooleanField(read_only=True)
    is_fully_completed = serializers.BooleanField(read_only=True)

    class Meta:
        model = InPersonDelivery
        fields = [
            'id', 'seller', 'seller_name', 'buyer', 'buyer_name',
            'meeting_status', 'meeting_location_name', 'meeting_address',
            'meeting_notes', 'scheduled_date', 'scheduled_time',
            'seller_contact_phone', 'buyer_contact_phone',
            'seller_confirmed', 'buyer_confirmed',
            'seller_confirmed_at', 'buyer_confirmed_at',
            'is_fully_confirmed',
            'seller_completed', 'buyer_completed',
            'seller_completed_at', 'buyer_completed_at',
            'is_fully_completed', 'completion_notes',
            'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = [
            'seller', 'buyer', 'seller_confirmed_at', 'buyer_confirmed_at',
            'seller_completed_at', 'buyer_completed_at',
            'completed_at', 'created_at', 'updated_at'
        ]


class InPersonDeliveryCreateSerializer(serializers.ModelSerializer):
    """Serializer para criar entrega presencial"""

    class Meta:
        model = InPersonDelivery
        fields = [
            'meeting_location_name', 'meeting_address', 'meeting_notes',
            'scheduled_date', 'scheduled_time',
            'seller_contact_phone', 'buyer_contact_phone'
        ]

    def validate(self, data):
        """Valida data e horário do encontro"""
        scheduled_date = data.get('scheduled_date')
        scheduled_time = data.get('scheduled_time')

        # Se data e hora foram fornecidos, validar que é no futuro
        if scheduled_date and scheduled_time:
            from datetime import datetime, time
            now = timezone.now()
            scheduled_datetime = timezone.make_aware(
                datetime.combine(scheduled_date, scheduled_time)
            )

            if scheduled_datetime <= now:
                raise serializers.ValidationError(
                    "Data e horário do encontro devem ser no futuro"
                )

        return data


class InPersonDeliveryUpdateSerializer(serializers.ModelSerializer):
    """Serializer para atualizar entrega presencial"""

    class Meta:
        model = InPersonDelivery
        fields = [
            'meeting_status', 'meeting_location_name', 'meeting_address',
            'meeting_notes', 'scheduled_date', 'scheduled_time',
            'completion_notes'
        ]

    def validate_meeting_status(self, value):
        """Valida transições de status"""
        instance = self.instance
        if not instance:
            return value

        # Define transições válidas
        valid_transitions = {
            'pending_schedule': ['scheduled', 'cancelled'],
            'scheduled': ['confirmed', 'cancelled', 'no_show'],
            'confirmed': ['in_progress', 'cancelled', 'no_show'],
            'in_progress': ['completed', 'cancelled'],
            'completed': [],  # Final state
            'cancelled': [],  # Final state
            'no_show': ['scheduled'],  # Pode reagendar
        }

        current_status = instance.meeting_status
        if value != current_status:
            if value not in valid_transitions.get(current_status, []):
                raise serializers.ValidationError(
                    f"Transição inválida de '{current_status}' para '{value}'"
                )

        return value


# =================== Order Delivery Serializers ===================
class OrderDeliverySerializer(serializers.ModelSerializer):
    """Serializer completo para entrega do pedido"""

    seller_name = serializers.CharField(source='seller.get_full_name', read_only=True)
    delivery_info = serializers.SerializerMethodField()
    shipment_details = ShipmentSerializer(source='shipment', read_only=True)
    in_person_details = InPersonDeliverySerializer(source='in_person_delivery', read_only=True)

    class Meta:
        model = OrderDelivery
        fields = [
            'id', 'order', 'seller', 'seller_name',
            'delivery_method', 'status', 'delivery_cost',
            'shipment', 'shipment_details',
            'in_person_delivery', 'in_person_details',
            'delivery_info',
            'created_at', 'updated_at', 'confirmed_at', 'completed_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    @extend_schema_field(serializers.DictField())
    def get_delivery_info(self, obj):
        """Retorna informações consolidadas da entrega"""
        return obj.get_delivery_info()


class OrderDeliveryCreateSerializer(serializers.Serializer):
    """Serializer para criar opção de entrega no checkout"""

    order_id = serializers.UUIDField()
    seller_id = serializers.IntegerField()
    delivery_method = serializers.ChoiceField(choices=DeliveryMethod.choices)

    # Para SHIPPING
    shipping_service_id = serializers.IntegerField(required=False, allow_null=True)

    # Para IN_PERSON
    meeting_location_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    meeting_address = serializers.JSONField(required=False)
    meeting_notes = serializers.CharField(required=False, allow_blank=True)
    scheduled_date = serializers.DateField(required=False, allow_null=True)
    scheduled_time = serializers.TimeField(required=False, allow_null=True)
    seller_contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    buyer_contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=20)

    def validate(self, data):
        """Valida que os campos corretos estão preenchidos conforme o tipo de entrega"""
        delivery_method = data.get('delivery_method')

        if delivery_method == DeliveryMethod.SHIPPING:
            if not data.get('shipping_service_id'):
                raise serializers.ValidationError({
                    'shipping_service_id': 'Campo obrigatório para envio via transportadora'
                })

        elif delivery_method == DeliveryMethod.IN_PERSON:
            required_fields = [
                'meeting_location_name',
                'meeting_address',
                'seller_contact_phone',
                'buyer_contact_phone'
            ]

            missing_fields = [
                field for field in required_fields
                if not data.get(field)
            ]

            if missing_fields:
                raise serializers.ValidationError({
                    field: 'Campo obrigatório para entrega presencial'
                    for field in missing_fields
                })

            # Validar data/hora no futuro se fornecidos
            scheduled_date = data.get('scheduled_date')
            scheduled_time = data.get('scheduled_time')

            if scheduled_date and scheduled_time:
                from datetime import datetime
                now = timezone.now()
                scheduled_datetime = timezone.make_aware(
                    datetime.combine(scheduled_date, scheduled_time)
                )

                if scheduled_datetime <= now:
                    raise serializers.ValidationError(
                        "Data e horário do encontro devem ser no futuro"
                    )

        return data


class DeliveryMethodChoiceSerializer(serializers.Serializer):
    """Serializer para escolher método de entrega no checkout"""

    seller_id = serializers.IntegerField()
    delivery_method = serializers.ChoiceField(choices=DeliveryMethod.choices)

    # Para shipping: ID do serviço escolhido na cotação
    shipping_service_id = serializers.IntegerField(required=False, allow_null=True)

    # Para in-person: dados do encontro
    meeting_data = serializers.JSONField(required=False)

    def validate(self, data):
        """Valida campos conforme método escolhido"""
        delivery_method = data['delivery_method']

        if delivery_method == DeliveryMethod.SHIPPING:
            if not data.get('shipping_service_id'):
                raise serializers.ValidationError(
                    'shipping_service_id é obrigatório para envio via transportadora'
                )

        elif delivery_method == DeliveryMethod.IN_PERSON:
            meeting_data = data.get('meeting_data', {})

            required_fields = [
                'meeting_location_name',
                'seller_contact_phone',
                'buyer_contact_phone'
            ]

            missing = [f for f in required_fields if not meeting_data.get(f)]
            if missing:
                raise serializers.ValidationError({
                    'meeting_data': f'Campos obrigatórios ausentes: {", ".join(missing)}'
                })

        return data


class DeliveryStatusLogSerializer(serializers.ModelSerializer):
    """Serializer para log de status de entrega"""

    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)

    class Meta:
        model = DeliveryStatusLog
        fields = [
            'id', 'order_delivery', 'from_status', 'to_status',
            'changed_by', 'changed_by_name', 'notes', 'metadata',
            'created_at'
        ]
        read_only_fields = ['created_at']


