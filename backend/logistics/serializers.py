from rest_framework import serializers
from .models import ShippingQuote, Shipment, ShipmentTracking, Address


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

        # Verifica se já existe um endereço com o mesmo tipo
        if Address.objects.filter(
            user=user,
            address_type=address_type,
            is_active=True
        ).exists():
            raise serializers.ValidationError({
                "address_type": "Você já possui um endereço deste tipo cadastrado."
            })

        # Verifica se já existe um endereço de envio
        if data['is_shipping_address'] and Address.objects.filter(
            user=user,
            is_shipping_address=True,
            is_active=True
        ).exists():
            raise serializers.ValidationError({
                "address_type": "Você já possui um endereço de envio cadastrado."
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