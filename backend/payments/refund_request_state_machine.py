"""
RefundRequest State Machine

Centraliza todas as transições de estado para RefundRequest.
Toda mudança de status DEVE passar por esta classe.

Transições válidas:
    requested         → seller_reviewing       (sistema: auto-aprovação falhou)
    requested         → auto_approved          (sistema: critérios objetivos)
    seller_reviewing  → approved               (vendedor)
    seller_reviewing  → rejected               (vendedor)
    seller_reviewing  → escalated              (sistema: prazo expirou)
    rejected          → escalated              (comprador: discordou em até 7 dias)
    rejected          → closed                 (sistema: 7 dias sem ação)
    escalated         → platform_approved      (staff)
    escalated         → platform_rejected      (staff)
    platform_rejected → closed                 (sistema: 7 dias sem ação)
    auto_approved     → stripe_refund_pending  (sistema)
    approved          → stripe_refund_pending  (sistema)
    platform_approved → stripe_refund_pending  (sistema)
    stripe_refund_pending → refunded           (webhook charge.refunded)
    qualquer pré-stripe → withdrawn            (comprador)
"""

import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

# Estados que permitem ao comprador retirar a solicitação
WITHDRAWABLE_STATUSES = {
    'requested',
    'seller_reviewing',
    'auto_approved',
    'approved',
    'rejected',
    'escalated',
    'platform_approved',
}

# Transições permitidas: {from_status: set(to_status)}
VALID_TRANSITIONS = {
    'requested': {
        'seller_reviewing',
        'auto_approved',
        'withdrawn',
    },
    'seller_reviewing': {
        'approved',
        'rejected',
        'escalated',
        'withdrawn',
    },
    'auto_approved': {
        'stripe_refund_pending',
        'withdrawn',
    },
    'approved': {
        'stripe_refund_pending',
        'withdrawn',
    },
    'rejected': {
        'escalated',
        'closed',
        'withdrawn',
    },
    'escalated': {
        'platform_approved',
        'platform_rejected',
        'withdrawn',
    },
    'platform_approved': {
        'stripe_refund_pending',
        'withdrawn',
    },
    'platform_rejected': {
        'closed',
        'withdrawn',
    },
    'stripe_refund_pending': {
        'refunded',
    },
    # Terminais — sem saída
    'refunded': set(),
    'withdrawn': set(),
    'closed': set(),
}


class RefundRequestStateMachineError(Exception):
    """Transição de estado inválida."""
    pass


class RefundRequestStateMachine:
    """
    Gerencia transições de estado de RefundRequest.

    Uso:
        RefundRequestStateMachine.transition(
            refund_request=rr,
            to_status='approved',
            changed_by=seller_user,
            actor_type='seller',
            notes='Aprovado após análise',
        )
    """

    @staticmethod
    def transition(
        refund_request,
        to_status: str,
        changed_by=None,
        actor_type: str = 'system',
        notes: str = '',
    ):
        """
        Executa uma transição de estado e persiste no audit trail.

        Args:
            refund_request: instância de RefundRequest (será salva em-place)
            to_status: status de destino
            changed_by: User que iniciou a transição (None para sistema)
            actor_type: 'buyer' | 'seller' | 'system' | 'platform'
            notes: texto livre para auditoria

        Raises:
            RefundRequestStateMachineError: se a transição for inválida
        """
        from .models import RefundRequestHistory

        from_status = refund_request.status

        allowed = VALID_TRANSITIONS.get(from_status, set())
        if to_status not in allowed:
            raise RefundRequestStateMachineError(
                f'Transição inválida: {from_status} → {to_status}. '
                f'Permitidas: {allowed or "nenhuma (estado terminal)"}.'
            )

        logger.info(
            'RefundRequest state transition',
            extra={
                'refund_request_id': str(refund_request.id),
                'from_status': from_status,
                'to_status': to_status,
                'actor_type': actor_type,
                'changed_by': changed_by.id if changed_by else None,
            },
        )

        # Atualizar status
        refund_request.status = to_status

        # Marcar resolved_at nos estados terminais
        if to_status in ('refunded', 'withdrawn', 'closed'):
            refund_request.resolved_at = timezone.now()

        refund_request.save()

        # Registrar no audit trail
        RefundRequestHistory.objects.create(
            refund_request=refund_request,
            from_status=from_status,
            to_status=to_status,
            changed_by=changed_by,
            actor_type=actor_type,
            notes=notes,
        )

        return refund_request
