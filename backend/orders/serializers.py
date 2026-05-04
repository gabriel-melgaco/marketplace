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


def _order_has_in_person(shipping_services: dict) -> bool:
    """True se qualquer vendedor do pedido tem entrega presencial (in_person ou split)."""
    for seller_data in (shipping_services or {}).values():
        if seller_data.get('delivery_method') in ('in_person', 'split'):
            return True
    return False


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
    has_in_person = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'buyer', 'buyer_name', 'buyer_email',
            'status', 'status_display', 'subtotal', 'shipping_cost', 'total',
            'shipping_address', 'shipping_services', 'payment_method',
            'buyer_notes', 'internal_notes',
            'created_at', 'updated_at', 'cancelled_at',
            'has_in_person',
            'items', 'status_history'
        ]
        read_only_fields = [
            'id', 'order_number', 'buyer', 'created_at',
            'updated_at', 'cancelled_at'
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_has_in_person(self, obj):
        return _order_has_in_person(obj.shipping_services)


class OrderCreateSerializer(serializers.Serializer):
    """
    Serializer para criar pedido com seleção de método de entrega por item (listing).

    Formato:
    {
        "shipping_address_id": 5,
        "items_delivery": [
            {"listing_id": 30, "delivery_method": "melhor_envio", "service_id": 3},
            {"listing_id": 31, "delivery_method": "in_person"}
        ],
        "in_person_by_seller": {
            "9": {
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
                "scheduled_date": "2026-03-10",
                "scheduled_time": "14:00",
                "meeting_notes": "Próximo à entrada principal"
            }
        },
        "payment_method": "pix",
        "buyer_notes": ""
    }

    Regras de delivery_method por item:
    - listing.shipping_method='in_person'   → obrigatório delivery_method='in_person'
    - listing.shipping_method='melhor_envio' → obrigatório delivery_method='melhor_envio'
    - listing.shipping_method='both'         → pode ser 'melhor_envio' ou 'in_person'

    Quando delivery_method='melhor_envio': service_id é obrigatório.
    in_person_by_seller é opcional e todos os seus sub-campos também são opcionais.

    Internamente o serializer converte items_delivery + in_person_by_seller para o
    formato shipping_services por vendedor, que é então passado ao service layer:
    - Vendedor só melhor_envio  → {"delivery_method": "shipping", "service_id": ...}
    - Vendedor só in_person     → {"delivery_method": "in_person", ...}
    - Vendedor com ambos (split) → {"delivery_method": "split", "shipping": {...}, "in_person": {...}}
    """
    shipping_address_id = serializers.IntegerField(required=True)
    items_delivery = serializers.ListField(
        child=serializers.DictField(),
        required=True,
        allow_empty=False,
        help_text=(
            "Lista de escolhas de entrega por listing. "
            "Cada item deve ter: listing_id (int), delivery_method ('melhor_envio' ou 'in_person'). "
            "service_id (int) é obrigatório quando delivery_method='melhor_envio'. "
            "Todos os listings do carrinho devem estar presentes."
        )
    )
    in_person_by_seller = serializers.DictField(
        required=False,
        default=dict,
        help_text=(
            "Detalhes do encontro presencial por seller_id (chave como string). "
            "Todos os campos são opcionais: meeting_location_name, meeting_address, "
            "seller_contact_phone, buyer_contact_phone, scheduled_date, scheduled_time, meeting_notes."
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

    def validate_items_delivery(self, value):
        """
        Valida a lista de items_delivery.

        - Cada entry deve ter listing_id (int) e delivery_method ('melhor_envio' ou 'in_person').
        - Quando delivery_method='melhor_envio', service_id é obrigatório.
        - Listing_ids devem ser únicos.
        - Valida constraints de shipping_method do listing (buscado do DB).
        """
        from products.models import MarketplaceListing, ShippingMethodChoices as SMC

        if not value:
            raise serializers.ValidationError("items_delivery não pode ser vazio.")

        seen_listing_ids = set()
        validated_entries = []

        for idx, entry in enumerate(value):
            if not isinstance(entry, dict):
                raise serializers.ValidationError(
                    f"Item {idx}: deve ser um objeto com listing_id e delivery_method."
                )

            # Validate listing_id
            listing_id = entry.get('listing_id')
            if listing_id is None:
                raise serializers.ValidationError(
                    f"Item {idx}: listing_id é obrigatório."
                )
            try:
                listing_id = int(listing_id)
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    f"Item {idx}: listing_id deve ser um inteiro."
                )

            if listing_id in seen_listing_ids:
                raise serializers.ValidationError(
                    f"Item {idx}: listing_id {listing_id} duplicado em items_delivery."
                )
            seen_listing_ids.add(listing_id)

            # Validate delivery_method
            delivery_method = entry.get('delivery_method')
            if delivery_method not in ('melhor_envio', 'in_person'):
                raise serializers.ValidationError(
                    f"Item {idx} (listing {listing_id}): delivery_method inválido '{delivery_method}'. "
                    f"Deve ser 'melhor_envio' ou 'in_person'."
                )

            # service_id is required for melhor_envio
            service_id = entry.get('service_id')
            if delivery_method == 'melhor_envio':
                if service_id is None:
                    raise serializers.ValidationError(
                        f"Item {idx} (listing {listing_id}): service_id é obrigatório "
                        f"quando delivery_method='melhor_envio'."
                    )
                try:
                    service_id = int(service_id)
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        f"Item {idx} (listing {listing_id}): service_id deve ser um inteiro."
                    )

            # Validate shipping_method constraint from listing
            try:
                listing = MarketplaceListing.objects.get(id=listing_id)
            except MarketplaceListing.DoesNotExist:
                raise serializers.ValidationError(
                    f"Item {idx}: listing {listing_id} não encontrado."
                )

            listing_sm = listing.shipping_method
            if listing_sm == SMC.IN_PERSON and delivery_method != 'in_person':
                raise serializers.ValidationError(
                    f"Item {idx} (listing {listing_id} — '{listing.title}'): "
                    f"este anúncio aceita somente entrega presencial. "
                    f"delivery_method deve ser 'in_person'."
                )
            if listing_sm == SMC.MELHOR_ENVIO and delivery_method != 'melhor_envio':
                raise serializers.ValidationError(
                    f"Item {idx} (listing {listing_id} — '{listing.title}'): "
                    f"este anúncio aceita somente envio via Melhor Envio. "
                    f"delivery_method deve ser 'melhor_envio'."
                )

            validated_entries.append({
                'listing_id': listing_id,
                'listing': listing,
                'delivery_method': delivery_method,
                'service_id': service_id,
            })

        return validated_entries

    def validate(self, data):
        """
        Validação cruzada:
        1. Carrinho não pode estar vazio.
        2. Todos os listings do carrinho devem ter entrada em items_delivery.
        3. Nenhum listing_id em items_delivery pode estar fora do carrinho.
        4. Para cada vendedor com itens melhor_envio: ShippingQuote válida com service_id.
        5. Converte items_delivery + in_person_by_seller → shipping_services (formato interno).
        """
        from logistics.models import ShippingQuote
        from django.utils import timezone
        from decimal import Decimal

        user = self.context['request'].user

        # 1. Check cart exists and is not empty
        try:
            cart = user.cart
            cart_items = list(
                cart.items.select_related('listing__seller').all()
            )
            if not cart_items:
                raise serializers.ValidationError("Carrinho está vazio.")
        except Cart.DoesNotExist:
            raise serializers.ValidationError("Carrinho não encontrado.")

        items_delivery = data.get('items_delivery', [])
        in_person_by_seller = data.get('in_person_by_seller', {})

        # Build lookup: listing_id → entry
        delivery_by_listing = {e['listing_id']: e for e in items_delivery}

        # 2 & 3. All cart listings must be in items_delivery and vice-versa
        cart_listing_ids = {ci.listing_id for ci in cart_items}
        input_listing_ids = set(delivery_by_listing.keys())

        missing_listings = cart_listing_ids - input_listing_ids
        if missing_listings:
            raise serializers.ValidationError({
                'items_delivery': (
                    f"Todos os itens do carrinho devem ter entrada em items_delivery. "
                    f"Listings sem entrega: {missing_listings}"
                )
            })

        extra_listings = input_listing_ids - cart_listing_ids
        if extra_listings:
            raise serializers.ValidationError({
                'items_delivery': (
                    f"Listings não estão no carrinho: {extra_listings}"
                )
            })

        # 4. Group entries by seller, then validate ShippingQuotes for melhor_envio
        from collections import defaultdict
        entries_by_seller = defaultdict(list)
        for ci in cart_items:
            listing_id = ci.listing_id
            entry = delivery_by_listing[listing_id]
            seller_id = ci.listing.seller_id
            entries_by_seller[seller_id].append(entry)

        for seller_id, seller_entries in entries_by_seller.items():
            me_entries = [e for e in seller_entries if e['delivery_method'] == 'melhor_envio']
            if not me_entries:
                continue

            # Validate ShippingQuote exists for this seller
            quote = ShippingQuote.objects.filter(
                user=user,
                seller_id=seller_id,
                expires_at__gt=timezone.now()
            ).order_by('-created_at').first()

            if not quote:
                raise serializers.ValidationError({
                    'items_delivery': (
                        f"Cotação de frete para o vendedor {seller_id} expirou ou não foi encontrada. "
                        f"Recalcule o frete antes de finalizar o pedido."
                    )
                })

            quotes_data = quote.quotes_data
            by_listing = quotes_data.get('by_listing', {}) if isinstance(quotes_data, dict) else {}
            aggregate_services = (
                quotes_data.get('services', []) if isinstance(quotes_data, dict) else
                (quotes_data if isinstance(quotes_data, list) else [])
            )

            # Validate that all ME listing_ids for this seller were part of the original quote.
            if isinstance(quotes_data, dict) and 'melhor_envio_listing_ids' in quotes_data:
                quoted_listing_ids = set(quotes_data['melhor_envio_listing_ids'])
                me_listing_ids = {e['listing_id'] for e in me_entries}
                invalid_ids = me_listing_ids - quoted_listing_ids
                if invalid_ids:
                    raise serializers.ValidationError({
                        'items_delivery': (
                            f'Listing(s) {invalid_ids} do vendedor {seller_id} não estavam '
                            f'no carrinho quando o frete foi calculado. Recalcule o frete.'
                        )
                    })

            # Validate service_id for each ME listing individually.
            # If the quote has per-listing breakdown (by_listing), validate against it.
            # Otherwise fall back to the aggregate services list (backward compat).
            for entry in me_entries:
                listing_id = entry['listing_id']
                service_id = entry['service_id']

                if by_listing and str(listing_id) in by_listing:
                    # New format: validate against per-listing services
                    listing_services = by_listing[str(listing_id)].get('services', [])
                    service_found = next(
                        (s for s in listing_services if isinstance(s, dict) and s.get('id') == service_id),
                        None
                    )
                    if not service_found:
                        raise serializers.ValidationError({
                            'items_delivery': (
                                f"Serviço {service_id} não disponível para o listing {listing_id} "
                                f"(vendedor {seller_id}). Recalcule o frete e escolha um serviço válido."
                            )
                        })
                else:
                    # Old format: validate against aggregate services list
                    service_found = next(
                        (s for s in aggregate_services if isinstance(s, dict) and s.get('id') == service_id),
                        None
                    )
                    if not service_found:
                        raise serializers.ValidationError({
                            'items_delivery': (
                                f"Serviço {service_id} não encontrado na cotação do vendedor {seller_id}. "
                                f"Recalcule o frete e escolha um serviço válido."
                            )
                        })

        # 5. Convert items_delivery + in_person_by_seller → shipping_services (internal format)
        shipping_services = self._build_shipping_services(
            entries_by_seller=entries_by_seller,
            in_person_by_seller=in_person_by_seller,
        )

        data['shipping_services'] = shipping_services
        return data

    @staticmethod
    def _build_shipping_services(entries_by_seller: dict, in_person_by_seller: dict) -> dict:
        """
        Converte o formato por-item para o formato interno por-vendedor.

        Retorna um dict com str(seller_id) como chave e um dos seguintes formatos:
        - {"delivery_method": "shipping", "service_id": int}
        - {"delivery_method": "in_person", "cost": 0, ...detalhes opcionais...}
        - {"delivery_method": "split", "shipping": {...}, "in_person": {...}}
        """
        shipping_services = {}

        for seller_id, seller_entries in entries_by_seller.items():
            has_me = any(e['delivery_method'] == 'melhor_envio' for e in seller_entries)
            has_ip = any(e['delivery_method'] == 'in_person' for e in seller_entries)

            # Gather in_person meeting details for this seller (all fields optional)
            ip_details_raw = in_person_by_seller.get(str(seller_id), {})
            if not isinstance(ip_details_raw, dict):
                ip_details_raw = {}
            ip_address = ip_details_raw.get('meeting_address', {})
            ip_details = {
                'meeting_location_name': ip_details_raw.get('meeting_location_name', ''),
                'meeting_address': ip_address if isinstance(ip_address, dict) else {},
                'seller_contact_phone': ip_details_raw.get('seller_contact_phone', ''),
                'buyer_contact_phone': ip_details_raw.get('buyer_contact_phone', ''),
                'scheduled_date': ip_details_raw.get('scheduled_date'),
                'scheduled_time': ip_details_raw.get('scheduled_time'),
                'meeting_notes': ip_details_raw.get('meeting_notes', ''),
            }

            # Build per_listing map: {str(listing_id): service_id} for ME entries
            per_listing = {
                str(e['listing_id']): {'service_id': e['service_id']}
                for e in seller_entries
                if e['delivery_method'] == 'melhor_envio'
            }

            if has_me and not has_ip:
                # All items shipped via Melhor Envio
                shipping_services[str(seller_id)] = {
                    'delivery_method': 'shipping',
                    'per_listing': per_listing,
                }

            elif has_ip and not has_me:
                # All items in-person
                shipping_services[str(seller_id)] = {
                    'delivery_method': 'in_person',
                    'cost': 0,
                    **ip_details,
                }

            else:
                # Split: seller has both melhor_envio and in_person items
                shipping_services[str(seller_id)] = {
                    'delivery_method': 'split',
                    'shipping': {'per_listing': per_listing},
                    'in_person': ip_details,
                }

        return shipping_services


class OrderListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listagem de pedidos"""
    items_count = serializers.SerializerMethodField()
    buyer_name = serializers.CharField(source='buyer.get_full_name', read_only=True)
    seller_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    has_in_person = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'buyer_name', 'seller_name', 'status', 'status_display',
            'total', 'items_count', 'has_in_person', 'created_at'
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_items_count(self, obj):
        return obj.items.count()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_seller_name(self, obj):
        if obj.seller:
            return obj.seller.get_full_name()
        # Fallback: derive from items (legacy orders created before seller FK was added)
        first_item = obj.items.select_related('seller').first()
        if first_item:
            return first_item.seller.get_full_name()
        return None

    @extend_schema_field(serializers.BooleanField())
    def get_has_in_person(self, obj):
        return _order_has_in_person(obj.shipping_services)
