from django.contrib import admin
from .models import (
    ShippingQuote, Shipment, ShipmentTracking, Address,
    OrderDelivery, InPersonDelivery, DeliveryStatusLog,
    CarrierRule,
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
        'seller_completed',
        'buyer_completed',
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
        'seller_completed_at',
        'buyer_completed_at',
        'completed_at',
    )
    fieldsets = (
        ('Participantes', {
            'fields': ('seller', 'buyer')
        }),
        ('Local e Agendamento', {
            'fields': (
                'meeting_status', 'meeting_location_name', 'meeting_address',
                'meeting_notes', 'scheduled_date', 'scheduled_time',
                'seller_contact_phone', 'buyer_contact_phone',
            )
        }),
        ('Confirmação do Encontro', {
            'fields': (
                'seller_confirmed', 'seller_confirmed_at',
                'buyer_confirmed', 'buyer_confirmed_at',
            )
        }),
        ('Confirmação de Conclusão', {
            'fields': (
                'seller_completed', 'seller_completed_at',
                'buyer_completed', 'buyer_completed_at',
                'completion_notes', 'completed_at',
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
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


class CarrierRuleAdmin(admin.ModelAdmin):
    list_display = (
        'carrier_name',
        'modality',
        'max_height',
        'max_width',
        'max_length',
        'max_weight',
        'max_sum_dimensions',
        'is_active',
        'updated_at',
    )
    list_filter = ('carrier_name', 'is_active')
    search_fields = ('carrier_name', 'modality', 'notes')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Identificacao', {
            'fields': ('carrier_name', 'modality', 'is_active', 'notes'),
        }),
        ('Dimensoes Minimas (cm)', {
            'fields': ('min_height', 'min_width', 'min_length'),
            'classes': ('collapse',),
        }),
        ('Dimensoes Maximas (cm)', {
            'fields': ('max_height', 'max_width', 'max_length'),
        }),
        ('Peso (kg)', {
            'fields': ('min_weight', 'max_weight'),
        }),
        ('Restricoes de Soma/Lado', {
            'fields': ('min_sum_dimensions', 'max_sum_dimensions', 'max_single_side'),
            'classes': ('collapse',),
        }),
        ('Taxa Nao Mecanizavel', {
            'fields': ('non_mechanizable_threshold',),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


admin.site.register(CarrierRule, CarrierRuleAdmin)
