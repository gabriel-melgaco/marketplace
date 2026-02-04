from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Payment, PaymentWebhook, SellerPayout


# =================== Inline Admins ===================
class PaymentWebhookInline(admin.TabularInline):
    model = PaymentWebhook
    extra = 0
    readonly_fields = [
        'stripe_event_id', 'event_type', 'processed', 
        'processed_at', 'created_at'
    ]
    fields = [
        'stripe_event_id', 'event_type', 'processed', 
        'processed_at', 'created_at'
    ]
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


# =================== Payment Admin ===================
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order_link', 'user_link', 'amount_formatted',
        'status_badge', 'payment_method', 'created_at'
    ]
    list_filter = ['status', 'payment_method', 'created_at', 'paid_at']
    search_fields = [
        'stripe_payment_intent_id', 'stripe_charge_id',
        'order__order_number', 'user__email'
    ]
    readonly_fields = [
        'order', 'user', 'stripe_payment_intent_id', 'stripe_charge_id',
        'stripe_customer_id', 'amount', 'currency', 'status',
        'payment_method', 'description', 'failure_message',
        'receipt_url_link', 'refund_amount', 'refund_reason',
        'created_at', 'updated_at', 'paid_at', 'refunded_at'
    ]
    
    fieldsets = (
        ('Informações do Pagamento', {
            'fields': (
                'order', 'user', 'amount', 'currency', 
                'status', 'payment_method'
            )
        }),
        ('Stripe IDs', {
            'fields': (
                'stripe_payment_intent_id', 'stripe_charge_id',
                'stripe_customer_id'
            ),
            'classes': ('collapse',)
        }),
        ('Detalhes', {
            'fields': ('description', 'failure_message', 'receipt_url_link')
        }),
        ('Reembolso', {
            'fields': ('refund_amount', 'refund_reason', 'refunded_at'),
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at', 'paid_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [PaymentWebhookInline]
    
    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html(
            '<a href="{}">{}</a>', 
            url, obj.order.order_number
        )
    order_link.short_description = 'Pedido'
    
    def user_link(self, obj):
        url = reverse('admin:authentication_customuser_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_link.short_description = 'Usuário'
    
    def amount_formatted(self, obj):
        return f'{obj.currency.upper()} {obj.amount}'
    amount_formatted.short_description = 'Valor'
    amount_formatted.admin_order_field = 'amount'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'processing': '#17a2b8',
            'succeeded': '#28a745',
            'failed': '#dc3545',
            'cancelled': '#6c757d',
            'refunded': '#6c757d',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def receipt_url_link(self, obj):
        if obj.receipt_url:
            return format_html(
                '<a href="{}" target="_blank">Ver Recibo no Stripe</a>',
                obj.receipt_url
            )
        return '-'
    receipt_url_link.short_description = 'Recibo'
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


# =================== Payment Webhook Admin ===================
@admin.register(PaymentWebhook)
class PaymentWebhookAdmin(admin.ModelAdmin):
    list_display = [
        'stripe_event_id', 'event_type', 'payment_link',
        'processed_badge', 'created_at'
    ]
    list_filter = ['event_type', 'processed', 'created_at']
    search_fields = ['stripe_event_id', 'event_type']
    readonly_fields = [
        'stripe_event_id', 'event_type', 'payload', 'payment',
        'processed', 'processed_at', 'error_message', 'created_at'
    ]
    
    fieldsets = (
        ('Informações do Webhook', {
            'fields': ('stripe_event_id', 'event_type', 'payment')
        }),
        ('Processamento', {
            'fields': ('processed', 'processed_at', 'error_message')
        }),
        ('Payload', {
            'fields': ('payload',),
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def payment_link(self, obj):
        if obj.payment:
            url = reverse('admin:payments_payment_change', args=[obj.payment.id])
            return format_html(
                '<a href="{}">{}</a>',
                url, obj.payment.stripe_payment_intent_id
            )
        return '-'
    payment_link.short_description = 'Pagamento'
    
    def processed_badge(self, obj):
        if obj.processed:
            return format_html(
                '<span style="background-color: #28a745; color: white; '
                'padding: 3px 10px; border-radius: 3px; font-size: 11px;">✓ Processado</span>'
            )
        return format_html(
            '<span style="background-color: #ffc107; color: white; '
            'padding: 3px 10px; border-radius: 3px; font-size: 11px;">Pendente</span>'
        )
    processed_badge.short_description = 'Status'
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


# =================== Seller Payout Admin ===================
@admin.register(SellerPayout)
class SellerPayoutAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'seller_link', 'order_link', 'net_amount_formatted',
        'status_badge', 'scheduled_for', 'paid_at'
    ]
    list_filter = ['status', 'scheduled_for', 'paid_at', 'created_at']
    search_fields = [
        'seller__email', 'order__order_number', 'stripe_transfer_id'
    ]
    readonly_fields = [
        'seller', 'order', 'gross_amount', 'platform_fee',
        'net_amount', 'status', 'stripe_transfer_id',
        'created_at', 'scheduled_for', 'paid_at',
        'platform_fee_percentage'
    ]
    
    fieldsets = (
        ('Informações do Repasse', {
            'fields': ('seller', 'order', 'status')
        }),
        ('Valores', {
            'fields': (
                'gross_amount', 'platform_fee', 
                'platform_fee_percentage', 'net_amount'
            )
        }),
        ('Stripe', {
            'fields': ('stripe_transfer_id',),
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('created_at', 'scheduled_for', 'paid_at'),
            'classes': ('collapse',)
        }),
    )
    
    def seller_link(self, obj):
        url = reverse('admin:authentication_customuser_change', args=[obj.seller.id])
        return format_html('<a href="{}">{}</a>', url, obj.seller.email)
    seller_link.short_description = 'Vendedor'
    
    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = 'Pedido'
    
    def net_amount_formatted(self, obj):
        return f'R$ {obj.net_amount}'
    net_amount_formatted.short_description = 'Valor Líquido'
    net_amount_formatted.admin_order_field = 'net_amount'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'processing': '#17a2b8',
            'completed': '#28a745',
            'failed': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def platform_fee_percentage(self, obj):
        if obj.gross_amount > 0:
            percentage = (obj.platform_fee / obj.gross_amount) * 100
            return f'{percentage:.1f}%'
        return '0%'
    platform_fee_percentage.short_description = 'Taxa (%)'
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Permitir deletar apenas se estiver pendente
        if obj and obj.status == 'pending':
            return True
        return False