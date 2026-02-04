from django.contrib import admin
from .models import ShippingQuote, Shipment, ShipmentTracking, Address


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
