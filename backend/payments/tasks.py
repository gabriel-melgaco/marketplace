"""
Payments Celery Tasks

Tasks periódicas para manutenção do fluxo de reembolso não-unilateral.

Registrar no CELERY_BEAT_SCHEDULE (api/settings.py):

    'expire-seller-review-hourly': {
        'task': 'payments.tasks.expire_seller_review_task',
        'schedule': crontab(minute=0),   # a cada hora
    },
    'expire-buyer-escalation-hourly': {
        'task': 'payments.tasks.expire_buyer_escalation_window_task',
        'schedule': crontab(minute=15),
    },
    'notify-seller-deadline-reminder-daily': {
        'task': 'payments.tasks.notify_seller_deadline_reminder_task',
        'schedule': crontab(hour=9, minute=0),  # 9h UTC diariamente
    },
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def process_scheduled_transfers(self):
    """
    Processa ScheduledTransfers pendentes cujo scheduled_for <= agora.

    Para cada registro elegível, chama
    TransferDispatchService.dispatch_transfers_for_order() e atualiza o
    status do ScheduledTransfer para 'dispatched' ou 'failed'.

    Frequência recomendada: horária (crontab(minute=0)).
    """
    from payments.models import ScheduledTransfer
    from payments.services import TransferDispatchService

    now = timezone.now()
    pending_qs = (
        ScheduledTransfer.objects
        .filter(status='pending', scheduled_for__lte=now)
        .select_related('order', 'payment')
    )

    total = pending_qs.count()
    logger.info(
        'process_scheduled_transfers: found %d scheduled transfers to process',
        total,
    )

    success = 0
    errors = 0

    for st in pending_qs:
        order = st.order
        payment = st.payment

        if not payment.stripe_charge_id:
            error_msg = (
                f"Payment {payment.id} (order={order.order_number}) "
                f"has no stripe_charge_id — cannot dispatch transfers."
            )
            logger.error(
                'process_scheduled_transfers: %s', error_msg,
                extra={
                    'scheduled_transfer_id': st.id,
                    'order_id': str(order.id),
                    'payment_id': payment.id,
                },
            )
            st.status = 'failed'
            st.error_message = error_msg
            st.save(update_fields=['status', 'error_message', 'updated_at'])
            errors += 1
            continue

        try:
            logger.info(
                'process_scheduled_transfers: dispatching transfers for order %s',
                order.order_number,
                extra={
                    'scheduled_transfer_id': st.id,
                    'order_id': str(order.id),
                    'payment_id': payment.id,
                    'charge_id': payment.stripe_charge_id,
                },
            )

            TransferDispatchService.dispatch_transfers_for_order(
                order=order,
                payment=payment,
                charge_id=payment.stripe_charge_id,
            )

            st.status = 'dispatched'
            st.error_message = ''
            st.save(update_fields=['status', 'error_message', 'updated_at'])
            success += 1

            logger.info(
                'process_scheduled_transfers: successfully dispatched order %s',
                order.order_number,
                extra={'scheduled_transfer_id': st.id, 'order_id': str(order.id)},
            )

        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                'process_scheduled_transfers: failed for ScheduledTransfer %s (order=%s): %s',
                st.id, order.order_number, exc,
                exc_info=True,
                extra={
                    'scheduled_transfer_id': st.id,
                    'order_id': str(order.id),
                    'payment_id': payment.id,
                },
            )
            st.status = 'failed'
            st.error_message = error_msg
            st.save(update_fields=['status', 'error_message', 'updated_at'])
            errors += 1

    logger.info(
        'process_scheduled_transfers: done. total=%d success=%d errors=%d',
        total, success, errors,
    )
    return {'total': total, 'success': success, 'errors': errors}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def expire_seller_review_task(self):
    """
    Verifica RefundRequests em 'seller_reviewing' com seller_deadline expirado
    e os transiciona para 'escalated'.

    Frequência recomendada: horária.
    """
    from payments.models import RefundRequest
    from payments.refund_request_service import RefundRequestService

    now = timezone.now()
    expired = RefundRequest.objects.filter(
        status='seller_reviewing',
        seller_deadline__lte=now,
    ).select_related('payment', 'order', 'requested_by')

    count = expired.count()
    logger.info(
        'expire_seller_review_task: found %d expired seller reviews',
        count,
    )

    success = 0
    errors = 0
    for rr in expired:
        try:
            RefundRequestService.expire_seller_review(rr)
            success += 1
        except Exception as exc:
            errors += 1
            logger.error(
                'expire_seller_review_task: failed for RefundRequest %s: %s',
                rr.id, exc,
                exc_info=True,
            )

    logger.info(
        'expire_seller_review_task: done. success=%d errors=%d',
        success, errors,
    )
    return {'processed': count, 'success': success, 'errors': errors}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def expire_buyer_escalation_window_task(self):
    """
    Verifica RefundRequests em 'rejected' ou 'platform_rejected'
    com escalation_deadline expirado e os transiciona para 'closed'.

    Frequência recomendada: horária.
    """
    from payments.models import RefundRequest
    from payments.refund_request_service import RefundRequestService

    now = timezone.now()
    expired = RefundRequest.objects.filter(
        status__in=['rejected', 'platform_rejected'],
        escalation_deadline__lte=now,
    ).select_related('payment', 'order', 'requested_by')

    count = expired.count()
    logger.info(
        'expire_buyer_escalation_window_task: found %d expired windows',
        count,
    )

    success = 0
    errors = 0
    for rr in expired:
        try:
            RefundRequestService.expire_buyer_escalation_window(rr)
            success += 1
        except Exception as exc:
            errors += 1
            logger.error(
                'expire_buyer_escalation_window_task: failed for RefundRequest %s: %s',
                rr.id, exc,
                exc_info=True,
            )

    logger.info(
        'expire_buyer_escalation_window_task: done. success=%d errors=%d',
        success, errors,
    )
    return {'processed': count, 'success': success, 'errors': errors}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notify_seller_deadline_reminder_task(self):
    """
    Busca RefundRequests em 'seller_reviewing' cuja seller_deadline
    vence em menos de 24 horas e envia notificação de lembrete ao vendedor.

    Frequência recomendada: diária (ex: 9h UTC).
    """
    from payments.models import RefundRequest
    from notifications.services import NotificationService
    from notifications.models import NotificationType

    now = timezone.now()
    remind_before = now + timedelta(hours=24)

    upcoming = RefundRequest.objects.filter(
        status='seller_reviewing',
        seller_deadline__gt=now,
        seller_deadline__lte=remind_before,
    ).select_related('order', 'requested_by')

    count = upcoming.count()
    logger.info(
        'notify_seller_deadline_reminder_task: found %d expiring soon',
        count,
    )

    notified = 0
    for rr in upcoming:
        try:
            order = rr.order
            seen = set()
            for item in order.items.select_related('seller').all():
                seller = item.seller
                if seller.id in seen:
                    continue
                seen.add(seller.id)

                hours_left = max(
                    0,
                    int((rr.seller_deadline - now).total_seconds() / 3600),
                )

                NotificationService.notify(
                    recipient=seller,
                    event_type=NotificationType.ORDER_STATUS_CHANGED,
                    title=f'Lembrete: responda ao reembolso — Pedido #{order.order_number}',
                    body=(
                        f'Você tem aproximadamente {hours_left}h para responder '
                        f'à solicitação de reembolso de '
                        f'R$ {rr.amount_requested:.2f} do pedido #{order.order_number}. '
                        f'Após o prazo, a disputa será escalada automaticamente para a plataforma.'
                    ),
                    metadata={
                        'refund_request_id': str(rr.id),
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'seller_deadline': rr.seller_deadline.isoformat(),
                        'hours_left': hours_left,
                    },
                    idempotency_key=(
                        f'rr_seller_reminder_{rr.id}_{seller.id}_'
                        f'{now.date().isoformat()}'
                    ),
                )
                notified += 1
        except Exception as exc:
            logger.error(
                'notify_seller_deadline_reminder_task: failed for RefundRequest %s: %s',
                rr.id, exc,
                exc_info=True,
            )

    logger.info(
        'notify_seller_deadline_reminder_task: done. notified=%d',
        notified,
    )
    return {'upcoming': count, 'notified': notified}
