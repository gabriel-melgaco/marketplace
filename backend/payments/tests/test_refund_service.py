"""
Tests for RefundService

Validates:
- Refund uses OrderStateMachine (no direct assignment)
- Transfer Reversals are created for dispatched splits
- Partial refund creates proportional reversals
- Idempotency keys are deterministic
- Failures on reversals don't abort refund
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from products.models import (
    Products, Brand, Condition, MarketplaceListing, Category, Series
)
from orders.models import Order, OrderItem, OrderStatusHistory
from payments.models import Payment, PaymentSplit
from payments.refund_service import RefundService, RefundError

User = get_user_model()


class TestRefundServiceOrderStateMachine(TestCase):
    """Test that RefundService uses OrderStateMachine, not direct assignment"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            email='buyer_ref@test.com', password='pass'
        )
        self.seller = User.objects.create_user(
            email='seller_ref@test.com', password='pass',
            stripe_account_id='acct_ref_001',
        )
        self.category = Category.objects.create(name='CatRef', slug='catref')
        self.series = Series.objects.create(name='SeriesRef', slug='seriesref')
        self.product = Products.objects.create(
            name='ProdRef', slug='prodref', category=self.category, series=self.series
        )
        self.brand = Brand.objects.create(name='BrandRef', slug='brandref')
        self.condition = Condition.objects.create(name='NewRef', slug='newref')
        self.listing = MarketplaceListing.objects.create(
            product=self.product, seller=self.seller,
            brand=self.brand, condition=self.condition,
            price=Decimal('100.00'), quantity=5, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('10.00'),
            total=Decimal('110.00'),
            shipping_address={'street': 'Test'},
            status='paid'  # Must be 'paid' for REFUNDED transition to be valid
        )
        OrderItem.objects.create(
            order=self.order, listing=self.listing, seller=self.seller,
            quantity=1, unit_price=Decimal('100.00'), subtotal=Decimal('100.00'),
            shipping_cost=Decimal('10.00'),
            product_name='ProdRef', product_code='', brand_name='BrandRef',
            condition_name='NewRef', weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'), width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )
        self.payment = Payment.objects.create(
            order=self.order, user=self.buyer,
            stripe_payment_intent_id='pi_ref_001',
            stripe_charge_id='ch_ref_001',
            transfer_group='group_' + str(self.order.id),
            amount=Decimal('110.00'),
            currency='brl',
            payment_method='credit_card',
            status='succeeded',
            idempotency_key='pi_ref_001_key',
        )
        self.split = PaymentSplit.objects.create(
            payment=self.payment,
            seller=self.seller,
            gross_amount=Decimal('110.00'),
            platform_fee_amount=Decimal('11.00'),
            net_amount=Decimal('99.00'),
            stripe_transfer_id='tr_ref_001',
            transfer_status='dispatched',
        )

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_refund_uses_order_state_machine(self, mock_refund_create, mock_reversal):
        """Refund transitions order via OrderStateMachine, not direct assignment"""
        mock_refund = MagicMock()
        mock_refund.id = 're_test_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund
        mock_reversal.return_value = MagicMock(id='rev_test_001')

        initial_history_count = OrderStatusHistory.objects.filter(
            order=self.order
        ).count()

        RefundService.create_refund(payment=self.payment, amount=None, reason='test')

        # Order status changed to refunded via StateMachine
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'refunded')

        # OrderStatusHistory record created (proves StateMachine was used)
        new_history = OrderStatusHistory.objects.filter(order=self.order).count()
        self.assertGreater(new_history, initial_history_count)

        # Payment status updated
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded')

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_refund_creates_transfer_reversal(self, mock_refund_create, mock_reversal):
        """Full refund creates Transfer Reversal for the dispatched split"""
        mock_refund = MagicMock()
        mock_refund.id = 're_test_002'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund
        mock_reversal.return_value = MagicMock(id='rev_test_002')

        RefundService.create_refund(payment=self.payment, amount=None, reason='test')

        # Transfer Reversal was called
        mock_reversal.assert_called_once()
        call_args = mock_reversal.call_args
        # First positional arg should be the transfer_id
        self.assertEqual(call_args[0][0], 'tr_ref_001')
        call_kwargs = call_args[1]
        # Amount should equal net_amount in cents = 99.00 * 100 = 9900
        self.assertEqual(call_kwargs['amount'], 9900)

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_partial_refund_creates_proportional_reversal(self, mock_refund_create, mock_reversal):
        """Partial refund reverses proportional amount from seller transfer"""
        mock_refund = MagicMock()
        mock_refund.id = 're_partial_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund
        mock_reversal.return_value = MagicMock(id='rev_partial_001')

        # Partial refund: 55.00 out of 110.00 = 50%
        RefundService.create_refund(
            payment=self.payment,
            amount=Decimal('55.00'),
            reason='partial test'
        )

        mock_reversal.assert_called_once()
        call_kwargs = mock_reversal.call_args[1]

        # Expected reversal: 99.00 * (55/110) = 99.00 * 0.5 = 49.50 → 4950 cents
        self.assertEqual(call_kwargs['amount'], 4950)

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_refund_uses_deterministic_idempotency_key(self, mock_refund_create, mock_reversal):
        """Refund idempotency key is deterministic: re_{payment.id}_{date}"""
        from django.utils import timezone

        mock_refund = MagicMock()
        mock_refund.id = 're_idem_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund
        mock_reversal.return_value = MagicMock()

        RefundService.create_refund(payment=self.payment, amount=None, reason='idem test')

        call_kwargs = mock_refund_create.call_args[1]
        idem_key = call_kwargs.get('idempotency_key', '')

        today = timezone.now().date().isoformat()
        expected_key = f"re_{self.payment.id}_{today}"
        self.assertEqual(idem_key, expected_key)

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_reversal_failure_does_not_abort_refund(self, mock_refund_create, mock_reversal):
        """If Transfer Reversal fails, refund still completes (logged for manual reconciliation)"""
        import stripe

        mock_refund = MagicMock()
        mock_refund.id = 're_revfail_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund

        # Reversal raises Stripe error
        mock_reversal.side_effect = stripe.error.StripeError('Transfer reversal failed')

        # Should NOT raise — refund completes, reversal failure is logged
        RefundService.create_refund(payment=self.payment, amount=None, reason='reversal fail test')

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded')

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'refunded')

    def test_refund_raises_for_non_succeeded_payment(self):
        """Refund raises ValueError if payment is not in succeeded status"""
        self.payment.status = 'pending'
        self.payment.save()

        with self.assertRaises(ValueError) as ctx:
            RefundService.create_refund(payment=self.payment)

        self.assertIn('succeeded', str(ctx.exception))

    def test_refund_raises_for_amount_exceeding_payment(self):
        """Refund raises ValueError if amount > payment amount"""
        with self.assertRaises(ValueError) as ctx:
            RefundService.create_refund(
                payment=self.payment,
                amount=Decimal('999.99')
            )

        self.assertIn('cannot exceed', str(ctx.exception))

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_refund_skips_non_dispatched_splits(self, mock_refund_create, mock_reversal):
        """Refund does not create reversals for pending splits (no stripe_transfer_id)"""
        mock_refund = MagicMock()
        mock_refund.id = 're_pending_split_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund

        # Change split to pending (no transfer dispatched yet)
        self.split.transfer_status = 'pending'
        self.split.stripe_transfer_id = ''
        self.split.save()

        RefundService.create_refund(payment=self.payment, amount=None, reason='no split test')

        # No Transfer Reversal since split was not dispatched
        mock_reversal.assert_not_called()

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded')
