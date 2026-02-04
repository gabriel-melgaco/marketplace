from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError



from .models import ShippingQuote, Shipment, ShipmentTracking, Address
from .serializers import (
    AddressSerializer, AddressCreateSerializer,
    ShippingQuoteRequestSerializer, ShippingQuoteSerializer,
    ShipmentSerializer, ShipmentCreateSerializer,
    CEPLookupSerializer, ShippingQuoteResponseSerializer
)
from .services import MelhorEnvioService
from orders.models import Order, Cart
from products.models import MarketplaceListing


# =================== Address Views ===================
class AddressListView(generics.ListCreateAPIView):
    """
    Listar[GET] e criar[POST] endereços do usuário
    
    Address Types:
    - 'home': Residencial
    - 'work': Comercial
    - 'shipping': Envio (Vendedor)
    - 'other': Outro
    """
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AddressCreateSerializer
        return AddressSerializer
    
    def get_queryset(self):
        return Address.objects.filter(
            user=self.request.user,
            is_active=True
        )
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Detalhes, atualizar e deletar endereço"""
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return AddressSerializer
        return AddressCreateSerializer

    def get_queryset(self):
        return Address.objects.filter(
            user=self.request.user,
            is_active=True
        )
    
    def perform_destroy(self, instance):
        """
        Soft delete - marca como inativo
        Não permite excluir endereço de envio se houver anúncios ativos
        """
        is_shipping_address = instance.is_shipping_address

        has_active_listings = MarketplaceListing.objects.filter(
            seller=self.request.user,
            is_active=True
        ).exists()

        if is_shipping_address and has_active_listings:
            raise ValidationError(
                'Você possui anúncios ativos. '
                'Exclua ou desative os anúncios antes de remover o endereço de envio.'
            )

        instance.is_active = False
        instance.save(update_fields=['is_active'])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_default_address(request, pk):
    """Definir endereço como padrão"""
    address = get_object_or_404(
        Address,
        id=pk,
        user=request.user,
        is_active=True
    )
    
    # Remove padrão dos outros endereços do mesmo tipo
    Address.objects.filter(
        user=request.user,
        address_type=address.address_type,
        is_default=True
    ).exclude(id=pk).update(is_default=False)
    
    # Define este como padrão
    address.is_default = True
    address.save()
    
    serializer = AddressSerializer(address)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_shipping_addresses(request):
    """Listar endereços de envio do vendedor"""
    addresses = Address.objects.filter(
        user=request.user,
        is_shipping_address=True,
        is_active=True
    )

    if not addresses.exists():
        return Response(
            {'message': 'Você não possui endereços de envio cadastrados'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = AddressSerializer(addresses, many=True)
    return Response(serializer.data)


# =================== Shipping Quote Views ===================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def calculate_shipping(request):
    """
    Calcular frete agrupado por vendedor usando endereço salvo
    
    Body:
    {
        "shipping_address_id": 5
    }
    
    Response:
    {
        "quotes_by_seller": {
            "1": {
                "seller_name": "Vendedor X",
                "services": [...],
                "total_value": 100.00
            }
        },
        "shipping_address": {...},
        "total_items": 5,
        "total_value": 250.00
    }
    """
    # Validar shipping_address_id
    shipping_address_id = request.data.get('shipping_address_id')
    
    if not shipping_address_id:
        return Response(
            {'error': 'shipping_address_id é obrigatório'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Buscar endereço do usuário
    shipping_address = get_object_or_404(
        Address,
        id=shipping_address_id,
        user=request.user,
        is_active=True
    )
    
    user = request.user
    
    # Buscar carrinho
    try:
        cart = user.cart
    except Cart.DoesNotExist:
        return Response(
            {'error': 'Carrinho não encontrado'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if not cart.items.exists():
        return Response(
            {'error': 'Carrinho está vazio'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Calcular frete por vendedor usando Melhor Envio
        melhor_envio = MelhorEnvioService()
        quotes_by_seller = melhor_envio.create_shipping_quote_by_seller(
            user=user,
            cart=cart,
            destination_zipcode=shipping_address.zipcode.replace('-', '')
        )
        
        # Calcular totais
        total_items = cart.items.count()
        total_value = cart.get_total()
        
        return Response({
            'quotes_by_seller': quotes_by_seller,
            'shipping_address': AddressSerializer(shipping_address).data,
            'shipping_address_id': shipping_address.id,
            'total_items': total_items,
            'total_value': float(total_value)
        })
        
    except Exception as e:
        return Response(
            {
                'error': 'Erro ao calcular frete',
                'detail': str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_shipping_quotes(request):
    """Listar cotações salvas do usuário (últimas 10)"""
    quotes = ShippingQuote.objects.filter(
        user=request.user
    ).select_related('seller').order_by('-created_at')[:10]
    
    serializer = ShippingQuoteSerializer(quotes, many=True)
    return Response(serializer.data)


# =================== Shipment Views ===================
class ShipmentListView(generics.ListAPIView):
    """
    Listar envios
    
    - Vendedores veem envios que criaram
    - Compradores veem envios de seus pedidos
    """
    serializer_class = ShipmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        return Shipment.objects.filter(
            Q(seller=user) | Q(order__buyer=user)
        ).select_related(
            'order', 'seller'
        ).prefetch_related(
            'tracking_history'
        ).order_by('-created_at')


class ShipmentDetailView(generics.RetrieveAPIView):
    """Detalhes de um envio"""
    serializer_class = ShipmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        return Shipment.objects.filter(
            Q(seller=user) | Q(order__buyer=user)
        ).select_related(
            'order', 'seller'
        ).prefetch_related(
            'tracking_history'
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def create_shipments_for_order(request):
    """
    Criar envios para todos os vendedores de um pedido
    
    Body SIMPLIFICADO (shipping_services vem do pedido):
    {
        "order_id": "uuid-do-pedido"
    }
    
    O shipping_services é pego automaticamente do pedido salvo.
    Caso queira sobrescrever, pode enviar shipping_services no body.
    """
    order_id = request.data.get('order_id')
    
    if not order_id:
        return Response(
            {'error': 'order_id é obrigatório'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Buscar pedido
    order = get_object_or_404(Order, id=order_id)
    
    # Verificar permissão (admin, comprador ou vendedor do pedido)
    user = request.user
    if not user.is_staff and user != order.buyer:
        if not order.items.filter(seller=user).exists():
            return Response(
                {'error': 'Sem permissão para criar envios deste pedido'},
                status=status.HTTP_403_FORBIDDEN
            )
    
    # Verificar se pagamento foi confirmado
    if order.status != 'payment_confirmed':
        return Response(
            {'error': 'Pedido precisa ter pagamento confirmado'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # CORRIGIDO: Pegar shipping_services do pedido (salvo no checkout)
    # Permite sobrescrever se enviar no body
    shipping_services = request.data.get('shipping_services', order.shipping_services)
    
    if not shipping_services:
        return Response(
            {
                'error': 'shipping_services não encontrado',
                'detail': 'O pedido não possui informações de frete salvas. '
                         'Isso pode ocorrer se o pedido foi criado antes da atualização do sistema.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Agrupar itens por vendedor
    sellers = order.items.values_list('seller', flat=True).distinct()
    
    created_shipments = []
    errors = []
    melhor_envio = MelhorEnvioService()
    
    for seller_id in sellers:
        seller_items = order.items.filter(seller_id=seller_id)
        seller = seller_items.first().seller
        
        # Verificar se já existe envio para este vendedor
        existing = Shipment.objects.filter(order=order, seller=seller).first()
        if existing:
            created_shipments.append(existing)
            continue
        
        # Pegar serviço de frete escolhido do shipping_services salvo
        seller_shipping = shipping_services.get(str(seller_id))
        
        if not seller_shipping:
            errors.append({
                'seller_id': seller_id,
                'seller_name': seller.get_full_name() or seller.email,
                'error': f'Serviço de frete não encontrado para vendedor {seller_id}'
            })
            continue
        
        # Extrair service_id (pode ser int ou dict)
        if isinstance(seller_shipping, dict):
            service_id = seller_shipping.get('service_id')
        else:
            service_id = seller_shipping
        
        if not service_id:
            errors.append({
                'seller_id': seller_id,
                'seller_name': seller.get_full_name() or seller.email,
                'error': f'service_id não encontrado para vendedor {seller_id}'
            })
            continue
        
        try:
            # Criar envio via Melhor Envio
            shipment = melhor_envio.create_shipment(
                order=order,
                seller=seller,
                shipping_service_id=service_id
            )
            created_shipments.append(shipment)
            
        except Exception as e:
            errors.append({
                'seller_id': seller_id,
                'seller_name': seller.get_full_name() or seller.email,
                'error': str(e)
            })
    
    # Atualizar status do pedido se criou algum envio
    if created_shipments and not errors:
        order.status = 'processing'
        order.save()
    
    serializer = ShipmentSerializer(created_shipments, many=True)
    
    response_data = {
        'shipments': serializer.data,
        'created_count': len(created_shipments),
        'errors': errors,
        'order_status': order.status
    }
    
    response_status = status.HTTP_201_CREATED if created_shipments else status.HTTP_400_BAD_REQUEST
    return Response(response_data, status=response_status)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_shipping_label(request, pk):
    """
    Gerar etiqueta de envio
    
    Apenas o vendedor pode gerar a etiqueta do seu envio
    """
    shipment = get_object_or_404(
        Shipment, 
        id=pk, 
        seller=request.user
    )
    
    # Verificar se etiqueta já foi gerada
    if shipment.label_url:
        return Response({
            'message': 'Etiqueta já foi gerada anteriormente',
            'label_url': shipment.label_url,
            'shipment_id': shipment.id
        })
    
    try:
        melhor_envio = MelhorEnvioService()
        label_url = melhor_envio.generate_label(shipment)
        
        return Response({
            'label_url': label_url,
            'shipment_id': shipment.id,
            'message': 'Etiqueta gerada com sucesso'
        })
        
    except Exception as e:
        return Response(
            {
                'error': 'Erro ao gerar etiqueta',
                'detail': str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def track_shipment(request, pk):
    """
    Atualizar rastreamento do envio
    
    Vendedor, comprador ou admin podem rastrear
    """
    # Buscar envio
    shipment = get_object_or_404(Shipment, id=pk)
    
    # Verificar permissão
    user = request.user
    if user != shipment.seller and user != shipment.order.buyer and not user.is_staff:
        return Response(
            {'error': 'Sem permissão para rastrear este envio'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        melhor_envio = MelhorEnvioService()
        tracking_data = melhor_envio.track_shipment(shipment)
        
        # Recarregar shipment para pegar dados atualizados
        shipment.refresh_from_db()
        serializer = ShipmentSerializer(shipment)
        
        return Response({
            'shipment': serializer.data,
            'tracking_data': tracking_data,
            'message': 'Rastreamento atualizado'
        })
        
    except Exception as e:
        return Response(
            {
                'error': 'Erro ao rastrear envio',
                'detail': str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_order_shipments(request, order_id):
    """
    Listar todos os envios de um pedido
    
    Útil para pedidos com múltiplos vendedores
    """
    order = get_object_or_404(Order, id=order_id)
    
    # Verificar permissão
    user = request.user
    if user != order.buyer and not order.items.filter(seller=user).exists() and not user.is_staff:
        return Response(
            {'error': 'Sem permissão para ver envios deste pedido'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    shipments = Shipment.objects.filter(
        order=order
    ).select_related(
        'seller'
    ).prefetch_related(
        'tracking_history'
    )
    
    serializer = ShipmentSerializer(shipments, many=True)
    
    return Response({
        'order_id': str(order.id),
        'order_number': order.order_number,
        'shipments': serializer.data,
        'shipments_count': shipments.count()
    })


# =================== Utility Views ===================
@api_view(['POST'])
@permission_classes([AllowAny])
def lookup_zipcode(request):
    """
    Buscar informações de um CEP via ViaCEP
    
    Body:
    {
        "zipcode": "01310100"
    }
    
    Response:
    {
        "zipcode": "01310-100",
        "street": "Avenida Paulista",
        "neighborhood": "Bela Vista",
        "city": "São Paulo",
        "state": "SP"
    }
    """
    serializer = CEPLookupSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(
            serializer.errors, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    zipcode = serializer.validated_data['zipcode']
    
    try:
        melhor_envio = MelhorEnvioService()
        address_data = melhor_envio.lookup_zipcode(zipcode)
        return Response(address_data)
        
    except Exception as e:
        return Response(
            {
                'error': 'Erro ao buscar CEP',
                'detail': str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )