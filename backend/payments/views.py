from rest_framework import generics, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.utils import timezone
from django.db import models
from drf_spectacular.utils import extend_schema, inline_serializer
import json
import stripe

from .models import Payment, PaymentWebhook, SellerPayout, PaymentSplit
from .serializers import (
    PaymentSerializer, PaymentIntentCreateSerializer,
    PaymentConfirmSerializer, RefundSerializer,
    SellerPayoutSerializer, PaymentSplitSerializer,
)
from .payment_intent_service import PaymentIntentService, SellerNotReadyError
from .webhook_service import WebhookService
from .refund_service import RefundService, RefundError
from .services import StripeService  # Legacy support
from orders.models import Order
from orders.services.product_validation_service import (
    ProductValidationService, InsufficientStockError, ProductValidationError
)

import logging

logger = logging.getLogger(__name__)


# =================== Payment Views ===================
@extend_schema(tags=['Payments'], summary='List payments', description='List all payments for the authenticated user.')
class PaymentListView(generics.ListAPIView):
    """Listar pagamentos do usuário"""
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).order_by('-created_at')


@extend_schema(tags=['Payments'], summary='Get payment details', description='Get detailed information about a specific payment.')
class PaymentDetailView(generics.RetrieveAPIView):
    """Detalhes de um pagamento"""
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)


@extend_schema(
    tags=['Payments'],
    summary='Create payment intent',
    request=PaymentIntentCreateSerializer,
    responses={200: PaymentSerializer},
    description="Create a Stripe Payment Intent for an order. Validates stock availability before creating."
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
        existing_payment = order.payment

        # Se pagamento já foi confirmado, rejeitar
        if existing_payment.status in ['succeeded', 'processing']:
            return Response(
                {'error': 'Pedido já possui pagamento confirmado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Se pagamento está pending, tentar reutilizar o payment intent existente
        elif existing_payment.status == 'pending':
            try:
                # Tentar recuperar payment intent do Stripe
                intent = PaymentIntentService.retrieve_payment_intent(
                    existing_payment.stripe_payment_intent_id
                )

                # Se payment intent ainda está válido (não cancelado), retornar ele
                if intent.status in ['requires_payment_method', 'requires_confirmation', 'requires_action']:
                    logger.info(
                        f"Reusing existing payment intent for order {order.id}",
                        extra={
                            'order_id': str(order.id),
                            'payment_id': existing_payment.id,
                            'payment_intent_id': intent.id,
                            'payment_intent_status': intent.status
                        }
                    )

                    return Response({
                        'payment_id': existing_payment.id,
                        'client_secret': intent.client_secret,
                        'amount': float(existing_payment.amount),
                        'currency': existing_payment.currency,
                        'payment_method': existing_payment.payment_method,
                        'reused': True  # Flag indicating this is a reused payment intent
                    })

                # Se foi cancelado ou expirou, permitir criar novo (continua execução)
                logger.info(
                    f"Existing payment intent is {intent.status}, creating new one",
                    extra={
                        'order_id': str(order.id),
                        'old_payment_intent_id': intent.id,
                        'old_status': intent.status
                    }
                )

            except Exception as e:
                # Se falhou ao buscar do Stripe, permitir criar novo
                logger.warning(
                    f"Failed to retrieve existing payment intent, creating new one: {str(e)}",
                    extra={
                        'order_id': str(order.id),
                        'payment_id': existing_payment.id,
                        'error': str(e)
                    }
                )

    # NOVO: Re-validar stock antes de criar payment intent
    # Previne criação de PI para items sem estoque ou inativos
    try:
        # Validar estoque e disponibilidade de todos os items do pedido
        for item in order.items.select_related('listing').all():
            ProductValidationService.validate_listing_availability(
                listing=item.listing,
                quantity=item.quantity
            )
    except (InsufficientStockError, ProductValidationError) as e:
        logger.warning(
            f"Payment intent blocked - validation error for order {order.id}",
            extra={
                'order_id': str(order.id),
                'user_id': request.user.id,
                'error': str(e),
                'error_type': type(e).__name__
            }
        )
        return Response(
            {
                'error': 'Item indisponível',
                'detail': str(e),
                'message': 'Um ou mais itens do pedido não estão mais disponíveis. '
                          'Por favor, revise seu carrinho.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Criar Payment Intent usando novo serviço
        payment, client_secret = PaymentIntentService.create_payment_intent(
            order=order,
            payment_method=payment_method,
            user=request.user
        )

        logger.info(
            f"Payment intent created for user {request.user.id}",
            extra={
                'user_id': request.user.id,
                'order_id': str(order.id),
                'payment_id': payment.id
            }
        )

        return Response({
            'payment_id': payment.id,
            'client_secret': client_secret,
            'amount': float(payment.amount),
            'currency': payment.currency,
            'payment_method': payment.payment_method
        })

    except SellerNotReadyError as e:
        logger.warning(
            f"Seller not ready for payment intent: {str(e)}",
            extra={'order_id': str(order.id), 'user_id': request.user.id}
        )
        return Response(
            {
                'error': 'Vendedor não está pronto para receber pagamentos',
                'detail': str(e),
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    except ValueError as e:
        logger.warning(f"Validation error creating payment intent: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

    except Exception as e:
        logger.error(f"Error creating payment intent: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Erro ao criar pagamento. Tente novamente.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Payments'],
    summary='Check payment status (deprecated)',
    request=PaymentConfirmSerializer,
    responses={200: PaymentSerializer},
    description="DEPRECATED: Only checks payment status. Actual payment confirmation happens via Stripe webhook."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_payment(request):
    """
    DEPRECADO: Apenas verifica status do pagamento

    IMPORTANTE: A confirmação real do pagamento ocorre via webhook do Stripe.
    Este endpoint apenas consulta o status atual.
    """
    serializer = PaymentConfirmSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    payment_intent_id = serializer.validated_data['payment_intent_id']

    try:
        # Buscar pagamento
        payment = Payment.objects.get(
            stripe_payment_intent_id=payment_intent_id,
            user=request.user
        )

        # Apenas retornar status atual (não modifica)
        logger.info(
            f"Payment status checked: {payment.status}",
            extra={
                'payment_id': payment.id,
                'user_id': request.user.id
            }
        )

        payment_serializer = PaymentSerializer(payment)
        return Response(payment_serializer.data)

    except Payment.DoesNotExist:
        return Response(
            {'error': 'Pagamento não encontrado'},
            status=status.HTTP_404_NOT_FOUND
        )

    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Erro ao verificar pagamento'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Payments'],
    summary='Check payment status',
    responses={200: PaymentSerializer},
    description="Check the current status of a payment by payment intent ID."
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

        # Apenas retornar status atual do banco
        # Status é atualizado via webhook
        logger.info(
            f"Payment status retrieved: {payment.status}",
            extra={
                'payment_id': payment.id,
                'payment_intent_id': payment_intent_id
            }
        )

        payment_serializer = PaymentSerializer(payment)
        return Response(payment_serializer.data)

    except Payment.DoesNotExist:
        return Response(
            {'error': 'Pagamento não encontrado'},
            status=status.HTTP_404_NOT_FOUND
        )

    except Exception as e:
        logger.error(f"Error retrieving payment: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Erro ao buscar pagamento'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=['Payments'],
    summary='Request refund',
    request=RefundSerializer,
    responses={200: PaymentSerializer},
    description="Request a full or partial refund for a succeeded payment."
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
        # Criar reembolso usando novo serviço
        refunded_payment = RefundService.create_refund(
            payment=payment,
            amount=amount,
            reason=reason
        )

        logger.info(
            f"Refund created for payment {payment.id}",
            extra={
                'payment_id': payment.id,
                'user_id': request.user.id,
                'refund_amount': float(amount) if amount else float(payment.amount)
            }
        )

        payment_serializer = PaymentSerializer(refunded_payment)
        return Response(payment_serializer.data)

    except ValueError as e:
        logger.warning(f"Validation error creating refund: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

    except Exception as e:
        logger.error(f"Error creating refund: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Erro ao criar reembolso. Tente novamente.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =================== Webhook Views ===================
@extend_schema(exclude=True)
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def stripe_webhook(request):
    """
    Receber e processar webhooks do Stripe

    Processa eventos de pagamento com:
    - Verificação de assinatura
    - Idempotência (eventos duplicados são ignorados)
    - Validação de valores
    - Atualização atômica de status
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    if not sig_header:
        logger.warning("Webhook received without signature")
        return HttpResponse('Missing signature', status=400)

    try:
        # Processar webhook com novo serviço
        WebhookService.handle_webhook(payload, sig_header)

        logger.info("Webhook processed successfully")
        return HttpResponse('Success', status=200)

    except ValueError as e:
        logger.error(f"Webhook validation error: {str(e)}")
        return HttpResponse(f'Validation error: {str(e)}', status=400)

    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}", exc_info=True)
        return HttpResponse(f'Webhook error: {str(e)}', status=400)


# =================== Seller Payout Views ===================
@extend_schema(
    tags=['Payments'],
    summary='List seller payouts',
    description=(
        'List all payment splits (repasses) for the authenticated seller. '
        'Each record represents a Stripe Transfer dispatched after a successful payment. '
        'transfer_status: pending = aguardando disparo | dispatched = transferido | failed = falhou.'
    ),
    responses={200: PaymentSplitSerializer(many=True)},
)
class SellerPayoutListView(generics.ListAPIView):
    """
    Listar repasses do vendedor.

    Usa PaymentSplit — o modelo real de repasses criado pelo TransferDispatchService
    após confirmação de pagamento via webhook payment_intent.succeeded.
    SellerPayout é um modelo legado e nunca é preenchido pelo fluxo atual.
    """
    serializer_class = PaymentSplitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            PaymentSplit.objects
            .filter(seller=self.request.user)
            .select_related('payment__order', 'seller')
            .order_by('-created_at')
        )


@extend_schema(
    tags=['Payments'],
    summary='Get payout details',
    description='Get detailed information about a specific seller payment split (repasse).',
    responses={200: PaymentSplitSerializer},
)
class SellerPayoutDetailView(generics.RetrieveAPIView):
    """
    Detalhes de um repasse.

    Usa PaymentSplit — o modelo real de repasses.
    """
    serializer_class = PaymentSplitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            PaymentSplit.objects
            .filter(seller=self.request.user)
            .select_related('payment__order', 'seller')
        )


@extend_schema(
    tags=['Payments'],
    summary='Get seller balance',
    responses={
        200: inline_serializer(
            name='SellerBalanceResponse',
            fields={
                'stripe_available': serializers.FloatField(allow_null=True),
                'stripe_pending': serializers.FloatField(allow_null=True),
                'stripe_balance_error': serializers.BooleanField(),
                'pending_transfers': serializers.DecimalField(max_digits=10, decimal_places=2),
                'dispatched_transfers': serializers.DecimalField(max_digits=10, decimal_places=2),
                'failed_transfers': serializers.DecimalField(max_digits=10, decimal_places=2),
                'splits_count': serializers.IntegerField(),
            }
        )
    },
    description=(
        "Get the seller's balance. "
        "stripe_available: saldo disponível para saque na conta Connect do vendedor (tempo real via Stripe API, em BRL). "
        "stripe_pending: saldo em liquidação na conta Connect (tipicamente 2-7 dias úteis). "
        "pending_transfers: valor de splits aguardando disparo ao Stripe. "
        "dispatched_transfers: valor já transferido ao vendedor (histórico local). "
        "failed_transfers: valor em splits com falha (requer reconciliação). "
        "total_dispatched: mesmo que dispatched_transfers (conveniência). "
        "splits_count: total de splits do vendedor. "
        "Nota: stripe_available/stripe_pending são a fonte de verdade para saldo; "
        "dispatched_transfers é o histórico de Transfers criados pela plataforma (não reflete saques bancários do vendedor)."
    ),
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seller_balance(request):
    """
    Saldo do vendedor: balance em tempo real do Stripe Connect + histórico local de repasses.

    - stripe_available / stripe_pending: saldo real na conta Connect do vendedor (via Stripe API)
    - pending_transfers / dispatched_transfers / failed_transfers: histórico local de PaymentSplit
    - Vendedores sem stripe_account_id recebem stripe_available=0 e stripe_pending=0
    """
    user = request.user

    # --- Histórico local de repasses (PaymentSplit) ---
    base_qs = PaymentSplit.objects.filter(seller=user)
    aggregated = base_qs.aggregate(
        pending_total=models.Sum(
            'net_amount', filter=models.Q(transfer_status='pending')
        ),
        dispatched_total=models.Sum(
            'net_amount', filter=models.Q(transfer_status='dispatched')
        ),
        failed_total=models.Sum(
            'net_amount', filter=models.Q(transfer_status='failed')
        ),
        splits_count=models.Count('id'),
    )

    pending = aggregated['pending_total'] or 0
    dispatched = aggregated['dispatched_total'] or 0
    failed = aggregated['failed_total'] or 0
    splits_count = aggregated['splits_count'] or 0

    # --- Balance em tempo real do Stripe Connect ---
    stripe_available = None
    stripe_pending = None
    stripe_balance_error = False
    stripe_account_id = getattr(user, 'stripe_account_id', None)

    if stripe_account_id:
        try:
            balance = stripe.Balance.retrieve(stripe_account=stripe_account_id)
            # Filtra por BRL; fallback para primeiro item caso não haja BRL
            brl_available = next(
                (b for b in balance.available if b['currency'] == 'brl'),
                balance.available[0] if balance.available else None,
            )
            brl_pending = next(
                (b for b in balance.pending if b['currency'] == 'brl'),
                balance.pending[0] if balance.pending else None,
            )
            stripe_available = round((brl_available['amount'] / 100), 2) if brl_available else 0
            stripe_pending = round((brl_pending['amount'] / 100), 2) if brl_pending else 0
        except stripe.error.StripeError as e:
            stripe_balance_error = True
            logger.warning(
                "Could not retrieve Stripe balance for seller",
                extra={'user_id': user.id, 'stripe_account_id': stripe_account_id, 'error': str(e)},
            )

    logger.info(
        "Seller balance retrieved",
        extra={
            'user_id': user.id,
            'stripe_available': stripe_available,
            'stripe_pending': stripe_pending,
            'dispatched': str(dispatched),
            'splits_count': splits_count,
        }
    )

    return Response({
        'stripe_available': stripe_available,
        'stripe_pending': stripe_pending,
        'stripe_balance_error': stripe_balance_error,
        'pending_transfers': pending,
        'dispatched_transfers': dispatched,
        'failed_transfers': failed,
        'splits_count': splits_count,
    })


