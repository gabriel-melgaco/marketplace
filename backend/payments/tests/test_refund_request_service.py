"""
Tests for RefundRequestService and RefundRequestStateMachine

Coverage:
    - create_request: elegibilidade, bloqueios, auto-aprovacao
    - seller_approve: fluxo completo com chamada Stripe
    - seller_reject: fluxo + escalada pelo comprador
    - buyer_escalate / buyer_withdraw
    - platform_decide: aprovacao e rejeicao
    - confirm_refunded: webhook confirma reembolso, atualiza Payment e Order
    - expire_seller_review / expire_buyer_escalation_window (tasks)
    - Transfer Reversal diferenciado por tipo (remorse nao reverte frete)
    - Transicoes invalidas da state machine
    - Idempotencia: confirm_refunded em status nao-pending retorna sem acao
"""

from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock, call
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from products.models import Products, Brand, Condition, MarketplaceListing, Category, Series
from orders.models import Order, OrderItem, OrderStatusHistory
from payments.models import Payment, PaymentSplit, RefundRequest, RefundRequestHistory
from payments.refund_request_service import (
    RefundRequestService,
    RefundRequestError,
    SELLER_REVIEW_DAYS,
    BUYER_ESCALATION_DAYS,
    PLATFORM_DECISION_DAYS,
    REMORSE_LIMIT_DAYS,
    NOT_RECEIVED_AUTO_DAYS,
    ACTIVE_STATUSES,
)
from payments.refund_request_state_machine import (
    RefundRequestStateMachine,
    RefundRequestStateMachineError,
)

User = get_user_model()


# ============================================================================
# Base fixture
# ============================================================================

class BaseRefundRequestTestCase(TestCase):
    """Shared fixture for all RefundRequest tests."""

    def setUp(self):
        self.buyer = User.objects.create_user(
            email='buyer@rr.test', password='pass'
        )
        self.seller = User.objects.create_user(
            email='seller@rr.test', password='pass',
            stripe_account_id='acct_rr_seller001',
        )
        self.staff = User.objects.create_user(
            email='staff@rr.test', password='pass',
            is_staff=True,
        )

        self.category = Category.objects.create(name='CatRR', slug='cat-rr')
        self.series = Series.objects.create(name='SeriesRR', slug='series-rr')
        self.product = Products.objects.create(
            name='ProdRR', slug='prod-rr',
            category=self.category, series=self.series,
        )
        self.brand = Brand.objects.create(name='BrandRR', slug='brand-rr')
        self.condition = Condition.objects.create(name='NewRR', slug='new-rr')
        self.listing = MarketplaceListing.objects.create(
            product=self.product, seller=self.seller,
            brand=self.brand, condition=self.condition,
            price=Decimal('200.00'), quantity=10, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )

        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('20.00'),
            total=Decimal('220.00'),
            shipping_address={'street': 'Rua Teste'},
            status='paid',
        )
        self.item = OrderItem.objects.create(
            order=self.order, listing=self.listing, seller=self.seller,
            quantity=1, unit_price=Decimal('200.00'), subtotal=Decimal('200.00'),
            shipping_cost=Decimal('20.00'),
            product_name='ProdRR', product_code='', brand_name='BrandRR',
            condition_name='NewRR', weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'), width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )

        self.payment = Payment.objects.create(
            order=self.order, user=self.buyer,
            stripe_payment_intent_id='pi_rr_001',
            stripe_charge_id='ch_rr_001',
            transfer_group='group_rr_001',
            amount=Decimal('220.00'),
            currency='brl',
            payment_method='credit_card',
            status='succeeded',
            idempotency_key='pi_rr_001_key',
        )
        self.split = PaymentSplit.objects.create(
            payment=self.payment,
            seller=self.seller,
            gross_amount=Decimal('220.00'),
            product_amount=Decimal('200.00'),
            shipping_amount=Decimal('20.00'),
            platform_fee_amount=Decimal('20.00'),
            net_amount=Decimal('180.00'),
            stripe_transfer_id='tr_rr_001',
            transfer_status='dispatched',
        )

    def _make_refund_request(self, status='seller_reviewing', refund_type='defective'):
        """Helper: create a RefundRequest bypassing service logic."""
        rr = RefundRequest.objects.create(
            payment=self.payment,
            order=self.order,
            requested_by=self.buyer,
            status=status,
            refund_type=refund_type,
            amount_requested=Decimal('220.00'),
            reason_buyer='Test reason',
        )
        RefundRequestHistory.objects.create(
            refund_request=rr,
            from_status='',
            to_status='requested',
            changed_by=self.buyer,
            actor_type='buyer',
            notes='',
        )
        if status != 'requested':
            RefundRequestHistory.objects.create(
                refund_request=rr,
                from_status='requested',
                to_status=status,
                actor_type='system',
                notes='',
            )
        return rr


# ============================================================================
# 1. create_request — elegibilidade
# ============================================================================

class TestCreateRequestEligibility(BaseRefundRequestTestCase):

    def test_payment_must_be_succeeded(self):
        self.payment.status = 'pending'
        self.payment.save()

        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.create_request(
                buyer=self.buyer,
                payment=self.payment,
                refund_type='defective',
                amount=Decimal('220.00'),
                reason='broken',
            )
        self.assertIn('confirmados', str(ctx.exception))

    def test_buyer_must_own_the_payment(self):
        other = User.objects.create_user(email='other@rr.test', password='pass')
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.create_request(
                buyer=other,
                payment=self.payment,
                refund_type='defective',
                amount=Decimal('100.00'),
                reason='not mine',
            )
        self.assertIn('comprador', str(ctx.exception))

    def test_amount_must_be_positive(self):
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.create_request(
                buyer=self.buyer,
                payment=self.payment,
                refund_type='defective',
                amount=Decimal('0.00'),
                reason='zero',
            )
        self.assertIn('maior que zero', str(ctx.exception))

    def test_amount_cannot_exceed_payment_amount(self):
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.create_request(
                buyer=self.buyer,
                payment=self.payment,
                refund_type='defective',
                amount=Decimal('999.00'),
                reason='too much',
            )
        self.assertIn('exceder', str(ctx.exception))

    def test_blocks_second_active_request(self):
        """Cannot open a second active RefundRequest for the same payment."""
        self._make_refund_request(status='seller_reviewing')

        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.create_request(
                buyer=self.buyer,
                payment=self.payment,
                refund_type='defective',
                amount=Decimal('100.00'),
                reason='duplicate',
            )
        self.assertIn('ativa', str(ctx.exception))

    @patch('payments.refund_request_service.RefundRequestService._notify_sellers')
    @patch('payments.refund_request_service.RefundRequestService._call_stripe_refund')
    def test_remorse_blocked_after_30_days(self, mock_stripe, mock_notify):
        """Remorse request blocked if payment is older than REMORSE_LIMIT_DAYS."""
        from django.db.models import F
        # Artificially age the payment
        Payment.objects.filter(pk=self.payment.pk).update(
            created_at=timezone.now() - timedelta(days=REMORSE_LIMIT_DAYS + 1)
        )
        self.payment.refresh_from_db()

        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.create_request(
                buyer=self.buyer,
                payment=self.payment,
                refund_type='remorse',
                amount=Decimal('100.00'),
                reason='changed my mind too late',
            )
        self.assertIn('arrependimento', str(ctx.exception))

    @patch('payments.refund_request_service.RefundRequestService._notify_sellers')
    @patch('payments.refund_request_service.RefundRequestService._call_stripe_refund')
    def test_remorse_allowed_within_30_days(self, mock_stripe, mock_notify):
        mock_stripe.return_value = None
        RefundRequestService.create_request(
            buyer=self.buyer,
            payment=self.payment,
            refund_type='remorse',
            amount=Decimal('100.00'),
            reason='changed my mind',
        )
        # Should not raise and should go to seller_reviewing (no auto-approval for remorse)
        rr = RefundRequest.objects.get(payment=self.payment, refund_type='remorse')
        self.assertEqual(rr.status, 'seller_reviewing')


# ============================================================================
# 2. create_request — auto-aprovacao
# ============================================================================

class TestCreateRequestAutoApproval(BaseRefundRequestTestCase):

    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_approved')
    @patch('payments.refund_request_service.RefundRequestService._call_stripe_refund')
    def test_not_received_auto_approved_after_30_days(self, mock_stripe, mock_notify):
        """not_received auto-approved when order is older than NOT_RECEIVED_AUTO_DAYS."""
        mock_stripe.return_value = None

        # Age the order
        Order.objects.filter(pk=self.order.pk).update(
            created_at=timezone.now() - timedelta(days=NOT_RECEIVED_AUTO_DAYS + 1)
        )
        self.order.refresh_from_db()
        # Order status must be shipped or processing
        self.order.status = 'shipped'
        self.order.save()

        rr = RefundRequestService.create_request(
            buyer=self.buyer,
            payment=self.payment,
            refund_type='not_received',
            amount=Decimal('220.00'),
            reason='not received after 30 days',
        )

        # Should be auto_approved → stripe_refund_pending (due to _call_stripe_refund → transition)
        # _call_stripe_refund is mocked, so status stays at auto_approved
        self.assertIn(rr.status, ('auto_approved', 'stripe_refund_pending'))
        mock_stripe.assert_called_once()
        mock_notify.assert_called_once()

    @patch('payments.refund_request_service.RefundRequestService._notify_sellers')
    def test_not_received_not_auto_approved_if_order_too_new(self, mock_notify):
        """not_received NOT auto-approved if order is recent."""
        # Order was just created (default)
        self.order.status = 'shipped'
        self.order.save()

        rr = RefundRequestService.create_request(
            buyer=self.buyer,
            payment=self.payment,
            refund_type='not_received',
            amount=Decimal('220.00'),
            reason='says not received but order is fresh',
        )

        self.assertEqual(rr.status, 'seller_reviewing')
        self.assertIsNotNone(rr.seller_deadline)
        mock_notify.assert_called_once()

    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_approved')
    @patch('payments.refund_request_service.RefundRequestService._call_stripe_refund')
    def test_duplicate_charge_auto_approved(self, mock_stripe, mock_notify_approved):
        """duplicate_charge auto-approved when another succeeded Payment exists for same order.

        Payment.order is a OneToOneField, so there can physically only be one Payment per
        Order in the DB. The auto-approval check uses Payment.objects.filter(order=...,
        status='succeeded').exclude(id=payment.id). We simulate a duplicate by patching
        that queryset to return a truthy result, testing only the business logic branch.
        """
        mock_stripe.return_value = None

        # Patch the queryset inside _check_auto_approval to simulate a duplicate payment
        mock_qs = MagicMock()
        mock_qs.exists.return_value = True

        with patch('payments.refund_request_service.Payment.objects') as mock_pm_objects:
            # _check_auto_approval calls Payment.objects.filter(...).exclude(...)
            mock_pm_objects.filter.return_value.exclude.return_value = mock_qs
            # RefundRequest.objects.filter (for active check) must still work for real
            # — so we only patch Payment.objects, not RefundRequest.objects
            rr = RefundRequestService.create_request(
                buyer=self.buyer,
                payment=self.payment,
                refund_type='duplicate_charge',
                amount=Decimal('220.00'),
                reason='charged twice',
            )

        self.assertIn(rr.status, ('auto_approved', 'stripe_refund_pending'))
        mock_stripe.assert_called_once()

    @patch('payments.refund_request_service.RefundRequestService._notify_sellers')
    def test_defective_never_auto_approved(self, mock_notify):
        """defective type is never auto-approved — always goes to seller review."""
        rr = RefundRequestService.create_request(
            buyer=self.buyer,
            payment=self.payment,
            refund_type='defective',
            amount=Decimal('220.00'),
            reason='product arrived broken',
        )
        self.assertEqual(rr.status, 'seller_reviewing')
        self.assertIsNotNone(rr.seller_deadline)

    @patch('payments.refund_request_service.RefundRequestService._notify_sellers')
    def test_create_request_creates_audit_trail(self, mock_notify):
        """Initial creation logs audit history entry."""
        rr = RefundRequestService.create_request(
            buyer=self.buyer,
            payment=self.payment,
            refund_type='defective',
            amount=Decimal('100.00'),
            reason='broken',
        )
        history = RefundRequestHistory.objects.filter(refund_request=rr)
        self.assertTrue(history.exists())
        # At minimum: initial 'requested' + 'seller_reviewing' transitions
        self.assertGreaterEqual(history.count(), 2)

    @patch('payments.refund_request_service.RefundRequestService._notify_sellers')
    def test_seller_deadline_set_for_non_auto_approved(self, mock_notify):
        """seller_deadline is set to now + SELLER_REVIEW_DAYS."""
        before = timezone.now()
        rr = RefundRequestService.create_request(
            buyer=self.buyer,
            payment=self.payment,
            refund_type='defective',
            amount=Decimal('100.00'),
            reason='broken',
        )
        after = timezone.now()

        expected_min = before + timedelta(days=SELLER_REVIEW_DAYS)
        expected_max = after + timedelta(days=SELLER_REVIEW_DAYS)
        self.assertGreaterEqual(rr.seller_deadline, expected_min)
        self.assertLessEqual(rr.seller_deadline, expected_max)


# ============================================================================
# 3. seller_approve
# ============================================================================

class TestSellerApprove(BaseRefundRequestTestCase):

    def setUp(self):
        super().setUp()
        self.rr = self._make_refund_request(status='seller_reviewing', refund_type='defective')
        self.rr.seller_deadline = timezone.now() + timedelta(days=3)
        self.rr.save()

    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_approved')
    @patch('payments.refund_request_service.RefundRequestService._call_stripe_refund')
    def test_seller_approve_transitions_to_approved(self, mock_stripe, mock_notify):
        mock_stripe.return_value = None

        result = RefundRequestService.seller_approve(
            refund_request=self.rr,
            seller=self.seller,
            amount_approved=Decimal('220.00'),
        )

        self.assertIn(result.status, ('approved', 'stripe_refund_pending'))
        self.assertEqual(result.amount_approved, Decimal('220.00'))
        self.assertEqual(result.decided_by, self.seller)
        mock_stripe.assert_called_once_with(self.rr)
        mock_notify.assert_called_once()

    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_approved')
    @patch('payments.refund_request_service.RefundRequestService._call_stripe_refund')
    def test_seller_approve_calls_stripe_with_approved_amount(self, mock_stripe, mock_notify):
        """_call_stripe_refund is called with the updated refund request."""
        mock_stripe.return_value = None

        partial = Decimal('110.00')
        RefundRequestService.seller_approve(
            refund_request=self.rr,
            seller=self.seller,
            amount_approved=partial,
        )

        self.rr.refresh_from_db()
        self.assertEqual(self.rr.amount_approved, partial)

    def test_seller_approve_blocked_if_wrong_status(self):
        self.rr.status = 'rejected'
        self.rr.save()

        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.seller_approve(
                refund_request=self.rr,
                seller=self.seller,
                amount_approved=Decimal('100.00'),
            )
        # Service message: 'Não é possível aprovar uma solicitação com status "rejected".'
        self.assertIn('aprovar', str(ctx.exception).lower())

    def test_seller_approve_blocked_if_seller_not_in_order(self):
        other_seller = User.objects.create_user(
            email='other_seller@rr.test', password='pass',
            stripe_account_id='acct_rr_other',
        )
        with self.assertRaises(RefundRequestError):
            RefundRequestService.seller_approve(
                refund_request=self.rr,
                seller=other_seller,
                amount_approved=Decimal('100.00'),
            )

    def test_seller_approve_blocked_if_amount_zero(self):
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.seller_approve(
                refund_request=self.rr,
                seller=self.seller,
                amount_approved=Decimal('0.00'),
            )
        self.assertIn('zero', str(ctx.exception))

    def test_seller_approve_blocked_if_amount_exceeds_requested(self):
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.seller_approve(
                refund_request=self.rr,
                seller=self.seller,
                amount_approved=Decimal('500.00'),
            )
        self.assertIn('exceder', str(ctx.exception))


# ============================================================================
# 4. seller_reject + buyer_escalate
# ============================================================================

class TestSellerRejectAndBuyerEscalate(BaseRefundRequestTestCase):

    def setUp(self):
        super().setUp()
        self.rr = self._make_refund_request(status='seller_reviewing', refund_type='defective')
        self.rr.seller_deadline = timezone.now() + timedelta(days=3)
        self.rr.save()

    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_rejected')
    def test_seller_reject_transitions_to_rejected(self, mock_notify):
        result = RefundRequestService.seller_reject(
            refund_request=self.rr,
            seller=self.seller,
            reason='Product is in perfect condition.',
        )
        self.assertEqual(result.status, 'rejected')
        self.assertEqual(result.reason_seller, 'Product is in perfect condition.')
        self.assertIsNotNone(result.escalation_deadline)
        mock_notify.assert_called_once()

    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_rejected')
    def test_seller_reject_requires_reason(self, mock_notify):
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.seller_reject(
                refund_request=self.rr,
                seller=self.seller,
                reason='',
            )
        self.assertIn('justificativa', str(ctx.exception))

    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_rejected')
    def test_seller_reject_blocked_if_wrong_status(self, mock_notify):
        self.rr.status = 'approved'
        self.rr.save()
        with self.assertRaises(RefundRequestError):
            RefundRequestService.seller_reject(
                refund_request=self.rr,
                seller=self.seller,
                reason='late rejection',
            )

    @patch('payments.refund_request_service.RefundRequestService._notify_platform_escalated')
    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_rejected')
    def test_buyer_escalate_after_rejection(self, mock_reject_notify, mock_escalate_notify):
        """Buyer can escalate a rejected request within the deadline window."""
        RefundRequestService.seller_reject(
            refund_request=self.rr,
            seller=self.seller,
            reason='I disagree',
        )

        result = RefundRequestService.buyer_escalate(
            refund_request=self.rr,
            buyer=self.buyer,
        )
        self.assertEqual(result.status, 'escalated')
        mock_escalate_notify.assert_called_once()

    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_rejected')
    def test_buyer_escalate_blocked_after_deadline(self, mock_notify):
        """Buyer cannot escalate after the escalation_deadline has passed."""
        RefundRequestService.seller_reject(
            refund_request=self.rr,
            seller=self.seller,
            reason='disagree',
        )
        # Force deadline to the past
        RefundRequest.objects.filter(pk=self.rr.pk).update(
            escalation_deadline=timezone.now() - timedelta(hours=1)
        )
        self.rr.refresh_from_db()

        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.buyer_escalate(
                refund_request=self.rr,
                buyer=self.buyer,
            )
        self.assertIn('expirou', str(ctx.exception))

    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_rejected')
    def test_buyer_escalate_blocked_if_wrong_buyer(self, mock_notify):
        """Only the original buyer can escalate."""
        RefundRequestService.seller_reject(
            refund_request=self.rr,
            seller=self.seller,
            reason='disagree',
        )
        other = User.objects.create_user(email='other_buyer@rr.test', password='pass')
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.buyer_escalate(
                refund_request=self.rr,
                buyer=other,
            )
        self.assertIn('comprador', str(ctx.exception))

    @patch('payments.refund_request_service.RefundRequestService._notify_platform_escalated')
    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_rejected')
    def test_escalated_sets_new_platform_deadline(self, mock_reject_notify, mock_escalate_notify):
        """After escalation, escalation_deadline updated to platform decision window."""
        RefundRequestService.seller_reject(
            refund_request=self.rr,
            seller=self.seller,
            reason='nope',
        )
        before = timezone.now()
        RefundRequestService.buyer_escalate(
            refund_request=self.rr,
            buyer=self.buyer,
        )
        after = timezone.now()

        self.rr.refresh_from_db()
        expected_min = before + timedelta(days=PLATFORM_DECISION_DAYS)
        expected_max = after + timedelta(days=PLATFORM_DECISION_DAYS)
        self.assertGreaterEqual(self.rr.escalation_deadline, expected_min)
        self.assertLessEqual(self.rr.escalation_deadline, expected_max)


# ============================================================================
# 5. buyer_withdraw
# ============================================================================

class TestBuyerWithdraw(BaseRefundRequestTestCase):

    @patch('payments.refund_request_service.RefundRequestService._notify_sellers')
    def test_buyer_can_withdraw_from_seller_reviewing(self, mock_notify):
        rr = self._make_refund_request(status='seller_reviewing')

        result = RefundRequestService.buyer_withdraw(
            refund_request=rr,
            buyer=self.buyer,
        )
        self.assertEqual(result.status, 'withdrawn')
        self.assertIsNotNone(result.resolved_at)

    def test_buyer_cannot_withdraw_from_refunded(self):
        rr = self._make_refund_request(status='refunded')
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.buyer_withdraw(
                refund_request=rr,
                buyer=self.buyer,
            )
        self.assertIn('retirar', str(ctx.exception))

    def test_buyer_cannot_withdraw_from_stripe_refund_pending(self):
        rr = self._make_refund_request(status='stripe_refund_pending')
        with self.assertRaises(RefundRequestError):
            RefundRequestService.buyer_withdraw(
                refund_request=rr,
                buyer=self.buyer,
            )

    def test_only_original_buyer_can_withdraw(self):
        rr = self._make_refund_request(status='seller_reviewing')
        other = User.objects.create_user(email='impostor@rr.test', password='pass')
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.buyer_withdraw(
                refund_request=rr,
                buyer=other,
            )
        self.assertIn('comprador', str(ctx.exception))


# ============================================================================
# 6. platform_decide
# ============================================================================

class TestPlatformDecide(BaseRefundRequestTestCase):

    def setUp(self):
        super().setUp()
        self.rr = self._make_refund_request(status='escalated', refund_type='defective')
        self.rr.escalation_deadline = timezone.now() + timedelta(days=5)
        self.rr.save()

    @patch('payments.refund_request_service.RefundRequestService._notify_platform_decision')
    @patch('payments.refund_request_service.RefundRequestService._call_stripe_refund')
    def test_platform_approve_transitions_to_platform_approved(self, mock_stripe, mock_notify):
        mock_stripe.return_value = None

        result = RefundRequestService.platform_decide(
            refund_request=self.rr,
            staff_user=self.staff,
            approve=True,
            reason='Buyer is correct.',
        )

        self.assertIn(result.status, ('platform_approved', 'stripe_refund_pending'))
        self.assertEqual(result.decided_by, self.staff)
        self.assertEqual(result.reason_platform, 'Buyer is correct.')
        mock_stripe.assert_called_once()
        mock_notify.assert_called_once_with(self.rr, approved=True)

    @patch('payments.refund_request_service.RefundRequestService._notify_platform_decision')
    def test_platform_reject_transitions_to_platform_rejected(self, mock_notify):
        result = RefundRequestService.platform_decide(
            refund_request=self.rr,
            staff_user=self.staff,
            approve=False,
            reason='Seller provided sufficient evidence.',
        )

        self.assertEqual(result.status, 'platform_rejected')
        mock_notify.assert_called_once_with(self.rr, approved=False)

    def test_platform_decide_blocked_if_not_escalated(self):
        self.rr.status = 'seller_reviewing'
        self.rr.save()

        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.platform_decide(
                refund_request=self.rr,
                staff_user=self.staff,
                approve=True,
                reason='forced',
            )
        self.assertIn('escalada', str(ctx.exception))

    def test_platform_decide_requires_reason(self):
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService.platform_decide(
                refund_request=self.rr,
                staff_user=self.staff,
                approve=False,
                reason='',
            )
        self.assertIn('justificativa', str(ctx.exception))

    @patch('payments.refund_request_service.RefundRequestService._notify_platform_decision')
    @patch('payments.refund_request_service.RefundRequestService._call_stripe_refund')
    def test_platform_approve_sets_amount_approved_if_missing(self, mock_stripe, mock_notify):
        """If amount_approved is not set, platform approval uses amount_requested."""
        mock_stripe.return_value = None
        self.assertIsNone(self.rr.amount_approved)

        RefundRequestService.platform_decide(
            refund_request=self.rr,
            staff_user=self.staff,
            approve=True,
            reason='Fine.',
        )

        self.rr.refresh_from_db()
        self.assertEqual(self.rr.amount_approved, self.rr.amount_requested)


# ============================================================================
# 7. confirm_refunded
# ============================================================================

class TestConfirmRefunded(BaseRefundRequestTestCase):

    def _make_stripe_refund_pending_rr(self):
        rr = RefundRequest.objects.create(
            payment=self.payment,
            order=self.order,
            requested_by=self.buyer,
            status='stripe_refund_pending',
            refund_type='defective',
            amount_requested=Decimal('220.00'),
            amount_approved=Decimal('220.00'),
            reason_buyer='Product broken',
        )
        return rr

    @patch('payments.refund_request_service.RefundRequestService._notify_refunded')
    @patch('payments.refund_request_service.RefundRequestService._reverse_seller_transfers')
    @patch('payments.refund_request_service.PaymentCallbackService', create=True)
    def test_confirm_refunded_transitions_to_refunded(
        self, mock_callback_cls, mock_reverse, mock_notify
    ):
        rr = self._make_stripe_refund_pending_rr()

        with patch('payments.refund_request_service.RefundRequestService._notify_refunded'):
            with patch('orders.services.PaymentCallbackService.on_refund_processed') as mock_on_refund:
                result = RefundRequestService.confirm_refunded(
                    refund_request=rr,
                    stripe_refund_id='re_rr_confirmed_001',
                )

        result.refresh_from_db()
        self.assertEqual(result.status, 'refunded')
        self.assertEqual(result.stripe_refund_id, 're_rr_confirmed_001')
        self.assertIsNotNone(result.resolved_at)

    @patch('payments.refund_request_service.RefundRequestService._notify_refunded')
    @patch('payments.refund_request_service.RefundRequestService._reverse_seller_transfers')
    def test_confirm_refunded_updates_payment(self, mock_reverse, mock_notify):
        rr = self._make_stripe_refund_pending_rr()

        with patch('orders.services.PaymentCallbackService.on_refund_processed'):
            RefundRequestService.confirm_refunded(
                refund_request=rr,
                stripe_refund_id='re_rr_pmt_update',
            )

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded')
        self.assertEqual(self.payment.refund_amount, Decimal('220.00'))
        self.assertEqual(self.payment.refund_reason, 'defective')
        self.assertIsNotNone(self.payment.refunded_at)
        self.assertIn('refund_request_id', self.payment.metadata)

    @patch('payments.refund_request_service.RefundRequestService._notify_refunded')
    @patch('payments.refund_request_service.RefundRequestService._reverse_seller_transfers')
    def test_confirm_refunded_is_idempotent(self, mock_reverse, mock_notify):
        """confirm_refunded called on non-stripe_refund_pending status does nothing."""
        rr = self._make_stripe_refund_pending_rr()

        with patch('orders.services.PaymentCallbackService.on_refund_processed'):
            RefundRequestService.confirm_refunded(rr, 're_first')

        # Call a second time — should silently skip
        initial_reverse_calls = mock_reverse.call_count

        rr.refresh_from_db()
        result = RefundRequestService.confirm_refunded(rr, 're_second')
        self.assertEqual(mock_reverse.call_count, initial_reverse_calls)  # no new calls
        self.assertEqual(result.status, 'refunded')

    @patch('payments.refund_request_service.RefundRequestService._notify_refunded')
    @patch('payments.refund_request_service.stripe.Transfer.create_reversal')
    def test_confirm_refunded_calls_reverse_seller_transfers(
        self, mock_reversal, mock_notify
    ):
        rr = self._make_stripe_refund_pending_rr()
        mock_reversal.return_value = MagicMock(id='rev_confirm_001')

        with patch('orders.services.PaymentCallbackService.on_refund_processed'):
            RefundRequestService.confirm_refunded(
                refund_request=rr,
                stripe_refund_id='re_rr_reversal_check',
            )

        # Transfer reversal should have been attempted for the dispatched split
        mock_reversal.assert_called_once()
        call_args = mock_reversal.call_args
        self.assertEqual(call_args[0][0], 'tr_rr_001')


# ============================================================================
# 8. Transfer Reversal por tipo
# ============================================================================

class TestTransferReversalByType(BaseRefundRequestTestCase):
    """
    Validates that _reverse_seller_transfers uses the correct base amount
    depending on refund_type.
    """

    def _make_rr_stripe_pending(self, refund_type, amount=Decimal('220.00')):
        return RefundRequest.objects.create(
            payment=self.payment,
            order=self.order,
            requested_by=self.buyer,
            status='stripe_refund_pending',
            refund_type=refund_type,
            amount_requested=amount,
            amount_approved=amount,
            reason_buyer='test',
        )

    @patch('payments.refund_request_service.stripe.Transfer.create_reversal')
    def test_remorse_reverses_only_product_amount(self, mock_reversal):
        """
        remorse: reversal_base = split.product_amount (NOT net_amount).
        split.product_amount = 200.00, refund_ratio = 220/220 = 1.0
        expected reversal = 200.00 * 1.0 = 200.00 → 20000 cents
        """
        mock_reversal.return_value = MagicMock(id='rev_remorse')
        rr = self._make_rr_stripe_pending(refund_type='remorse')

        RefundRequestService._reverse_seller_transfers(rr)

        mock_reversal.assert_called_once()
        call_kwargs = mock_reversal.call_args[1]
        self.assertEqual(call_kwargs['amount'], 20000)  # 200.00 * 100

    @patch('payments.refund_request_service.stripe.Transfer.create_reversal')
    def test_defective_reverses_full_net_amount(self, mock_reversal):
        """
        defective: reversal_base = split.net_amount.
        split.net_amount = 180.00, ratio = 220/220 = 1.0
        expected reversal = 180.00 → 18000 cents
        """
        mock_reversal.return_value = MagicMock(id='rev_defective')
        rr = self._make_rr_stripe_pending(refund_type='defective')

        RefundRequestService._reverse_seller_transfers(rr)

        mock_reversal.assert_called_once()
        call_kwargs = mock_reversal.call_args[1]
        self.assertEqual(call_kwargs['amount'], 18000)  # 180.00 * 100

    @patch('payments.refund_request_service.stripe.Transfer.create_reversal')
    def test_not_received_reverses_full_net_amount(self, mock_reversal):
        """not_received same as defective: uses net_amount."""
        mock_reversal.return_value = MagicMock(id='rev_not_received')
        rr = self._make_rr_stripe_pending(refund_type='not_received')

        RefundRequestService._reverse_seller_transfers(rr)

        mock_reversal.assert_called_once()
        call_kwargs = mock_reversal.call_args[1]
        self.assertEqual(call_kwargs['amount'], 18000)

    @patch('payments.refund_request_service.stripe.Transfer.create_reversal')
    def test_duplicate_charge_does_not_create_reversal(self, mock_reversal):
        """duplicate_charge: platform absorbs, no Transfer Reversal created."""
        rr = self._make_rr_stripe_pending(refund_type='duplicate_charge')

        RefundRequestService._reverse_seller_transfers(rr)

        mock_reversal.assert_not_called()

    @patch('payments.refund_request_service.stripe.Transfer.create_reversal')
    def test_partial_refund_reversal_is_proportional(self, mock_reversal):
        """
        Partial refund of 110.00 out of 220.00 = 50% ratio.
        defective: base = net_amount = 180.00 → 180 * 0.5 = 90.00 → 9000 cents
        """
        mock_reversal.return_value = MagicMock(id='rev_partial')
        rr = self._make_rr_stripe_pending(
            refund_type='defective', amount=Decimal('110.00')
        )

        RefundRequestService._reverse_seller_transfers(rr)

        mock_reversal.assert_called_once()
        call_kwargs = mock_reversal.call_args[1]
        self.assertEqual(call_kwargs['amount'], 9000)  # 90.00 * 100

    @patch('payments.refund_request_service.stripe.Transfer.create_reversal')
    def test_remorse_partial_reversal_is_proportional_on_product_only(self, mock_reversal):
        """
        Partial remorse refund of 110.00 out of 220.00 = 50%.
        base = product_amount = 200.00 → 200 * 0.5 = 100.00 → 10000 cents
        """
        mock_reversal.return_value = MagicMock(id='rev_remorse_partial')
        rr = self._make_rr_stripe_pending(
            refund_type='remorse', amount=Decimal('110.00')
        )

        RefundRequestService._reverse_seller_transfers(rr)

        mock_reversal.assert_called_once()
        call_kwargs = mock_reversal.call_args[1]
        self.assertEqual(call_kwargs['amount'], 10000)  # 100.00 * 100

    @patch('payments.refund_request_service.stripe.Transfer.create_reversal')
    def test_reversal_failure_does_not_abort_flow(self, mock_reversal):
        """If Transfer Reversal fails, no exception is raised — logged for reconciliation."""
        import stripe as stripe_module
        mock_reversal.side_effect = stripe_module.error.StripeError('reversal failed')
        rr = self._make_rr_stripe_pending(refund_type='defective')

        # Must not raise
        RefundRequestService._reverse_seller_transfers(rr)

        # Error message saved to split
        self.split.refresh_from_db()
        self.assertIn('Transfer Reversal failed', self.split.error_message)

    @patch('payments.refund_request_service.stripe.Transfer.create_reversal')
    def test_reversal_skipped_for_non_dispatched_split(self, mock_reversal):
        """Splits without a stripe_transfer_id are skipped."""
        self.split.transfer_status = 'pending'
        self.split.stripe_transfer_id = ''
        self.split.save()

        rr = self._make_rr_stripe_pending(refund_type='defective')
        RefundRequestService._reverse_seller_transfers(rr)

        mock_reversal.assert_not_called()

    @patch('payments.refund_request_service.stripe.Transfer.create_reversal')
    def test_reversal_idempotency_key_format(self, mock_reversal):
        """Reversal idempotency key follows format: rev_rr_{rr.id}_{transfer_id}_{date}"""
        mock_reversal.return_value = MagicMock(id='rev_idem')
        rr = self._make_rr_stripe_pending(refund_type='defective')

        RefundRequestService._reverse_seller_transfers(rr)

        call_kwargs = mock_reversal.call_args[1]
        today = timezone.now().date().isoformat()
        expected_key = f'rev_rr_{rr.id}_{self.split.stripe_transfer_id}_{today}'
        self.assertEqual(call_kwargs['idempotency_key'], expected_key)


# ============================================================================
# 9. _call_stripe_refund
# ============================================================================

class TestCallStripeRefund(BaseRefundRequestTestCase):

    def _make_approved_rr(self, refund_type='defective', amount=Decimal('220.00')):
        rr = RefundRequest.objects.create(
            payment=self.payment,
            order=self.order,
            requested_by=self.buyer,
            status='approved',
            refund_type=refund_type,
            amount_requested=amount,
            amount_approved=amount,
            reason_buyer='test',
        )
        RefundRequestHistory.objects.create(
            refund_request=rr, from_status='', to_status='approved',
            actor_type='seller', notes='',
        )
        return rr

    @patch('payments.refund_request_service.stripe.Refund.create')
    def test_call_stripe_refund_transitions_to_stripe_refund_pending(self, mock_create):
        mock_refund = MagicMock()
        mock_refund.id = 're_test_pending'
        mock_refund.status = 'pending'
        mock_create.return_value = mock_refund

        rr = self._make_approved_rr()
        RefundRequestService._call_stripe_refund(rr)

        rr.refresh_from_db()
        self.assertEqual(rr.status, 'stripe_refund_pending')

    @patch('payments.refund_request_service.stripe.Refund.create')
    def test_call_stripe_refund_uses_amount_approved_over_requested(self, mock_create):
        """When amount_approved is set, Stripe receives amount_approved in cents."""
        mock_refund = MagicMock(id='re_approved_amount', status='pending')
        mock_create.return_value = mock_refund

        rr = self._make_approved_rr(amount=Decimal('110.00'))
        rr.amount_approved = Decimal('110.00')
        rr.save()

        RefundRequestService._call_stripe_refund(rr)

        call_kwargs = mock_create.call_args[1]
        self.assertEqual(call_kwargs['amount'], 11000)  # 110.00 * 100

    @patch('payments.refund_request_service.stripe.Refund.create')
    def test_call_stripe_refund_idempotency_key_format(self, mock_create):
        """Idempotency key follows format: re_rr_{refund_request.id}"""
        mock_refund = MagicMock(id='re_idem', status='pending')
        mock_create.return_value = mock_refund

        rr = self._make_approved_rr()
        RefundRequestService._call_stripe_refund(rr)

        call_kwargs = mock_create.call_args[1]
        self.assertEqual(call_kwargs['idempotency_key'], f're_rr_{rr.id}')

    @patch('payments.refund_request_service.stripe.Refund.create')
    def test_call_stripe_refund_raises_on_stripe_error(self, mock_create):
        import stripe as stripe_module
        mock_create.side_effect = stripe_module.error.InvalidRequestError(
            'Payment intent not found', param='payment_intent'
        )

        rr = self._make_approved_rr()
        with self.assertRaises(RefundRequestError) as ctx:
            RefundRequestService._call_stripe_refund(rr)
        self.assertIn('Stripe', str(ctx.exception))

    @patch('payments.refund_request_service.stripe.Refund.create')
    def test_call_stripe_refund_idempotency_hit_does_not_raise(self, mock_create):
        """IdempotencyError is silently handled (already created)."""
        import stripe as stripe_module
        mock_create.side_effect = stripe_module.error.IdempotencyError(
            'Idempotency key already used'
        )

        rr = self._make_approved_rr()
        # Should not raise — swallowed gracefully
        RefundRequestService._call_stripe_refund(rr)


# ============================================================================
# 10. expire_seller_review (task)
# ============================================================================

class TestExpireSellerReview(BaseRefundRequestTestCase):

    def test_expire_seller_review_transitions_to_escalated(self):
        rr = self._make_refund_request(status='seller_reviewing')
        rr.seller_deadline = timezone.now() - timedelta(hours=1)
        rr.save()

        with patch('payments.refund_request_service.RefundRequestService._notify_platform_escalated'):
            result = RefundRequestService.expire_seller_review(rr)

        self.assertEqual(result.status, 'escalated')
        self.assertIsNotNone(result.escalation_deadline)

    def test_expire_seller_review_is_idempotent_on_other_statuses(self):
        """If status is not seller_reviewing, returns without change."""
        rr = self._make_refund_request(status='approved')

        result = RefundRequestService.expire_seller_review(rr)
        self.assertEqual(result.status, 'approved')

    def test_expire_seller_review_sets_platform_deadline(self):
        rr = self._make_refund_request(status='seller_reviewing')
        rr.seller_deadline = timezone.now() - timedelta(hours=1)
        rr.save()

        before = timezone.now()
        with patch('payments.refund_request_service.RefundRequestService._notify_platform_escalated'):
            RefundRequestService.expire_seller_review(rr)
        after = timezone.now()

        rr.refresh_from_db()
        expected_min = before + timedelta(days=PLATFORM_DECISION_DAYS)
        expected_max = after + timedelta(days=PLATFORM_DECISION_DAYS)
        self.assertGreaterEqual(rr.escalation_deadline, expected_min)
        self.assertLessEqual(rr.escalation_deadline, expected_max)

    def test_expire_seller_review_creates_audit_history(self):
        rr = self._make_refund_request(status='seller_reviewing')
        rr.seller_deadline = timezone.now() - timedelta(hours=1)
        rr.save()

        history_before = RefundRequestHistory.objects.filter(refund_request=rr).count()
        with patch('payments.refund_request_service.RefundRequestService._notify_platform_escalated'):
            RefundRequestService.expire_seller_review(rr)

        history_after = RefundRequestHistory.objects.filter(refund_request=rr).count()
        self.assertGreater(history_after, history_before)


# ============================================================================
# 11. expire_buyer_escalation_window (task)
# ============================================================================

class TestExpireBuyerEscalationWindow(BaseRefundRequestTestCase):

    def test_rejected_transitions_to_closed(self):
        rr = self._make_refund_request(status='rejected')
        rr.escalation_deadline = timezone.now() - timedelta(hours=1)
        rr.save()

        result = RefundRequestService.expire_buyer_escalation_window(rr)

        self.assertEqual(result.status, 'closed')
        self.assertIsNotNone(result.resolved_at)

    def test_platform_rejected_transitions_to_closed(self):
        rr = self._make_refund_request(status='platform_rejected')
        rr.escalation_deadline = timezone.now() - timedelta(hours=1)
        rr.save()

        result = RefundRequestService.expire_buyer_escalation_window(rr)
        self.assertEqual(result.status, 'closed')

    def test_expire_buyer_escalation_window_idempotent_on_other_statuses(self):
        """Only 'rejected' and 'platform_rejected' are acted upon."""
        rr = self._make_refund_request(status='seller_reviewing')
        result = RefundRequestService.expire_buyer_escalation_window(rr)
        self.assertEqual(result.status, 'seller_reviewing')


# ============================================================================
# 12. State machine: transicoes invalidas
# ============================================================================

class TestRefundRequestStateMachine(BaseRefundRequestTestCase):

    def test_valid_transition_requested_to_seller_reviewing(self):
        rr = self._make_refund_request(status='requested')
        result = RefundRequestStateMachine.transition(
            refund_request=rr,
            to_status='seller_reviewing',
            actor_type='system',
        )
        self.assertEqual(result.status, 'seller_reviewing')

    def test_invalid_transition_raises_state_machine_error(self):
        rr = self._make_refund_request(status='requested')
        with self.assertRaises(RefundRequestStateMachineError) as ctx:
            RefundRequestStateMachine.transition(
                refund_request=rr,
                to_status='refunded',  # not allowed from requested
                actor_type='system',
            )
        self.assertIn('Transição inválida', str(ctx.exception))

    def test_terminal_status_refunded_cannot_transition(self):
        rr = self._make_refund_request(status='refunded')
        with self.assertRaises(RefundRequestStateMachineError):
            RefundRequestStateMachine.transition(
                refund_request=rr,
                to_status='requested',
                actor_type='system',
            )

    def test_terminal_status_withdrawn_cannot_transition(self):
        rr = self._make_refund_request(status='withdrawn')
        with self.assertRaises(RefundRequestStateMachineError):
            RefundRequestStateMachine.transition(
                refund_request=rr,
                to_status='seller_reviewing',
                actor_type='system',
            )

    def test_terminal_status_closed_cannot_transition(self):
        rr = self._make_refund_request(status='closed')
        with self.assertRaises(RefundRequestStateMachineError):
            RefundRequestStateMachine.transition(
                refund_request=rr,
                to_status='escalated',
                actor_type='system',
            )

    def test_transition_creates_history_entry(self):
        rr = self._make_refund_request(status='requested')
        history_before = RefundRequestHistory.objects.filter(refund_request=rr).count()

        RefundRequestStateMachine.transition(
            refund_request=rr,
            to_status='seller_reviewing',
            changed_by=self.seller,
            actor_type='seller',
            notes='Test note',
        )

        history_after = RefundRequestHistory.objects.filter(refund_request=rr).count()
        self.assertEqual(history_after, history_before + 1)

        last = RefundRequestHistory.objects.filter(refund_request=rr).order_by('-created_at').first()
        self.assertEqual(last.from_status, 'requested')
        self.assertEqual(last.to_status, 'seller_reviewing')
        self.assertEqual(last.actor_type, 'seller')
        self.assertEqual(last.notes, 'Test note')
        self.assertEqual(last.changed_by, self.seller)

    def test_transition_sets_resolved_at_for_terminal_states(self):
        for terminal in ('refunded', 'withdrawn', 'closed'):
            # Build valid path to reach that terminal status
            if terminal == 'withdrawn':
                rr = self._make_refund_request(status='requested')
                RefundRequestStateMachine.transition(rr, 'withdrawn', actor_type='buyer')
            elif terminal == 'closed':
                rr = self._make_refund_request(status='rejected')
                RefundRequestStateMachine.transition(rr, 'closed', actor_type='system')
            elif terminal == 'refunded':
                rr = self._make_refund_request(status='stripe_refund_pending')
                RefundRequestStateMachine.transition(rr, 'refunded', actor_type='system')

            rr.refresh_from_db()
            self.assertIsNotNone(
                rr.resolved_at,
                f'resolved_at should be set after transitioning to {terminal}'
            )

    def test_transition_does_not_set_resolved_at_for_non_terminal(self):
        rr = self._make_refund_request(status='requested')
        RefundRequestStateMachine.transition(rr, 'seller_reviewing', actor_type='system')
        rr.refresh_from_db()
        self.assertIsNone(rr.resolved_at)


# ============================================================================
# 13. Full flow integration: seller rejects, buyer escalates, platform approves
# ============================================================================

class TestFullFlowSellerRejectBuyerEscalate(BaseRefundRequestTestCase):

    @patch('payments.refund_request_service.RefundRequestService._notify_refunded')
    @patch('payments.refund_request_service.RefundRequestService._notify_platform_decision')
    @patch('payments.refund_request_service.RefundRequestService._notify_platform_escalated')
    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_rejected')
    @patch('payments.refund_request_service.RefundRequestService._notify_sellers')
    def test_full_flow_buyer_escalate_platform_approve(
        self, mock_sellers, mock_rejected, mock_escalated, mock_decision, mock_refunded
    ):
        """End-to-end: requested -> seller_reviewing -> rejected -> escalated
        -> platform_approved -> stripe_refund_pending -> refunded"""

        # 1. Create request
        rr = RefundRequestService.create_request(
            buyer=self.buyer,
            payment=self.payment,
            refund_type='defective',
            amount=Decimal('220.00'),
            reason='broken product',
        )
        self.assertEqual(rr.status, 'seller_reviewing')

        # 2. Seller rejects
        RefundRequestService.seller_reject(
            refund_request=rr,
            seller=self.seller,
            reason='Product is fine',
        )
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'rejected')

        # 3. Buyer escalates
        RefundRequestService.buyer_escalate(
            refund_request=rr,
            buyer=self.buyer,
        )
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'escalated')

        # 4. Platform approves
        with patch('payments.refund_request_service.stripe.Refund.create') as mock_refund_create:
            mock_refund_create.return_value = MagicMock(id='re_platform_ok', status='pending')
            RefundRequestService.platform_decide(
                refund_request=rr,
                staff_user=self.staff,
                approve=True,
                reason='Buyer evidence is compelling',
            )

        rr.refresh_from_db()
        self.assertEqual(rr.status, 'stripe_refund_pending')

        # 5. Webhook confirms refund
        with patch('payments.refund_request_service.stripe.Transfer.create_reversal') as mock_rev:
            mock_rev.return_value = MagicMock(id='rev_full_flow')
            with patch('orders.services.PaymentCallbackService.on_refund_processed'):
                RefundRequestService.confirm_refunded(
                    refund_request=rr,
                    stripe_refund_id='re_full_flow_end',
                )

        rr.refresh_from_db()
        self.assertEqual(rr.status, 'refunded')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded')

        # History should trace all transitions
        history = RefundRequestHistory.objects.filter(refund_request=rr).order_by('created_at')
        statuses = list(history.values_list('to_status', flat=True))
        self.assertIn('seller_reviewing', statuses)
        self.assertIn('rejected', statuses)
        self.assertIn('escalated', statuses)
        self.assertIn('stripe_refund_pending', statuses)
        self.assertIn('refunded', statuses)


# ============================================================================
# 14. Full flow integration: seller approves directly
# ============================================================================

class TestFullFlowSellerApprove(BaseRefundRequestTestCase):

    @patch('payments.refund_request_service.RefundRequestService._notify_refunded')
    @patch('payments.refund_request_service.RefundRequestService._notify_buyer_approved')
    @patch('payments.refund_request_service.RefundRequestService._notify_sellers')
    def test_full_flow_seller_approve(self, mock_sellers, mock_approved, mock_refunded):
        """requested -> seller_reviewing -> approved -> stripe_refund_pending -> refunded"""

        # 1. Create request
        rr = RefundRequestService.create_request(
            buyer=self.buyer,
            payment=self.payment,
            refund_type='defective',
            amount=Decimal('220.00'),
            reason='arrived broken',
        )
        self.assertEqual(rr.status, 'seller_reviewing')

        # 2. Seller approves
        with patch('payments.refund_request_service.stripe.Refund.create') as mock_refund:
            mock_refund.return_value = MagicMock(id='re_seller_ok', status='pending')
            RefundRequestService.seller_approve(
                refund_request=rr,
                seller=self.seller,
                amount_approved=Decimal('220.00'),
            )

        rr.refresh_from_db()
        self.assertEqual(rr.status, 'stripe_refund_pending')

        # 3. Webhook confirms
        with patch('payments.refund_request_service.stripe.Transfer.create_reversal') as mock_rev:
            mock_rev.return_value = MagicMock(id='rev_seller_flow')
            with patch('orders.services.PaymentCallbackService.on_refund_processed'):
                RefundRequestService.confirm_refunded(
                    refund_request=rr,
                    stripe_refund_id='re_seller_flow_done',
                )

        rr.refresh_from_db()
        self.assertEqual(rr.status, 'refunded')
