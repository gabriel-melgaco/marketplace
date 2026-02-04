from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.utils import timezone
from django.db import models
from drf_spectacular.utils import extend_schema
import json

from .models import Payment, PaymentWebhook, SellerPayout
from .serializers import (
    PaymentSerializer, PaymentIntentCreateSerializer,
    PaymentConfirmSerializer, RefundSerializer,
    SellerPayoutSerializer
)
from .services import StripeService
from orders.models import Order


# =================== Payment Views ===================
class PaymentListView(generics.ListAPIView):
    """Listar pagamentos do usuário"""
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).order_by('-created_at')


class PaymentDetailView(generics.RetrieveAPIView):
    """Detalhes de um pagamento"""
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)


@extend_schema(
    request=PaymentIntentCreateSerializer,
    responses={200: PaymentSerializer},
    description="Criar Payment Intent no Stripe"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payment_intent(request):
    """Criar Payment Intent no Stripe"""
    serializer = PaymentIntentCreateSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    order_id = serializer.validated_data['order_id']
    payment_method = serializer.validated_data['payment_method']
    
    # Verificar se pedido existe e pertence ao usuário
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    
    # Verificar se pedido já tem pagamento
    if hasattr(order, 'payment'):
        if order.payment.status in ['succeeded', 'processing']:
            return Response(
                {'error': 'Pedido já possui pagamento confirmado'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    try:
        # Criar Payment Intent
        payment, client_secret = StripeService.create_payment_intent(
            order=order,
            payment_method=payment_method,
            user=request.user
        )
        
        return Response({
            'payment_id': payment.id,
            'client_secret': client_secret,
            'amount': float(payment.amount),
            'currency': payment.currency,
            'payment_method': payment.payment_method
        })
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    request=PaymentConfirmSerializer,
    responses={200: PaymentSerializer},
    description="Confirmar pagamento"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_payment(request):
    """Confirmar pagamento"""
    serializer = PaymentConfirmSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    payment_intent_id = serializer.validated_data['payment_intent_id']
    
    try:
        # Confirmar pagamento
        payment = StripeService.confirm_payment(payment_intent_id)
        
        payment_serializer = PaymentSerializer(payment)
        return Response(payment_serializer.data)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    responses={200: PaymentSerializer},
    description="Verificar status do pagamento"
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_payment_status(request, payment_intent_id):
    """Verificar status do pagamento"""
    try:
        payment = Payment.objects.get(
            stripe_payment_intent_id=payment_intent_id,
            user=request.user
        )
        
        # Atualizar status do Stripe
        updated_payment = StripeService.confirm_payment(payment_intent_id)
        
        payment_serializer = PaymentSerializer(updated_payment)
        return Response(payment_serializer.data)
        
    except Payment.DoesNotExist:
        return Response(
            {'error': 'Pagamento não encontrado'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    request=RefundSerializer,
    responses={200: PaymentSerializer},
    description="Solicitar reembolso"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_refund(request):
    """Solicitar reembolso"""
    serializer = RefundSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    payment_id = serializer.validated_data['payment_id']
    amount = serializer.validated_data.get('amount')
    reason = serializer.validated_data.get('reason', '')
    
    # Verificar se pagamento existe e pertence ao usuário
    payment = get_object_or_404(Payment, id=payment_id, user=request.user)
    
    # Verificar se pagamento foi bem-sucedido
    if payment.status != 'succeeded':
        return Response(
            {'error': 'Apenas pagamentos confirmados podem ser reembolsados'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verificar se já foi reembolsado
    if payment.status == 'refunded':
        return Response(
            {'error': 'Pagamento já foi reembolsado'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Criar reembolso
        refunded_payment = StripeService.create_refund(
            payment=payment,
            amount=amount,
            reason=reason
        )
        
        payment_serializer = PaymentSerializer(refunded_payment)
        return Response(payment_serializer.data)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


# =================== Webhook Views ===================
@extend_schema(exclude=True)
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def stripe_webhook(request):
    """Receber webhooks do Stripe"""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    if not sig_header:
        return HttpResponse('Missing signature', status=400)
    
    try:
        StripeService.handle_webhook(payload, sig_header)
        return HttpResponse('Success', status=200)
        
    except Exception as e:
        return HttpResponse(f'Webhook error: {str(e)}', status=400)


# =================== Seller Payout Views ===================
class SellerPayoutListView(generics.ListAPIView):
    """Listar repasses do vendedor"""
    serializer_class = SellerPayoutSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return SellerPayout.objects.filter(
            seller=self.request.user
        ).order_by('-created_at')


class SellerPayoutDetailView(generics.RetrieveAPIView):
    """Detalhes de um repasse"""
    serializer_class = SellerPayoutSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return SellerPayout.objects.filter(seller=self.request.user)


@extend_schema(
    responses={200: {
        'type': 'object',
        'properties': {
            'pending': {'type': 'number'},
            'processing': {'type': 'number'},
            'completed': {'type': 'number'},
            'total_available': {'type': 'number'}
        }
    }},
    description="Saldo disponível do vendedor"
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seller_balance(request):
    """Saldo disponível do vendedor"""
    user = request.user
    
    # Total pendente
    pending = SellerPayout.objects.filter(
        seller=user,
        status='pending'
    ).aggregate(total=models.Sum('net_amount'))['total'] or 0
    
    # Total processando
    processing = SellerPayout.objects.filter(
        seller=user,
        status='processing'
    ).aggregate(total=models.Sum('net_amount'))['total'] or 0
    
    # Total pago
    completed = SellerPayout.objects.filter(
        seller=user,
        status='completed'
    ).aggregate(total=models.Sum('net_amount'))['total'] or 0
    
    return Response({
        'pending': float(pending),
        'processing': float(processing),
        'completed': float(completed),
        'total_available': float(pending + processing)
    })


