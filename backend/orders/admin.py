import logging

from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import get_object_or_404, redirect

from .models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    Cart,
    CartItem
)
from .services.order_state_machine import OrderStateMachine, OrderStatusTransitionError

logger = logging.getLogger(__name__)


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
    readonly_fields = ('mark_delivered_button',)

    def mark_delivered_button(self, obj):
        if not OrderStateMachine.can_transition(obj.status, OrderStateMachine.DELIVERED):
            return format_html(
                '<span style="color: #999;">Transição para delivered não disponível no status atual ({})</span>',
                obj.status,
            )
        url = reverse('admin:orders_order_mark_delivered', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="background:#28a745;color:white;padding:6px 12px;'
            'border-radius:4px;text-decoration:none;font-weight:bold;">'
            'Marcar como Delivered</a>',
            url,
        )
    mark_delivered_button.short_description = 'Ação de Entrega'

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if obj and 'mark_delivered_button' not in fields:
            fields = list(fields) + ['mark_delivered_button']
        return fields

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'mark-delivered/<uuid:order_pk>/',
                self.admin_site.admin_view(self.mark_order_delivered),
                name='orders_order_mark_delivered',
            ),
        ]
        return custom_urls + urls

    def mark_order_delivered(self, request, order_pk):
        from payments.models import ScheduledTransfer

        order = get_object_or_404(Order, pk=order_pk)
        try:
            OrderStateMachine.transition_to(
                order=order,
                new_status=OrderStateMachine.DELIVERED,
                changed_by=request.user,
                notes=f'Marcado como delivered manualmente pelo admin {request.user.email}.',
            )
        except OrderStatusTransitionError as e:
            self.message_user(request, f'Transição inválida: {e}', messages.ERROR)
            return redirect('../../')
        except Exception as e:
            logger.error('Erro ao marcar order %s como delivered via admin: %s', order.order_number, e, exc_info=True)
            self.message_user(request, f'Erro inesperado: {e}', messages.ERROR)
            return redirect('../../')

        # Verificar se o ScheduledTransfer foi de fato criado
        order.refresh_from_db()
        st = ScheduledTransfer.objects.filter(order=order).first()
        if st:
            self.message_user(
                request,
                f'Pedido {order.order_number} marcado como delivered. '
                f'Repasse agendado para {st.scheduled_for.strftime("%d/%m/%Y %H:%M")} (status: {st.get_status_display()}).',
                messages.SUCCESS,
            )
        else:
            payment = getattr(order, 'payment', None)
            if payment is None:
                reason = 'o pedido não possui Payment associado'
            elif payment.status != 'succeeded':
                reason = f'o Payment está com status "{payment.status}" (necessário: succeeded)'
            else:
                reason = 'erro desconhecido ao criar ScheduledTransfer — verifique os logs'
            self.message_user(
                request,
                f'Pedido {order.order_number} marcado como delivered, '
                f'mas o repasse NÃO foi agendado: {reason}.',
                messages.WARNING,
            )

        return redirect('../../')


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
