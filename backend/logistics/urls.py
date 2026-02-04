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
]