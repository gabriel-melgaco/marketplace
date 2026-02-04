from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    # =================== Cart ===================
    path('cart/', views.CartDetailView.as_view(), name='cart-detail'),
    path('cart/add/', views.add_to_cart, name='cart-add'),
    path('cart/items/<int:item_id>/', views.update_cart_item, name='cart-item-update'),
    path('cart/items/<int:item_id>/remove/', views.remove_from_cart, name='cart-item-remove'),
    path('cart/clear/', views.clear_cart, name='cart-clear'),
    
    # =================== Orders (Buyer) ===================
    path('', views.OrderListView.as_view(), name='order-list'),
    path('<uuid:pk>/', views.OrderDetailView.as_view(), name='order-detail'),
    path('create/', views.create_order, name='order-create'),
    path('<uuid:pk>/cancel/', views.cancel_order, name='order-cancel'),
    
    # =================== Orders (Seller) ===================
    path('sales/', views.SellerOrdersView.as_view(), name='seller-orders'),
    path('sales/<uuid:pk>/', views.SellerOrderDetailView.as_view(), name='seller-order-detail'),
    path('sales/<uuid:pk>/update-status/', views.update_order_status, name='order-update-status'),
]