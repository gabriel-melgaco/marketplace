from django.urls import path
from . import views
from . import stripe_connect_views


app_name = 'payments'

urlpatterns = [
    # =================== Payments ===================
    path('', views.PaymentListView.as_view(), name='payment-list'),
    path('<int:pk>/', views.PaymentDetailView.as_view(), name='payment-detail'),

    # =================== Payment Processing ===================
    path('create-intent/', views.create_payment_intent, name='create-intent'),
    path('create-intents-batch/', views.create_payment_intents_batch, name='create-intents-batch'),
    path('confirm/', views.confirm_payment, name='confirm-payment'),
    path('status/<str:payment_intent_id>/', views.check_payment_status, name='check-status'),

    # DEPRECATED: mantido apenas para retornar 410 Gone
    path('refund/', views.request_refund, name='request-refund'),

    # =================== Refund Requests (non-unilateral) ===================
    path('refund-requests/', views.RefundRequestListView.as_view(), name='refund-request-list'),
    path('refund-requests/create/', views.create_refund_request, name='refund-request-create'),
    path('refund-requests/<uuid:pk>/', views.RefundRequestDetailView.as_view(), name='refund-request-detail'),
    path('refund-requests/<uuid:pk>/approve/', views.seller_approve_refund_request, name='refund-request-approve'),
    path('refund-requests/<uuid:pk>/reject/', views.seller_reject_refund_request, name='refund-request-reject'),
    path('refund-requests/<uuid:pk>/escalate/', views.buyer_escalate_refund_request, name='refund-request-escalate'),
    path('refund-requests/<uuid:pk>/withdraw/', views.buyer_withdraw_refund_request, name='refund-request-withdraw'),
    path('refund-requests/<uuid:pk>/decide/', views.platform_decide_refund_request, name='refund-request-decide'),

    # =================== Webhooks ===================
    path('webhook/', views.stripe_webhook, name='stripe-webhook'),

    # =================== Seller Payouts ===================
    path('payouts/', views.SellerPayoutListView.as_view(), name='payout-list'),
    path('payouts/<int:pk>/', views.SellerPayoutDetailView.as_view(), name='payout-detail'),
    path('balance/', views.seller_balance, name='seller-balance'),

    # Stripe Connect endpoints
    path('connect/create/', stripe_connect_views.create_connected_account, name='connect-create-account'),
    path('connect/disconnect/', stripe_connect_views.disconnect_connected_account, name='connect-disconnect-account'),
    path('connect/onboarding-link/', stripe_connect_views.get_onboarding_link, name='connect-onboarding-link'),
    path('connect/status/', stripe_connect_views.get_account_status, name='connect-account-status'),
    path('connect/sync/', stripe_connect_views.sync_account_status, name='connect-sync-status'),
    path('connect/checkout/', stripe_connect_views.create_checkout_with_connect, name='connect-checkout'),
    path('connect/webhook/', stripe_connect_views.stripe_connect_webhook, name='connect-webhook'),

    # Callbacks de onboarding (browser redirects do Stripe — sem JWT)
    path('connect/onboarding/return/', stripe_connect_views.onboarding_return, name='connect-onboarding-return'),
    path('connect/onboarding/refresh/', stripe_connect_views.onboarding_refresh, name='connect-onboarding-refresh'),
]