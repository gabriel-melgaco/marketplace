from django.urls import path
from . import views

app_name = 'logistics'

urlpatterns = [
    # =================== Addresses ===================
    path('addresses/', views.AddressListView.as_view(), name='address-list'),
    path('addresses/<int:pk>/', views.AddressDetailView.as_view(), name='address-detail'),
    path('addresses/<int:pk>/set-default/', views.set_default_address, name='address-set-default'),
    path('addresses/shipping/', views.get_shipping_addresses, name='shipping-addresses'),

    # =================== Listing Freight Quote (single listing, no DB save) ===================
    path('listings/<int:listing_id>/freight-quote/', views.listing_freight_quote, name='listing-freight-quote'),

    # =================== Shipping Quotes ===================
    path('shipping/calculate/', views.calculate_shipping, name='calculate-shipping'),
    path('shipping/quotes/', views.get_shipping_quotes, name='shipping-quotes'),

    # =================== Shipments ===================
    path('shipments/', views.ShipmentListView.as_view(), name='shipment-list'),
    path('shipments/<int:pk>/', views.ShipmentDetailView.as_view(), name='shipment-detail'),
    path('shipments/create/', views.create_shipments_for_order, name='shipment-create'),
    path('shipments/<int:pk>/label/', views.generate_shipping_label, name='shipment-label'),
    path('shipments/<int:pk>/track/', views.track_shipment, name='shipment-track'),
    path('shipments/<int:pk>/ship/', views.mark_shipment_shipped, name='shipment-ship'),
    path('shipments/order/<uuid:order_id>/', views.get_order_shipments, name='order-shipments'),

    # =================== Utilities ===================
    path('cep/lookup/', views.lookup_zipcode, name='cep-lookup'),

    # =================== Webhooks ===================
    path('webhooks/melhor-envio/', views.melhor_envio_webhook, name='melhor-envio-webhook'),
    # Alias without trailing slash: ME occasionally omits it; Django's APPEND_SLASH
    # cannot redirect POST requests, which causes a 500.  This entry lets Django
    # match the request directly instead of attempting the redirect.
    path('webhooks/melhor-envio', views.melhor_envio_webhook_no_slash, name='melhor-envio-webhook-no-slash'),
    path('webhooks/melhor-envio/callback/', views.melhor_envio_oauth_callback, name='melhor-envio-oauth-callback'),

    # =================== OAuth 2.0 Management (Admin only) ===================
    # GET: Returns authorization URL to start the OAuth flow
    path('webhooks/melhor-envio/authorize/', views.melhor_envio_oauth_authorize, name='melhor-envio-oauth-authorize'),
    # GET: Returns current token status for diagnostics
    path('webhooks/melhor-envio/token-status/', views.melhor_envio_oauth_token_status, name='melhor-envio-token-status'),

    # =================== Order Deliveries (Dual Delivery) ===================
    path('deliveries/create/', views.create_order_deliveries, name='create-order-deliveries'),
    path('deliveries/order/<uuid:order_id>/', views.get_order_deliveries_details, name='order-deliveries-details'),
    path('deliveries/user/', views.list_user_deliveries, name='list-user-deliveries'),

    # =================== In-Person Deliveries ===================
    path('in-person/<int:pk>/', views.get_in_person_delivery_detail, name='in-person-detail'),
    path('in-person/<int:pk>/confirm/', views.confirm_meeting, name='confirm-meeting'),
    path('in-person/<int:pk>/update/', views.update_meeting_details, name='update-meeting'),
    path('in-person/<int:pk>/complete/', views.complete_in_person_delivery, name='complete-in-person-delivery'),
    path('in-person/<int:pk>/cancel/', views.cancel_in_person_delivery, name='cancel-in-person-delivery'),
    path('in-person/', views.list_in_person_deliveries, name='list-in-person-deliveries'),

    # =================== Per-Seller Melhor Envio OAuth ===================
    path('me/connect/', views.seller_me_connect, name='seller-me-connect'),
    path('me/callback/', views.seller_me_callback, name='seller-me-callback'),
    path('me/status/', views.seller_me_status, name='seller-me-status'),
    path('me/disconnect/', views.seller_me_disconnect, name='seller-me-disconnect'),

    # =================== Carrier Services ===================
    # GET: Fetches live carrier services from Melhor Envio API
    path('carrier-services/', views.get_carrier_services, name='carrier-services'),

    # =================== ME Cart ===================
    path('cart/me/', views.list_me_cart, name='me-cart-list'),

    # =================== Debug ===================
    path('debug/me-account/', views.me_account_info, name='me-account-info'),
    path('debug/me-cart-test/', views.me_cart_minimal_test, name='me-cart-test'),
]
