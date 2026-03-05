"""
Views for Stripe Connect Integration
Handles seller onboarding, account management, and checkout
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseRedirect
from django.core import signing
from django.utils import timezone
from authentication.models import CustomUser
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiResponse
from rest_framework import serializers as rf_serializers
import json

from .stripe_connect_service import StripeConnectService, stripe_client
from orders.models import Order
from django.conf import settings


# =================== Connected Account Management ===================

@extend_schema(
    tags=['Stripe Connect'],
    summary='Create connected account',
    request=None,
    responses={
        201: inline_serializer(
            name='CreateConnectedAccountResponse',
            fields={
                'account_id': rf_serializers.CharField(),
                'message': rf_serializers.CharField()
            }
        ),
        400: OpenApiResponse(description='Account already exists or error'),
    },
    description="Create a Stripe Connect Express account. Any authenticated user can connect an account."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_connected_account(request):
    """
    Create a Stripe Connect account for the current user.
    Any authenticated user can connect a Stripe account.
    """

    user = request.user

    # Check if account already exists
    if user.stripe_account_id:
        return Response(
            {
                'error': 'Connected account already exists',
                'account_id': user.stripe_account_id
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Create connected account
        account = StripeConnectService.create_connected_account(user)
        
        return Response({
            'account_id': account.id,
            'message': 'Connected account created successfully',
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    tags=['Stripe Connect'],
    summary='Get onboarding link',
    request=None,
    responses={
        200: inline_serializer(
            name='OnboardingLinkResponse',
            fields={
                'url': rf_serializers.URLField(),
                'expires_at': rf_serializers.IntegerField()
            }
        ),
        400: OpenApiResponse(description='No connected account found or error')
    },
    description="Generate an Account Link for seller onboarding. Redirects to Stripe's hosted flow to verify identity, add bank account, and accept terms."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_onboarding_link(request):
    """
    Generate an Account Link for seller onboarding
    
    The seller will be redirected to Stripe's hosted onboarding flow to:
    - Verify identity
    - Add bank account
    - Accept terms of service
    """
    
    user = request.user
    
    # Check if connected account exists
    if not user.stripe_account_id:
        return Response(
            {'error': 'No connected account found. Create one first.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Token assinado com user_id — identifica o vendedor sem precisar de JWT
        # O Stripe redireciona o browser do vendedor para return_url/refresh_url,
        # por isso não podemos usar autenticação JWT nessas rotas.
        token = signing.dumps({'user_id': user.id}, salt='stripe-onboarding-callback')

        api_base = settings.BACKEND_BASE_URL.rstrip('/')
        return_url  = f"{api_base}/api/payments/connect/onboarding/return/?token={token}"
        refresh_url = f"{api_base}/api/payments/connect/onboarding/refresh/?token={token}"

        # Create account link
        account_link = StripeConnectService.create_account_link(
            user=user,
            refresh_url=refresh_url,
            return_url=return_url
        )
        
        return Response({
            'url': account_link.url,
            'expires_at': account_link.expires_at,
        })
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    tags=['Stripe Connect'],
    summary='Get account status',
    responses={
        200: inline_serializer(
            name='AccountStatusResponse',
            fields={
                'has_account': rf_serializers.BooleanField(),
                'ready_to_receive_payments': rf_serializers.BooleanField(),
                'onboarding_complete': rf_serializers.BooleanField(),
                'requirements_status': rf_serializers.CharField(allow_null=True, required=False)
            }
        ),
        400: OpenApiResponse(description='Error checking account status')
    },
    description="Get the current status of the seller's connected account. Returns onboarding completion status and payment readiness."
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_account_status(request):
    """
    Get the current status of the seller's connected account
    
    Returns:
    - ready_to_receive_payments: Can receive transfers
    - onboarding_complete: All requirements met
    - requirements_status: currently_due, past_due, or None
    """
    
    user = request.user
    
    if not user.stripe_account_id:
        return Response({
            'has_account': False,
            'ready_to_receive_payments': False,
            'onboarding_complete': False,
        })
    
    try:
        # Get account status from Stripe
        account_status = StripeConnectService.get_account_status(
            user.stripe_account_id
        )
        
        return Response({
            'has_account': True,
            'ready_to_receive_payments': account_status['ready_to_receive_payments'],
            'onboarding_complete': account_status['onboarding_complete'],
            'requirements_status': account_status['requirements_status'],
        })
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


# =================== Checkout with Destination Charges ===================

@extend_schema(
    tags=['Stripe Connect'],
    summary='Create checkout with destination charge',
    request=inline_serializer(
        name='CreateCheckoutWithConnectRequest',
        fields={
            'order_id': rf_serializers.UUIDField(help_text='Order UUID')
        }
    ),
    responses={
        200: inline_serializer(
            name='CreateCheckoutWithConnectResponse',
            fields={
                'checkout_url': rf_serializers.URLField(),
                'session_id': rf_serializers.CharField(),
                'platform_fee': rf_serializers.FloatField()
            }
        ),
        400: OpenApiResponse(description='Seller not connected or error')
    },
    description="Create a Stripe Checkout session with destination charge. Customer pays platform, which keeps fee and transfers rest to seller."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_checkout_with_connect(request):
    """
    Create a Stripe Checkout session with destination charge
    
    Payment Flow:
    1. Customer pays total to platform
    2. Platform keeps application fee
    3. Rest is transferred to seller's connected account
    """
    
    order_id = request.data.get('order_id')
    
    if not order_id:
        return Response(
            {'error': 'order_id is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get order and verify ownership
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    
    # Get seller from first order item
    # TODO: Handle multi-seller orders (create separate sessions)
    seller = order.items.first().seller
    
    if not seller.stripe_account_id:
        return Response(
            {'error': 'Seller has not connected their Stripe account'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if seller can receive payments
    try:
        seller_status = StripeConnectService.get_account_status(
            seller.stripe_account_id
        )
        
        if not seller_status['ready_to_receive_payments']:
            return Response(
                {'error': 'Seller cannot receive payments yet'},
                status=status.HTTP_400_BAD_REQUEST
            )
    except Exception as e:
        return Response(
            {'error': f'Error checking seller status: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Calculate platform fee
        platform_fee = StripeConnectService.calculate_platform_fee(
            float(order.total)
        )
        
        # Build URLs
        base_url = request.build_absolute_uri('/')
        success_url = f"{base_url}checkout/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}checkout/cancel"
        
        # Create checkout session
        session = StripeConnectService.create_checkout_session_with_destination_charge(
            order=order,
            seller_account_id=seller.stripe_account_id,
            application_fee_amount=platform_fee,
            success_url=success_url,
            cancel_url=cancel_url
        )
        
        return Response({
            'checkout_url': session.url,
            'session_id': session.id,
            'platform_fee': platform_fee / 100,  # Convert back to BRL
        })
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


# =================== Webhooks ===================

@extend_schema(exclude=True)
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def stripe_connect_webhook(request):
    """
    Handle Stripe Connect webhooks (thin events)
    
    Listens for:
    - v2.core.account[requirements].updated
    - v2.core.account[.recipient].capability_status_updated
    
    Setup with Stripe CLI:
    stripe listen --thin-events 'v2.core.account[requirements].updated,v2.core.account[.recipient].capability_status_updated' --forward-thin-to http://localhost:8000/api/payments/connect/webhook/
    """
    
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    # Get webhook secret from settings
    webhook_secret = getattr(settings, 'STRIPE_CONNECT_WEBHOOK_SECRET', None)
    
    if not webhook_secret:
        return HttpResponse(
            'Webhook secret not configured',
            status=400
        )
    
    if not sig_header:
        return HttpResponse('Missing signature', status=400)
    
    try:
        # Parse thin event
        # Thin events only contain event ID and type
        thin_event = stripe_client.parse_thin_event(
            payload,
            sig_header,
            webhook_secret
        )
        
        # Route event to appropriate handler
        if thin_event.type == 'v2.core.account[requirements].updated':
            result = StripeConnectService.handle_account_requirements_updated(
                thin_event.id
            )
            
        elif thin_event.type == 'v2.core.account[.recipient].capability_status_updated':
            result = StripeConnectService.handle_capability_status_updated(
                thin_event.id
            )
        else:
            return HttpResponse(f'Unhandled event type: {thin_event.type}', status=200)
        
        return HttpResponse('Success', status=200)
        
    except Exception as e:
        return HttpResponse(f'Webhook error: {str(e)}', status=400)


# =================== Onboarding Callbacks (browser redirects do Stripe) ===================

_ONBOARDING_SALT = 'stripe-onboarding-callback'
_TOKEN_MAX_AGE   = 60 * 60 * 24 * 7  # 7 dias — cobre expiração do link (24h) com folga


def _resolve_token(token):
    """Valida o token assinado e retorna o CustomUser, ou None se inválido."""
    if not token:
        return None
    try:
        data = signing.loads(token, salt=_ONBOARDING_SALT, max_age=_TOKEN_MAX_AGE)
        return CustomUser.objects.get(id=data['user_id'])
    except (signing.BadSignature, signing.SignatureExpired, CustomUser.DoesNotExist):
        return None


def onboarding_return(request):
    """
    Stripe redireciona aqui após o vendedor concluir (ou abandonar) o onboarding.

    Fluxo:
    1. Valida o token assinado → identifica o vendedor
    2. Consulta status real no Stripe
    3. Atualiza seller_verified no DB se conta já está ativa
    4. Redireciona para o frontend com ?status=active|pending|incomplete|error
    """
    frontend_url = settings.FRONTEND_BASE_URL.rstrip('/')
    redirect_base = f"{frontend_url}/seller/onboarding/complete"

    user = _resolve_token(request.GET.get('token'))
    if not user:
        return HttpResponseRedirect(f"{redirect_base}?status=error&reason=invalid_token")

    try:
        account_status = StripeConnectService.get_account_status(user.stripe_account_id)

        if account_status['ready_to_receive_payments']:
            if not user.seller_verified:
                user.seller_verified = True
                user.seller_verified_at = timezone.now()
                user.save(update_fields=['seller_verified', 'seller_verified_at'])
            return HttpResponseRedirect(f"{redirect_base}?status=active")

        if account_status['onboarding_complete']:
            return HttpResponseRedirect(f"{redirect_base}?status=pending")

        return HttpResponseRedirect(f"{redirect_base}?status=incomplete")

    except Exception:
        return HttpResponseRedirect(f"{redirect_base}?status=error")


def onboarding_refresh(request):
    """
    Stripe redireciona aqui quando o link de onboarding expirou (>24h sem concluir).

    Fluxo:
    1. Valida o token assinado → identifica o vendedor
    2. Gera novo account link com novos tokens nos callbacks
    3. Redireciona diretamente para a URL do Stripe
    """
    frontend_url = settings.FRONTEND_BASE_URL.rstrip('/')

    user = _resolve_token(request.GET.get('token'))
    if not user:
        return HttpResponseRedirect(f"{frontend_url}/seller/onboarding?status=error&reason=expired")

    try:
        new_token = signing.dumps({'user_id': user.id}, salt=_ONBOARDING_SALT)
        api_base = settings.BACKEND_BASE_URL.rstrip('/')
        new_return_url  = f"{api_base}/api/payments/connect/onboarding/return/?token={new_token}"
        new_refresh_url = f"{api_base}/api/payments/connect/onboarding/refresh/?token={new_token}"

        account_link = StripeConnectService.create_account_link(
            user=user,
            refresh_url=new_refresh_url,
            return_url=new_return_url,
        )
        return HttpResponseRedirect(account_link.url)

    except Exception:
        return HttpResponseRedirect(f"{frontend_url}/seller/onboarding?status=error&reason=refresh_failed")


