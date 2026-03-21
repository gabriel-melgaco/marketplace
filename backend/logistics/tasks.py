import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Statuses de RefundRequest que indicam disputa ativa (não-terminal)
OPEN_DISPUTE_STATUSES = {'requested', 'seller_reviewing', 'escalated', 'stripe_refund_pending'}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def auto_confirm_deliveries(self):
    """
    Confirma automaticamente entregas que estão em 'posted' ou 'in_transit' há mais de
    AUTO_CONFIRM_DELIVERY_DAYS dias sem confirmação do comprador e sem disputa aberta.

    Lógica:
      1. Busca Shipments com status posted/in_transit e posted_at <= now - AUTO_CONFIRM_DELIVERY_DAYS
      2. Descarta shipments cujo pedido tem RefundRequest com status ativo
      3. Marca cada shipment como delivered
      4. Se todos os shipments do pedido estiverem delivered → OrderStateMachine.transition_to(DELIVERED)
    """
    from logistics.models import Shipment
    from orders.services.order_state_machine import OrderStateMachine, OrderStatusTransitionError
    from payments.models import RefundRequest

    auto_confirm_days = getattr(settings, 'AUTO_CONFIRM_DELIVERY_DAYS', 20)
    cutoff = timezone.now() - timedelta(days=auto_confirm_days)

    candidates = (
        Shipment.objects
        .filter(
            status__in=('posted', 'in_transit'),
            posted_at__lte=cutoff,
        )
        .select_related('order__buyer', 'order__seller')
    )

    total = candidates.count()
    logger.info(
        'auto_confirm_deliveries: %d shipment(s) elegíveis (posted_at <= %s)',
        total, cutoff.isoformat()
    )

    confirmed = 0
    skipped_dispute = 0
    errors = 0

    for shipment in candidates:
        order = shipment.order

        # Verificar disputa ativa no pedido
        has_open_dispute = RefundRequest.objects.filter(
            order=order,
            status__in=OPEN_DISPUTE_STATUSES,
        ).exists()

        if has_open_dispute:
            logger.info(
                'auto_confirm_deliveries: shipment %s (order %s) ignorado — disputa ativa',
                shipment.id, order.order_number,
            )
            skipped_dispute += 1
            continue

        try:
            with transaction.atomic():
                shipment.status = 'delivered'
                shipment.delivered_at = timezone.now()
                shipment.save(update_fields=['status', 'delivered_at'])

                logger.info(
                    'auto_confirm_deliveries: shipment %s (order %s) marcado como delivered '
                    'após %d dias sem confirmação do comprador',
                    shipment.id, order.order_number, auto_confirm_days,
                )

                # Verificar se todos os shipments do pedido estão delivered
                pending_count = (
                    Shipment.objects
                    .filter(order=order)
                    .exclude(status='delivered')
                    .count()
                )

                if pending_count == 0 and OrderStateMachine.can_transition(
                    order.status, OrderStateMachine.DELIVERED
                ):
                    try:
                        OrderStateMachine.transition_to(
                            order=order,
                            new_status=OrderStateMachine.DELIVERED,
                            changed_by=None,
                            notes=(
                                f'Entrega confirmada automaticamente após {auto_confirm_days} dias '
                                'sem confirmação do comprador e sem disputa ativa.'
                            ),
                        )
                        logger.info(
                            'auto_confirm_deliveries: order %s transitado para DELIVERED',
                            order.order_number,
                        )
                    except OrderStatusTransitionError as exc:
                        logger.warning(
                            'auto_confirm_deliveries: não foi possível transicionar order %s → DELIVERED: %s',
                            order.order_number, exc,
                        )

            confirmed += 1

        except Exception as exc:
            errors += 1
            logger.error(
                'auto_confirm_deliveries: erro ao processar shipment %s (order %s): %s',
                shipment.id, order.order_number, exc,
                exc_info=True,
            )

    logger.info(
        'auto_confirm_deliveries finalizado — confirmados: %d | ignorados (disputa): %d | erros: %d',
        confirmed, skipped_dispute, errors,
    )
    return {'confirmed': confirmed, 'skipped_dispute': skipped_dispute, 'errors': errors}
