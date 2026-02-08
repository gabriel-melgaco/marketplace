from django.urls import path
from . import views

app_name = 'logistics'

urlpatterns = [
    # =================== Addresses ===================
    path('addresses/', views.AddressListView.as_view(), name='address-list'),
    path('addresses/<int:pk>/', views.AddressDetailView.as_view(), name='address-detail'),
    path('addresses/<int:pk>/set-default/', views.set_default_address, name='address-set-default'),
    path('addresses/shipping/', views.get_shipping_addresses, name='shipping-addresses'),
    
    # =================== Shipping Quotes ===================
    path('shipping/calculate/', views.calculate_shipping, name='calculate-shipping'),
    path('shipping/quotes/', views.get_shipping_quotes, name='shipping-quotes'),
    
    # =================== Shipments ===================
    path('shipments/', views.ShipmentListView.as_view(), name='shipment-list'),
    path('shipments/<int:pk>/', views.ShipmentDetailView.as_view(), name='shipment-detail'),
    path('shipments/create/', views.create_shipments_for_order, name='shipment-create'),
    path('shipments/<int:pk>/label/', views.generate_shipping_label, name='shipment-label'),
    path('shipments/<int:pk>/track/', views.track_shipment, name='shipment-track'),
    path('shipments/order/<uuid:order_id>/', views.get_order_shipments, name='order-shipments'),
    
    # =================== Utilities ===================
    path('cep/lookup/', views.lookup_zipcode, name='cep-lookup'),

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
]