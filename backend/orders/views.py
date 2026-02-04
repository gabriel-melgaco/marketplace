from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from collections import defaultdict
import datetime

from .models import Order, OrderItem, OrderStatusHistory, Cart, CartItem
from .serializers import (
    OrderSerializer, OrderListSerializer, OrderCreateSerializer,
    OrderUpdateStatusSerializer, CartSerializer, CartItemSerializer,
    CartItemCreateSerializer
)
from products.models import MarketplaceListing
from logistics.models import Address, ShippingQuote


# =================== Cart Views ===================
class CartDetailView(generics.RetrieveAPIView):
    """Ver carrinho do usuário"""
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        return cart


@extend_schema(
    request=CartItemCreateSerializer,
    responses={201: CartSerializer},
    description="Adicionar item ao carrinho"
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
    request={'quantity': int},
    responses={200: CartSerializer},
    description="Atualizar quantidade de item no carrinho"
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
    responses={200: CartSerializer},
    description="Remover item do carrinho"
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
    responses={200: CartSerializer},
    description="Limpar carrinho"
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
class OrderListView(generics.ListAPIView):
    """Listar pedidos do usuário comprador"""
    serializer_class = OrderListSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Order.objects.filter(
            buyer=self.request.user
        ).prefetch_related('items').order_by('-created_at')


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
    request=OrderCreateSerializer,
    responses={201: OrderSerializer},
    description="Criar pedido a partir do carrinho"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def create_order(request):
    """
    Criar pedido a partir do carrinho
    
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
    serializer = OrderCreateSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    user = request.user
    cart = get_object_or_404(Cart, user=user)
    
    if not cart.items.exists():
        return Response(
            {'error': 'Carrinho está vazio'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Buscar endereço de entrega
    shipping_address = get_object_or_404(
        Address,
        id=serializer.validated_data['shipping_address_id'],
        user=user,
        is_active=True
    )
    
    # Processar shipping_services (dict com seller_id: service_id)
    shipping_services_input = serializer.validated_data['shipping_services']
    
    # Calcular subtotal do carrinho
    subtotal = cart.get_total()
    
    # Calcular frete total e validar cotações
    total_shipping = 0
    shipping_services_data = {}  # Para salvar no pedido
    shipping_by_seller = {}  # Para distribuir entre itens
    
    for seller_id, service_id in shipping_services_input.items():
        # Buscar cotação mais recente válida do vendedor
        quote = ShippingQuote.objects.filter(
            user=user,
            seller_id=seller_id,
            expires_at__gt=timezone.now()
        ).order_by('-created_at').first()
        
        if not quote:
            return Response(
                {
                    'error': f'Cotação de frete para vendedor {seller_id} expirada ou não encontrada.',
                    'detail': 'Por favor, recalcule o frete antes de finalizar a compra.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Encontrar o serviço escolhido na cotação
        service_found = None
        quotes_list = quote.quotes_data
        
        # quotes_data pode ser list ou dict com 'services'
        if isinstance(quotes_list, dict):
            quotes_list = quotes_list.get('services', [])
        
        for service in quotes_list:
            if isinstance(service, dict) and service.get('id') == service_id:
                service_found = service
                break
        
        if not service_found:
            return Response(
                {
                    'error': f'Serviço de frete {service_id} não encontrado para vendedor {seller_id}.',
                    'detail': 'O serviço pode não estar mais disponível. Recalcule o frete.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extrair custo do frete
        shipping_cost = float(service_found.get('custom_price', service_found.get('price', 0)))
        total_shipping += shipping_cost
        
        # Armazenar dados do serviço
        shipping_services_data[str(seller_id)] = {
            'service_id': service_id,
            'service_name': service_found.get('name', ''),
            'company': service_found.get('company', ''),
            'cost': shipping_cost,
            'delivery_time': service_found.get('delivery_time', 0)
        }
        
        shipping_by_seller[seller_id] = shipping_cost
    
    # Calcular total
    total = float(subtotal) + total_shipping
    
    # Criar pedido
    order = Order.objects.create(
        buyer=user,
        status='pending',
        subtotal=subtotal,
        shipping_cost=total_shipping,
        total=total,
        shipping_address=shipping_address.to_dict(),
        shipping_services=shipping_services_data,  # Salvar serviços escolhidos
        payment_method=serializer.validated_data['payment_method'],
        buyer_notes=serializer.validated_data.get('buyer_notes', '')
    )
    
    # Agrupar itens do carrinho por vendedor
    items_by_seller = defaultdict(list)
    for cart_item in cart.items.select_related('listing__seller', 'listing__product', 'listing__brand', 'listing__condition'):
        seller_id = cart_item.listing.seller.id
        items_by_seller[seller_id].append(cart_item)
    
    # Criar itens do pedido
    for seller_id, cart_items in items_by_seller.items():
        # Pegar frete deste vendedor
        seller_shipping_cost = shipping_by_seller.get(seller_id, 0)
        
        # Buscar endereço do vendedor
        seller = cart_items[0].listing.seller
        seller_address = Address.objects.filter(
            user=seller,
            is_shipping_address=True,
            is_active=True
        ).first()
        
        # Criar item para cada produto do vendedor
        for cart_item in cart_items:
            listing = cart_item.listing
            
            # Verificar estoque
            if listing.quantity < cart_item.quantity:
                transaction.set_rollback(True)
                return Response(
                    {
                        'error': f'Estoque insuficiente para {listing.product.name}',
                        'detail': f'Disponível: {listing.quantity}, Solicitado: {cart_item.quantity}'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Criar item do pedido
            OrderItem.objects.create(
                order=order,
                listing=listing,
                seller=seller,
                product_name=listing.product.name,
                product_code=listing.product.code or '',
                brand_name=listing.brand.name,
                condition_name=listing.condition.name,
                quantity=cart_item.quantity,
                unit_price=listing.price,
                shipping_cost=seller_shipping_cost,  # Frete do vendedor
                weight_kg=listing.weight_kg,
                height_cm=listing.height_cm,
                width_cm=listing.width_cm,
                length_cm=listing.length_cm,
                seller_address=seller_address.to_dict() if seller_address else {}
            )
            
            # Decrementar estoque
            listing.quantity -= cart_item.quantity
            listing.sold_at = datetime.datetime.now()
            listing.save()
    
    # Criar histórico de status
    OrderStatusHistory.objects.create(
        order=order,
        old_status='',
        new_status='pending',
        changed_by=user,
        notes='Pedido criado'
    )
    
    # Limpar carrinho
    cart.items.all().delete()
    
    # Retornar pedido criado
    order_serializer = OrderSerializer(order)
    return Response(order_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    responses={200: OrderSerializer},
    description="Cancelar pedido"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def cancel_order(request, pk):
    """Cancelar pedido"""
    order = get_object_or_404(Order, id=pk, buyer=request.user)
    
    # Apenas pedidos pending ou payment_pending podem ser cancelados
    if order.status not in ['pending', 'payment_pending']:
        return Response(
            {'error': 'Pedido não pode ser cancelado neste status'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    old_status = order.status
    order.status = 'cancelled'
    order.cancelled_at = timezone.now()
    order.save()
    
    # Criar histórico
    OrderStatusHistory.objects.create(
        order=order,
        old_status=old_status,
        new_status='cancelled',
        changed_by=request.user,
        notes='Cancelado pelo comprador'
    )
    
    # Devolver estoque
    for item in order.items.all():
        item.listing.quantity += item.quantity
        item.listing.save()
    
    order_serializer = OrderSerializer(order)
    return Response(order_serializer.data)


# =================== Seller Views ===================
class SellerOrdersView(generics.ListAPIView):
    """Listar vendas do vendedor"""
    serializer_class = OrderListSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Retorna pedidos que contém itens deste vendedor
        return Order.objects.filter(
            items__seller=self.request.user
        ).distinct().prefetch_related('items').order_by('-created_at')


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
    request=OrderUpdateStatusSerializer,
    responses={200: OrderSerializer},
    description="Atualizar status do pedido (vendedor)"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_order_status(request, pk):
    """Atualizar status do pedido (vendedor ou admin)"""
    serializer = OrderUpdateStatusSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Verificar se o usuário é vendedor deste pedido
    order = get_object_or_404(
        Order,
        id=pk,
        items__seller=request.user
    )
    
    old_status = order.status
    new_status = serializer.validated_data['status']
    notes = serializer.validated_data.get('notes', '')
    
    # Validar transição de status
    valid_transitions = {
        'payment_confirmed': ['processing'],
        'processing': ['shipped'],
        'shipped': ['delivered'],
    }
    
    if old_status not in valid_transitions or new_status not in valid_transitions.get(old_status, []):
        return Response(
            {'error': f'Transição de {old_status} para {new_status} não permitida'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    order.status = new_status
    order.save()
    
    # Criar histórico
    OrderStatusHistory.objects.create(
        order=order,
        old_status=old_status,
        new_status=new_status,
        changed_by=request.user,
        notes=notes
    )
    
    order_serializer = OrderSerializer(order)
    return Response(order_serializer.data)