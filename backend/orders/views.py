from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter, OpenApiResponse
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
    request=OrderCreateSerializer,
    responses={201: OrderSerializer},
    description="Create an order from the cart. Validates stock and reserves items."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_order(request):
    """
    Criar pedido a partir do carrinho usando service layer.

    Payload esperado:
    {
        "shipping_address_id": 5,
        "shipping_services": {
            "1": 2,  // seller_id: service_id (da cotação)
            "3": 1
        },
        "payment_method": "credit_card",
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