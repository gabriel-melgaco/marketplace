from django.contrib import admin
from .models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    Cart,
    CartItem
)


class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number',
        'buyer',
        'seller',
        'status',
        'subtotal',
        'shipping_cost',
        'total',
        'created_at',
        'updated_at',
    )
    search_fields = (
        'order_number',
        'buyer__email',
        'buyer__first_name',
        'buyer__last_name',
        'seller__email',
        'seller__first_name',
        'seller__last_name',
        'status',
    )
    list_filter = ('status', 'seller')


admin.site.register(Order, OrderAdmin)


class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'order',
        'product_name',
        'seller',
        'quantity',
        'unit_price',
        'subtotal',
        'shipping_cost',
    )
    search_fields = (
        'order__order_number',
        'product_name',
        'seller__email',
    )


admin.site.register(OrderItem, OrderItemAdmin)


class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'order',
        'old_status',
        'new_status',
        'changed_by',
        'created_at',
    )
    search_fields = (
        'order__order_number',
        'old_status',
        'new_status',
        'changed_by__email',
    )


admin.site.register(OrderStatusHistory, OrderStatusHistoryAdmin)


class CartAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'created_at',
        'updated_at',
    )
    search_fields = (
        'user__email',
        'user__first_name',
        'user__last_name',
    )


admin.site.register(Cart, CartAdmin)


class CartItemAdmin(admin.ModelAdmin):
    list_display = (
        'cart',
        'listing',
        'quantity',
        'added_at',
    )
    search_fields = (
        'cart__user__email',
        'listing__product__name',
    )


admin.site.register(CartItem, CartItemAdmin)
