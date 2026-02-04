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
    path('confirm/', views.confirm_payment, name='confirm-payment'),
    path('status/<str:payment_intent_id>/', views.check_payment_status, name='check-status'),
    path('refund/', views.request_refund, name='request-refund'),
    
    # =================== Webhooks ===================
    path('webhook/', views.stripe_webhook, name='stripe-webhook'),
    
    # =================== Seller Payouts ===================
    path('payouts/', views.SellerPayoutListView.as_view(), name='payout-list'),
    path('payouts/<int:pk>/', views.SellerPayoutDetailView.as_view(), name='payout-detail'),
    path('balance/', views.seller_balance, name='seller-balance'),

    # Stripe Connect endpoints
    path('connect/create/', stripe_connect_views.create_connected_account, name='connect-create-account'),
    path('connect/onboarding-link/', stripe_connect_views.get_onboarding_link, name='connect-onboarding-link'),
    path('connect/status/', stripe_connect_views.get_account_status, name='connect-account-status'),
    path('connect/checkout/', stripe_connect_views.create_checkout_with_connect, name='connect-checkout'),
    path('connect/webhook/', stripe_connect_views.stripe_connect_webhook, name='connect-webhook'),
    
    # UI
    path('seller/onboarding/', stripe_connect_views.seller_onboarding_page, name='seller-onboarding'),
]