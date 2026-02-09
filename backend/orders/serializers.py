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
    Serializer para criar pedido com suporte a múltiplos métodos de entrega.

    Formato novo (recomendado):
    {
        "shipping_address_id": 5,
        "shipping_services": {
            "1": {
                "delivery_method": "shipping",
                "service_id": 2,
                "cost": 25.90
            },
            "2": {
                "delivery_method": "in_person",
                "meeting_location_name": "Shopping Iguatemi",
                "meeting_address": {
                    "street": "Av. Brigadeiro Faria Lima",
                    "number": "2232",
                    "city": "São Paulo",
                    "state": "SP",
                    "zipcode": "01451-000"
                },
                "seller_contact_phone": "11999999999",
                "buyer_contact_phone": "11888888888",
                "scheduled_date": "2026-02-15",
                "scheduled_time": "14:00",
                "meeting_notes": "Próximo à entrada principal"
            }
        },
        "payment_method": "pix",
        "buyer_notes": "Entregar após 18h"
    }

    Formato legado (retrocompatível):
    {
        "shipping_services": {
            "1": 2,
            "3": 1
        }
    }
    """
    shipping_address_id = serializers.IntegerField(required=True)
    shipping_services = serializers.DictField(
        required=True,
        help_text=(
            "Mapa de seller_id para configuração de entrega. "
            "Aceita formato novo (dict com delivery_method) ou legado (service_id inteiro)."
        )
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
        """
        Valida e normaliza shipping_services.
        Aceita formato legado (seller_id: service_id) e novo (seller_id: {delivery_method, ...}).
        Converte formato legado para o novo formato automaticamente.
        """
        if not value or not isinstance(value, dict):
            raise serializers.ValidationError(
                "shipping_services deve ser um objeto com seller_id como chave"
            )

        normalized = {}

        for seller_key, service_config in value.items():
            # Converter chave para inteiro
            try:
                seller_id = int(seller_key)
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    f"seller_id inválido: {seller_key}. Deve ser numérico."
                )

            # Formato legado: seller_id: service_id (inteiro)
            if isinstance(service_config, (int, float)):
                normalized[seller_id] = {
                    'delivery_method': 'shipping',
                    'service_id': int(service_config),
                }
                continue

            # Formato legado via string numérica
            if isinstance(service_config, str):
                try:
                    normalized[seller_id] = {
                        'delivery_method': 'shipping',
                        'service_id': int(service_config),
                    }
                    continue
                except ValueError:
                    raise serializers.ValidationError(
                        f"Valor inválido para seller {seller_id}: {service_config}"
                    )

            # Formato novo: seller_id: {delivery_method: ..., ...}
            if isinstance(service_config, dict):
                delivery_method = service_config.get('delivery_method', 'shipping')

                if delivery_method not in ('shipping', 'in_person'):
                    raise serializers.ValidationError(
                        f"delivery_method inválido para seller {seller_id}: '{delivery_method}'. "
                        f"Deve ser 'shipping' ou 'in_person'."
                    )

                if delivery_method == 'shipping':
                    service_id = service_config.get('service_id')
                    if service_id is None:
                        raise serializers.ValidationError(
                            f"service_id é obrigatório para entrega shipping do seller {seller_id}."
                        )
                    try:
                        normalized[seller_id] = {
                            'delivery_method': 'shipping',
                            'service_id': int(service_id),
                            'cost': service_config.get('cost'),
                        }
                    except (ValueError, TypeError):
                        raise serializers.ValidationError(
                            f"service_id inválido para seller {seller_id}."
                        )

                elif delivery_method == 'in_person':
                    # Validar campos obrigatórios para in-person
                    required_fields = [
                        'meeting_location_name',
                        'meeting_address',
                        'seller_contact_phone',
                        'buyer_contact_phone',
                    ]
                    missing = [f for f in required_fields if not service_config.get(f)]
                    if missing:
                        raise serializers.ValidationError(
                            f"Campos obrigatórios ausentes para entrega presencial do seller "
                            f"{seller_id}: {', '.join(missing)}"
                        )

                    # Validar meeting_address tem campos mínimos
                    address = service_config.get('meeting_address', {})
                    if not isinstance(address, dict):
                        raise serializers.ValidationError(
                            f"meeting_address deve ser um objeto para seller {seller_id}."
                        )

                    address_required = ['street', 'city', 'state']
                    missing_addr = [f for f in address_required if not address.get(f)]
                    if missing_addr:
                        raise serializers.ValidationError(
                            f"Campos obrigatórios ausentes em meeting_address do seller "
                            f"{seller_id}: {', '.join(missing_addr)}"
                        )

                    normalized[seller_id] = {
                        'delivery_method': 'in_person',
                        'cost': 0,
                        'meeting_location_name': service_config['meeting_location_name'],
                        'meeting_address': address,
                        'seller_contact_phone': service_config['seller_contact_phone'],
                        'buyer_contact_phone': service_config['buyer_contact_phone'],
                        'scheduled_date': service_config.get('scheduled_date'),
                        'scheduled_time': service_config.get('scheduled_time'),
                        'meeting_notes': service_config.get('meeting_notes', ''),
                    }

                continue

            raise serializers.ValidationError(
                f"Formato inválido para seller {seller_id}. "
                f"Deve ser um inteiro (service_id) ou objeto com delivery_method."
            )

        return normalized

    def validate(self, data):
        """Valida se o carrinho não está vazio e se todos os vendedores têm entrega configurada"""
        user = self.context['request'].user

        # Verificar carrinho
        try:
            cart = user.cart
            if not cart.items.exists():
                raise serializers.ValidationError("Carrinho está vazio.")
        except Cart.DoesNotExist:
            raise serializers.ValidationError("Carrinho não encontrado.")

        # Verificar se todos os vendedores do carrinho têm entrega especificada
        sellers_in_cart = set(cart.get_sellers().values_list('id', flat=True))
        sellers_in_shipping = set(data['shipping_services'].keys())

        missing_sellers = sellers_in_cart - sellers_in_shipping
        if missing_sellers:
            raise serializers.ValidationError({
                'shipping_services': f"Entrega não especificada para vendedores: {missing_sellers}"
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