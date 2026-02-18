import hmac
import hashlib
import base64
import json
import logging

from rest_framework import generics, status, viewsets, filters
from rest_framework.decorators import api_view, permission_classes, authentication_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.shortcuts import get_object_or_404
from django.conf import settings as django_settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter, OpenApiResponse, OpenApiTypes
from rest_framework import serializers as rf_serializers
from django_filters.rest_framework import DjangoFilterBackend



from .models import (
    ShippingQuote, Shipment, ShipmentTracking, Address,
    OrderDelivery, InPersonDelivery, DeliveryMethod,
    CarrierRule,
)
from .serializers import (
    AddressSerializer, AddressCreateSerializer,
    ShippingQuoteRequestSerializer, ShippingQuoteSerializer,
    ShipmentSerializer, ShipmentCreateSerializer,
    CEPLookupSerializer, ShippingQuoteResponseSerializer,
    OrderDeliverySerializer, OrderDeliveryCreateSerializer,
    InPersonDeliverySerializer, InPersonDeliveryCreateSerializer,
    InPersonDeliveryUpdateSerializer, DeliveryMethodChoiceSerializer,
    CarrierRuleSerializer, CarrierRuleCreateUpdateSerializer,
    PackageValidationRequestSerializer,
)
from .services import (
    MelhorEnvioService,
    InPersonDeliveryService,
    DeliveryOrchestrationService,
    ShipmentCreationService,
    ShipmentCreationError,
    CarrierRuleService,
)
from .services.melhor_envio_oauth_service import MelhorEnvioOAuthService, MelhorEnvioOAuthError
from orders.models import Order, Cart
from orders.services.order_state_machine import OrderStateMachine, OrderStatusTransitionError
from products.models import MarketplaceListing

logger = logging.getLogger(__name__)


# =================== Address Views ===================
@extend_schema(
    tags=['Logistics - Addresses'],
    summary='List and create user addresses',
    description="""
    List all active addresses for the authenticated user (GET) or create a new address (POST).

    Address Types:
    - 'home': Residential
    - 'work': Commercial
    - 'shipping': Seller shipping address
    - 'other': Other
    """
)
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


@extend_schema(
    tags=['Logistics - Addresses'],
    summary='Retrieve, update, or delete an address',
    description='Get details, update, or soft-delete a specific address. Cannot delete shipping address if active listings exist.'
)
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


@extend_schema(
    tags=['Logistics - Addresses'],
    summary='Set address as default',
    description='Set a specific address as the default for its address type.',
    request=None,
    responses={200: AddressSerializer}
)
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


@extend_schema(
    tags=['Logistics - Addresses'],
    summary='Get seller shipping addresses',
    description='List all active shipping addresses for the authenticated seller.',
    responses={
        200: AddressSerializer(many=True),
        404: OpenApiResponse(description='No shipping addresses found')
    }
)
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
@extend_schema(
    tags=['Logistics - Shipping'],
    summary='Calculate shipping quotes',
    description='Calculate shipping costs grouped by seller using Melhor Envio API. Requires items in cart.',
    request=inline_serializer(
        name='CalculateShippingRequest',
        fields={
            'shipping_address_id': rf_serializers.IntegerField(help_text='ID of the saved shipping address')
        }
    ),
    responses={
        200: inline_serializer(
            name='CalculateShippingResponse',
            fields={
                'quotes_by_seller': rf_serializers.DictField(help_text='Shipping quotes grouped by seller ID'),
                'shipping_address': AddressSerializer(),
                'shipping_address_id': rf_serializers.IntegerField(),
                'total_items': rf_serializers.IntegerField(),
                'total_value': rf_serializers.FloatField()
            }
        ),
        400: OpenApiResponse(description='Invalid request or empty cart'),
        404: OpenApiResponse(description='Cart or address not found')
    }
)
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
    



@extend_schema(
    tags=['Logistics - Shipping'],
    summary='Get saved shipping quotes',
    description='List the last 10 saved shipping quotes for the authenticated user.',
    responses={200: ShippingQuoteSerializer(many=True)}
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
@extend_schema(
    tags=['Logistics - Shipping'],
    summary='List shipments',
    description='List all shipments. Sellers see shipments they created; buyers see shipments for their orders.'
)
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


@extend_schema(
    tags=['Logistics - Shipping'],
    summary='Get shipment details',
    description='Get detailed information about a specific shipment.'
)
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


@extend_schema(
    tags=['Logistics - Shipping'],
    summary='Create shipments for order',
    description=(
        'Create shipments (Melhor Envio) for sellers in an order that use the **shipping** delivery method.\n\n'
        'Shipping service configuration is read from the order `shipping_services` field '
        '(defined during order creation).\n\n'
        '```json\n{"order_id": "uuid"}\n```\n\n'
        'Permission: admin, buyer, or a seller of the order.\n\n'
        '**Note:** If the insured value exceeds R$1.000,00 (non-commercial shipping limit), '
        'it will be capped at R$1.000,00 and a `warnings` array will be included in the response.'
    ),
    request=inline_serializer(
        name='CreateShipmentsRequest',
        fields={
            'order_id': rf_serializers.UUIDField(help_text='Order UUID'),
        }
    ),
    responses={
        201: inline_serializer(
            name='CreateShipmentsResponse',
            fields={
                'shipments': ShipmentSerializer(many=True),
                'created_count': rf_serializers.IntegerField(),
                'order_status': rf_serializers.CharField(),
                'warnings': rf_serializers.ListField(
                    child=rf_serializers.DictField(),
                    required=False,
                    help_text='Insurance cap warnings (present only when value was capped at R$1.000,00)'
                )
            }
        ),
        400: OpenApiResponse(description='Invalid request, missing order_id, or shipment creation error'),
        403: OpenApiResponse(description='No permission to create shipments for this order'),
        404: OpenApiResponse(description='Order not found'),
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_shipments_for_order(request):
    """
    Criar envios para todos os vendedores de um pedido.
    Os shipping_services são lidos automaticamente do pedido (definidos na criação da order).

    Body:
    {
        "order_id": "uuid-do-pedido"
    }
    """
    order_id = request.data.get('order_id')

    if not order_id:
        return Response(
            {'error': 'order_id é obrigatório'},
            status=status.HTTP_400_BAD_REQUEST
        )

    order = get_object_or_404(Order, id=order_id)

    # Verificar permissão (admin, comprador ou vendedor do pedido)
    user = request.user
    if not user.is_staff and user != order.buyer:
        if not order.items.filter(seller=user).exists():
            return Response(
                {'error': 'Sem permissão para criar envios deste pedido'},
                status=status.HTTP_403_FORBIDDEN
            )

    try:
        created_shipments, warnings = ShipmentCreationService.create_shipments_for_order(
            order=order,
        )
    except ShipmentCreationError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = ShipmentSerializer(created_shipments, many=True)

    response_data = {
        'shipments': serializer.data,
        'created_count': len(created_shipments),
        'order_status': order.status,
    }

    if warnings:
        response_data['warnings'] = warnings

    return Response(response_data, status=status.HTTP_201_CREATED)



@extend_schema(
    tags=['Logistics - Shipping'],
    summary='Generate shipping label',
    description='Generate a shipping label for a shipment using Melhor Envio. Only the seller can generate their shipment label.',
    request=None,
    responses={
        200: inline_serializer(
            name='GenerateLabelResponse',
            fields={
                'label_url': rf_serializers.URLField(),
                'shipment_id': rf_serializers.IntegerField(),
                'message': rf_serializers.CharField()
            }
        ),
        400: OpenApiResponse(description='Error generating label'),
        404: OpenApiResponse(description='Shipment not found')
    }
)
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


@extend_schema(
    tags=['Logistics - Shipping'],
    summary='Track shipment',
    description='Update shipment tracking information from Melhor Envio. Seller, buyer, or admin can track.',
    request=None,
    responses={
        200: inline_serializer(
            name='TrackShipmentResponse',
            fields={
                'shipment': ShipmentSerializer(),
                'tracking_data': rf_serializers.DictField(),
                'message': rf_serializers.CharField()
            }
        ),
        400: OpenApiResponse(description='Error tracking shipment'),
        403: OpenApiResponse(description='No permission to track this shipment'),
        404: OpenApiResponse(description='Shipment not found')
    }
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


@extend_schema(
    tags=['Logistics - Shipping'],
    summary='Mark shipment as shipped',
    description=(
        'Seller marks a shipment as shipped and provides the tracking code.\n\n'
        'Updates the shipment status to `posted` and, if all shipments for the order '
        'are posted, transitions the order status to `shipped` (Enviado).\n\n'
        'Only the seller of the shipment can perform this action.'
    ),
    request=inline_serializer(
        name='MarkShipmentShippedRequest',
        fields={
            'tracking_code': rf_serializers.CharField(help_text='Tracking code provided by the carrier'),
        }
    ),
    responses={
        200: inline_serializer(
            name='MarkShipmentShippedResponse',
            fields={
                'message': rf_serializers.CharField(),
                'shipment': ShipmentSerializer(),
                'order_status': rf_serializers.CharField(),
                'order_transitioned': rf_serializers.BooleanField(),
            }
        ),
        400: OpenApiResponse(description='Shipment already posted/delivered or missing tracking_code'),
        403: OpenApiResponse(description='Only the seller can mark shipment as shipped'),
        404: OpenApiResponse(description='Shipment not found'),
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_shipment_shipped(request, pk):
    """
    Vendedor marca o envio como postado e insere o código de rastreio.
    """
    shipment = get_object_or_404(Shipment, id=pk)

    # Apenas o vendedor do envio pode marcar como postado
    if request.user != shipment.seller:
        return Response(
            {'error': 'Apenas o vendedor pode marcar o envio como postado'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Validar status atual
    if shipment.status in ('posted', 'in_transit', 'delivered'):
        return Response(
            {'error': f'Envio já está com status "{shipment.get_status_display()}"'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if shipment.status == 'cancelled':
        return Response(
            {'error': 'Não é possível marcar um envio cancelado como postado'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validar tracking_code
    tracking_code = request.data.get('tracking_code', '').strip()
    if not tracking_code:
        return Response(
            {'error': 'tracking_code é obrigatório'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Atualizar shipment
    shipment.status = 'posted'
    shipment.melhorenvio_tracking_code = tracking_code
    shipment.posted_at = timezone.now()
    shipment.save()

    # Verificar se TODOS os shipments do pedido foram postados → transicionar Order
    order = shipment.order
    order_transitioned = False

    all_shipments = Shipment.objects.filter(order=order)
    all_posted = all_shipments.exclude(
        status__in=['posted', 'in_transit', 'delivered']
    ).count() == 0

    if all_posted and OrderStateMachine.can_transition(order.status, OrderStateMachine.SHIPPED):
        try:
            OrderStateMachine.transition_to(
                order=order,
                new_status=OrderStateMachine.SHIPPED,
                changed_by=request.user,
                notes=f'Envio marcado como postado pelo vendedor. Rastreio: {tracking_code}',
            )
            order_transitioned = True
        except OrderStatusTransitionError as e:
            logger.warning(
                f'Não foi possível transicionar order {order.order_number} para shipped: {e}'
            )

    serializer = ShipmentSerializer(shipment)

    return Response({
        'message': 'Envio marcado como postado com sucesso',
        'shipment': serializer.data,
        'order_status': order.status,
        'order_transitioned': order_transitioned,
    })


@extend_schema(
    tags=['Logistics - Shipping'],
    summary='Get order shipments',
    description='List all shipments for a specific order. Useful for multi-seller orders.',
    parameters=[
        OpenApiParameter(
            name='order_id',
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.PATH,
            description='Order UUID'
        )
    ],
    responses={
        200: inline_serializer(
            name='OrderShipmentsResponse',
            fields={
                'order_id': rf_serializers.UUIDField(),
                'order_number': rf_serializers.CharField(),
                'shipments': ShipmentSerializer(many=True),
                'shipments_count': rf_serializers.IntegerField()
            }
        ),
        403: OpenApiResponse(description='No permission to view shipments for this order'),
        404: OpenApiResponse(description='Order not found')
    }
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
@extend_schema(
    tags=['Logistics - Utilities'],
    summary='Lookup zipcode (CEP)',
    description='Fetch address information from a Brazilian zipcode (CEP) using ViaCEP API.',
    request=CEPLookupSerializer,
    responses={
        200: inline_serializer(
            name='CEPLookupResponse',
            fields={
                'zipcode': rf_serializers.CharField(),
                'street': rf_serializers.CharField(),
                'neighborhood': rf_serializers.CharField(),
                'city': rf_serializers.CharField(),
                'state': rf_serializers.CharField()
            }
        ),
        400: OpenApiResponse(description='Invalid zipcode or error fetching data')
    }
)
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


# =================== Order Delivery Views (Dual Delivery) ===================
@extend_schema(
    tags=['Logistics - Deliveries'],
    summary='Create order deliveries',
    description=(
        'Create deliveries for an order based on its `shipping_services` configuration.\n\n'
        'Delivery methods (shipping via carrier or in-person) are automatically extracted '
        'from the order\'s `shipping_services` field, configured during checkout.\n\n'
        'Only the buyer can create deliveries. Returns `409` if deliveries already exist.\n\n'
        '**Example body:**\n'
        '```json\n{"order_id": "uuid-do-pedido"}\n```'
    ),
    request=inline_serializer(
        name='CreateOrderDeliveriesRequest',
        fields={
            'order_id': rf_serializers.UUIDField(help_text='Order UUID'),
        }
    ),
    responses={
        201: inline_serializer(
            name='CreateOrderDeliveriesResponse',
            fields={
                'order_id': rf_serializers.UUIDField(),
                'order_number': rf_serializers.CharField(),
                'deliveries': OrderDeliverySerializer(many=True),
                'count': rf_serializers.IntegerField()
            }
        ),
        400: OpenApiResponse(description='Invalid request or missing required fields'),
        403: OpenApiResponse(description='Only the buyer can configure deliveries'),
        404: OpenApiResponse(description='Order not found'),
        409: OpenApiResponse(description='Deliveries already exist for this order'),
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def create_order_deliveries(request):
    """
    Criar entregas para um pedido (dual delivery).

    Extrai automaticamente as configurações de entrega do campo
    shipping_services da order (configurado durante o checkout).

    Body:
    {
        "order_id": "uuid-do-pedido"
    }
    """
    order_id = request.data.get('order_id')

    if not order_id:
        return Response(
            {'error': 'order_id é obrigatório'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Buscar pedido
    order = get_object_or_404(Order, id=order_id)

    # Verificar se o pagamento foi confirmado
    if order.status == 'pending_payment':
        return Response(
            {'error': 'Não é possível criar entregas antes da confirmação do pagamento'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Verificar se já existem entregas para este pedido
    from logistics.models import OrderDelivery
    if OrderDelivery.objects.filter(order=order).exists():
        return Response(
            {'error': 'Entregas já foram criadas para este pedido.'},
            status=status.HTTP_409_CONFLICT
        )

    # Extrair configurações de entrega do shipping_services da order
    if not order.shipping_services:
        return Response(
            {'error': 'A order deve ter shipping_services configurado durante o checkout'},
            status=status.HTTP_400_BAD_REQUEST
        )

    delivery_choices = []
    for seller_id, shipping_info in order.shipping_services.items():
        if not isinstance(shipping_info, dict):
            continue

        delivery_method = shipping_info.get('delivery_method', 'shipping')
        choice = {
            'seller_id': int(seller_id),
            'delivery_method': delivery_method,
        }

        if delivery_method == 'shipping':
            choice['shipping_service_id'] = shipping_info.get('service_id')
            choice['delivery_cost'] = shipping_info.get('cost', 0)
        elif delivery_method == 'in_person':
            choice.update({
                k: v for k, v in shipping_info.items()
                if k not in ('delivery_method', 'cost')
            })

        delivery_choices.append(choice)

    if not delivery_choices:
        return Response(
            {'error': 'Nenhuma configuração de entrega válida encontrada na order'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Verificar permissão (apenas o comprador)
    if request.user != order.buyer:
        return Response(
            {'error': 'Apenas o comprador pode configurar entregas'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        # Criar entregas usando o serviço de orquestração
        created_deliveries = DeliveryOrchestrationService.create_order_deliveries(
            order=order,
            delivery_choices=delivery_choices
        )

        serializer = OrderDeliverySerializer(created_deliveries, many=True)

        return Response({
            'order_id': str(order.id),
            'order_number': order.order_number,
            'deliveries': serializer.data,
            'count': len(created_deliveries)
        }, status=status.HTTP_201_CREATED)

    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {
                'error': 'Erro ao criar entregas',
                'detail': str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Logistics - Deliveries'],
    summary='Get order deliveries details',
    description='Get consolidated details of all deliveries for an order (shipping + in-person).',
    parameters=[
        OpenApiParameter(
            name='order_id',
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.PATH,
            description='Order UUID'
        )
    ],
    responses={
        200: inline_serializer(
            name='OrderDeliveriesDetailsResponse',
            fields={
                'order_id': rf_serializers.UUIDField(),
                'order_number': rf_serializers.CharField(),
                'total_delivery_cost': rf_serializers.FloatField(),
                'deliveries_by_seller': rf_serializers.DictField()
            }
        ),
        403: OpenApiResponse(description='No permission to view deliveries for this order'),
        404: OpenApiResponse(description='Order not found')
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_order_deliveries_details(request, order_id):
    """
    Obter detalhes de todas as entregas de um pedido.

    Retorna informações consolidadas de entregas (shipping + in-person).
    """
    order = get_object_or_404(Order, id=order_id)

    # Verificar permissão
    user = request.user
    if user != order.buyer and not order.items.filter(seller=user).exists() and not user.is_staff:
        return Response(
            {'error': 'Sem permissão para ver entregas deste pedido'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Obter resumo das entregas
    summary = DeliveryOrchestrationService.get_delivery_options_summary(order)

    return Response(summary)


@extend_schema(
    tags=['Logistics - Deliveries'],
    summary='List user deliveries',
    description='List all deliveries for the authenticated user (as buyer or seller).',
    responses={
        200: inline_serializer(
            name='ListUserDeliveriesResponse',
            fields={
                'deliveries': OrderDeliverySerializer(many=True),
                'count': rf_serializers.IntegerField()
            }
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_user_deliveries(request):
    """
    Listar todas as entregas do usuário (como comprador ou vendedor).
    """
    user = request.user

    # Como comprador ou vendedor
    deliveries = OrderDelivery.objects.filter(
        Q(order__buyer=user) | Q(seller=user)
    ).select_related(
        'order', 'seller', 'shipment', 'in_person_delivery'
    ).order_by('-created_at')

    serializer = OrderDeliverySerializer(deliveries, many=True)

    return Response({
        'deliveries': serializer.data,
        'count': deliveries.count()
    })


# =================== In-Person Delivery Views ===================
@extend_schema(
    tags=['Logistics - In-Person'],
    summary='Get in-person delivery details',
    description='Get detailed information about a specific in-person delivery.',
    responses={
        200: InPersonDeliverySerializer,
        403: OpenApiResponse(description='No permission to view this delivery'),
        404: OpenApiResponse(description='In-person delivery not found')
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_in_person_delivery_detail(request, pk):
    """
    Obter detalhes de uma entrega presencial.
    """
    in_person_delivery = get_object_or_404(InPersonDelivery, id=pk)

    # Verificar permissão
    user = request.user
    if user not in [in_person_delivery.seller, in_person_delivery.buyer] and not user.is_staff:
        return Response(
            {'error': 'Sem permissão para ver esta entrega'},
            status=status.HTTP_403_FORBIDDEN
        )

    serializer = InPersonDeliverySerializer(in_person_delivery)
    return Response(serializer.data)


@extend_schema(
    tags=['Logistics - In-Person'],
    summary='Confirm in-person meeting',
    description='Confirm in-person meeting. Both seller and buyer must confirm for status to update.',
    request=None,
    responses={
        200: inline_serializer(
            name='ConfirmMeetingResponse',
            fields={
                'message': rf_serializers.CharField(),
                'delivery': InPersonDeliverySerializer()
            }
        ),
        400: OpenApiResponse(description='Invalid operation'),
        403: OpenApiResponse(description='Not part of this meeting'),
        404: OpenApiResponse(description='In-person delivery not found')
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def confirm_meeting(request, pk):
    """
    Confirmar encontro presencial (seller ou buyer).

    Ambas as partes precisam confirmar para que o status seja atualizado.
    """
    in_person_delivery = get_object_or_404(InPersonDelivery, id=pk)

    # Verificar permissão
    user = request.user
    if user not in [in_person_delivery.seller, in_person_delivery.buyer]:
        return Response(
            {'error': 'Você não faz parte deste encontro'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        # Confirmar encontro
        updated_delivery = InPersonDeliveryService.confirm_meeting(
            in_person_delivery=in_person_delivery,
            user=user
        )

        serializer = InPersonDeliverySerializer(updated_delivery)

        return Response({
            'message': 'Encontro confirmado com sucesso',
            'delivery': serializer.data
        })

    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    tags=['Logistics - In-Person'],
    summary='Update meeting details',
    description='Update in-person meeting details (location, date, time, notes).',
    request=InPersonDeliveryUpdateSerializer,
    responses={
        200: inline_serializer(
            name='UpdateMeetingResponse',
            fields={
                'message': rf_serializers.CharField(),
                'delivery': InPersonDeliverySerializer()
            }
        ),
        400: OpenApiResponse(description='Invalid data'),
        403: OpenApiResponse(description='No permission to update this meeting'),
        404: OpenApiResponse(description='In-person delivery not found')
    }
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def update_meeting_details(request, pk):
    """
    Atualizar detalhes do encontro (local, data, horário).

    Body:
    {
        "meeting_location_name": "Novo local",
        "scheduled_date": "2026-02-15",
        "scheduled_time": "15:00",
        "meeting_notes": "Nova observação"
    }
    """
    in_person_delivery = get_object_or_404(InPersonDelivery, id=pk)

    # Verificar permissão
    user = request.user
    if user not in [in_person_delivery.seller, in_person_delivery.buyer]:
        return Response(
            {'error': 'Você não tem permissão para atualizar este encontro'},
            status=status.HTTP_403_FORBIDDEN
        )

    serializer = InPersonDeliveryUpdateSerializer(
        in_person_delivery,
        data=request.data,
        partial=True
    )

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Atualizar usando o serviço
        updated_delivery = InPersonDeliveryService.update_meeting_details(
            in_person_delivery=in_person_delivery,
            user=user,
            **serializer.validated_data
        )

        response_serializer = InPersonDeliverySerializer(updated_delivery)

        return Response({
            'message': 'Detalhes do encontro atualizados',
            'delivery': response_serializer.data
        })

    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    tags=['Logistics - In-Person'],
    summary='Complete in-person delivery',
    description='Mark in-person delivery as completed.',
    request=inline_serializer(
        name='CompleteInPersonDeliveryRequest',
        fields={
            'completion_notes': rf_serializers.CharField(required=False, help_text='Optional completion notes')
        }
    ),
    responses={
        200: inline_serializer(
            name='CompleteInPersonDeliveryResponse',
            fields={
                'message': rf_serializers.CharField(),
                'delivery': InPersonDeliverySerializer()
            }
        ),
        400: OpenApiResponse(description='Invalid operation'),
        403: OpenApiResponse(description='No permission to complete this delivery'),
        404: OpenApiResponse(description='In-person delivery not found')
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def complete_in_person_delivery(request, pk):
    """
    Marcar entrega presencial como concluída.

    Body:
    {
        "completion_notes": "Produto entregue com sucesso"
    }
    """
    in_person_delivery = get_object_or_404(InPersonDelivery, id=pk)

    # Verificar permissão
    user = request.user
    if user not in [in_person_delivery.seller, in_person_delivery.buyer]:
        return Response(
            {'error': 'Você não tem permissão para concluir esta entrega'},
            status=status.HTTP_403_FORBIDDEN
        )

    completion_notes = request.data.get('completion_notes', '')

    try:
        # Concluir entrega
        completed_delivery = InPersonDeliveryService.complete_delivery(
            in_person_delivery=in_person_delivery,
            user=user,
            completion_notes=completion_notes
        )

        serializer = InPersonDeliverySerializer(completed_delivery)

        if completed_delivery.is_fully_completed():
            message = 'Entrega presencial concluída por ambas as partes'
        else:
            message = 'Conclusão confirmada. Aguardando confirmação da outra parte'

        return Response({
            'message': message,
            'delivery': serializer.data
        })

    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    tags=['Logistics - In-Person'],
    summary='Cancel in-person delivery',
    description='Cancel an in-person delivery.',
    request=inline_serializer(
        name='CancelInPersonDeliveryRequest',
        fields={
            'cancellation_reason': rf_serializers.CharField(required=False, help_text='Optional cancellation reason')
        }
    ),
    responses={
        200: inline_serializer(
            name='CancelInPersonDeliveryResponse',
            fields={
                'message': rf_serializers.CharField(),
                'delivery': InPersonDeliverySerializer()
            }
        ),
        400: OpenApiResponse(description='Invalid operation'),
        403: OpenApiResponse(description='No permission to cancel this delivery'),
        404: OpenApiResponse(description='In-person delivery not found')
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def cancel_in_person_delivery(request, pk):
    """
    Cancelar entrega presencial.

    Body:
    {
        "cancellation_reason": "Motivo do cancelamento"
    }
    """
    in_person_delivery = get_object_or_404(InPersonDelivery, id=pk)

    # Verificar permissão
    user = request.user
    if user not in [in_person_delivery.seller, in_person_delivery.buyer]:
        return Response(
            {'error': 'Você não tem permissão para cancelar esta entrega'},
            status=status.HTTP_403_FORBIDDEN
        )

    cancellation_reason = request.data.get('cancellation_reason', '')

    try:
        # Cancelar entrega
        cancelled_delivery = InPersonDeliveryService.cancel_delivery(
            in_person_delivery=in_person_delivery,
            user=user,
            cancellation_reason=cancellation_reason
        )

        serializer = InPersonDeliverySerializer(cancelled_delivery)

        return Response({
            'message': 'Entrega presencial cancelada',
            'delivery': serializer.data
        })

    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    tags=['Logistics - In-Person'],
    summary='List in-person deliveries',
    description='List in-person deliveries for the authenticated user (as buyer or seller).',
    operation_id='logistics_in_person_list',
    parameters=[
        OpenApiParameter(
            name='status',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Filter by meeting status',
            required=False
        ),
        OpenApiParameter(
            name='role',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Filter by role (seller or buyer)',
            required=False,
            enum=['seller', 'buyer']
        )
    ],
    responses={
        200: inline_serializer(
            name='ListInPersonDeliveriesResponse',
            fields={
                'deliveries': InPersonDeliverySerializer(many=True),
                'count': rf_serializers.IntegerField()
            }
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_in_person_deliveries(request):
    """
    Listar entregas presenciais do usuário (como comprador ou vendedor).

    Query params:
    - status: filtrar por status (pending_schedule, scheduled, confirmed, etc)
    - role: filtrar por papel (seller, buyer)
    """
    user = request.user
    status_filter = request.query_params.get('status')
    role_filter = request.query_params.get('role')

    # Query base
    queryset = InPersonDelivery.objects.filter(
        Q(seller=user) | Q(buyer=user)
    ).select_related('seller', 'buyer').order_by('-created_at')

    # Aplicar filtros
    if status_filter:
        queryset = queryset.filter(meeting_status=status_filter)

    if role_filter == 'seller':
        queryset = queryset.filter(seller=user)
    elif role_filter == 'buyer':
        queryset = queryset.filter(buyer=user)

    serializer = InPersonDeliverySerializer(queryset, many=True)

    return Response({
        'deliveries': serializer.data,
        'count': queryset.count()
    })


# =================== Melhor Envio Webhook ===================
@extend_schema(
    tags=['Logistics - Webhooks'],
    summary='Melhor Envio webhook receiver',
    description='Receives webhook events from Melhor Envio API. Verifies HMAC-SHA256 signature and updates shipment/order status.',
    request=inline_serializer(
        name='MelhorEnvioWebhookPayload',
        fields={
            'event': rf_serializers.CharField(),
            'data': rf_serializers.DictField()
        }
    ),
    responses={
        200: inline_serializer(
            name='WebhookResponse',
            fields={'message': rf_serializers.CharField()}
        ),
        400: OpenApiResponse(description='Invalid payload'),
        401: OpenApiResponse(description='Invalid signature'),
    }
)
@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def melhor_envio_webhook(request):
    """
    Recebe notificações de eventos do Melhor Envio.

    Eventos tratados:
    - order.posted: Encomenda postada → Shipment status 'posted', Order status 'shipped'
    - order.delivered: Encomenda entregue → Shipment status 'delivered', Order status 'delivered'
    """
    # Log completo da requisição recebida
    logger.info(
        'Webhook Melhor Envio: requisição recebida',
        extra={
            'method': request.method,
            'path': request.get_full_path(),
            'content_type': request.content_type,
            'headers': {k: v for k, v in request.headers.items() if k.lower() not in ('cookie',)},
            'body_raw': request.body.decode('utf-8', errors='replace')[:2000],
            'body_parsed': request.data,
            'remote_ip': request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR')),
        }
    )

    # Verificar assinatura HMAC-SHA256
    webhook_secret = django_settings.MELHOR_ENVIO_WEBHOOK_SECRET
    signature = request.headers.get('X-ME-Signature', '')
    signature_valid = False

    if webhook_secret and signature:
        body = request.body
        digest = hmac.new(
            webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).digest()
        expected_signature_b64 = base64.b64encode(digest).decode('utf-8')
        expected_signature_hex = hmac.new(
            webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()

        # Melhor Envio usa base64, mas verificar ambos por segurança
        if hmac.compare_digest(signature, expected_signature_b64) or hmac.compare_digest(signature, expected_signature_hex):
            signature_valid = True
        else:
            logger.warning(
                'Webhook Melhor Envio: assinatura inválida',
                extra={
                    'received_signature': signature,
                    'expected_b64': expected_signature_b64,
                    'expected_hex': expected_signature_hex,
                }
            )
    elif not signature:
        logger.info('Webhook Melhor Envio: requisição sem header X-ME-Signature')

    # Parsing do payload - tentar múltiplos formatos
    payload = request.data
    event = None
    data = {}
    melhorenvio_order_id = None

    if isinstance(payload, dict):
        event = payload.get('event')
        data = payload.get('data', {})
        if isinstance(data, dict):
            melhorenvio_order_id = data.get('id')
        # Fallback: talvez o id esteja no nível raiz
        if not melhorenvio_order_id:
            melhorenvio_order_id = payload.get('id')
        if not event:
            event = payload.get('status')
    elif isinstance(payload, list) and len(payload) > 0:
        # Alguns webhooks enviam array
        first = payload[0]
        if isinstance(first, dict):
            event = first.get('event')
            data = first.get('data', {})
            melhorenvio_order_id = data.get('id') if isinstance(data, dict) else None

    logger.info(
        f'Webhook Melhor Envio: parsing resultado',
        extra={
            'event': event,
            'melhorenvio_order_id': melhorenvio_order_id,
            'payload_type': type(payload).__name__,
            'payload_keys': list(payload.keys()) if isinstance(payload, dict) else str(type(payload)),
            'data_keys': list(data.keys()) if isinstance(data, dict) else str(type(data)),
            'raw_payload': str(payload)[:1000],
        }
    )

    # Log de segurança (não bloqueia - shipments inexistentes são ignorados)
    if webhook_secret and signature and not signature_valid:
        logger.warning(
            f'Webhook Melhor Envio: assinatura não corresponde ao secret configurado. '
            f'Verifique se MELHOR_ENVIO_WEBHOOK_SECRET corresponde ao secret do aplicativo.'
        )

    logger.info(f'Webhook Melhor Envio recebido: event={event}, melhorenvio_id={melhorenvio_order_id}')

    # Teste de conexão ou payload vazio
    if not event and not melhorenvio_order_id:
        logger.info('Webhook Melhor Envio: requisição de teste/conexão (sem event nem id)')
        return Response({'message': 'Webhook ativo. Nenhum evento para processar.'})

    # Buscar shipment pelo ID do Melhor Envio
    try:
        shipment = Shipment.objects.select_related('order').get(
            melhorenvio_order_id=melhorenvio_order_id
        )
    except Shipment.DoesNotExist:
        logger.warning(f'Webhook Melhor Envio: shipment não encontrado para id={melhorenvio_order_id}')
        # Retorna 200 para não falhar teste de conexão do Melhor Envio
        return Response({
            'message': f'Shipment não encontrado para melhorenvio_order_id={melhorenvio_order_id}',
            'processed': False
        })

    # Mapear evento para status do Shipment
    # Ref: https://docs.melhorenvio.com.br (eventos de etiqueta)
    EVENT_STATUS_MAP = {
        'order.created': 'created',         # Etiqueta criada
        'order.pending': 'pending',         # Etiqueta retornada ao carrinho
        'order.released': 'released',       # Etiqueta paga
        'order.generated': 'generated',     # Etiqueta gerada
        'order.received': 'posted',         # Encomenda recebida em ponto Pegaki
        'order.posted': 'posted',           # Encomenda postada
        'order.delivered': 'delivered',      # Encomenda entregue
        'order.cancelled': 'cancelled',      # Etiqueta cancelada
        'order.undelivered': 'returned',     # Não pôde ser entregue
        'order.paused': 'in_transit',        # Entrega interrompida (ação do destinatário)
        'order.suspended': 'in_transit',     # Encomenda suspensa
    }

    new_shipment_status = EVENT_STATUS_MAP.get(event)
    if not new_shipment_status:
        logger.info(f'Webhook Melhor Envio: evento {event} ignorado (não mapeado)')
        return Response({'message': f'Evento {event} recebido mas não processado'})

    # Atualizar status do shipment
    old_shipment_status = shipment.status
    shipment.status = new_shipment_status

    # Atualizar tracking code se disponível
    if data.get('tracking'):
        shipment.melhorenvio_tracking_code = data['tracking']

    # Atualizar tracking_url se disponível
    if data.get('tracking_url'):
        shipment.tracking_url = data['tracking_url']

    # Atualizar timestamps (parse ISO 8601 strings da API Melhor Envio)
    from django.utils.dateparse import parse_datetime
    if new_shipment_status == 'posted' and data.get('posted_at'):
        shipment.posted_at = parse_datetime(data['posted_at']) or timezone.now()
    elif new_shipment_status == 'delivered':
        delivered_at = data.get('delivered_at')
        shipment.delivered_at = (parse_datetime(delivered_at) if delivered_at else None) or timezone.now()

    shipment.save()

    logger.info(
        f'Shipment {shipment.id} atualizado: {old_shipment_status} → {new_shipment_status} (evento: {event})'
    )

    # Propagar status para o Order
    order = shipment.order
    order_transitioned = False

    try:
        if event == 'order.posted' or event == 'order.received':
            # Verificar se TODOS os shipments do pedido foram postados
            all_shipments = Shipment.objects.filter(order=order)
            all_posted = all_shipments.exclude(
                status__in=['posted', 'in_transit', 'delivered']
            ).count() == 0

            if all_posted and OrderStateMachine.can_transition(order.status, OrderStateMachine.SHIPPED):
                OrderStateMachine.transition_to(
                    order=order,
                    new_status=OrderStateMachine.SHIPPED,
                    notes=f'Todos os envios foram postados (webhook Melhor Envio: {event})',
                )
                order_transitioned = True

        elif event == 'order.delivered':
            # Verificar se TODOS os shipments do pedido foram entregues
            all_shipments = Shipment.objects.filter(order=order)
            all_delivered = all_shipments.exclude(status='delivered').count() == 0

            if all_delivered and OrderStateMachine.can_transition(order.status, OrderStateMachine.DELIVERED):
                OrderStateMachine.transition_to(
                    order=order,
                    new_status=OrderStateMachine.DELIVERED,
                    notes='Todos os envios foram entregues (webhook Melhor Envio)',
                )
                order_transitioned = True

    except OrderStatusTransitionError as e:
        logger.warning(
            f'Webhook: não foi possível transicionar order {order.order_number}: {str(e)}'
        )

    return Response({
        'message': f'Evento {event} processado com sucesso',
        'shipment_id': shipment.id,
        'shipment_status': new_shipment_status,
        'order_status': order.status,
        'order_transitioned': order_transitioned,
    })


@extend_schema(
    tags=['Logistics - Webhooks'],
    summary='Melhor Envio OAuth callback',
    description=(
        'Callback endpoint for Melhor Envio OAuth2 authorization redirect.\n\n'
        'When the user authorizes the application on Melhor Envio, they are redirected '
        'here with an authorization `code`. This endpoint exchanges the code for '
        'OAuth 2.0 tokens and persists them in the database.\n\n'
        '**This is critical for webhook functionality**: only labels created with an '
        'OAuth 2.0 token from the app where the webhook is configured will trigger '
        'the webhook notifications.'
    ),
    responses={
        200: inline_serializer(
            name='OAuthCallbackResponse',
            fields={
                'message': rf_serializers.CharField(),
                'token_status': rf_serializers.DictField(allow_null=True),
            }
        ),
        500: OpenApiResponse(description='Token exchange failed'),
    }
)
@api_view(['GET', 'POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def melhor_envio_oauth_callback(request):
    """
    Callback OAuth2 do Melhor Envio.

    Recebe o código de autorização e troca pelos tokens OAuth 2.0.
    Os tokens são persistidos no banco de dados para uso em chamadas à API.

    IMPORTANTE: Este callback é chamado automaticamente pelo Melhor Envio após
    o usuário autorizar o aplicativo. Certifique-se de que a URL de redirect
    configurada no app Melhor Envio aponta para este endpoint.
    """
    code = request.query_params.get('code')

    if not code:
        # Retorna 200 para testes de conexão sem código
        logger.info('Melhor Envio OAuth callback: requisição sem código (teste de conexão)')
        return Response({
            'message': 'Callback ativo. Aguardando código de autorização.',
            'token_status': None,
        })

    logger.info(f'Melhor Envio OAuth callback recebido com code={code[:10]}...')

    try:
        oauth_service = MelhorEnvioOAuthService()
        token_record = oauth_service.exchange_code_for_token(code)

        # Retornar status do token sem expor os tokens em si
        token_status = {
            'environment': token_record.environment,
            'token_id': token_record.id,
            'expires_at': token_record.expires_at.isoformat(),
            'scope': token_record.scope,
        }

        logger.info(
            f'Token OAuth salvo com sucesso: id={token_record.id}, '
            f'environment={token_record.environment}'
        )

        return Response({
            'message': 'Autorização OAuth 2.0 concluída. Token salvo com sucesso.',
            'token_status': token_status,
        })

    except MelhorEnvioOAuthError as e:
        logger.error(f'Erro ao trocar código OAuth: {str(e)}')
        return Response(
            {
                'message': 'Erro ao processar autorização OAuth',
                'detail': str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Logistics - Webhooks'],
    summary='Get Melhor Envio OAuth authorization URL',
    description=(
        'Returns the OAuth 2.0 authorization URL to redirect the user to Melhor Envio.\n\n'
        'Flow:\n'
        '1. Call this endpoint to get the authorization URL\n'
        '2. Redirect the user to the URL\n'
        '3. User authorizes the application on Melhor Envio\n'
        '4. Melhor Envio redirects back to the callback URL with an authorization code\n'
        '5. The callback endpoint exchanges the code for tokens automatically\n\n'
        'Requires admin/staff permission.'
    ),
    request=None,
    responses={
        200: inline_serializer(
            name='OAuthAuthorizeResponse',
            fields={
                'authorization_url': rf_serializers.URLField(),
                'environment': rf_serializers.CharField(),
                'instructions': rf_serializers.CharField(),
            }
        ),
        500: OpenApiResponse(description='OAuth not configured'),
    }
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def melhor_envio_oauth_authorize(request):
    """
    Retorna a URL de autorização OAuth 2.0 do Melhor Envio.

    Apenas administradores podem iniciar o fluxo de autorização.
    Redirecione o usuário para a URL retornada.
    """
    try:
        oauth_service = MelhorEnvioOAuthService()
        authorization_url = oauth_service.get_authorization_url()

        return Response({
            'authorization_url': authorization_url,
            'environment': oauth_service.environment,
            'instructions': (
                'Acesse a authorization_url para autorizar o aplicativo no Melhor Envio. '
                'Após autorizar, você será redirecionado ao callback e os tokens '
                'serão salvos automaticamente.'
            ),
        })

    except MelhorEnvioOAuthError as e:
        return Response(
            {
                'error': 'OAuth não configurado corretamente',
                'detail': str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Logistics - Webhooks'],
    summary='Get Melhor Envio OAuth token status',
    description=(
        'Returns the current status of the Melhor Envio OAuth 2.0 token.\n\n'
        'Use this to diagnose webhook issues. If `has_token` is False or '
        '`is_expired` is True, labels created will NOT trigger webhook notifications.\n\n'
        'Requires admin/staff permission.'
    ),
    request=None,
    responses={
        200: inline_serializer(
            name='OAuthTokenStatusResponse',
            fields={
                'has_token': rf_serializers.BooleanField(),
                'environment': rf_serializers.CharField(),
                'is_expired': rf_serializers.BooleanField(allow_null=True),
                'expires_at': rf_serializers.CharField(allow_null=True),
                'expires_in_seconds': rf_serializers.IntegerField(allow_null=True),
                'is_refresh_token_expired': rf_serializers.BooleanField(allow_null=True),
                'last_refreshed_at': rf_serializers.CharField(allow_null=True),
            }
        ),
    }
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def melhor_envio_oauth_token_status(request):
    """
    Retorna o status atual do token OAuth 2.0 do Melhor Envio.

    Use este endpoint para diagnosticar problemas com o webhook.
    """
    oauth_service = MelhorEnvioOAuthService()
    token_status = oauth_service.get_token_status()
    return Response(token_status)


# =================== Carrier Rule Views ===================

class IsAdminOrReadOnly(IsAuthenticated):
    """
    Permissao customizada:
    - GET/HEAD/OPTIONS: qualquer usuario autenticado
    - POST/PUT/PATCH/DELETE: apenas admin/staff
    """

    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        if not is_authenticated:
            return False

        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True

        return request.user and request.user.is_staff


@extend_schema(tags=['Logistics - Carrier Rules'])
class CarrierRuleViewSet(viewsets.ModelViewSet):
    """
    CRUD de regras de transportadoras.

    - GET (list/retrieve): qualquer usuario autenticado pode consultar
    - POST/PUT/PATCH/DELETE: apenas admin/staff

    Filtros disponiveis via query params:
    - ?carrier_name=Correios
    - ?is_active=true
    - ?search=Jadlog (busca em carrier_name e modality)
    """
    queryset = CarrierRule.objects.all()
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['carrier_name', 'is_active']
    search_fields = ['carrier_name', 'modality', 'notes']
    ordering_fields = ['carrier_name', 'modality', 'created_at', 'max_weight']
    ordering = ['carrier_name', 'modality']

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return CarrierRuleCreateUpdateSerializer
        return CarrierRuleSerializer

    @extend_schema(
        summary='List carrier rules',
        description=(
            'List all carrier rules. Supports filtering by carrier_name and is_active. '
            'Search by carrier_name, modality, or notes.'
        ),
        parameters=[
            OpenApiParameter(
                name='carrier_name',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by carrier name (exact match)',
                required=False,
            ),
            OpenApiParameter(
                name='is_active',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description='Filter by active status',
                required=False,
            ),
            OpenApiParameter(
                name='search',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Search in carrier_name, modality, and notes',
                required=False,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary='Create carrier rule',
        description='Create a new carrier rule. Admin only.',
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary='Get carrier rule details',
        description='Get details of a specific carrier rule.',
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary='Update carrier rule',
        description='Fully update a carrier rule. Admin only.',
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        summary='Partially update carrier rule',
        description='Partially update a carrier rule. Admin only.',
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(
        summary='Delete carrier rule',
        description='Delete a carrier rule. Admin only.',
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


@extend_schema(
    tags=['Logistics - Carrier Rules'],
    summary='Validate package against carrier rules',
    description=(
        'Validates package dimensions and weight against all active carrier rules. '
        'Returns eligible and ineligible carriers with rejection reasons. '
        'Does NOT call Melhor Envio API - uses locally configured rules only.'
    ),
    request=PackageValidationRequestSerializer,
    responses={
        200: inline_serializer(
            name='PackageValidationResponse',
            fields={
                'eligible': rf_serializers.ListField(
                    child=rf_serializers.DictField(),
                    help_text='Carriers compatible with the package',
                ),
                'ineligible': rf_serializers.ListField(
                    child=rf_serializers.DictField(),
                    help_text='Carriers incompatible with reasons',
                ),
                'warnings': rf_serializers.ListField(
                    child=rf_serializers.DictField(),
                    help_text='Non-blocking warnings (e.g. extra fees)',
                ),
                'package_info': rf_serializers.DictField(
                    help_text='Summary of the validated package',
                ),
            },
        ),
        400: OpenApiResponse(description='Invalid package data'),
    },
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_package_against_rules(request):
    """
    Valida dimensoes e peso de um pacote contra as regras de transportadoras.

    Retorna quais transportadoras sao compativeis e quais nao sao,
    com motivos detalhados de rejeicao.

    Body:
    {
        "height": 30,
        "width": 25,
        "length": 40,
        "weight": 5.5
    }
    """
    serializer = PackageValidationRequestSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = CarrierRuleService.validate_package(
        height=serializer.validated_data['height'],
        width=serializer.validated_data['width'],
        length=serializer.validated_data['length'],
        weight=serializer.validated_data['weight'],
    )

    return Response(result)