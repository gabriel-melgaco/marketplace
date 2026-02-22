from django.contrib import admin
from .models import (
    ShippingQuote, Shipment, ShipmentTracking, Address,
    OrderDelivery, InPersonDelivery, DeliveryStatusLog,
    MelhorEnvioOAuthToken, SellerMelhorEnvioToken,
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


@admin.register(MelhorEnvioOAuthToken)
class MelhorEnvioOAuthTokenAdmin(admin.ModelAdmin):
    """
    Admin para gerenciar tokens OAuth 2.0 do Melhor Envio.

    ATENÇÃO: Tokens de acesso são dados sensíveis.
    O admin exibe apenas os primeiros 20 caracteres.
    """

    list_display = (
        'id',
        'environment',
        'is_active',
        'is_expired_display',
        'expires_at',
        'refresh_token_expires_at',
        'last_refreshed_at',
        'created_at',
    )
    list_filter = ('environment', 'is_active')
    readonly_fields = (
        'token_type',
        'expires_at',
        'refresh_token_expires_at',
        'scope',
        'last_refreshed_at',
        'created_at',
        'updated_at',
        'access_token_preview',
        'refresh_token_preview',
    )

    # Nunca mostrar tokens completos no admin
    exclude = ('access_token', 'refresh_token')

    fieldsets = (
        ('Status', {
            'fields': ('environment', 'is_active', 'token_type'),
        }),
        ('Tokens (somente leitura - primeiros 20 caracteres)', {
            'fields': ('access_token_preview', 'refresh_token_preview'),
        }),
        ('Expiração', {
            'fields': ('expires_at', 'refresh_token_expires_at'),
        }),
        ('Metadata', {
            'fields': ('scope', 'last_refreshed_at', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def is_expired_display(self, obj):
        return obj.is_expired()
    is_expired_display.short_description = 'Expirado?'
    is_expired_display.boolean = True

    def access_token_preview(self, obj):
        if obj.access_token:
            return f'{obj.access_token[:20]}...'
        return '(vazio)'
    access_token_preview.short_description = 'Access Token (preview)'

    def refresh_token_preview(self, obj):
        if obj.refresh_token:
            return f'{obj.refresh_token[:20]}...'
        return '(vazio)'
    refresh_token_preview.short_description = 'Refresh Token (preview)'

    def has_add_permission(self, request):
        # Tokens são criados apenas via fluxo OAuth, não manualmente
        return False


@admin.register(SellerMelhorEnvioToken)
class SellerMelhorEnvioTokenAdmin(admin.ModelAdmin):
    """
    Admin para gerenciar tokens OAuth 2.0 por vendedor.

    Permite visualizar qual conta ME está vinculada a cada vendedor
    e diagnosticar problemas de autenticação (ex: me_document vazio).
    """

    list_display = (
        'seller',
        'environment',
        'me_email',
        'me_document_preview',
        'me_firstname',
        'is_active',
        'is_expired_display',
        'expires_at',
        'created_at',
    )
    list_filter = ('environment', 'is_active')
    search_fields = ('seller__email', 'me_email', 'me_firstname')
    readonly_fields = (
        'expires_at',
        'refresh_token_expires_at',
        'scope',
        'last_refreshed_at',
        'created_at',
        'updated_at',
        'access_token_preview',
        'refresh_token_preview',
        'me_email',
        'me_document_preview',
        'me_firstname',
    )

    # Nunca mostrar tokens completos no admin
    exclude = ('access_token', 'refresh_token')

    fieldsets = (
        ('Vendedor', {
            'fields': ('seller', 'environment', 'is_active'),
        }),
        ('Conta Melhor Envio vinculada', {
            'fields': ('me_email', 'me_document_preview', 'me_firstname'),
            'description': (
                'Dados da conta ME conectada via OAuth. '
                'Se me_document estiver vazio, o vendedor precisa reconectar a conta ME.'
            ),
        }),
        ('Tokens (somente leitura - primeiros 20 caracteres)', {
            'fields': ('access_token_preview', 'refresh_token_preview'),
        }),
        ('Expiração', {
            'fields': ('expires_at', 'refresh_token_expires_at'),
        }),
        ('Metadata', {
            'fields': ('scope', 'last_refreshed_at', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def is_expired_display(self, obj):
        return obj.is_expired()
    is_expired_display.short_description = 'Expirado?'
    is_expired_display.boolean = True

    def me_document_preview(self, obj):
        if obj.me_document:
            return f'{obj.me_document[:3]}***{obj.me_document[-2:]}'
        return '⚠ VAZIO - reconectar conta ME'
    me_document_preview.short_description = 'CPF/CNPJ ME'

    def access_token_preview(self, obj):
        if obj.access_token:
            return f'{obj.access_token[:20]}...'
        return '(vazio)'
    access_token_preview.short_description = 'Access Token (preview)'

    def refresh_token_preview(self, obj):
        if obj.refresh_token:
            return f'{obj.refresh_token[:20]}...'
        return '(vazio)'
    refresh_token_preview.short_description = 'Refresh Token (preview)'

    def has_add_permission(self, request):
        # Tokens são criados apenas via fluxo OAuth, não manualmente
        return False
