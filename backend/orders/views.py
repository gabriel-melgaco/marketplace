from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter, OpenApiResponse, OpenApiExample
from rest_framework import serializers as rf_serializers
from collections import defaultdict
import datetime

from .models import Order, OrderItem, OrderStatusHistory, Cart, CartItem
from .serializers import (
    OrderSerializer, OrderListSerializer, OrderCreateSerializer,
    OrderUpdateStatusSerializer, CartSerializer, CartItemSerializer,
    CartItemCreateSerializer
)
from .services import (
    OrderCreationService,
    OrderCreationError,
    OrderStateMachine,
    OrderStatusTransitionError
)
from products.models import MarketplaceListing
from logistics.models import Address, ShippingQuote


# =================== Cart Views ===================
@extend_schema(tags=['Cart'], summary='Get cart', description='Retrieve the current user\'s shopping cart.')
class CartDetailView(generics.RetrieveAPIView):
    """Ver carrinho do usuário"""
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        return cart


@extend_schema(
    tags=['Cart'],
    summary='Add item to cart',
    request=CartItemCreateSerializer,
    responses={201: CartSerializer},
    description="Add an item to the shopping cart. If item already exists, increments quantity."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_to_cart(request):
    """Adicionar item ao carrinho"""
    serializer = CartItemCreateSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    listing_id = serializer.validated_data['listing']
    quantity = serializer.validated_data['quantity']
    
    # Verificar se listing existe e está ativo
    listing = get_object_or_404(
        MarketplaceListing,
        id=listing_id.id,
        is_active=True,
        quantity__gte=quantity
    )

    # Verificar se o usuário não é o vendedor do produto
    if listing.seller == request.user:
        return Response(
            {'error': 'Você não pode adicionar ao carrinho um produto que você mesmo está vendendo'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Criar ou pegar carrinho
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    # Verificar se item já existe no carrinho
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        listing=listing,
        defaults={'quantity': quantity}
    )
    
    if not created:
        # Atualizar quantidade
        cart_item.quantity += quantity
        
        # Verificar estoque
        if cart_item.quantity > listing.quantity:
            return Response(
                {'error': 'Quantidade solicitada maior que estoque disponível'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cart_item.save()
    
    cart_serializer = CartSerializer(cart)
    return Response(cart_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=['Cart'],
    summary='Update cart item quantity',
    request=inline_serializer(
        name='UpdateCartItemRequest',
        fields={'quantity': rf_serializers.IntegerField(min_value=1)}
    ),
    responses={200: CartSerializer},
    description="Update the quantity of an item in the cart."
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_cart_item(request, item_id):
    """Atualizar quantidade de item no carrinho"""
    cart_item = get_object_or_404(
        CartItem,
        id=item_id,
        cart__user=request.user
    )
    
    quantity = request.data.get('quantity')
    
    if not quantity or quantity < 1:
        return Response(
            {'error': 'Quantidade inválida'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verificar estoque
    if quantity > cart_item.listing.quantity:
        return Response(
            {'error': 'Quantidade maior que estoque disponível'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    cart_item.quantity = quantity
    cart_item.save()
    
    cart_serializer = CartSerializer(cart_item.cart)
    return Response(cart_serializer.data)


@extend_schema(
    tags=['Cart'],
    summary='Remove item from cart',
    responses={200: CartSerializer},
    description="Remove a specific item from the cart."
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_from_cart(request, item_id):
    """Remover item do carrinho"""
    cart_item = get_object_or_404(
        CartItem,
        id=item_id,
        cart__user=request.user
    )

    cart_item.delete()

    cart = cart_item.cart
    cart_serializer = CartSerializer(cart)
    return Response(cart_serializer.data)


@extend_schema(
    tags=['Cart'],
    summary='Clear cart',
    responses={200: CartSerializer},
    description="Remove all items from the cart."
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def clear_cart(request):
    """Limpar carrinho"""
    cart = get_object_or_404(Cart, user=request.user)
    cart.items.all().delete()
    
    cart_serializer = CartSerializer(cart)
    return Response(cart_serializer.data)


# =================== Order Views ===================
@extend_schema(tags=['Orders'], summary='List buyer orders', description='List all orders for the authenticated buyer.')
class OrderListView(generics.ListAPIView):
    """Listar pedidos do usuário comprador"""
    serializer_class = OrderListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(
            buyer=self.request.user
        ).prefetch_related('items').order_by('-created_at')


@extend_schema(tags=['Orders'], summary='Get order details', description='Get detailed information about a specific order.')
class OrderDetailView(generics.RetrieveAPIView):
    """Detalhes de um pedido do comprador"""
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Order.objects.filter(buyer=self.request.user)
    
    def get_object(self):
        order_id = self.kwargs.get('pk')
        return get_object_or_404(
            self.get_queryset(),
            id=order_id
        )


@extend_schema(
    tags=['Orders'],
    summary='Create order',
    request=inline_serializer(
        name='OrderCreateRequest',
        fields={
            'shipping_address_id': rf_serializers.IntegerField(
                help_text='ID do endereço de entrega do comprador'
            ),
            'items_delivery': rf_serializers.ListField(
                child=inline_serializer(
                    name='ItemDeliveryEntry',
                    fields={
                        'listing_id': rf_serializers.IntegerField(
                            help_text='ID do listing do carrinho'
                        ),
                        'delivery_method': rf_serializers.ChoiceField(
                            choices=['melhor_envio', 'in_person'],
                            help_text=(
                                'Método de entrega para este item. '
                                "'melhor_envio' requer service_id. "
                                'Deve respeitar listing.shipping_method: '
                                "in_person-only → obrigado 'in_person'; "
                                "melhor_envio-only → obrigatório 'melhor_envio'; "
                                "both → qualquer um."
                            )
                        ),
                        'service_id': rf_serializers.IntegerField(
                            required=False,
                            help_text="ID do serviço de frete (obrigatório quando delivery_method='melhor_envio')"
                        ),
                    }
                ),
                help_text=(
                    'Lista de escolhas de entrega por listing (um entry por item do carrinho). '
                    'Todos os listings do carrinho devem estar presentes.'
                )
            ),
            'in_person_by_seller': rf_serializers.DictField(
                required=False,
                default=dict,
                help_text=(
                    'Detalhes do encontro presencial por seller_id (chave como string). '
                    'Todos os campos são opcionais: meeting_location_name, meeting_address '
                    '(street, number, city, state, zipcode), seller_contact_phone, '
                    'buyer_contact_phone, scheduled_date (YYYY-MM-DD), '
                    'scheduled_time (HH:MM), meeting_notes. '
                    'Pode omitir vendedores ou enviar sub-objeto vazio {}.'
                )
            ),
            'payment_method': rf_serializers.ChoiceField(
                choices=['credit_card', 'debit_card', 'pix', 'boleto'],
                help_text='Método de pagamento'
            ),
            'buyer_notes': rf_serializers.CharField(
                required=False,
                allow_blank=True,
                help_text='Observações do comprador (opcional)'
            ),
        }
    ),
    responses={201: OrderSerializer},
    description=(
        "Create an order from the cart. Delivery method is chosen **per item** (listing), "
        "not per seller.\n\n"
        "## Fields\n\n"
        "**`items_delivery`** (required): List with one entry per cart item.\n"
        "- `listing_id`: ID of the listing in the cart\n"
        "- `delivery_method`: `'melhor_envio'` or `'in_person'`\n"
        "- `service_id`: Required when `delivery_method='melhor_envio'`. "
        "Must match a service in a valid (non-expired) ShippingQuote for that seller.\n\n"
        "**Listing constraints** — `delivery_method` must respect `listing.shipping_method`:\n"
        "- `in_person` listing → must choose `'in_person'`\n"
        "- `melhor_envio` listing → must choose `'melhor_envio'`\n"
        "- `both` listing → either is valid\n\n"
        "**`in_person_by_seller`** (optional): Meeting details per seller_id (string key).\n"
        "All sub-fields are optional — can be filled later via update endpoint:\n"
        "`meeting_location_name`, `meeting_address`, `seller_contact_phone`, "
        "`buyer_contact_phone`, `scheduled_date`, `scheduled_time`, `meeting_notes`\n\n"
        "## Internal Conversion\n\n"
        "The API converts `items_delivery` + `in_person_by_seller` into an internal "
        "per-seller format before processing:\n"
        "- Seller with only `melhor_envio` items → `shipping` delivery\n"
        "- Seller with only `in_person` items → `in_person` delivery\n"
        "- Seller with mixed items → `split` delivery\n\n"
        "## Shipping Cost\n\n"
        "Costs are always taken from the server-side ShippingQuote — never from client input."
    ),
    examples=[
        OpenApiExample(
            name='Mixed cart: listing 30 (both→melhor_envio) + listing 31 (in_person)',
            description=(
                'Seller 9 has two listings: listing 30 (shipping_method=both) chosen for '
                'Melhor Envio delivery, and listing 31 (shipping_method=in_person) for in-person. '
                'This produces a split delivery internally.'
            ),
            value={
                'shipping_address_id': 5,
                'items_delivery': [
                    {'listing_id': 30, 'delivery_method': 'melhor_envio', 'service_id': 3},
                    {'listing_id': 31, 'delivery_method': 'in_person'},
                ],
                'in_person_by_seller': {
                    '9': {
                        'meeting_location_name': 'Shopping Iguatemi',
                        'meeting_address': {
                            'street': 'Av. Brigadeiro Faria Lima',
                            'number': '2232',
                            'city': 'São Paulo',
                            'state': 'SP',
                            'zipcode': '01451-000'
                        },
                        'seller_contact_phone': '11999999999',
                        'buyer_contact_phone': '11888888888',
                        'scheduled_date': '2026-03-10',
                        'scheduled_time': '14:00',
                        'meeting_notes': 'Próximo à entrada principal'
                    }
                },
                'payment_method': 'pix',
                'buyer_notes': ''
            },
            request_only=True,
        ),
        OpenApiExample(
            name='All Melhor Envio',
            description='All cart items shipped via Melhor Envio (two sellers)',
            value={
                'shipping_address_id': 5,
                'items_delivery': [
                    {'listing_id': 10, 'delivery_method': 'melhor_envio', 'service_id': 2},
                    {'listing_id': 20, 'delivery_method': 'melhor_envio', 'service_id': 1},
                ],
                'in_person_by_seller': {},
                'payment_method': 'credit_card',
                'buyer_notes': ''
            },
            request_only=True,
        ),
        OpenApiExample(
            name='All in-person',
            description='All cart items picked up in-person with meeting details',
            value={
                'shipping_address_id': 5,
                'items_delivery': [
                    {'listing_id': 10, 'delivery_method': 'in_person'},
                    {'listing_id': 20, 'delivery_method': 'in_person'},
                ],
                'in_person_by_seller': {
                    '1': {
                        'meeting_location_name': 'Loja Física Centro',
                        'meeting_address': {
                            'street': 'Rua Augusta',
                            'number': '100',
                            'city': 'São Paulo',
                            'state': 'SP',
                            'zipcode': '01304-000'
                        },
                        'seller_contact_phone': '11999999999',
                        'buyer_contact_phone': '11888888888'
                    },
                    '2': {}
                },
                'payment_method': 'pix',
                'buyer_notes': ''
            },
            request_only=True,
        ),
        OpenApiExample(
            name='Split with in-person meeting details',
            description=(
                'Seller 9 has listing 30 (both → melhor_envio, service 3) and '
                'listing 31 (in_person). Meeting details provided for in-person items.'
            ),
            value={
                'shipping_address_id': 5,
                'items_delivery': [
                    {'listing_id': 30, 'delivery_method': 'melhor_envio', 'service_id': 3},
                    {'listing_id': 31, 'delivery_method': 'in_person'},
                ],
                'in_person_by_seller': {
                    '9': {
                        'meeting_location_name': 'Portaria do Condomínio',
                        'seller_contact_phone': '11912345678',
                        'buyer_contact_phone': '11987654321',
                        'scheduled_date': '2026-03-15',
                        'scheduled_time': '10:00'
                    }
                },
                'payment_method': 'pix',
                'buyer_notes': 'Ligar antes de chegar'
            },
            request_only=True,
        ),
    ],
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_order(request):
    """
    Criar pedido a partir do carrinho usando service layer.
    Método de entrega selecionado por item (listing), não por vendedor.

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
                "seller_contact_phone": "11999999999",
                "buyer_contact_phone": "11888888888"
            }
        },
        "payment_method": "pix",
        "buyer_notes": "Opcional"
    }
    """
    # Validate request data
    serializer = OrderCreateSerializer(
        data=request.data,
        context={'request': request}
    )

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = request.user

    # Get user's cart
    cart = get_object_or_404(Cart, user=user)

    if not cart.items.exists():
        return Response(
            {'error': 'Carrinho está vazio'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Get shipping address
    shipping_address = get_object_or_404(
        Address,
        id=serializer.validated_data['shipping_address_id'],
        user=user,
        is_active=True
    )

    # Extract validated data
    shipping_services_input = serializer.validated_data['shipping_services']
    payment_method = serializer.validated_data['payment_method']
    buyer_notes = serializer.validated_data.get('buyer_notes', '')

    # Create order using service layer
    try:
        order = OrderCreationService.create_order_from_cart(
            user=user,
            cart=cart,
            shipping_address=shipping_address,
            shipping_services_input=shipping_services_input,
            payment_method=payment_method,
            buyer_notes=buyer_notes
        )

        # Return created order
        order_serializer = OrderSerializer(order)
        return Response(order_serializer.data, status=status.HTTP_201_CREATED)

    except OrderCreationError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        # Log unexpected errors
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error creating order: {str(e)}", exc_info=True)

        return Response(
            {'error': 'Erro ao criar pedido. Por favor, tente novamente.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Orders'],
    summary='Cancel order',
    request=None,
    responses={200: OrderSerializer},
    description="Cancel an order and release reserved stock. Only possible in certain states."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_order(request, pk):
    """Cancelar pedido usando service layer"""
    order = get_object_or_404(Order, id=pk, buyer=request.user)

    # Validate order can be cancelled
    if not OrderStateMachine.can_transition(order.status, OrderStateMachine.CANCELED):
        return Response(
            {
                'error': f'Pedido não pode ser cancelado no status atual: {order.get_status_display()}',
                'current_status': order.status,
                'allowed_transitions': OrderStateMachine.get_available_transitions(order.status)
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Cancel order and release stock using service layer
        OrderCreationService.cancel_order_and_release_stock(
            order=order,
            canceled_by=request.user,
            reason='Cancelado pelo comprador'
        )

        # Return updated order
        order_serializer = OrderSerializer(order)
        return Response(order_serializer.data)

    except OrderStatusTransitionError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error canceling order: {str(e)}", exc_info=True)

        return Response(
            {'error': 'Erro ao cancelar pedido. Por favor, tente novamente.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =================== Seller Views ===================
@extend_schema(tags=['Seller Orders'], summary='List seller orders', description='List all orders containing items from the authenticated seller.')
class SellerOrdersView(generics.ListAPIView):
    """Listar vendas do vendedor"""
    serializer_class = OrderListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Retorna pedidos que contém itens deste vendedor
        return Order.objects.filter(
            items__seller=self.request.user
        ).distinct().prefetch_related('items').order_by('-created_at')


@extend_schema(tags=['Seller Orders'], summary='Get seller order details', description='Get detailed information about an order containing the seller\'s items.')
class SellerOrderDetailView(generics.RetrieveAPIView):
    """Detalhes de uma venda"""
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Order.objects.filter(items__seller=self.request.user).distinct()
    
    def get_object(self):
        order_id = self.kwargs.get('pk')
        return get_object_or_404(self.get_queryset(), id=order_id)


@extend_schema(
    tags=['Seller Orders'],
    summary='Update order status',
    request=OrderUpdateStatusSerializer,
    responses={200: OrderSerializer},
    description="Update order status (seller only). Validates state transitions using state machine."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_order_status(request, pk):
    """Atualizar status do pedido (vendedor) usando state machine"""
    serializer = OrderUpdateStatusSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Get order - verify user is seller of this order
    order = get_object_or_404(
        Order,
        id=pk,
        items__seller=request.user
    )

    new_status = serializer.validated_data['status']
    notes = serializer.validated_data.get('notes', '')

    # Validate transition using state machine
    try:
        OrderStateMachine.transition_to(
            order=order,
            new_status=new_status,
            changed_by=request.user,
            notes=notes or f'Status atualizado pelo vendedor',
            is_payment_system=False
        )

        # Return updated order
        order_serializer = OrderSerializer(order)
        return Response(order_serializer.data)

    except OrderStatusTransitionError as e:
        return Response(
            {
                'error': str(e),
                'current_status': order.status,
                'requested_status': new_status,
                'allowed_transitions': OrderStateMachine.get_available_transitions(order.status)
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating order status: {str(e)}", exc_info=True)

        return Response(
            {'error': 'Erro ao atualizar status do pedido.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )