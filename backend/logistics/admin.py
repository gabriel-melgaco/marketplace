from django.contrib import admin
from .models import (
    ShippingQuote, Shipment, ShipmentTracking, Address,
    OrderDelivery, InPersonDelivery, DeliveryStatusLog
)


class AddressAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'nickname',
        'address_type',
        'recipient_name',
        'city',
        'state',
        'is_default',
        'is_shipping_address',
        'is_active',
        'created_at',
    )
    search_fields = (
        'user__email',
        'nickname',
        'recipient_name',
        'zipcode',
        'city',
        'street',
        'state',
    )


admin.site.register(Address, AddressAdmin)


class ShippingQuoteAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'seller',
        'origin_zipcode',
        'destination_zipcode',
        'weight',
        'expires_at',
        'created_at',
    )
    search_fields = (
        'user__email',
        'seller__email',
        'origin_zipcode',
        'destination_zipcode',
    )


admin.site.register(ShippingQuote, ShippingQuoteAdmin)


class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order',
        'seller',
        'melhorenvio_tracking_code',
        'carrier_name',
        'status',
        'created_at',
        'posted_at',
        'delivered_at',
    )
    search_fields = (
        'order__order_number',
        'seller__email',
        'melhorenvio_tracking_code',
        'carrier_name',
        'status',
    )


admin.site.register(Shipment, ShipmentAdmin)


class ShipmentTrackingAdmin(admin.ModelAdmin):
    list_display = (
        'shipment',
        'status',
        'location',
        'occurred_at',
        'created_at',
    )
    search_fields = (
        'shipment__melhorenvio_tracking_code',
        'shipment__order__order_number',
        'status',
        'location',
    )


admin.site.register(ShipmentTracking, ShipmentTrackingAdmin)


class OrderDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order',
        'seller',
        'delivery_method',
        'status',
        'delivery_cost',
        'created_at',
        'confirmed_at',
        'completed_at',
    )
    list_filter = ('delivery_method', 'status', 'created_at')
    search_fields = (
        'order__order_number',
        'seller__email',
    )
    readonly_fields = ('created_at', 'updated_at', 'confirmed_at', 'completed_at')


admin.site.register(OrderDelivery, OrderDeliveryAdmin)


class InPersonDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'seller',
        'buyer',
        'meeting_location_name',
        'meeting_status',
        'scheduled_date',
        'scheduled_time',
        'seller_confirmed',
        'buyer_confirmed',
        'created_at',
    )
    list_filter = ('meeting_status', 'scheduled_date', 'seller_confirmed', 'buyer_confirmed')
    search_fields = (
        'seller__email',
        'buyer__email',
        'meeting_location_name',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
        'seller_confirmed_at',
        'buyer_confirmed_at',
        'completed_at'
    )


admin.site.register(InPersonDelivery, InPersonDeliveryAdmin)


class DeliveryStatusLogAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order_delivery',
        'from_status',
        'to_status',
        'changed_by',
        'created_at',
    )
    list_filter = ('from_status', 'to_status', 'created_at')
    search_fields = (
        'order_delivery__order__order_number',
        'changed_by__email',
    )
    readonly_fields = ('created_at',)


admin.site.register(DeliveryStatusLog, DeliveryStatusLogAdmin)
