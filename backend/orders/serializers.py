from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Order, OrderItem, OrderStatusHistory, Cart, CartItem
from products.serializers import MarketplaceListingSerializer


# =================== Cart Serializers ===================
class CartItemSerializer(serializers.ModelSerializer):
    """Serializer de item do carrinho"""
    listing = MarketplaceListingSerializer(read_only=True)
    subtotal = serializers.SerializerMethodField()
    seller_id = serializers.IntegerField(source='listing.seller.id', read_only=True)
    seller_name = serializers.CharField(source='listing.seller.get_full_name', read_only=True)
    
    class Meta:
        model = CartItem
        fields = ['id', 'listing', 'quantity', 'subtotal', 'seller_id', 'seller_name', 'added_at']
        read_only_fields = ['added_at']
    
    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_subtotal(self, obj):
        return obj.get_subtotal()


class CartItemCreateSerializer(serializers.ModelSerializer):
    """Serializer para adicionar item ao carrinho"""
    class Meta:
        model = CartItem
        fields = ['listing', 'quantity']


class CartSerializer(serializers.ModelSerializer):
    """Serializer do carrinho"""
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    sellers = serializers.SerializerMethodField()
    
    class Meta:
        model = Cart
        fields = ['id', 'items', 'total', 'items_count', 'sellers', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_total(self, obj):
        return obj.get_total()
    
    @extend_schema_field(serializers.IntegerField())
    def get_items_count(self, obj):
        return obj.items.count()
    
    @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
    def get_sellers(self, obj):
        """Lista de IDs dos vendedores no carrinho"""
        return list(obj.get_sellers().values_list('id', flat=True))


# =================== Order Item Serializers ===================
class OrderItemSerializer(serializers.ModelSerializer):
    """Serializer de item do pedido"""
    seller_name = serializers.CharField(source='seller.get_full_name', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'listing', 'seller', 'seller_name', 'product_name', 'product_code',
            'brand_name', 'condition_name', 'quantity', 'unit_price',
            'subtotal', 'shipping_cost', 'weight_kg', 'height_cm', 'width_cm', 'length_cm',
            'seller_address'
        ]
        read_only_fields = ['subtotal']


# =================== Order Status History Serializers ===================
class OrderStatusHistorySerializer(serializers.ModelSerializer):
    """Serializer de histórico de status"""
    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)
    
    class Meta:
        model = OrderStatusHistory
        fields = ['id', 'old_status', 'new_status', 'changed_by', 'changed_by_name', 'notes', 'created_at']


# =================== Order Serializers ===================
class OrderSerializer(serializers.ModelSerializer):
    """Serializer completo do pedido"""
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    buyer_name = serializers.CharField(source='buyer.get_full_name', read_only=True)
    buyer_email = serializers.EmailField(source='buyer.email', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'buyer', 'buyer_name', 'buyer_email',
            'status', 'status_display', 'subtotal', 'shipping_cost', 'total',
            'shipping_address', 'shipping_services', 'payment_method',
            'buyer_notes', 'internal_notes',
            'created_at', 'updated_at', 'cancelled_at',
            'items', 'status_history'
        ]
        read_only_fields = [
            'id', 'order_number', 'buyer', 'created_at', 
            'updated_at', 'cancelled_at'
        ]


class OrderCreateSerializer(serializers.Serializer):
    """
    Serializer para criar pedido
    
    Exemplo de payload:
    {
        "shipping_address_id": 5,
        "shipping_services": {
            "1": 2,  // seller_id: service_id
            "3": 1
        },
        "payment_method": "credit_card",
        "buyer_notes": "Entregar após 18h"
    }
    """
    shipping_address_id = serializers.IntegerField(required=True)
    shipping_services = serializers.DictField(
        child=serializers.IntegerField(),
        required=True,
        help_text="Mapa de seller_id para service_id escolhido na cotação"
    )
    payment_method = serializers.ChoiceField(
        choices=[
            ('credit_card', 'Cartão de Crédito'),
            ('debit_card', 'Cartão de Débito'),
            ('pix', 'PIX'),
            ('boleto', 'Boleto')
        ],
        required=True
    )
    buyer_notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_shipping_address_id(self, value):
        """Valida se o endereço existe e pertence ao usuário"""
        from logistics.models import Address
        user = self.context['request'].user
        
        if not Address.objects.filter(id=value, user=user, is_active=True).exists():
            raise serializers.ValidationError("Endereço inválido ou não encontrado.")
        
        return value
    
    def validate_shipping_services(self, value):
        """Valida se shipping_services foi fornecido corretamente"""
        if not value or not isinstance(value, dict):
            raise serializers.ValidationError(
                "shipping_services deve ser um objeto com seller_id: service_id"
            )
        
        # Converter chaves para inteiros se vieram como strings
        try:
            return {int(k): int(v) for k, v in value.items()}
        except (ValueError, TypeError):
            raise serializers.ValidationError(
                "shipping_services deve conter apenas IDs numéricos"
            )
    
    def validate(self, data):
        """Valida se o carrinho não está vazio e se todos os vendedores têm frete"""
        user = self.context['request'].user
        
        # Verificar carrinho
        try:
            cart = user.cart
            if not cart.items.exists():
                raise serializers.ValidationError("Carrinho está vazio.")
        except Cart.DoesNotExist:
            raise serializers.ValidationError("Carrinho não encontrado.")
        
        # Verificar se todos os vendedores do carrinho têm frete especificado
        sellers_in_cart = set(cart.get_sellers().values_list('id', flat=True))
        sellers_in_shipping = set(data['shipping_services'].keys())
        
        missing_sellers = sellers_in_cart - sellers_in_shipping
        if missing_sellers:
            raise serializers.ValidationError({
                'shipping_services': f"Frete não especificado para vendedores: {missing_sellers}"
            })
        
        extra_sellers = sellers_in_shipping - sellers_in_cart
        if extra_sellers:
            raise serializers.ValidationError({
                'shipping_services': f"Vendedores não estão no carrinho: {extra_sellers}"
            })
        
        return data


class OrderListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listagem de pedidos"""
    items_count = serializers.SerializerMethodField()
    buyer_name = serializers.CharField(source='buyer.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'buyer_name', 'status', 'status_display',
            'total', 'items_count', 'created_at'
        ]
    
    @extend_schema_field(serializers.IntegerField())
    def get_items_count(self, obj):
        return obj.items.count()


class OrderUpdateStatusSerializer(serializers.Serializer):
    """Serializer para atualizar status do pedido"""
    status = serializers.ChoiceField(
        choices=Order.STATUS_CHOICES
    )
    notes = serializers.CharField(required=False, allow_blank=True)