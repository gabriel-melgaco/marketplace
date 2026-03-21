from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.conf import settings
from authentication.models import CustomUser
from .models import (
    Payment, PaymentSplit, PaymentWebhook, Dispute,
    ScheduledTransfer, RefundRequest, RefundRequestHistory,
)


# =================== Helpers ===================

def _status_badge(status, label, color_map):
    color = color_map.get(status, '#6c757d')
    return format_html(
        '<span style="background-color: {}; color: white; padding: 3px 10px; '
        'border-radius: 3px; font-size: 11px;">{}</span>',
        color, label
    )


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


class PaymentSplitInline(admin.TabularInline):
    model = PaymentSplit
    extra = 0
    readonly_fields = [
        'seller_link', 'gross_amount', 'platform_fee_amount',
        'net_amount', 'transfer_status_badge', 'stripe_transfer_id', 'created_at'
    ]
    fields = [
        'seller_link', 'gross_amount', 'platform_fee_amount',
        'net_amount', 'transfer_status_badge', 'stripe_transfer_id', 'created_at'
    ]

    def seller_link(self, obj):
        url = reverse('admin:authentication_customuser_change', args=[obj.seller.id])
        return format_html('<a href="{}">{}</a>', url, obj.seller.email)
    seller_link.short_description = 'Vendedor'

    def transfer_status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'dispatched': '#28a745',
            'failed': '#dc3545',
        }
        return _status_badge(obj.transfer_status, obj.get_transfer_status_display(), colors)
    transfer_status_badge.short_description = 'Status Transfer'

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DisputeInline(admin.TabularInline):
    model = Dispute
    extra = 0
    readonly_fields = [
        'stripe_dispute_id', 'amount', 'reason',
        'status', 'reversal_attempted', 'created_at'
    ]
    fields = [
        'stripe_dispute_id', 'amount', 'reason',
        'status', 'reversal_attempted', 'created_at'
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
        'status_badge', 'payment_method', 'transfer_group', 'created_at'
    ]
    list_filter = ['status', 'payment_method', 'created_at', 'paid_at']
    search_fields = [
        'stripe_payment_intent_id', 'stripe_charge_id', 'transfer_group',
        'order__order_number', 'user__email'
    ]
    readonly_fields = [
        'order', 'user', 'stripe_payment_intent_id', 'stripe_charge_id',
        'stripe_customer_id', 'transfer_group', 'amount', 'currency', 'status',
        'payment_method', 'platform_fee_total', 'idempotency_key', 'metadata',
        'description', 'failure_message', 'receipt_url_link',
        'refund_amount', 'refund_reason', 'refunded_at',
        'created_at', 'updated_at', 'paid_at',
    ]

    fieldsets = (
        ('Informações do Pagamento', {
            'fields': (
                'order', 'user', 'amount', 'currency',
                'status', 'payment_method', 'platform_fee_total'
            )
        }),
        ('Stripe IDs', {
            'fields': (
                'stripe_payment_intent_id', 'stripe_charge_id',
                'stripe_customer_id', 'transfer_group'
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
        ('Metadados', {
            'fields': ('idempotency_key', 'metadata'),
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at', 'paid_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [PaymentSplitInline, DisputeInline, PaymentWebhookInline]

    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
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
        return _status_badge(obj.status, obj.get_status_display(), colors)
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


# =================== Payment Split Admin ===================

@admin.register(PaymentSplit)
class PaymentSplitAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'payment_link', 'seller_link', 'gross_amount',
        'platform_fee_amount', 'net_amount', 'transfer_status_badge',
        'stripe_transfer_id', 'created_at'
    ]
    list_filter = ['transfer_status', 'created_at']
    search_fields = [
        'seller__email', 'stripe_transfer_id',
        'payment__stripe_payment_intent_id', 'payment__order__order_number'
    ]
    readonly_fields = [
        'payment', 'seller', 'gross_amount', 'platform_fee_amount',
        'net_amount', 'transfer_status', 'stripe_transfer_id',
        'error_message', 'created_at', 'updated_at',
    ]

    fieldsets = (
        ('Relacionamentos', {
            'fields': ('payment', 'seller')
        }),
        ('Valores', {
            'fields': ('gross_amount', 'platform_fee_amount', 'net_amount')
        }),
        ('Stripe Transfer', {
            'fields': ('transfer_status', 'stripe_transfer_id', 'error_message')
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def payment_link(self, obj):
        url = reverse('admin:payments_payment_change', args=[obj.payment.id])
        return format_html(
            '<a href="{}">{}</a>',
            url, obj.payment.stripe_payment_intent_id
        )
    payment_link.short_description = 'Pagamento'

    def seller_link(self, obj):
        url = reverse('admin:authentication_customuser_change', args=[obj.seller.id])
        return format_html('<a href="{}">{}</a>', url, obj.seller.email)
    seller_link.short_description = 'Vendedor'

    def transfer_status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'dispatched': '#28a745',
            'failed': '#dc3545',
        }
        return _status_badge(obj.transfer_status, obj.get_transfer_status_display(), colors)
    transfer_status_badge.short_description = 'Status'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# =================== Dispute Admin ===================

@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = [
        'stripe_dispute_id', 'payment_link', 'amount_formatted',
        'reason', 'status_badge', 'reversal_attempted', 'created_at'
    ]
    list_filter = ['status', 'reason', 'reversal_attempted', 'created_at']
    search_fields = [
        'stripe_dispute_id', 'stripe_charge_id',
        'payment__stripe_payment_intent_id', 'payment__order__order_number'
    ]
    readonly_fields = [
        'payment', 'stripe_dispute_id', 'stripe_charge_id',
        'amount', 'currency', 'reason', 'status',
        'reversal_attempted', 'reversal_amount',
        'stripe_payload', 'created_at', 'updated_at',
    ]

    fieldsets = (
        ('Disputa', {
            'fields': ('payment', 'stripe_dispute_id', 'stripe_charge_id')
        }),
        ('Detalhes', {
            'fields': ('amount', 'currency', 'reason', 'status')
        }),
        ('Reversão de Transfer', {
            'fields': ('reversal_attempted', 'reversal_amount')
        }),
        ('Payload Stripe', {
            'fields': ('stripe_payload',),
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def payment_link(self, obj):
        url = reverse('admin:payments_payment_change', args=[obj.payment.id])
        return format_html(
            '<a href="{}">{}</a>',
            url, obj.payment.stripe_payment_intent_id
        )
    payment_link.short_description = 'Pagamento'

    def amount_formatted(self, obj):
        return f'{obj.currency.upper()} {obj.amount}'
    amount_formatted.short_description = 'Valor'
    amount_formatted.admin_order_field = 'amount'

    def status_badge(self, obj):
        colors = {
            'needs_response': '#dc3545',
            'warning_needs_response': '#dc3545',
            'under_review': '#ffc107',
            'warning_under_review': '#ffc107',
            'won': '#28a745',
            'charge_refunded': '#6c757d',
            'warning_closed': '#6c757d',
            'lost': '#343a40',
        }
        return _status_badge(obj.status, obj.status.replace('_', ' ').title(), colors)
    status_badge.short_description = 'Status'

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
                'padding: 3px 10px; border-radius: 3px; font-size: 11px;">Processado</span>'
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


# =================== Stripe Connected Accounts Admin ===================

class SellerConnectedAccountProxy(CustomUser):
    """Proxy para exibir vendedores com conta Stripe Connect no painel de pagamentos."""

    class Meta:
        proxy = True
        verbose_name = 'Conta Conectada Stripe'
        verbose_name_plural = 'Contas Conectadas Stripe'


@admin.register(SellerConnectedAccountProxy)
class SellerConnectedAccountAdmin(admin.ModelAdmin):
    list_display = [
        'email', 'full_name', 'stripe_account_id',
        'connect_status_badge', 'seller_verified', 'seller_verified_at', 'date_joined'
    ]
    list_filter = ['seller_verified', 'date_joined']
    search_fields = ['email', 'first_name', 'last_name', 'stripe_account_id']
    readonly_fields = [
        'email', 'first_name', 'last_name', 'stripe_account_id',
        'seller_verified', 'seller_verified_at', 'date_joined',
        'stripe_dashboard_link',
    ]

    fieldsets = (
        ('Vendedor', {
            'fields': ('email', 'first_name', 'last_name', 'date_joined')
        }),
        ('Stripe Connect', {
            'fields': (
                'stripe_account_id', 'stripe_dashboard_link',
                'seller_verified', 'seller_verified_at'
            )
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(stripe_account_id='')

    def full_name(self, obj):
        return obj.get_full_name() or '-'
    full_name.short_description = 'Nome'

    def connect_status_badge(self, obj):
        if obj.seller_verified:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-size: 11px;">Ativo</span>'
            )
        return format_html(
            '<span style="background-color: #ffc107; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 11px;">Pendente</span>'
        )
    connect_status_badge.short_description = 'Status Connect'

    def stripe_dashboard_link(self, obj):
        if obj.stripe_account_id:
            url = f'https://dashboard.stripe.com/connect/accounts/{obj.stripe_account_id}'
            return format_html('<a href="{}" target="_blank">{}</a>', url, obj.stripe_account_id)
        return '-'
    stripe_dashboard_link.short_description = 'Dashboard Stripe'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False



# =================== Scheduled Transfer Admin ===================

@admin.register(ScheduledTransfer)
class ScheduledTransferAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order_link', 'payment_link', 'status_badge',
        'scheduled_for', 'error_message_short', 'created_at',
    ]
    list_filter = ['status', 'scheduled_for', 'created_at']
    search_fields = [
        'order__order_number', 'payment__stripe_payment_intent_id',
        'payment__stripe_charge_id',
    ]
    readonly_fields = [
        'order', 'payment', 'status', 'scheduled_for',
        'error_message', 'created_at', 'updated_at',
    ]

    fieldsets = (
        ('Pedido e Pagamento', {
            'fields': ('order', 'payment')
        }),
        ('Agendamento', {
            'fields': ('status', 'scheduled_for')
        }),
        ('Erro', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = 'Pedido'

    def payment_link(self, obj):
        url = reverse('admin:payments_payment_change', args=[obj.payment.id])
        return format_html('<a href="{}">{}</a>', url, obj.payment.stripe_payment_intent_id)
    payment_link.short_description = 'Pagamento'

    def status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'dispatched': '#28a745',
            'failed': '#dc3545',
        }
        return _status_badge(obj.status, obj.get_status_display(), colors)
    status_badge.short_description = 'Status'

    def error_message_short(self, obj):
        if obj.error_message:
            return obj.error_message[:60] + ('…' if len(obj.error_message) > 60 else '')
        return '-'
    error_message_short.short_description = 'Erro'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# =================== RefundRequest Admin ===================

class RefundRequestHistoryInline(admin.TabularInline):
    model = RefundRequestHistory
    extra = 0
    readonly_fields = [
        'from_status', 'to_status', 'changed_by', 'actor_type', 'notes', 'created_at'
    ]
    fields = [
        'from_status', 'to_status', 'changed_by', 'actor_type', 'notes', 'created_at'
    ]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order_link', 'buyer_link', 'refund_type',
        'amount_requested', 'amount_approved',
        'status_badge', 'seller_deadline', 'created_at',
    ]
    list_filter = ['status', 'refund_type', 'created_at']
    search_fields = [
        'id', 'order__order_number', 'requested_by__email',
        'payment__stripe_payment_intent_id',
    ]
    readonly_fields = [
        'id', 'payment', 'order', 'requested_by', 'status',
        'refund_type', 'amount_requested',
        'reason_buyer', 'reason_seller', 'reason_platform',
        'evidence_urls', 'seller_evidence_urls',
        'seller_deadline', 'escalation_deadline',
        'decided_by', 'stripe_refund_id', 'metadata',
        'created_at', 'updated_at', 'resolved_at',
    ]
    # amount_approved editável pelo staff para correções manuais
    fieldsets = (
        ('Identificação', {
            'fields': ('id', 'payment', 'order', 'requested_by')
        }),
        ('Tipo e Valor', {
            'fields': ('refund_type', 'amount_requested', 'amount_approved')
        }),
        ('Status e Prazos', {
            'fields': ('status', 'seller_deadline', 'escalation_deadline', 'resolved_at')
        }),
        ('Motivos', {
            'fields': ('reason_buyer', 'reason_seller', 'reason_platform')
        }),
        ('Evidências', {
            'fields': ('evidence_urls', 'seller_evidence_urls'),
            'classes': ('collapse',)
        }),
        ('Decisão', {
            'fields': ('decided_by', 'stripe_refund_id')
        }),
        ('Metadados', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    inlines = [RefundRequestHistoryInline]

    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = 'Pedido'

    def buyer_link(self, obj):
        url = reverse('admin:authentication_customuser_change', args=[obj.requested_by.id])
        return format_html('<a href="{}">{}</a>', url, obj.requested_by.email)
    buyer_link.short_description = 'Comprador'

    def status_badge(self, obj):
        colors = {
            'requested': '#17a2b8',
            'seller_reviewing': '#ffc107',
            'auto_approved': '#28a745',
            'approved': '#28a745',
            'rejected': '#dc3545',
            'escalated': '#fd7e14',
            'platform_approved': '#28a745',
            'platform_rejected': '#dc3545',
            'stripe_refund_pending': '#6f42c1',
            'refunded': '#6c757d',
            'withdrawn': '#adb5bd',
            'closed': '#343a40',
        }
        return _status_badge(obj.status, obj.get_status_display(), colors)
    status_badge.short_description = 'Status'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False