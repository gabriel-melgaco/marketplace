from rest_framework import generics, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.utils import timezone
from django.db import models
from drf_spectacular.utils import extend_schema, inline_serializer
import json
import stripe

from .models import Payment, PaymentWebhook, SellerPayout, PaymentSplit, RefundRequest, ScheduledTransfer
from .serializers import (
    PaymentSerializer, PaymentIntentCreateSerializer,
    PaymentConfirmSerializer, RefundSerializer,
    SellerPayoutSerializer, PaymentSplitSerializer, ScheduledTransferSerializer,
    RefundRequestSerializer, RefundRequestCreateSerializer,
    RefundRequestApproveSerializer, RefundRequestRejectSerializer,
    RefundRequestPlatformDecideSerializer,
    PaymentIntentBatchCreateSerializer, PaymentIntentBatchResponseSerializer,
    PaymentIntentBatchItemSerializer, PaymentIntentBatchErrorItemSerializer,
)
from .payment_intent_service import PaymentIntentService, SellerNotReadyError
from .webhook_service import WebhookService
from .refund_service import RefundService, RefundError
from .refund_request_service import RefundRequestService, RefundRequestError
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
    summary='Create payment intents (batch, multi-seller)',
    request=PaymentIntentBatchCreateSerializer,
    responses={200: PaymentIntentBatchResponseSerializer},
    description=(
        "Create one Stripe PaymentIntent per Order in the list.\n\n"
        "Use this endpoint after POST /orders/ returns multiple Orders "
        "(multi-seller cart). Send all order_ids at once; the platform creates "
        "one PaymentIntent per Order and returns all client_secrets.\n\n"
        "## Response structure\n\n"
        "**`succeeded`**: list of successfully created/reused PaymentIntents.\n"
        "Each item contains `order_id`, `payment_id`, `client_secret`, `amount`, "
        "`currency`, `payment_method`, and `reused` (true if PI was already pending).\n\n"
        "**`failed`**: list of Orders for which PI creation failed, with `error` reason.\n\n"
        "The response always returns HTTP 200. The caller must inspect `failed` "
        "to determine if any order requires user action.\n\n"
        "## Idempotency\n\n"
        "If a pending PaymentIntent already exists for an Order, it is reused. "
        "A PI already succeeded returns an error entry in `failed`."
    ),
    operation_id='payments_create_intents_batch',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payment_intents_batch(request):
    """
    Criar PaymentIntents em batch — um por Order.

    Retorna todos os client_secrets para o frontend processar em paralelo.
    Erros individuais são isolados: a falha num Order não cancela os demais.
    """
    serializer = PaymentIntentBatchCreateSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    order_ids = serializer.validated_data['order_ids']
    payment_method = serializer.validated_data['payment_method']

    succeeded = []
    failed = []

    for order_id in order_ids:
        order_id_str = str(order_id)

        # Verificar se order existe e pertence ao usuário
        try:
            order = Order.objects.get(id=order_id, buyer=request.user)
        except Order.DoesNotExist:
            failed.append({
                'order_id': order_id,
                'error': 'Pedido não encontrado ou não pertence ao usuário',
            })
            continue

        # Verificar se pedido já tem pagamento confirmado
        if hasattr(order, 'payment'):
            existing_payment = order.payment

            if existing_payment.status in ['succeeded', 'processing']:
                failed.append({
                    'order_id': order_id,
                    'error': 'Pedido já possui pagamento confirmado',
                })
                continue

            if existing_payment.status == 'pending':
                try:
                    intent = PaymentIntentService.retrieve_payment_intent(
                        existing_payment.stripe_payment_intent_id
                    )
                    if intent.status in [
                        'requires_payment_method',
                        'requires_confirmation',
                        'requires_action',
                    ]:
                        logger.info(
                            "Batch: reusing existing payment intent for order %s",
                            order_id_str,
                            extra={
                                'order_id': order_id_str,
                                'payment_id': existing_payment.id,
                                'payment_intent_id': intent.id,
                            },
                        )
                        succeeded.append({
                            'order_id': order_id,
                            'payment_id': existing_payment.id,
                            'client_secret': intent.client_secret,
                            'amount': float(existing_payment.amount),
                            'currency': existing_payment.currency,
                            'payment_method': existing_payment.payment_method,
                            'reused': True,
                        })
                        continue
                    # PI cancelado/expirado — cai para criação abaixo
                except Exception as e:
                    logger.warning(
                        "Batch: failed to retrieve existing PI for order %s, proceeding to create: %s",
                        order_id_str,
                        str(e),
                    )

        # Validar estoque de todos os itens do pedido
        try:
            for item in order.items.select_related('listing').all():
                ProductValidationService.validate_listing_availability(
                    listing=item.listing,
                    quantity=item.quantity,
                )
        except (InsufficientStockError, ProductValidationError) as e:
            logger.warning(
                "Batch: payment intent blocked for order %s — stock error: %s",
                order_id_str,
                str(e),
            )
            failed.append({
                'order_id': order_id,
                'error': 'Item indisponível',
                'detail': str(e),
            })
            continue

        # Criar PaymentIntent
        try:
            payment, client_secret = PaymentIntentService.create_payment_intent(
                order=order,
                payment_method=payment_method,
                user=request.user,
            )
            succeeded.append({
                'order_id': order_id,
                'payment_id': payment.id,
                'client_secret': client_secret,
                'amount': float(payment.amount),
                'currency': payment.currency,
                'payment_method': payment.payment_method,
                'reused': False,
            })
        except SellerNotReadyError as e:
            logger.warning(
                "Batch: seller not ready for order %s: %s",
                order_id_str,
                str(e),
            )
            failed.append({
                'order_id': order_id,
                'error': 'Vendedor não está pronto para receber pagamentos',
                'detail': str(e),
            })
        except ValueError as e:
            failed.append({
                'order_id': order_id,
                'error': str(e),
            })
        except Exception as e:
            logger.error(
                "Batch: unexpected error creating PI for order %s: %s",
                order_id_str,
                str(e),
                exc_info=True,
            )
            failed.append({
                'order_id': order_id,
                'error': 'Erro ao criar pagamento. Tente novamente.',
            })

    logger.info(
        "Batch payment intent creation completed",
        extra={
            'user_id': request.user.id,
            'total_orders': len(order_ids),
            'succeeded': len(succeeded),
            'failed': len(failed),
        },
    )

    return Response({
        'succeeded': succeeded,
        'failed': failed,
    })


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
    summary='Request refund (DEPRECATED)',
    request=RefundSerializer,
    responses={
        410: inline_serializer(
            name='DeprecatedRefundResponse',
            fields={'detail': serializers.CharField()},
        )
    },
    description=(
        "DEPRECATED — Este endpoint foi descontinuado. "
        "Use POST /api/payments/refund-requests/ para solicitar reembolso "
        "via fluxo de revisão não-unilateral."
    ),
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_refund(request):
    """
    DEPRECADO: Endpoint de reembolso unilateral removido.
    Direciona para o novo fluxo de reembolso não-unilateral.
    """
    return Response(
        {
            'detail': (
                'Este endpoint foi descontinuado. '
                'Use POST /api/payments/refund-requests/ para solicitar reembolso.'
            )
        },
        status=status.HTTP_410_GONE,
    )


# =================== RefundRequest Views ===================

@extend_schema(
    tags=['Refund Requests'],
    summary='List refund requests',
    responses={200: RefundRequestSerializer(many=True)},
    description=(
        'Lista solicitações de reembolso do usuário autenticado. '
        'Compradores veem suas próprias solicitações. '
        'Vendedores veem solicitações relacionadas a pedidos com seus itens. '
        'Staff vê todas.'
    ),
)
class RefundRequestListView(generics.ListAPIView):
    """Lista RefundRequests filtradas por perfil do usuário."""
    serializer_class = RefundRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return (
                RefundRequest.objects
                .select_related('payment', 'order', 'requested_by', 'decided_by')
                .prefetch_related('history')
                .order_by('-created_at')
            )
        if getattr(user, 'is_seller', False):
            # Vendedor vê solicitações de pedidos que contêm seus itens
            from orders.models import OrderItem
            order_ids = (
                OrderItem.objects.filter(seller=user)
                .values_list('order_id', flat=True)
                .distinct()
            )
            return (
                RefundRequest.objects
                .filter(order_id__in=order_ids)
                .select_related('payment', 'order', 'requested_by', 'decided_by')
                .prefetch_related('history')
                .order_by('-created_at')
            )
        # Comprador vê apenas as próprias solicitações
        return (
            RefundRequest.objects
            .filter(requested_by=user)
            .select_related('payment', 'order', 'requested_by', 'decided_by')
            .prefetch_related('history')
            .order_by('-created_at')
        )


@extend_schema(
    tags=['Refund Requests'],
    summary='Get refund request details',
    responses={200: RefundRequestSerializer},
    description='Retorna detalhes completos de uma solicitação de reembolso incluindo audit trail.',
)
class RefundRequestDetailView(generics.RetrieveAPIView):
    """Detalhe de um RefundRequest."""
    serializer_class = RefundRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return RefundRequest.objects.all()
        if getattr(user, 'is_seller', False):
            from orders.models import OrderItem
            order_ids = (
                OrderItem.objects.filter(seller=user)
                .values_list('order_id', flat=True)
                .distinct()
            )
            return RefundRequest.objects.filter(
                models.Q(requested_by=user) | models.Q(order_id__in=order_ids)
            )
        return RefundRequest.objects.filter(requested_by=user)


@extend_schema(
    tags=['Refund Requests'],
    summary='Create refund request',
    request=RefundRequestCreateSerializer,
    responses={201: RefundRequestSerializer},
    description=(
        'Abre uma solicitação de reembolso não-unilateral. '
        'O sistema avalia auto-aprovação (not_received/duplicate_charge) '
        'ou encaminha para revisão do vendedor. '
        'Tipos: remorse (até 30 dias), defective, not_received, duplicate_charge.'
    ),
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_refund_request(request):
    """Abre uma nova solicitação de reembolso."""
    serializer = RefundRequestCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    payment = get_object_or_404(Payment, id=data['payment_id'], user=request.user)

    try:
        refund_request = RefundRequestService.create_request(
            buyer=request.user,
            payment=payment,
            refund_type=data['refund_type'],
            amount=data['amount_requested'],
            reason=data['reason_buyer'],
            evidence_urls=data.get('evidence_urls', []),
        )
        logger.info(
            'RefundRequest created via API',
            extra={
                'refund_request_id': str(refund_request.id),
                'user_id': request.user.id,
                'payment_id': payment.id,
            },
        )
        return Response(
            RefundRequestSerializer(refund_request).data,
            status=status.HTTP_201_CREATED,
        )
    except RefundRequestError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error('Error creating RefundRequest: %s', e, exc_info=True)
        return Response(
            {'error': 'Erro ao criar solicitação. Tente novamente.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    tags=['Refund Requests'],
    summary='Seller approves refund request',
    request=RefundRequestApproveSerializer,
    responses={200: RefundRequestSerializer},
    description=(
        'Vendedor aprova a solicitação de reembolso, podendo definir '
        'um valor parcial (amount_approved <= amount_requested).'
    ),
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seller_approve_refund_request(request, pk):
    """Vendedor aprova a solicitação."""
    refund_request = get_object_or_404(RefundRequest, id=pk)

    serializer = RefundRequestApproveSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        updated = RefundRequestService.seller_approve(
            refund_request=refund_request,
            seller=request.user,
            amount_approved=serializer.validated_data['amount_approved'],
        )
        return Response(RefundRequestSerializer(updated).data)
    except RefundRequestError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error('Error approving RefundRequest %s: %s', pk, e, exc_info=True)
        return Response(
            {'error': 'Erro ao aprovar solicitação.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    tags=['Refund Requests'],
    summary='Seller rejects refund request',
    request=RefundRequestRejectSerializer,
    responses={200: RefundRequestSerializer},
    description=(
        'Vendedor rejeita a solicitação com justificativa obrigatória. '
        'O comprador terá 7 dias para escalar para a plataforma.'
    ),
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seller_reject_refund_request(request, pk):
    """Vendedor rejeita a solicitação."""
    refund_request = get_object_or_404(RefundRequest, id=pk)

    serializer = RefundRequestRejectSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        updated = RefundRequestService.seller_reject(
            refund_request=refund_request,
            seller=request.user,
            reason=serializer.validated_data['reason'],
            evidence_urls=serializer.validated_data.get('evidence_urls', []),
        )
        return Response(RefundRequestSerializer(updated).data)
    except RefundRequestError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error('Error rejecting RefundRequest %s: %s', pk, e, exc_info=True)
        return Response(
            {'error': 'Erro ao rejeitar solicitação.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    tags=['Refund Requests'],
    summary='Buyer escalates refund request',
    request=None,
    responses={200: RefundRequestSerializer},
    description=(
        'Comprador discorda da rejeição do vendedor e escala para a plataforma. '
        'Só permitido dentro de 7 dias após a rejeição.'
    ),
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def buyer_escalate_refund_request(request, pk):
    """Comprador escala a solicitação para a plataforma."""
    refund_request = get_object_or_404(RefundRequest, id=pk)

    try:
        updated = RefundRequestService.buyer_escalate(
            refund_request=refund_request,
            buyer=request.user,
        )
        return Response(RefundRequestSerializer(updated).data)
    except RefundRequestError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error('Error escalating RefundRequest %s: %s', pk, e, exc_info=True)
        return Response(
            {'error': 'Erro ao escalar solicitação.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    tags=['Refund Requests'],
    summary='Buyer withdraws refund request',
    request=None,
    responses={200: RefundRequestSerializer},
    description='Comprador retira a solicitação de reembolso antes do processamento Stripe.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def buyer_withdraw_refund_request(request, pk):
    """Comprador retira a solicitação."""
    refund_request = get_object_or_404(RefundRequest, id=pk)

    try:
        updated = RefundRequestService.buyer_withdraw(
            refund_request=refund_request,
            buyer=request.user,
        )
        return Response(RefundRequestSerializer(updated).data)
    except RefundRequestError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error('Error withdrawing RefundRequest %s: %s', pk, e, exc_info=True)
        return Response(
            {'error': 'Erro ao retirar solicitação.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    tags=['Refund Requests'],
    summary='Platform decides on escalated refund request',
    request=RefundRequestPlatformDecideSerializer,
    responses={200: RefundRequestSerializer},
    description=(
        'Staff da plataforma decide sobre uma solicitação escalada. '
        'approve=true aprova o reembolso; approve=false rejeita definitivamente.'
    ),
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def platform_decide_refund_request(request, pk):
    """Staff decide sobre solicitação escalada."""
    refund_request = get_object_or_404(RefundRequest, id=pk)

    serializer = RefundRequestPlatformDecideSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        updated = RefundRequestService.platform_decide(
            refund_request=refund_request,
            staff_user=request.user,
            approve=serializer.validated_data['approve'],
            reason=serializer.validated_data['reason'],
        )
        return Response(RefundRequestSerializer(updated).data)
    except RefundRequestError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error('Error deciding RefundRequest %s: %s', pk, e, exc_info=True)
        return Response(
            {'error': 'Erro ao decidir solicitação.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
    summary='List scheduled transfers',
    description=(
        'List all scheduled transfers (repasses agendados) for the authenticated seller.\n\n'
        'A `ScheduledTransfer` is created when an order transitions to `delivered`. '
        'The Celery Beat task processes records with `scheduled_for <= now` and `status=pending`, '
        'dispatching the actual Stripe Transfer.\n\n'
        'Possible statuses: `pending` (aguardando), `dispatched` (executado), `failed` (falhou).'
    ),
    responses={200: ScheduledTransferSerializer(many=True)},
)
class ScheduledTransferListView(generics.ListAPIView):
    serializer_class = ScheduledTransferSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            ScheduledTransfer.objects
            .filter(order__seller=self.request.user)
            .select_related('order', 'payment')
            .order_by('-scheduled_for')
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
                'stripe_in_transit': serializers.FloatField(allow_null=True),
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
        "stripe_in_transit: valor de payouts já sacados pelo vendedor que ainda estão a caminho do banco "
        "(via stripe.Payout.list(status='in_transit')). Corresponde ao 'Em trânsito para o banco' no Stripe Dashboard. "
        "pending_transfers: valor de splits aguardando disparo ao Stripe. "
        "dispatched_transfers: valor já transferido ao vendedor (histórico local). "
        "failed_transfers: valor em splits com falha (requer reconciliação). "
        "splits_count: total de splits do vendedor. "
        "Nota: stripe_available/stripe_pending/stripe_in_transit são a fonte de verdade para saldo; "
        "dispatched_transfers é o histórico de Transfers criados pela plataforma (não reflete saques bancários do vendedor). "
        "stripe_available, stripe_pending e stripe_in_transit são None quando stripe_balance_error=True ou quando "
        "o vendedor não possui stripe_account_id configurado."
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
    stripe_in_transit = None
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

            # Payouts em trânsito (já sacados, ainda não chegaram no banco)
            payouts = stripe.Payout.list(status='in_transit', limit=100, stripe_account=stripe_account_id)
            stripe_in_transit = round(sum(p['amount'] for p in payouts.auto_paging_iter()) / 100, 2)

        except stripe.error.StripeError as e:
            stripe_balance_error = True
            stripe_available = None
            stripe_pending = None
            stripe_in_transit = None
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
            'stripe_in_transit': stripe_in_transit,
            'dispatched': str(dispatched),
            'splits_count': splits_count,
        }
    )

    return Response({
        'stripe_available': stripe_available,
        'stripe_pending': stripe_pending,
        'stripe_in_transit': stripe_in_transit,
        'stripe_balance_error': stripe_balance_error,
        'pending_transfers': pending,
        'dispatched_transfers': dispatched,
        'failed_transfers': failed,
        'splits_count': splits_count,
    })


