"""
Tests for TransferDispatchService

Validates:
- Correct split calculation per seller
- Transfer creation with source_transaction (charge_id)
- Idempotency key format
- Handling sellers without stripe_account_id
- PaymentSplit record creation
- Dispatch continues for other sellers when one fails
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock, call
from django.test import TestCase
from django.contrib.auth import get_user_model

from products.models import (
    Products, Brand, Condition, MarketplaceListing, Category, Series
)
from orders.models import Order, OrderItem
from payments.models import Payment, PaymentSplit
from payments.services.transfer_dispatch_service import TransferDispatchService

import stripe

User = get_user_model()


class TestTransferDispatchServiceSplitCalculation(TestCase):
    """Unit tests for calculate_seller_split"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            email='buyer@test.com', password='pass'
        )
        self.seller = User.objects.create_user(
            email='seller@test.com', password='pass',
            stripe_account_id='acct_seller_001',
        )
        self.brand = Brand.objects.create(name='Brand', slug='brand')
        self.condition = Condition.objects.create(name='New', slug='new')
        self.category = Category.objects.create(name='Cat', slug='cat')
        self.series = Series.objects.create(name='Series', slug='series')
        self.product = Products.objects.create(
            name='Product', slug='product', category=self.category, series=self.series
        )
        self.listing = MarketplaceListing.objects.create(
            product=self.product, seller=self.seller,
            brand=self.brand, condition=self.condition,
            price=Decimal('100.00'), quantity=10, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('10.00'),
            width_cm=Decimal('10.00'), length_cm=Decimal('10.00'),
        )
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('20.00'),
            total=Decimal('220.00'),
            shipping_address={'street': 'Test'},
            status='pending_payment'
        )
        OrderItem.objects.create(
            order=self.order, listing=self.listing, seller=self.seller,
            quantity=2, unit_price=Decimal('100.00'), subtotal=Decimal('200.00'),
            shipping_cost=Decimal('20.00'),
            product_name='Product', product_code='', brand_name='Brand',
            condition_name='New', weight_kg=Decimal('1.00'),
            height_cm=Decimal('10.00'), width_cm=Decimal('10.00'),
            length_cm=Decimal('10.00'),
        )

    def test_calculate_seller_split_full_order(self):
        """
        New formula: fee only on product_amount (NOT shipping).
        product=200, shipping=20, fee=200*10%=20.00, net=200-20=180.00
        Transfer=net=180.00 (shipping excluded from Transfer)
        """
        platform_fee_pct = Decimal('10')
        (
            product_cents, shipping_cents, fee_cents, net_cents,
            product_dec, shipping_dec, fee_dec, net_dec
        ) = TransferDispatchService.calculate_seller_split(
            self.order, self.seller, platform_fee_pct
        )

        # product = 200 (items subtotal only)
        self.assertEqual(product_dec, Decimal('200.00'))
        # shipping = 20 (retained by platform)
        self.assertEqual(shipping_dec, Decimal('20.00'))
        # fee = 200 * 10% = 20.00 (applied only on product, NOT on shipping)
        self.assertEqual(fee_dec, Decimal('20.00'))
        # net = 200 - 20 = 180.00 (Transfer amount)
        self.assertEqual(net_dec, Decimal('180.00'))
        # cents
        self.assertEqual(product_cents, 20000)
        self.assertEqual(shipping_cents, 2000)
        self.assertEqual(fee_cents, 2000)
        self.assertEqual(net_cents, 18000)

    def test_calculate_seller_split_shipping_not_in_fee_base(self):
        """Verify shipping is excluded from fee calculation base"""
        platform_fee_pct = Decimal('10')
        (
            product_cents, shipping_cents, fee_cents, net_cents,
            product_dec, shipping_dec, fee_dec, net_dec
        ) = TransferDispatchService.calculate_seller_split(
            self.order, self.seller, platform_fee_pct
        )

        # Fee must equal product * 10%, not (product+shipping) * 10%
        expected_fee_on_product_only = (product_dec * Decimal('10') / Decimal('100')).quantize(
            Decimal('0.01')
        )
        expected_fee_on_gross = ((product_dec + shipping_dec) * Decimal('10') / Decimal('100')).quantize(
            Decimal('0.01')
        )
        self.assertEqual(fee_dec, expected_fee_on_product_only)
        self.assertNotEqual(fee_dec, expected_fee_on_gross)

    def test_calculate_total_platform_fee(self):
        """Total platform fee should be fee only on product amount (not shipping)"""
        total_fee = TransferDispatchService.calculate_total_platform_fee(self.order)
        # Only one seller: product=200, fee = 200 * 10% = 20.00 (shipping=20 excluded)
        self.assertEqual(total_fee, Decimal('20.00'))


class TestTransferDispatchServiceDispatch(TestCase):
    """Integration tests for dispatch_transfers_for_order"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            email='buyer2@test.com', password='pass'
        )
        self.seller1 = User.objects.create_user(
            email='seller1@test.com', password='pass',
            stripe_account_id='acct_seller_001',
        )
        self.seller2 = User.objects.create_user(
            email='seller2@test.com', password='pass',
            stripe_account_id='acct_seller_002',
        )
        self.brand = Brand.objects.create(name='Brand2', slug='brand2')
        self.condition = Condition.objects.create(name='Used', slug='used')
        self.category = Category.objects.create(name='Weights', slug='weights')
        self.series = Series.objects.create(name='Series2', slug='series2')
        self.product1 = Products.objects.create(
            name='ProductA', slug='producta', category=self.category, series=self.series
        )
        self.product2 = Products.objects.create(
            name='ProductB', slug='productb', category=self.category, series=self.series
        )
        self.listing1 = MarketplaceListing.objects.create(
            product=self.product1, seller=self.seller1,
            brand=self.brand, condition=self.condition,
            price=Decimal('150.00'), quantity=5, is_active=True,
            weight_kg=Decimal('2.00'), height_cm=Decimal('10.00'),
            width_cm=Decimal('10.00'), length_cm=Decimal('10.00'),
        )
        self.listing2 = MarketplaceListing.objects.create(
            product=self.product2, seller=self.seller2,
            brand=self.brand, condition=self.condition,
            price=Decimal('80.00'), quantity=5, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )

        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('230.00'),
            shipping_cost=Decimal('30.00'),
            total=Decimal('260.00'),
            shipping_address={'street': 'Test'},
            status='paid'
        )
        OrderItem.objects.create(
            order=self.order, listing=self.listing1, seller=self.seller1,
            quantity=1, unit_price=Decimal('150.00'), subtotal=Decimal('150.00'),
            shipping_cost=Decimal('20.00'),
            product_name='ProductA', product_code='', brand_name='Brand2',
            condition_name='Used', weight_kg=Decimal('2.00'),
            height_cm=Decimal('10.00'), width_cm=Decimal('10.00'),
            length_cm=Decimal('10.00'),
        )
        OrderItem.objects.create(
            order=self.order, listing=self.listing2, seller=self.seller2,
            quantity=1, unit_price=Decimal('80.00'), subtotal=Decimal('80.00'),
            shipping_cost=Decimal('10.00'),
            product_name='ProductB', product_code='', brand_name='Brand2',
            condition_name='Used', weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'), width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )

        self.payment = Payment.objects.create(
            order=self.order,
            user=self.buyer,
            stripe_payment_intent_id='pi_test_dispatch',
            stripe_charge_id='ch_test_dispatch',
            transfer_group='group_' + str(self.order.id),
            amount=Decimal('260.00'),
            currency='brl',
            payment_method='credit_card',
            status='succeeded',
            idempotency_key='pi_test_dispatch_key',
        )

    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    def test_dispatch_creates_transfers_for_each_seller(self, mock_transfer_create):
        """dispatch_transfers_for_order creates one Transfer per seller with correct amounts"""
        charge_id = 'ch_test_dispatch'

        # Mock transfer responses
        mock_transfer_s1 = MagicMock()
        mock_transfer_s1.id = 'tr_seller1_001'
        mock_transfer_s2 = MagicMock()
        mock_transfer_s2.id = 'tr_seller2_001'
        mock_transfer_create.side_effect = [mock_transfer_s1, mock_transfer_s2]

        splits = TransferDispatchService.dispatch_transfers_for_order(
            order=self.order,
            payment=self.payment,
            charge_id=charge_id,
        )

        # Two sellers — two splits
        self.assertEqual(len(splits), 2)

        # Both should be dispatched
        dispatched = [s for s in splits if s.transfer_status == 'dispatched']
        self.assertEqual(len(dispatched), 2)

        # Stripe.Transfer.create called twice
        self.assertEqual(mock_transfer_create.call_count, 2)

        # Verify source_transaction is set on each call
        for call_args in mock_transfer_create.call_args_list:
            kwargs = call_args[1]  # keyword args
            self.assertIn('source_transaction', kwargs)
            self.assertEqual(kwargs['source_transaction'], charge_id)

        # Verify new fields on splits
        for split in splits:
            # product_amount and shipping_amount must be populated
            self.assertGreater(split.product_amount, 0)
            self.assertGreaterEqual(split.shipping_amount, 0)
            # gross_amount = product + shipping (backward compat)
            self.assertEqual(split.gross_amount, split.product_amount + split.shipping_amount)
            # net_amount = product - fee (shipping excluded)
            self.assertEqual(split.net_amount, split.product_amount - split.platform_fee_amount)

    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    def test_transfer_amount_excludes_shipping(self, mock_transfer_create):
        """Transfer amount must be net (product - fee) — shipping must NOT be included"""
        charge_id = 'ch_test_shipping_excluded'

        mock_tr_s1 = MagicMock()
        mock_tr_s1.id = 'tr_no_shipping_1'
        mock_tr_s2 = MagicMock()
        mock_tr_s2.id = 'tr_no_shipping_2'
        mock_transfer_create.side_effect = [mock_tr_s1, mock_tr_s2]

        splits = TransferDispatchService.dispatch_transfers_for_order(
            order=self.order,
            payment=self.payment,
            charge_id=charge_id,
        )

        for call_args, split in zip(mock_transfer_create.call_args_list, splits):
            kwargs = call_args[1]
            # Transfer amount in cents must equal net_amount (no shipping)
            expected_net_cents = int(split.net_amount * 100)
            self.assertEqual(kwargs['amount'], expected_net_cents)
            # Metadata must contain product_amount and shipping_amount
            metadata = kwargs['metadata']
            self.assertIn('product_amount', metadata)
            self.assertIn('shipping_amount', metadata)
            # shipping_amount in metadata must match the split record
            self.assertEqual(Decimal(metadata['shipping_amount']), split.shipping_amount)

    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    def test_dispatch_uses_deterministic_idempotency_key(self, mock_transfer_create):
        """Idempotency key must be deterministic: tr_{order_id}_{seller_id}_{charge_id[:8]}"""
        charge_id = 'ch_test_idempkey'

        mock_tr = MagicMock()
        mock_tr.id = 'tr_idem_001'
        mock_transfer_create.return_value = mock_tr

        splits = TransferDispatchService.dispatch_transfers_for_order(
            order=self.order,
            payment=self.payment,
            charge_id=charge_id,
        )

        # Verify idempotency key format in call args
        for c in mock_transfer_create.call_args_list:
            idem_key = c[1].get('idempotency_key') or c[0][-1] if c[0] else None
            kwargs = c[1]
            self.assertIn('idempotency_key', kwargs)
            key = kwargs['idempotency_key']
            # Key format: tr_{order_id}_{seller_id}_{charge_id[:8]}
            self.assertTrue(key.startswith('tr_'))
            self.assertIn(charge_id[:8], key)

    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    def test_dispatch_skips_seller_without_stripe_account(self, mock_transfer_create):
        """Seller without stripe_account_id is marked failed, dispatch continues"""
        # Remove stripe_account_id from seller1
        self.seller1.stripe_account_id = ''
        self.seller1.save()

        mock_tr = MagicMock()
        mock_tr.id = 'tr_seller2_only'
        mock_transfer_create.return_value = mock_tr

        charge_id = 'ch_test_noacct'

        splits = TransferDispatchService.dispatch_transfers_for_order(
            order=self.order,
            payment=self.payment,
            charge_id=charge_id,
        )

        # Two splits created
        self.assertEqual(len(splits), 2)

        # One failed (seller1 without account), one dispatched (seller2)
        failed = [s for s in splits if s.transfer_status == 'failed']
        dispatched = [s for s in splits if s.transfer_status == 'dispatched']
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(dispatched), 1)

        # Only one Stripe transfer created (for seller2)
        self.assertEqual(mock_transfer_create.call_count, 1)

    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    def test_dispatch_raises_without_charge_id(self, mock_transfer_create):
        """dispatch_transfers_for_order raises TransferDispatchError if charge_id is empty"""
        from payments.services.transfer_dispatch_service import TransferDispatchError

        with self.assertRaises(TransferDispatchError):
            TransferDispatchService.dispatch_transfers_for_order(
                order=self.order,
                payment=self.payment,
                charge_id='',
            )

        mock_transfer_create.assert_not_called()

    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    def test_dispatch_idempotent_for_already_dispatched_split(self, mock_transfer_create):
        """Re-running dispatch for an already dispatched split skips it"""
        charge_id = 'ch_test_idem_dispatch'

        # Pre-create a dispatched split for seller1
        PaymentSplit.objects.create(
            payment=self.payment,
            seller=self.seller1,
            gross_amount=Decimal('170.00'),
            platform_fee_amount=Decimal('17.00'),
            net_amount=Decimal('153.00'),
            stripe_transfer_id='tr_already_dispatched',
            transfer_status='dispatched',
        )

        mock_tr = MagicMock()
        mock_tr.id = 'tr_new_for_seller2'
        mock_transfer_create.return_value = mock_tr

        splits = TransferDispatchService.dispatch_transfers_for_order(
            order=self.order,
            payment=self.payment,
            charge_id=charge_id,
        )

        # Both splits exist
        self.assertEqual(len(splits), 2)

        # Stripe.Transfer.create called only once (for seller2 — seller1 skipped)
        self.assertEqual(mock_transfer_create.call_count, 1)

    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    def test_dispatch_marks_split_failed_on_stripe_error(self, mock_transfer_create):
        """When Stripe raises an error, split is marked failed and dispatch continues"""
        mock_transfer_create.side_effect = stripe.error.StripeError('Network error')

        charge_id = 'ch_test_stripe_error'

        splits = TransferDispatchService.dispatch_transfers_for_order(
            order=self.order,
            payment=self.payment,
            charge_id=charge_id,
        )

        # Two splits, both failed (Stripe error for both)
        failed = [s for s in splits if s.transfer_status == 'failed']
        self.assertEqual(len(failed), 2)

        # Error message stored
        for split in failed:
            self.assertIn('error_message', split.__dict__)
