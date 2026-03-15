"""
RefundRequest Service

Toda lógica de negócio de reembolso não-unilateral passa por aqui.

Regras de elegibilidade:
    - payment.status == 'succeeded'
    - Não existe RefundRequest ativo para o mesmo payment
    - remorse: payment criado há no máximo 30 dias
    - defective / not_received: sem limite de tempo

Critérios de auto-aprovação:
    - not_received: order criado há mais de 30 dias E status ainda é shipped/processing
    - duplicate_charge: existe outro Payment succeeded para o mesmo order

Impacto financeiro nos Transfer Reversals:
    - remorse: revertemos apenas product_amount × ratio (NÃO o frete)
    - defective / not_received: revertemos net_amount completo × ratio
    - duplicate_charge: NÃO cria Transfer Reversals (plataforma absorve)
"""

import logging
import stripe
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from .models import Payment, PaymentSplit, RefundRequest
from .refund_request_state_machine import RefundRequestStateMachine, RefundRequestStateMachineError

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

# Número de dias que o vendedor tem para responder
SELLER_REVIEW_DAYS = 3
# Janela para o comprador escalar após rejeição
BUYER_ESCALATION_DAYS = 7
# Prazo da plataforma para decidir disputas escaladas
PLATFORM_DECISION_DAYS = 5
# Limite de dias para reembolso por arrependimento
REMORSE_LIMIT_DAYS = 30
# Prazo mínimo sem entrega para auto-aprovação de not_received
NOT_RECEIVED_AUTO_DAYS = 30

# Statuses que indicam um RefundRequest ainda ativo
ACTIVE_STATUSES = {
    'requested',
    'seller_reviewing',
    'auto_approved',
    'approved',
    'escalated',
    'platform_approved',
    'stripe_refund_pending',
}


class RefundRequestError(Exception):
    """Erro de negócio em operação de RefundRequest."""
    pass


class RefundRequestService:

    # =========================================================================
    # Públicos
    # =========================================================================

    @staticmethod
    @transaction.atomic
    def create_request(
        buyer,
        payment: Payment,
        refund_type: str,
        amount: Decimal,
        reason: str,
        evidence_urls: list = None,
    ) -> RefundRequest:
        """
        Abre uma nova solicitação de reembolso.

        Verifica elegibilidade, decide se auto-aprovação se aplica e
        notifica vendedor(es).

        Returns:
            RefundRequest criado (status pode já ser 'auto_approved').
        """
        evidence_urls = evidence_urls or []

        # 1. Validar elegibilidade
        RefundRequestService._check_eligibility(buyer, payment, refund_type, amount)

        # 2. Criar registro
        order = payment.order
        refund_request = RefundRequest.objects.create(
            payment=payment,
            order=order,
            requested_by=buyer,
            status='requested',
            refund_type=refund_type,
            amount_requested=amount,
            reason_buyer=reason,
            evidence_urls=evidence_urls,
        )

        # Registrar transição inicial no audit trail
        from .models import RefundRequestHistory
        RefundRequestHistory.objects.create(
            refund_request=refund_request,
            from_status='',
            to_status='requested',
            changed_by=buyer,
            actor_type='buyer',
            notes=f'Tipo: {refund_type}. Valor: R$ {amount}.',
        )

        logger.info(
            'RefundRequest created',
            extra={
                'refund_request_id': str(refund_request.id),
                'payment_id': payment.id,
                'order_id': str(order.id),
                'refund_type': refund_type,
                'amount': str(amount),
                'buyer_id': buyer.id,
            },
        )

        # 3. Verificar auto-aprovação
        auto_approved = RefundRequestService._check_auto_approval(refund_request)

        if auto_approved:
            RefundRequestStateMachine.transition(
                refund_request=refund_request,
                to_status='auto_approved',
                actor_type='system',
                notes='Auto-aprovação por critérios objetivos.',
            )
            # Disparar reembolso no Stripe imediatamente
            RefundRequestService._call_stripe_refund(refund_request)
            RefundRequestService._notify_buyer_approved(refund_request)
        else:
            # Encaminhar para revisão do vendedor
            deadline = timezone.now() + timedelta(days=SELLER_REVIEW_DAYS)
            refund_request.seller_deadline = deadline
            refund_request.save(update_fields=['seller_deadline'])

            RefundRequestStateMachine.transition(
                refund_request=refund_request,
                to_status='seller_reviewing',
                actor_type='system',
                notes=(
                    f'Encaminhado para revisão do vendedor. '
                    f'Prazo: {deadline.strftime("%d/%m/%Y %H:%M")}.'
                ),
            )
            RefundRequestService._notify_sellers(refund_request)

        return refund_request

    @staticmethod
    @transaction.atomic
    def seller_approve(
        refund_request: RefundRequest,
        seller,
        amount_approved: Decimal,
    ) -> RefundRequest:
        """
        Vendedor aprova a solicitação (total ou parcial).

        Valida que o vendedor é dono de pelo menos um item do pedido.
        """
        if refund_request.status != 'seller_reviewing':
            raise RefundRequestError(
                f'Não é possível aprovar uma solicitação com status '
                f'"{refund_request.status}".'
            )

        # Verificar se seller tem itens no pedido
        order = refund_request.order
        seller_items = order.items.filter(seller=seller)
        if not seller_items.exists():
            raise RefundRequestError(
                'Vendedor não possui itens neste pedido.'
            )

        # Validar valor aprovado
        if amount_approved <= 0:
            raise RefundRequestError('O valor aprovado deve ser maior que zero.')
        if amount_approved > refund_request.amount_requested:
            raise RefundRequestError(
                f'Valor aprovado ({amount_approved}) não pode exceder '
                f'o valor solicitado ({refund_request.amount_requested}).'
            )

        refund_request.amount_approved = amount_approved
        refund_request.decided_by = seller
        refund_request.save(update_fields=['amount_approved', 'decided_by', 'updated_at'])

        RefundRequestStateMachine.transition(
            refund_request=refund_request,
            to_status='approved',
            changed_by=seller,
            actor_type='seller',
            notes=f'Aprovado pelo vendedor. Valor aprovado: R$ {amount_approved}.',
        )

        # Disparar reembolso no Stripe
        RefundRequestService._call_stripe_refund(refund_request)
        RefundRequestService._notify_buyer_approved(refund_request)

        logger.info(
            'RefundRequest approved by seller',
            extra={
                'refund_request_id': str(refund_request.id),
                'seller_id': seller.id,
                'amount_approved': str(amount_approved),
            },
        )
        return refund_request

    @staticmethod
    @transaction.atomic
    def seller_reject(
        refund_request: RefundRequest,
        seller,
        reason: str,
        evidence_urls: list = None,
    ) -> RefundRequest:
        """
        Vendedor rejeita a solicitação.
        Comprador terá BUYER_ESCALATION_DAYS dias para escalar.
        """
        if refund_request.status != 'seller_reviewing':
            raise RefundRequestError(
                f'Não é possível rejeitar uma solicitação com status '
                f'"{refund_request.status}".'
            )

        order = refund_request.order
        if not order.items.filter(seller=seller).exists():
            raise RefundRequestError(
                'Vendedor não possui itens neste pedido.'
            )

        if not reason or not reason.strip():
            raise RefundRequestError(
                'É obrigatório fornecer justificativa para rejeitar.'
            )

        escalation_deadline = timezone.now() + timedelta(days=BUYER_ESCALATION_DAYS)
        refund_request.reason_seller = reason
        refund_request.seller_evidence_urls = evidence_urls or []
        refund_request.escalation_deadline = escalation_deadline
        refund_request.decided_by = seller
        refund_request.save(
            update_fields=[
                'reason_seller',
                'seller_evidence_urls',
                'escalation_deadline',
                'decided_by',
                'updated_at',
            ]
        )

        RefundRequestStateMachine.transition(
            refund_request=refund_request,
            to_status='rejected',
            changed_by=seller,
            actor_type='seller',
            notes=f'Rejeitado pelo vendedor. Prazo de escalada: {escalation_deadline.strftime("%d/%m/%Y")}.',
        )

        RefundRequestService._notify_buyer_rejected(refund_request)

        logger.info(
            'RefundRequest rejected by seller',
            extra={
                'refund_request_id': str(refund_request.id),
                'seller_id': seller.id,
            },
        )
        return refund_request

    @staticmethod
    @transaction.atomic
    def buyer_escalate(
        refund_request: RefundRequest,
        buyer,
    ) -> RefundRequest:
        """
        Comprador discorda da rejeição e escala para a plataforma.
        Só é possível dentro do prazo de BUYER_ESCALATION_DAYS após a rejeição.
        """
        if refund_request.status != 'rejected':
            raise RefundRequestError(
                f'Apenas solicitações rejeitadas podem ser escaladas pelo comprador. '
                f'Status atual: "{refund_request.status}".'
            )

        if refund_request.requested_by_id != buyer.id:
            raise RefundRequestError(
                'Apenas o comprador que fez a solicitação pode escalá-la.'
            )

        # Verificar prazo
        if (
            refund_request.escalation_deadline
            and timezone.now() > refund_request.escalation_deadline
        ):
            raise RefundRequestError(
                'O prazo para escalar esta solicitação expirou.'
            )

        platform_deadline = timezone.now() + timedelta(days=PLATFORM_DECISION_DAYS)
        refund_request.escalation_deadline = platform_deadline
        refund_request.save(update_fields=['escalation_deadline', 'updated_at'])

        RefundRequestStateMachine.transition(
            refund_request=refund_request,
            to_status='escalated',
            changed_by=buyer,
            actor_type='buyer',
            notes=(
                f'Comprador discordou da rejeição. '
                f'Prazo para decisão da plataforma: {platform_deadline.strftime("%d/%m/%Y")}.'
            ),
        )

        RefundRequestService._notify_platform_escalated(refund_request)

        logger.info(
            'RefundRequest escalated by buyer',
            extra={
                'refund_request_id': str(refund_request.id),
                'buyer_id': buyer.id,
            },
        )
        return refund_request

    @staticmethod
    @transaction.atomic
    def buyer_withdraw(
        refund_request: RefundRequest,
        buyer,
    ) -> RefundRequest:
        """
        Comprador retira a solicitação.
        Só permitido antes do Stripe ser chamado.
        """
        from .refund_request_state_machine import WITHDRAWABLE_STATUSES

        if refund_request.status not in WITHDRAWABLE_STATUSES:
            raise RefundRequestError(
                f'Não é possível retirar uma solicitação com status '
                f'"{refund_request.status}".'
            )

        if refund_request.requested_by_id != buyer.id:
            raise RefundRequestError(
                'Apenas o comprador que fez a solicitação pode retirá-la.'
            )

        RefundRequestStateMachine.transition(
            refund_request=refund_request,
            to_status='withdrawn',
            changed_by=buyer,
            actor_type='buyer',
            notes='Comprador retirou a solicitação.',
        )

        logger.info(
            'RefundRequest withdrawn by buyer',
            extra={
                'refund_request_id': str(refund_request.id),
                'buyer_id': buyer.id,
            },
        )
        return refund_request

    @staticmethod
    @transaction.atomic
    def platform_decide(
        refund_request: RefundRequest,
        staff_user,
        approve: bool,
        reason: str,
    ) -> RefundRequest:
        """
        Staff da plataforma decide sobre uma solicitação escalada.

        Args:
            approve: True = a favor do comprador, False = a favor do vendedor
        """
        if refund_request.status != 'escalated':
            raise RefundRequestError(
                f'Apenas solicitações escaladas podem ser decididas pela plataforma. '
                f'Status atual: "{refund_request.status}".'
            )

        if not reason or not reason.strip():
            raise RefundRequestError(
                'É obrigatório fornecer justificativa para a decisão da plataforma.'
            )

        refund_request.reason_platform = reason
        refund_request.decided_by = staff_user
        refund_request.save(update_fields=['reason_platform', 'decided_by', 'updated_at'])

        if approve:
            # Usar valor solicitado se não há valor aprovado
            if not refund_request.amount_approved:
                refund_request.amount_approved = refund_request.amount_requested
                refund_request.save(update_fields=['amount_approved', 'updated_at'])

            RefundRequestStateMachine.transition(
                refund_request=refund_request,
                to_status='platform_approved',
                changed_by=staff_user,
                actor_type='platform',
                notes=f'Aprovado pela plataforma. Motivo: {reason}.',
            )
            RefundRequestService._call_stripe_refund(refund_request)
            RefundRequestService._notify_platform_decision(refund_request, approved=True)
        else:
            closing_deadline = timezone.now() + timedelta(days=BUYER_ESCALATION_DAYS)
            refund_request.escalation_deadline = closing_deadline
            refund_request.save(update_fields=['escalation_deadline', 'updated_at'])

            RefundRequestStateMachine.transition(
                refund_request=refund_request,
                to_status='platform_rejected',
                changed_by=staff_user,
                actor_type='platform',
                notes=f'Rejeitado pela plataforma. Motivo: {reason}.',
            )
            RefundRequestService._notify_platform_decision(refund_request, approved=False)

        logger.info(
            'RefundRequest platform decision',
            extra={
                'refund_request_id': str(refund_request.id),
                'staff_id': staff_user.id,
                'approved': approve,
            },
        )
        return refund_request

    @staticmethod
    @transaction.atomic
    def confirm_refunded(
        refund_request: RefundRequest,
        stripe_refund_id: str,
    ) -> RefundRequest:
        """
        Chamado pelo webhook charge.refunded para confirmar que o Stripe
        processou o reembolso.

        Atualiza Payment, Order e dispara Transfer Reversals.
        """
        if refund_request.status != 'stripe_refund_pending':
            # Idempotência: já foi processado
            logger.info(
                'confirm_refunded called on non-pending refund request — skipping',
                extra={
                    'refund_request_id': str(refund_request.id),
                    'status': refund_request.status,
                },
            )
            return refund_request

        refund_request.stripe_refund_id = stripe_refund_id
        refund_request.save(update_fields=['stripe_refund_id', 'updated_at'])

        RefundRequestStateMachine.transition(
            refund_request=refund_request,
            to_status='refunded',
            actor_type='system',
            notes=f'Confirmado via webhook Stripe. refund_id={stripe_refund_id}.',
        )

        # Atualizar Payment
        payment = refund_request.payment
        refund_amount = refund_request.amount_approved or refund_request.amount_requested
        payment.status = 'refunded'
        payment.refund_amount = refund_amount
        payment.refund_reason = refund_request.refund_type
        payment.refunded_at = timezone.now()
        if not payment.metadata:
            payment.metadata = {}
        payment.metadata['refund_request_id'] = str(refund_request.id)
        payment.metadata['stripe_refund_id'] = stripe_refund_id
        payment.save()

        # Atualizar Order
        try:
            from orders.services import PaymentCallbackService
            PaymentCallbackService.on_refund_processed(
                order=refund_request.order,
                refund_amount=float(refund_amount),
                refund_reason=refund_request.refund_type,
            )
        except Exception as e:
            logger.error(
                'Failed to update order status after refund confirmation: %s',
                e,
                extra={'refund_request_id': str(refund_request.id)},
                exc_info=True,
            )
            raise RefundRequestError(f'Erro ao atualizar status do pedido: {e}')

        # Criar Transfer Reversals nos vendedores
        RefundRequestService._reverse_seller_transfers(refund_request)

        # Notificar comprador e vendedores
        RefundRequestService._notify_refunded(refund_request)

        logger.info(
            'RefundRequest confirmed as refunded',
            extra={
                'refund_request_id': str(refund_request.id),
                'stripe_refund_id': stripe_refund_id,
                'refund_amount': str(refund_amount),
            },
        )
        return refund_request

    # =========================================================================
    # Tasks/Sistema
    # =========================================================================

    @staticmethod
    @transaction.atomic
    def expire_seller_review(refund_request: RefundRequest) -> RefundRequest:
        """
        Chamado pela task periódica quando o prazo do vendedor expirou.
        Transiciona de seller_reviewing → escalated.
        """
        if refund_request.status != 'seller_reviewing':
            return refund_request

        platform_deadline = timezone.now() + timedelta(days=PLATFORM_DECISION_DAYS)
        refund_request.escalation_deadline = platform_deadline
        refund_request.save(update_fields=['escalation_deadline', 'updated_at'])

        RefundRequestStateMachine.transition(
            refund_request=refund_request,
            to_status='escalated',
            actor_type='system',
            notes=(
                f'Prazo do vendedor expirou sem resposta. '
                f'Escalado automaticamente para a plataforma. '
                f'Prazo para decisão: {platform_deadline.strftime("%d/%m/%Y")}.'
            ),
        )

        RefundRequestService._notify_platform_escalated(refund_request)

        logger.warning(
            'RefundRequest escalated due to seller deadline expiry',
            extra={'refund_request_id': str(refund_request.id)},
        )
        return refund_request

    @staticmethod
    @transaction.atomic
    def expire_buyer_escalation_window(refund_request: RefundRequest) -> RefundRequest:
        """
        Chamado pela task periódica quando o prazo do comprador para escalar
        ou o prazo pós-plataforma-rejeitada expirou.
        Transiciona: rejected → closed | platform_rejected → closed
        """
        if refund_request.status not in ('rejected', 'platform_rejected'):
            return refund_request

        RefundRequestStateMachine.transition(
            refund_request=refund_request,
            to_status='closed',
            actor_type='system',
            notes='Prazo expirado sem ação do comprador. Solicitação encerrada automaticamente.',
        )

        logger.info(
            'RefundRequest closed due to inaction',
            extra={'refund_request_id': str(refund_request.id)},
        )
        return refund_request

    # =========================================================================
    # Privados
    # =========================================================================

    @staticmethod
    def _check_eligibility(buyer, payment: Payment, refund_type: str, amount: Decimal):
        """
        Verifica se o comprador pode abrir um RefundRequest para este pagamento.
        Levanta RefundRequestError se inelegível.
        """
        # Apenas pagamentos confirmados
        if payment.status != 'succeeded':
            raise RefundRequestError(
                'Apenas pagamentos confirmados podem ser reembolsados.'
            )

        # O comprador deve ser o dono do pagamento
        if payment.user_id != buyer.id:
            raise RefundRequestError(
                'Você não é o comprador deste pagamento.'
            )

        # Não pode haver outro RefundRequest ativo para o mesmo pagamento
        active = RefundRequest.objects.filter(
            payment=payment,
            status__in=ACTIVE_STATUSES,
        ).exists()
        if active:
            raise RefundRequestError(
                'Já existe uma solicitação de reembolso ativa para este pagamento.'
            )

        # Validar valor
        if amount <= 0:
            raise RefundRequestError('O valor solicitado deve ser maior que zero.')
        if amount > payment.amount:
            raise RefundRequestError(
                f'O valor solicitado ({amount}) não pode exceder '
                f'o valor do pagamento ({payment.amount}).'
            )

        # Janela de tempo por tipo
        if refund_type == 'remorse':
            limit = payment.created_at + timedelta(days=REMORSE_LIMIT_DAYS)
            if timezone.now() > limit:
                raise RefundRequestError(
                    f'O prazo para reembolso por arrependimento é de '
                    f'{REMORSE_LIMIT_DAYS} dias após o pagamento. '
                    f'Prazo expirado em {limit.strftime("%d/%m/%Y")}.'
                )

    @staticmethod
    def _check_auto_approval(refund_request: RefundRequest) -> bool:
        """
        Retorna True se a solicitação deve ser auto-aprovada.

        Critérios:
            not_received: order criado há mais de NOT_RECEIVED_AUTO_DAYS dias
                          E order.status ainda é shipped ou processing
            duplicate_charge: existe outro Payment succeeded para o mesmo order
        """
        rtype = refund_request.refund_type
        order = refund_request.order

        if rtype == 'not_received':
            threshold = timezone.now() - timedelta(days=NOT_RECEIVED_AUTO_DAYS)
            old_enough = order.created_at < threshold
            not_delivered = order.status in ('shipped', 'processing')
            if old_enough and not_delivered:
                logger.info(
                    'Auto-approval: not_received criteria met',
                    extra={
                        'refund_request_id': str(refund_request.id),
                        'order_created_at': order.created_at.isoformat(),
                        'order_status': order.status,
                    },
                )
                return True

        elif rtype == 'duplicate_charge':
            payment = refund_request.payment
            duplicates = Payment.objects.filter(
                order=order,
                status='succeeded',
            ).exclude(id=payment.id)
            if duplicates.exists():
                logger.info(
                    'Auto-approval: duplicate_charge criteria met',
                    extra={
                        'refund_request_id': str(refund_request.id),
                        'order_id': str(order.id),
                        'duplicate_payments': list(
                            duplicates.values_list('id', flat=True)
                        ),
                    },
                )
                return True

        return False

    @staticmethod
    def _call_stripe_refund(refund_request: RefundRequest):
        """
        Cria o Refund no Stripe e transiciona para stripe_refund_pending.

        O valor usado é amount_approved (se definido) ou amount_requested.
        A confirmação final ocorre via webhook charge.refunded →
        RefundRequestService.confirm_refunded().
        """
        amount = refund_request.amount_approved or refund_request.amount_requested
        amount_cents = int(amount * 100)

        idempotency_key = f're_rr_{refund_request.id}'

        logger.info(
            'Creating Stripe Refund for RefundRequest',
            extra={
                'refund_request_id': str(refund_request.id),
                'payment_id': refund_request.payment_id,
                'amount_cents': amount_cents,
                'idempotency_key': idempotency_key,
            },
        )

        try:
            refund = stripe.Refund.create(
                payment_intent=refund_request.payment.stripe_payment_intent_id,
                amount=amount_cents,
                reason='requested_by_customer',
                metadata={
                    'refund_request_id': str(refund_request.id),
                    'order_number': refund_request.order.order_number,
                    'refund_type': refund_request.refund_type,
                },
                idempotency_key=idempotency_key,
            )

            logger.info(
                'Stripe Refund created',
                extra={
                    'refund_id': refund.id,
                    'status': refund.status,
                    'refund_request_id': str(refund_request.id),
                },
            )

        except stripe.error.IdempotencyError:
            logger.warning(
                'Idempotency hit creating Stripe Refund — already exists',
                extra={'idempotency_key': idempotency_key},
            )

        except stripe.error.StripeError as e:
            logger.error(
                'Stripe error creating Refund: %s',
                e,
                extra={
                    'refund_request_id': str(refund_request.id),
                    'error_type': type(e).__name__,
                },
                exc_info=True,
            )
            raise RefundRequestError(f'Erro ao chamar Stripe: {e}')

        # Transicionar para stripe_refund_pending
        RefundRequestStateMachine.transition(
            refund_request=refund_request,
            to_status='stripe_refund_pending',
            actor_type='system',
            notes=f'Refund criado no Stripe. Valor: R$ {amount}.',
        )

    @staticmethod
    def _reverse_seller_transfers(refund_request: RefundRequest):
        """
        Cria Transfer Reversals proporcional para cada split despachado.

        Regras por tipo de reembolso:
            remorse         → reverter apenas product_amount × ratio
            defective       → reverter net_amount × ratio
            not_received    → reverter net_amount × ratio
            duplicate_charge → NÃO reverter (plataforma absorve)
            platform_decision → reverter net_amount × ratio
        """
        rtype = refund_request.refund_type
        payment = refund_request.payment

        if rtype == 'duplicate_charge':
            logger.info(
                'Skipping Transfer Reversals for duplicate_charge — platform absorbs',
                extra={'refund_request_id': str(refund_request.id)},
            )
            return

        dispatched_splits = PaymentSplit.objects.filter(
            payment=payment,
            transfer_status='dispatched',
        ).exclude(stripe_transfer_id='')

        if not dispatched_splits.exists():
            logger.info(
                'No dispatched splits to reverse',
                extra={'refund_request_id': str(refund_request.id)},
            )
            return

        refund_amount = refund_request.amount_approved or refund_request.amount_requested
        refund_ratio = refund_amount / payment.amount

        today_str = timezone.now().date().isoformat()

        for split in dispatched_splits:
            # Base de reversão depende do tipo
            if rtype == 'remorse':
                # Arrependimento: NÃO reverter frete — apenas produto
                base = split.product_amount
            else:
                # Defeito / não recebido / decisão plataforma: reverter tudo
                base = split.net_amount

            reversal_decimal = (base * refund_ratio).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            reversal_cents = int(reversal_decimal * 100)

            if reversal_cents <= 0:
                continue

            idem_key = (
                f'rev_rr_{refund_request.id}_{split.stripe_transfer_id}_{today_str}'
            )

            logger.info(
                'Creating Transfer Reversal for refund request',
                extra={
                    'refund_request_id': str(refund_request.id),
                    'split_id': split.id,
                    'transfer_id': split.stripe_transfer_id,
                    'reversal_cents': reversal_cents,
                    'refund_type': rtype,
                    'idempotency_key': idem_key,
                },
            )

            try:
                stripe.Transfer.create_reversal(
                    split.stripe_transfer_id,
                    amount=reversal_cents,
                    description=(
                        f'Reversal for RefundRequest {refund_request.id} '
                        f'({rtype}) — order {refund_request.order.order_number}'
                    ),
                    metadata={
                        'refund_request_id': str(refund_request.id),
                        'payment_id': str(payment.id),
                        'split_id': str(split.id),
                        'seller_id': str(split.seller_id),
                        'refund_type': rtype,
                        'refund_ratio': str(refund_ratio),
                    },
                    idempotency_key=idem_key,
                )
                logger.info(
                    'Transfer Reversal created',
                    extra={
                        'transfer_id': split.stripe_transfer_id,
                        'reversed_cents': reversal_cents,
                        'seller_id': split.seller_id,
                    },
                )
            except stripe.error.IdempotencyError:
                logger.warning(
                    'Idempotency hit on Transfer Reversal — already exists',
                    extra={'idempotency_key': idem_key},
                )
            except stripe.error.StripeError as e:
                # Falha não deve abortar o fluxo — registrar para reconciliação
                logger.error(
                    'Failed to create Transfer Reversal for split %s: %s',
                    split.id,
                    e,
                    extra={
                        'split_id': split.id,
                        'transfer_id': split.stripe_transfer_id,
                        'error_type': type(e).__name__,
                    },
                    exc_info=True,
                )
                split.error_message = (
                    f'Transfer Reversal failed (RefundRequest {refund_request.id}): {e}'
                )
                split.save(update_fields=['error_message', 'updated_at'])

    # =========================================================================
    # Notificações
    # =========================================================================

    @staticmethod
    def _notify_sellers(refund_request: RefundRequest):
        """Notifica os vendedores do pedido sobre nova solicitação."""
        try:
            from notifications.services import NotificationService
            from notifications.models import NotificationType

            order = refund_request.order
            seen = set()
            for item in order.items.select_related('seller').all():
                seller = item.seller
                if seller.id in seen:
                    continue
                seen.add(seller.id)
                NotificationService.notify(
                    recipient=seller,
                    event_type=NotificationType.ORDER_STATUS_CHANGED,
                    title=f'Nova solicitação de reembolso — Pedido #{order.order_number}',
                    body=(
                        f'O comprador abriu uma solicitação de reembolso de '
                        f'R$ {refund_request.amount_requested:.2f} '
                        f'para o pedido #{order.order_number}. '
                        f'Motivo: {refund_request.get_refund_type_display()}. '
                        f'Você tem {SELLER_REVIEW_DAYS} dias para responder.'
                    ),
                    metadata={
                        'refund_request_id': str(refund_request.id),
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'amount_requested': str(refund_request.amount_requested),
                        'refund_type': refund_request.refund_type,
                    },
                    idempotency_key=f'rr_seller_notify_{refund_request.id}_{seller.id}',
                )
        except Exception as exc:
            logger.warning(
                'Failed to notify sellers for RefundRequest %s: %s',
                refund_request.id, exc,
            )

    @staticmethod
    def _notify_buyer_approved(refund_request: RefundRequest):
        """Notifica o comprador que o reembolso foi aprovado."""
        try:
            from notifications.services import NotificationService
            from notifications.models import NotificationType

            amount = refund_request.amount_approved or refund_request.amount_requested
            order = refund_request.order
            NotificationService.notify(
                recipient=refund_request.requested_by,
                event_type=NotificationType.ORDER_STATUS_CHANGED,
                title=f'Reembolso aprovado — Pedido #{order.order_number}',
                body=(
                    f'Sua solicitação de reembolso de R$ {amount:.2f} '
                    f'para o pedido #{order.order_number} foi aprovada. '
                    f'O valor será creditado em até 10 dias úteis.'
                ),
                metadata={
                    'refund_request_id': str(refund_request.id),
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'amount_approved': str(amount),
                },
                idempotency_key=f'rr_buyer_approved_{refund_request.id}',
            )
        except Exception as exc:
            logger.warning(
                'Failed to notify buyer (approved) for RefundRequest %s: %s',
                refund_request.id, exc,
            )

    @staticmethod
    def _notify_buyer_rejected(refund_request: RefundRequest):
        """Notifica o comprador que o reembolso foi rejeitado."""
        try:
            from notifications.services import NotificationService
            from notifications.models import NotificationType

            order = refund_request.order
            NotificationService.notify(
                recipient=refund_request.requested_by,
                event_type=NotificationType.ORDER_STATUS_CHANGED,
                title=f'Solicitação de reembolso rejeitada — Pedido #{order.order_number}',
                body=(
                    f'Sua solicitação de reembolso para o pedido #{order.order_number} '
                    f'foi rejeitada pelo vendedor. '
                    f'Motivo: {refund_request.reason_seller}. '
                    f'Você pode escalar para a plataforma em até '
                    f'{BUYER_ESCALATION_DAYS} dias.'
                ),
                metadata={
                    'refund_request_id': str(refund_request.id),
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'reason_seller': refund_request.reason_seller,
                },
                idempotency_key=f'rr_buyer_rejected_{refund_request.id}',
            )
        except Exception as exc:
            logger.warning(
                'Failed to notify buyer (rejected) for RefundRequest %s: %s',
                refund_request.id, exc,
            )

    @staticmethod
    def _notify_platform_escalated(refund_request: RefundRequest):
        """Notifica staff que há uma disputa escalada para revisão."""
        try:
            from notifications.services import NotificationService
            from notifications.models import NotificationType
            from django.contrib.auth import get_user_model

            User = get_user_model()
            staff_users = User.objects.filter(is_staff=True, is_active=True)
            order = refund_request.order

            for staff in staff_users:
                NotificationService.notify(
                    recipient=staff,
                    event_type=NotificationType.DISPUTE_OPENED,
                    title=f'Reembolso escalado — Pedido #{order.order_number}',
                    body=(
                        f'Uma solicitação de reembolso de R$ {refund_request.amount_requested:.2f} '
                        f'foi escalada para revisão da plataforma. '
                        f'Pedido #{order.order_number}. '
                        f'Tipo: {refund_request.get_refund_type_display()}.'
                    ),
                    metadata={
                        'refund_request_id': str(refund_request.id),
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'refund_type': refund_request.refund_type,
                        'amount_requested': str(refund_request.amount_requested),
                    },
                    idempotency_key=f'rr_staff_escalated_{refund_request.id}_{staff.id}',
                )
        except Exception as exc:
            logger.warning(
                'Failed to notify platform for RefundRequest %s: %s',
                refund_request.id, exc,
            )

    @staticmethod
    def _notify_platform_decision(refund_request: RefundRequest, approved: bool):
        """Notifica comprador e vendedores sobre decisão da plataforma."""
        try:
            from notifications.services import NotificationService
            from notifications.models import NotificationType

            order = refund_request.order
            verb = 'aprovado' if approved else 'rejeitado'

            # Comprador
            NotificationService.notify(
                recipient=refund_request.requested_by,
                event_type=NotificationType.ORDER_STATUS_CHANGED,
                title=f'Decisão da plataforma — Pedido #{order.order_number}',
                body=(
                    f'A plataforma {verb} sua solicitação de reembolso '
                    f'para o pedido #{order.order_number}. '
                    f'Motivo: {refund_request.reason_platform}.'
                ),
                metadata={
                    'refund_request_id': str(refund_request.id),
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'approved': approved,
                },
                idempotency_key=f'rr_platform_decision_buyer_{refund_request.id}',
            )

            # Vendedores
            seen = set()
            for item in order.items.select_related('seller').all():
                seller = item.seller
                if seller.id in seen:
                    continue
                seen.add(seller.id)
                NotificationService.notify(
                    recipient=seller,
                    event_type=NotificationType.ORDER_STATUS_CHANGED,
                    title=f'Decisão da plataforma — Pedido #{order.order_number}',
                    body=(
                        f'A plataforma {verb} a solicitação de reembolso '
                        f'para o pedido #{order.order_number}. '
                        f'Motivo: {refund_request.reason_platform}.'
                    ),
                    metadata={
                        'refund_request_id': str(refund_request.id),
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'approved': approved,
                    },
                    idempotency_key=f'rr_platform_decision_seller_{refund_request.id}_{seller.id}',
                )
        except Exception as exc:
            logger.warning(
                'Failed to notify platform decision for RefundRequest %s: %s',
                refund_request.id, exc,
            )

    @staticmethod
    def _notify_refunded(refund_request: RefundRequest):
        """Notifica comprador e vendedores que o reembolso foi efetivado."""
        try:
            from notifications.services import NotificationService
            from notifications.models import NotificationType

            order = refund_request.order
            amount = refund_request.amount_approved or refund_request.amount_requested

            # Comprador
            NotificationService.notify(
                recipient=refund_request.requested_by,
                event_type=NotificationType.ORDER_STATUS_CHANGED,
                title=f'Reembolso efetivado — Pedido #{order.order_number}',
                body=(
                    f'O reembolso de R$ {amount:.2f} para o pedido '
                    f'#{order.order_number} foi processado com sucesso. '
                    f'O crédito aparecerá em sua fatura em até 10 dias úteis.'
                ),
                metadata={
                    'refund_request_id': str(refund_request.id),
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'amount_refunded': str(amount),
                    'stripe_refund_id': refund_request.stripe_refund_id,
                },
                idempotency_key=f'rr_refunded_buyer_{refund_request.id}',
            )

            # Vendedores
            seen = set()
            for item in order.items.select_related('seller').all():
                seller = item.seller
                if seller.id in seen:
                    continue
                seen.add(seller.id)
                NotificationService.notify(
                    recipient=seller,
                    event_type=NotificationType.ORDER_STATUS_CHANGED,
                    title=f'Reembolso efetivado — Pedido #{order.order_number}',
                    body=(
                        f'O reembolso de R$ {amount:.2f} foi processado para o pedido '
                        f'#{order.order_number}. '
                        f'Os valores correspondentes foram revertidos da sua conta Stripe.'
                    ),
                    metadata={
                        'refund_request_id': str(refund_request.id),
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'amount_refunded': str(amount),
                    },
                    idempotency_key=f'rr_refunded_seller_{refund_request.id}_{seller.id}',
                )
        except Exception as exc:
            logger.warning(
                'Failed to notify refunded for RefundRequest %s: %s',
                refund_request.id, exc,
            )
