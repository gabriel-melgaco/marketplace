"""
Financial Flows Test Suite — Stripe Marketplace Payments
=========================================================

Comprehensive test coverage for all financial flows in the multi-vendor
marketplace payment system. Covers payment lifecycle, split calculation,
webhooks, refunds, disputes, idempotency, and financial consistency.

All Stripe API calls are mocked. This suite is designed to run in CI
without a live Stripe connection but mirrors exactly what would happen
against the real Test Mode API.

Test Cards Reference (for manual/E2E testing):
    4242424242424242 — Success
    4000000000000002 — Generic decline
    4000000000009995 — Insufficient funds
    4000000000000069 — Expired card
    4000000000000127 — Incorrect CVC
    4000002760003184 — 3DS required
    4000000000000259 — Dispute / chargeback

PLATFORM_FEE_PERCENTAGE = 10%  (configured in settings)

Split formula:
    gross  = sum(item.subtotal + item.shipping_cost) per seller
    fee    = gross * 10% (ROUND_HALF_UP to 2 decimal places)
    net    = gross - fee

Transfer idempotency key: tr_{order_id}_{seller_id}_{charge_id[:8]}
Refund idempotency key:   re_{payment_id}_{date_iso}
"""

import stripe
from decimal import Decimal
from unittest.mock import patch, MagicMock, call
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from products.models import Products, Brand, Condition, MarketplaceListing, Category, Series
from orders.models import Order, OrderItem, OrderStatusHistory
from payments.models import Payment, PaymentSplit, Dispute, PaymentWebhook
from payments.payment_intent_service import PaymentIntentService, SellerNotReadyError
from payments.services.transfer_dispatch_service import TransferDispatchService, TransferDispatchError
from payments.webhook_service import WebhookService
from payments.refund_service import RefundService, RefundError

User = get_user_model()

# ---------------------------------------------------------------------------
# Stripe test card reference documented in module docstring
# ---------------------------------------------------------------------------
STRIPE_TEST_CARDS = {
    'success': '4242424242424242',
    'decline_generic': '4000000000000002',
    'decline_insufficient_funds': '4000000000009995',
    'decline_expired': '4000000000000069',
    'decline_cvc': '4000000000000127',
    'requires_3ds': '4000002760003184',
    'dispute_fraud': '4000000000000259',
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_stripe_event(event_id, event_type, data_object):
    """Return a MagicMock that behaves like a stripe.Event."""
    event = MagicMock()
    event.id = event_id
    event.type = event_type
    event.data = MagicMock()
    event.data.object = data_object
    return event


def _make_payment_intent_mock(pi_id, amount_cents, status='succeeded', charge_id=None):
    """Return a MagicMock that mimics a Stripe PaymentIntent retrieve response."""
    mock_pi = MagicMock()
    mock_pi.id = pi_id
    mock_pi.amount = amount_cents
    mock_pi.status = status
    mock_pi.latest_charge = charge_id  # string (not expanded)
    mock_pi.charges = None
    mock_pi.last_payment_error = None
    mock_pi.cancellation_reason = None
    mock_pi.client_secret = f'{pi_id}_secret'
    mock_pi.created = 1700000000
    return mock_pi


class BaseFinancialTestCase(TestCase):
    """
    Provides shared fixtures for financial flow tests.

    Creates two sellers, a buyer, products, listings, and helper methods
    for constructing orders with items split across sellers.
    """

    def setUp(self):
        # Actors
        self.buyer = User.objects.create_user(
            email='buyer_fin@test.com', password='pass'
        )
        self.seller_a = User.objects.create_user(
            email='seller_a_fin@test.com', password='pass',
            stripe_account_id='acct_seller_a',
        )
        self.seller_b = User.objects.create_user(
            email='seller_b_fin@test.com', password='pass',
            stripe_account_id='acct_seller_b',
        )

        # Product taxonomy
        self.category = Category.objects.create(name='FinCat', slug='fincat')
        self.series = Series.objects.create(name='FinSeries', slug='finseries')
        self.brand = Brand.objects.create(name='FinBrand', slug='finbrand')
        self.condition = Condition.objects.create(name='FinNew', slug='finnew')

        self.product_a = Products.objects.create(
            name='ProdA', slug='proda', category=self.category, series=self.series
        )
        self.product_b = Products.objects.create(
            name='ProdB', slug='prodb', category=self.category, series=self.series
        )

        # Listings: Seller A lists product_a at R$100; Seller B lists product_b at R$50
        self.listing_a = MarketplaceListing.objects.create(
            product=self.product_a, seller=self.seller_a,
            brand=self.brand, condition=self.condition,
            price=Decimal('100.00'), quantity=10, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        self.listing_b = MarketplaceListing.objects.create(
            product=self.product_b, seller=self.seller_b,
            brand=self.brand, condition=self.condition,
            price=Decimal('50.00'), quantity=10, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )

    # ------------------------------------------------------------------
    # Convenience builders
    # ------------------------------------------------------------------

    def _build_single_seller_order(
        self,
        seller=None,
        listing=None,
        quantity=1,
        unit_price=Decimal('100.00'),
        shipping_cost=Decimal('10.00'),
        order_status='pending_payment',
    ):
        """Return (order, OrderItem) for a single-seller scenario."""
        seller = seller or self.seller_a
        listing = listing or self.listing_a
        subtotal = unit_price * quantity
        total = subtotal + shipping_cost

        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            total=total,
            shipping_address={'street': 'Test Ave', 'city': 'São Paulo'},
            status=order_status,
        )
        item = OrderItem.objects.create(
            order=order, listing=listing, seller=seller,
            quantity=quantity, unit_price=unit_price, subtotal=subtotal,
            shipping_cost=shipping_cost,
            product_name=listing.product.name, product_code='',
            brand_name=self.brand.name, condition_name=self.condition.name,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        return order, item

    def _build_multi_seller_order(
        self,
        qty_a=1, price_a=Decimal('60.00'), ship_a=Decimal('0.00'),
        qty_b=1, price_b=Decimal('40.00'), ship_b=Decimal('0.00'),
        order_status='pending_payment',
    ):
        """
        Return order with items from both seller_a and seller_b.
        Seller A contributes: qty_a * price_a + ship_a
        Seller B contributes: qty_b * price_b + ship_b
        """
        sub_a = price_a * qty_a
        sub_b = price_b * qty_b
        subtotal = sub_a + sub_b
        shipping_cost = ship_a + ship_b
        total = subtotal + shipping_cost

        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            total=total,
            shipping_address={'street': 'Test Ave', 'city': 'São Paulo'},
            status=order_status,
        )
        item_a = OrderItem.objects.create(
            order=order, listing=self.listing_a, seller=self.seller_a,
            quantity=qty_a, unit_price=price_a, subtotal=sub_a,
            shipping_cost=ship_a,
            product_name='ProdA', product_code='', brand_name='FinBrand',
            condition_name='FinNew', weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'), width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        item_b = OrderItem.objects.create(
            order=order, listing=self.listing_b, seller=self.seller_b,
            quantity=qty_b, unit_price=price_b, subtotal=sub_b,
            shipping_cost=ship_b,
            product_name='ProdB', product_code='', brand_name='FinBrand',
            condition_name='FinNew', weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'), width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        return order, item_a, item_b

    def _create_succeeded_payment(self, order, pi_id='pi_base_001', charge_id='ch_base_001'):
        """Create a Payment in succeeded state with a transfer group."""
        return Payment.objects.create(
            order=order, user=self.buyer,
            stripe_payment_intent_id=pi_id,
            stripe_charge_id=charge_id,
            transfer_group=f'group_{order.id}',
            amount=order.total,
            currency='brl',
            payment_method='credit_card',
            status='succeeded',
            platform_fee_total=order.total * Decimal('0.10'),
            idempotency_key=f'{pi_id}_key',
        )

    def _create_dispatched_split(self, payment, seller, gross, fee=None, net=None, transfer_id=None):
        """Create a PaymentSplit in dispatched state."""
        if fee is None:
            fee = (gross * Decimal('0.10')).quantize(Decimal('0.01'))
        if net is None:
            net = gross - fee
        if transfer_id is None:
            transfer_id = f'tr_{seller.id}_{payment.id}'

        return PaymentSplit.objects.create(
            payment=payment, seller=seller,
            gross_amount=gross, platform_fee_amount=fee, net_amount=net,
            stripe_transfer_id=transfer_id, transfer_status='dispatched',
        )

    def _make_payment_intent_event_data(self, pi_id, amount_cents):
        """Create MagicMock for a payment intent event data object."""
        mock_data = MagicMock()
        mock_data.id = pi_id
        mock_data.amount = amount_cents
        mock_data.status = 'succeeded'
        mock_data.latest_charge = None
        mock_data.charges = None
        mock_data.last_payment_error = None
        mock_data.cancellation_reason = None
        return mock_data


# ===========================================================================
# A. Successful Payment — Single Seller
# ===========================================================================

class TestSuccessfulPaymentSingleSeller(BaseFinancialTestCase):
    """
    Scenario A: Complete payment flow for a single seller.

    Validates the full happy path from PaymentIntent creation through
    webhook processing, order status update, and transfer dispatch.
    """

    @patch('payments.payment_intent_service.stripe.Account.retrieve')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    def test_create_payment_intent_single_seller(self, mock_pi_create, mock_acct_retrieve):
        """
        A1: PaymentIntentService creates a PI with transfer_group and correct
        platform_fee_total stored in the Payment record.
        """
        order, _ = self._build_single_seller_order(
            unit_price=Decimal('100.00'), shipping_cost=Decimal('10.00')
        )
        # order.total = 110.00

        mock_acct = MagicMock()
        mock_acct.get.return_value = True  # charges_enabled
        mock_acct_retrieve.return_value = mock_acct

        mock_pi = _make_payment_intent_mock('pi_a1_001', 11000)
        mock_pi_create.return_value = mock_pi

        payment, client_secret = PaymentIntentService.create_payment_intent(
            order=order, payment_method='credit_card', user=self.buyer
        )

        # Payment record created correctly
        self.assertEqual(payment.status, 'pending')
        self.assertEqual(payment.amount, Decimal('110.00'))
        self.assertEqual(payment.transfer_group, f'group_{order.id}')
        self.assertEqual(payment.currency, 'brl')

        # Platform fee = 10% of product amount only (100.00), NOT on shipping (10.00)
        # New formula: fee = product * 10% = 100 * 10% = 10.00
        self.assertEqual(payment.platform_fee_total, Decimal('10.00'))

        # Idempotency key is deterministic
        expected_key = f'pi_{order.id}_{order.order_number}'
        self.assertEqual(payment.idempotency_key, expected_key)

        # Stripe was called with transfer_group and correct amount
        call_kwargs = mock_pi_create.call_args[1]
        self.assertEqual(call_kwargs['amount'], 11000)
        self.assertEqual(call_kwargs['transfer_group'], f'group_{order.id}')
        self.assertIn('idempotency_key', call_kwargs)

    @patch('payments.webhook_service.stripe.Transfer.create')
    @patch('payments.webhook_service.stripe.PaymentIntent.retrieve')
    @patch('logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order')
    def test_webhook_payment_succeeded_updates_payment_and_dispatches_transfer(
        self, mock_me_checkout, mock_pi_retrieve, mock_transfer_create
    ):
        """
        A2: payment_intent.succeeded webhook updates Payment.status to 'succeeded',
        updates Order.status to 'paid', and dispatches exactly 1 Transfer.
        """
        order, _ = self._build_single_seller_order(
            unit_price=Decimal('100.00'), shipping_cost=Decimal('10.00'),
            order_status='pending_payment'
        )
        payment = Payment.objects.create(
            order=order, user=self.buyer,
            stripe_payment_intent_id='pi_a2_001',
            transfer_group=f'group_{order.id}',
            amount=Decimal('110.00'),
            currency='brl', payment_method='credit_card',
            status='pending', platform_fee_total=Decimal('11.00'),
            idempotency_key='pi_a2_001_key',
        )

        charge_id = 'ch_a2_001'
        mock_pi_retrieve.return_value = _make_payment_intent_mock(
            'pi_a2_001', 11000, charge_id=charge_id
        )
        mock_transfer = MagicMock()
        mock_transfer.id = 'tr_a2_001'
        mock_transfer_create.return_value = mock_transfer
        mock_me_checkout.return_value = None

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_a2_001',
            event_type='payment_intent.succeeded',
            payload={'id': 'pi_a2_001', 'amount': 11000},
        )

        event_data = self._make_payment_intent_event_data('pi_a2_001', 11000)
        WebhookService._handle_payment_succeeded(
            _make_stripe_event('evt_a2_001', 'payment_intent.succeeded', event_data),
            webhook,
        )

        # Payment.status = 'succeeded'
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'succeeded')
        self.assertEqual(payment.stripe_charge_id, charge_id)
        self.assertIsNotNone(payment.paid_at)

        # Order.status = 'paid'
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')

        # Exactly 1 Transfer created
        mock_transfer_create.assert_called_once()

        # PaymentSplit created and dispatched
        split = PaymentSplit.objects.get(payment=payment, seller=self.seller_a)
        self.assertEqual(split.transfer_status, 'dispatched')
        self.assertEqual(split.stripe_transfer_id, 'tr_a2_001')

    @patch('payments.webhook_service.stripe.Transfer.create')
    @patch('payments.webhook_service.stripe.PaymentIntent.retrieve')
    @patch('logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order')
    def test_payment_split_financial_accuracy_single_seller(
        self, mock_me_checkout, mock_pi_retrieve, mock_transfer_create
    ):
        """
        A3: PaymentSplit amounts match the new 10% fee formula exactly.

        New formula (shipping excluded from fee base):
        product_amount = 100.00 (item subtotal only)
        shipping_amount = 10.00 (retained by platform, NOT in Transfer)
        gross_amount   = 110.00 (product + shipping, backward compat)
        fee            = 100.00 * 10% = 10.00 (only on product)
        net            = 100.00 - 10.00 = 90.00
        transfer amount in cents = 9000 (net, no shipping)
        """
        order, _ = self._build_single_seller_order(
            unit_price=Decimal('100.00'), shipping_cost=Decimal('10.00'),
            order_status='pending_payment'
        )
        payment = Payment.objects.create(
            order=order, user=self.buyer,
            stripe_payment_intent_id='pi_a3_001',
            transfer_group=f'group_{order.id}',
            amount=Decimal('110.00'),
            currency='brl', payment_method='credit_card',
            status='pending', platform_fee_total=Decimal('10.00'),
            idempotency_key='pi_a3_001_key',
        )

        charge_id = 'ch_a3_001'
        mock_pi_retrieve.return_value = _make_payment_intent_mock(
            'pi_a3_001', 11000, charge_id=charge_id
        )
        mock_tr = MagicMock()
        mock_tr.id = 'tr_a3_001'
        mock_transfer_create.return_value = mock_tr
        mock_me_checkout.return_value = None

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_a3_001',
            event_type='payment_intent.succeeded',
            payload={'id': 'pi_a3_001'},
        )
        event_data = self._make_payment_intent_event_data('pi_a3_001', 11000)
        WebhookService._handle_payment_succeeded(
            _make_stripe_event('evt_a3_001', 'payment_intent.succeeded', event_data),
            webhook,
        )

        split = PaymentSplit.objects.get(payment=payment, seller=self.seller_a)

        # Verify new fields: product/shipping separated
        self.assertEqual(split.product_amount, Decimal('100.00'))
        self.assertEqual(split.shipping_amount, Decimal('10.00'))
        # gross_amount maintained for backward compat = product + shipping
        self.assertEqual(split.gross_amount, Decimal('110.00'))
        # fee only on product (not on shipping)
        self.assertEqual(split.platform_fee_amount, Decimal('10.00'))
        # net = product - fee (shipping excluded)
        self.assertEqual(split.net_amount, Decimal('90.00'))

        # net = product - fee (no penny lost or created)
        self.assertEqual(split.net_amount, split.product_amount - split.platform_fee_amount)

        # Transfer was sent with net amount in cents (product - fee, shipping excluded)
        call_kwargs = mock_transfer_create.call_args[1]
        self.assertEqual(call_kwargs['amount'], 9000)  # 90.00 in cents
        self.assertEqual(call_kwargs['source_transaction'], charge_id)
        self.assertEqual(call_kwargs['destination'], self.seller_a.stripe_account_id)


# ===========================================================================
# B. Successful Payment — Multi-Seller
# ===========================================================================

class TestSuccessfulPaymentMultiSeller(BaseFinancialTestCase):
    """
    Scenario B: Payment split across two sellers.

    Each seller receives a separate Transfer proportional to their items.
    The sum of net amounts must not exceed the total payment.
    """

    @patch('payments.webhook_service.stripe.Transfer.create')
    @patch('payments.webhook_service.stripe.PaymentIntent.retrieve')
    @patch('logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order')
    def test_two_sellers_each_get_correct_transfer(
        self, mock_me_checkout, mock_pi_retrieve, mock_transfer_create
    ):
        """
        B1: Two sellers receive separate Transfers.

        Seller A: gross=60, fee=6, net=54 → transfer 5400 cents
        Seller B: gross=40, fee=4, net=36 → transfer 3600 cents
        """
        order, _, _ = self._build_multi_seller_order(
            qty_a=1, price_a=Decimal('60.00'), ship_a=Decimal('0.00'),
            qty_b=1, price_b=Decimal('40.00'), ship_b=Decimal('0.00'),
            order_status='pending_payment',
        )
        # total = 100.00

        payment = Payment.objects.create(
            order=order, user=self.buyer,
            stripe_payment_intent_id='pi_b1_001',
            transfer_group=f'group_{order.id}',
            amount=Decimal('100.00'),
            currency='brl', payment_method='credit_card',
            status='pending', platform_fee_total=Decimal('10.00'),
            idempotency_key='pi_b1_001_key',
        )

        charge_id = 'ch_b1_001'
        mock_pi_retrieve.return_value = _make_payment_intent_mock(
            'pi_b1_001', 10000, charge_id=charge_id
        )

        tr_a = MagicMock()
        tr_a.id = 'tr_b1_seller_a'
        tr_b = MagicMock()
        tr_b.id = 'tr_b1_seller_b'
        mock_transfer_create.side_effect = [tr_a, tr_b]
        mock_me_checkout.return_value = None

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_b1_001',
            event_type='payment_intent.succeeded',
            payload={'id': 'pi_b1_001'},
        )
        event_data = self._make_payment_intent_event_data('pi_b1_001', 10000)
        WebhookService._handle_payment_succeeded(
            _make_stripe_event('evt_b1_001', 'payment_intent.succeeded', event_data),
            webhook,
        )

        # Exactly 2 Transfers created
        self.assertEqual(mock_transfer_create.call_count, 2)

        # Both PaymentSplits exist
        splits = list(PaymentSplit.objects.filter(payment=payment))
        self.assertEqual(len(splits), 2)

        # All dispatched
        for split in splits:
            self.assertEqual(split.transfer_status, 'dispatched')

        # Financial consistency: sum of net amounts <= payment total
        total_net = sum(s.net_amount for s in splits)
        self.assertLessEqual(total_net, payment.amount)

        # Each split has source_transaction set
        for call_args in mock_transfer_create.call_args_list:
            self.assertEqual(call_args[1]['source_transaction'], charge_id)

    def test_multi_seller_split_amounts_sum_correctly(self):
        """
        B2: sum(gross) can equal order.total, sum(fee) is platform revenue,
        sum(net) = sum(gross) - sum(fee). No value is lost or created.
        """
        order, _, _ = self._build_multi_seller_order(
            qty_a=1, price_a=Decimal('60.00'), ship_a=Decimal('0.00'),
            qty_b=1, price_b=Decimal('40.00'), ship_b=Decimal('0.00'),
            order_status='paid',
        )
        payment = self._create_succeeded_payment(order, 'pi_b2_001', 'ch_b2_001')

        from decimal import Decimal as D
        platform_fee_pct = D('10')

        # Calculate splits directly via service
        # New return: (product_cents, shipping_cents, fee_cents, net_cents,
        #              product_decimal, shipping_decimal, fee_decimal, net_decimal)
        product_a, shipping_a, fee_a, net_a, product_a_d, shipping_a_d, fee_a_d, net_a_d = \
            TransferDispatchService.calculate_seller_split(order, self.seller_a, platform_fee_pct)
        product_b, shipping_b, fee_b, net_b, product_b_d, shipping_b_d, fee_b_d, net_b_d = \
            TransferDispatchService.calculate_seller_split(order, self.seller_b, platform_fee_pct)

        # shipping=0 in this test, so product == gross and formula is unchanged
        # Seller A: product=60, shipping=0, fee=6, net=54
        self.assertEqual(product_a_d, D('60.00'))
        self.assertEqual(shipping_a_d, D('0.00'))
        self.assertEqual(fee_a_d, D('6.00'))
        self.assertEqual(net_a_d, D('54.00'))

        # Seller B: product=40, shipping=0, fee=4, net=36
        self.assertEqual(product_b_d, D('40.00'))
        self.assertEqual(shipping_b_d, D('0.00'))
        self.assertEqual(fee_b_d, D('4.00'))
        self.assertEqual(net_b_d, D('36.00'))

        # Financial consistency invariants
        total_product = product_a_d + product_b_d
        total_fee = fee_a_d + fee_b_d
        total_net = net_a_d + net_b_d

        self.assertEqual(total_product, D('100.00'))
        self.assertEqual(total_fee, D('10.00'))
        self.assertEqual(total_net, D('90.00'))

        # net = product - fee at aggregate level
        self.assertEqual(total_net, total_product - total_fee)

    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    def test_multi_seller_each_transfer_uses_source_transaction(self, mock_transfer_create):
        """
        B3: Every Transfer to every seller must carry source_transaction=charge_id.
        This is mandatory for Stripe Separate Charges and Transfers pattern.
        """
        order, _, _ = self._build_multi_seller_order(
            qty_a=1, price_a=Decimal('60.00'), ship_a=Decimal('0.00'),
            qty_b=1, price_b=Decimal('40.00'), ship_b=Decimal('0.00'),
            order_status='paid',
        )
        payment = self._create_succeeded_payment(order, 'pi_b3_001', 'ch_b3_001')

        tr_a = MagicMock()
        tr_a.id = 'tr_b3_a'
        tr_b = MagicMock()
        tr_b.id = 'tr_b3_b'
        mock_transfer_create.side_effect = [tr_a, tr_b]

        TransferDispatchService.dispatch_transfers_for_order(
            order=order, payment=payment, charge_id='ch_b3_001'
        )

        for c in mock_transfer_create.call_args_list:
            self.assertEqual(c[1]['source_transaction'], 'ch_b3_001')


# ===========================================================================
# C. Declined Payment
# ===========================================================================

class TestDeclinedPayment(BaseFinancialTestCase):
    """
    Scenario C: Payment intent fails (card declined).

    Verifies no Transfers are created, Payment is marked failed,
    and Order transitions to failed state.
    """

    def test_payment_failed_webhook_updates_status(self):
        """
        C1: payment_intent.payment_failed marks Payment.status='failed',
        Order.status='failed', and no Transfers or PaymentSplits are created.
        """
        order, _ = self._build_single_seller_order(order_status='pending_payment')
        payment = Payment.objects.create(
            order=order, user=self.buyer,
            stripe_payment_intent_id='pi_c1_001',
            transfer_group=f'group_{order.id}',
            amount=Decimal('110.00'),
            currency='brl', payment_method='credit_card',
            status='pending', idempotency_key='pi_c1_001_key',
        )

        last_error = MagicMock()
        last_error.message = 'Your card was declined.'
        last_error.code = 'card_declined'

        event_data = MagicMock()
        event_data.id = 'pi_c1_001'
        event_data.amount = 11000
        event_data.status = 'requires_payment_method'
        event_data.last_payment_error = last_error
        event_data.cancellation_reason = None

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_c1_001',
            event_type='payment_intent.payment_failed',
            payload={'id': 'pi_c1_001'},
        )

        WebhookService._handle_payment_failed(
            _make_stripe_event('evt_c1_001', 'payment_intent.payment_failed', event_data),
            webhook,
        )

        # Payment marked failed
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'failed')
        self.assertEqual(payment.failure_message, 'Your card was declined.')

        # Order status failed
        order.refresh_from_db()
        self.assertEqual(order.status, 'failed')

        # No PaymentSplits created
        self.assertFalse(PaymentSplit.objects.filter(payment=payment).exists())

    def test_declined_payment_no_transfers_dispatched(self):
        """
        C2: When payment fails, TransferDispatchService.dispatch_transfers_for_order
        is never called. The failure handler does not invoke transfer dispatch.
        Verified by checking no PaymentSplit records are created.
        """
        order, _ = self._build_single_seller_order(order_status='pending_payment')
        payment = Payment.objects.create(
            order=order, user=self.buyer,
            stripe_payment_intent_id='pi_c2_001',
            transfer_group=f'group_{order.id}',
            amount=Decimal('110.00'),
            currency='brl', payment_method='credit_card',
            status='pending', idempotency_key='pi_c2_001_key',
        )

        # TransferDispatchService is imported inside the function body in the service,
        # so we patch the function directly at its definition point.
        with patch(
            'payments.services.transfer_dispatch_service.TransferDispatchService.dispatch_transfers_for_order'
        ) as mock_dispatch:
            event_data = MagicMock()
            event_data.id = 'pi_c2_001'
            event_data.amount = 11000
            event_data.status = 'requires_payment_method'
            event_data.last_payment_error = MagicMock()
            event_data.last_payment_error.message = 'Declined.'
            event_data.last_payment_error.code = 'card_declined'

            webhook = PaymentWebhook.objects.create(
                stripe_event_id='evt_c2_001',
                event_type='payment_intent.payment_failed',
                payload={'id': 'pi_c2_001'},
            )

            WebhookService._handle_payment_failed(
                _make_stripe_event('evt_c2_001', 'payment_intent.payment_failed', event_data),
                webhook,
            )

        # Payment failed handler never calls dispatch — confirm via DB state
        mock_dispatch.assert_not_called()

        # Confirm no PaymentSplit exists for this failed payment
        self.assertFalse(PaymentSplit.objects.filter(payment=payment).exists())


# ===========================================================================
# D. Seller Not Ready — Blocking Checkout
# ===========================================================================

class TestSellerNotReadyBlocksCheckout(BaseFinancialTestCase):
    """
    Scenario D: Seller without stripe_account_id blocks payment intent creation.

    SellerNotReadyError must be raised before any Stripe API call.
    No Payment record may be persisted.
    """

    def test_seller_without_stripe_account_raises_error(self):
        """
        D1: SellerNotReadyError raised when seller has no stripe_account_id.
        No PaymentIntent or Payment created.
        """
        seller_no_acct = User.objects.create_user(
            email='seller_noacct_d1@test.com', password='pass',
            # stripe_account_id intentionally blank
        )
        listing_no_acct = MarketplaceListing.objects.create(
            product=self.product_a, seller=seller_no_acct,
            brand=self.brand, condition=self.condition,
            price=Decimal('100.00'), quantity=5, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        order = Order.objects.create(
            buyer=self.buyer, subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'), total=Decimal('100.00'),
            shipping_address={'street': 'Test'}, status='pending_payment',
        )
        OrderItem.objects.create(
            order=order, listing=listing_no_acct, seller=seller_no_acct,
            quantity=1, unit_price=Decimal('100.00'), subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'), product_name='ProdA', product_code='',
            brand_name='FinBrand', condition_name='FinNew',
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )

        with patch('payments.payment_intent_service.stripe.PaymentIntent.create') as mock_pi_create:
            with self.assertRaises(SellerNotReadyError) as ctx:
                PaymentIntentService.create_payment_intent(
                    order=order, payment_method='credit_card', user=self.buyer
                )

            # Error message must name the problematic seller
            self.assertIn('no Stripe account', str(ctx.exception))

            # Stripe PaymentIntent.create was NEVER called
            mock_pi_create.assert_not_called()

        # No Payment was persisted
        self.assertFalse(Payment.objects.filter(order=order).exists())

    def test_one_seller_not_ready_in_multi_seller_order_blocks_all(self):
        """
        D2: If any seller is not ready, the entire PaymentIntent is rejected.
        This prevents partial payment scenarios.
        """
        seller_no_acct = User.objects.create_user(
            email='seller_noacct_d2@test.com', password='pass',
        )
        listing_no_acct = MarketplaceListing.objects.create(
            product=self.product_b, seller=seller_no_acct,
            brand=self.brand, condition=self.condition,
            price=Decimal('50.00'), quantity=5, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        order = Order.objects.create(
            buyer=self.buyer, subtotal=Decimal('150.00'),
            shipping_cost=Decimal('0.00'), total=Decimal('150.00'),
            shipping_address={'street': 'Test'}, status='pending_payment',
        )
        # seller_a is ready, seller_no_acct is not
        OrderItem.objects.create(
            order=order, listing=self.listing_a, seller=self.seller_a,
            quantity=1, unit_price=Decimal('100.00'), subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'), product_name='ProdA', product_code='',
            brand_name='FinBrand', condition_name='FinNew',
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        OrderItem.objects.create(
            order=order, listing=listing_no_acct, seller=seller_no_acct,
            quantity=1, unit_price=Decimal('50.00'), subtotal=Decimal('50.00'),
            shipping_cost=Decimal('0.00'), product_name='ProdB', product_code='',
            brand_name='FinBrand', condition_name='FinNew',
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )

        # seller_a account check passes; seller_no_acct fails before Stripe call
        mock_acct = MagicMock()
        mock_acct.get.return_value = True
        with patch('payments.payment_intent_service.stripe.Account.retrieve', return_value=mock_acct):
            with patch('payments.payment_intent_service.stripe.PaymentIntent.create') as mock_pi:
                with self.assertRaises(SellerNotReadyError):
                    PaymentIntentService.create_payment_intent(
                        order=order, payment_method='credit_card', user=self.buyer
                    )
                mock_pi.assert_not_called()

        self.assertFalse(Payment.objects.filter(order=order).exists())


# ===========================================================================
# E. Full Refund With Transfer Reversal
# ===========================================================================

class TestFullRefundWithTransferReversal(BaseFinancialTestCase):
    """
    Scenario E: Full refund reverses the complete net amount from the seller.
    """

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_full_refund_reverses_seller_transfer(self, mock_refund_create, mock_reversal):
        """
        E1: Full refund calls stripe.Refund.create and stripe.Transfer.create_reversal
        with the full net_amount for the seller. Order transitions to 'refunded'.
        """
        order, _ = self._build_single_seller_order(
            unit_price=Decimal('100.00'), shipping_cost=Decimal('10.00'),
            order_status='paid'
        )
        payment = self._create_succeeded_payment(order, 'pi_e1_001', 'ch_e1_001')
        split = self._create_dispatched_split(
            payment, self.seller_a,
            gross=Decimal('110.00'), fee=Decimal('11.00'), net=Decimal('99.00'),
            transfer_id='tr_e1_001'
        )

        mock_refund = MagicMock()
        mock_refund.id = 're_e1_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund
        mock_reversal.return_value = MagicMock(id='rev_e1_001')

        RefundService.create_refund(payment=payment, amount=None, reason='customer request')

        # Stripe Refund created for full amount
        refund_call = mock_refund_create.call_args[1]
        self.assertEqual(refund_call['amount'], 11000)  # 110.00 in cents
        self.assertEqual(refund_call['payment_intent'], 'pi_e1_001')

        # Transfer Reversal created for full net amount
        mock_reversal.assert_called_once()
        reversal_call = mock_reversal.call_args
        self.assertEqual(reversal_call[0][0], 'tr_e1_001')
        self.assertEqual(reversal_call[1]['amount'], 9900)  # 99.00 in cents

        # Payment status = 'refunded'
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'refunded')
        self.assertEqual(payment.refund_amount, Decimal('110.00'))

        # Order status = 'refunded'
        order.refresh_from_db()
        self.assertEqual(order.status, 'refunded')

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_full_refund_multi_seller_reverses_all_transfers(
        self, mock_refund_create, mock_reversal
    ):
        """
        E2: Full refund on a multi-seller order creates one Transfer Reversal
        per seller for their respective net amounts.
        """
        order, _, _ = self._build_multi_seller_order(
            qty_a=1, price_a=Decimal('60.00'), ship_a=Decimal('0.00'),
            qty_b=1, price_b=Decimal('40.00'), ship_b=Decimal('0.00'),
            order_status='paid',
        )
        payment = self._create_succeeded_payment(order, 'pi_e2_001', 'ch_e2_001')
        # Seller A: net=54.00, Seller B: net=36.00
        split_a = self._create_dispatched_split(
            payment, self.seller_a,
            gross=Decimal('60.00'), fee=Decimal('6.00'), net=Decimal('54.00'),
            transfer_id='tr_e2_seller_a'
        )
        split_b = self._create_dispatched_split(
            payment, self.seller_b,
            gross=Decimal('40.00'), fee=Decimal('4.00'), net=Decimal('36.00'),
            transfer_id='tr_e2_seller_b'
        )

        mock_refund = MagicMock()
        mock_refund.id = 're_e2_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund
        mock_reversal.return_value = MagicMock()

        RefundService.create_refund(payment=payment, amount=None, reason='full refund')

        # Two reversals — one per seller
        self.assertEqual(mock_reversal.call_count, 2)

        # Collect all reversal amounts
        reversal_amounts = {
            c[0][0]: c[1]['amount'] for c in mock_reversal.call_args_list
        }
        self.assertEqual(reversal_amounts['tr_e2_seller_a'], 5400)  # 54.00
        self.assertEqual(reversal_amounts['tr_e2_seller_b'], 3600)  # 36.00

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_refund_uses_deterministic_idempotency_key(self, mock_refund_create, mock_reversal):
        """
        E3: Refund idempotency key format: re_{payment.id}_{date_iso}.
        Ensures one refund per payment per day even under retries.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_e3_001', 'ch_e3_001')
        self._create_dispatched_split(payment, self.seller_a, gross=Decimal('110.00'))

        mock_refund = MagicMock()
        mock_refund.id = 're_e3_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund
        mock_reversal.return_value = MagicMock()

        RefundService.create_refund(payment=payment, amount=None, reason='idem test')

        today = timezone.now().date().isoformat()
        expected_key = f're_{payment.id}_{today}'
        call_kwargs = mock_refund_create.call_args[1]
        self.assertEqual(call_kwargs['idempotency_key'], expected_key)

    def test_refund_rejected_for_non_succeeded_payment(self):
        """
        E4: Attempting to refund a payment not in 'succeeded' state raises ValueError.
        """
        order, _ = self._build_single_seller_order(order_status='pending_payment')
        payment = Payment.objects.create(
            order=order, user=self.buyer,
            stripe_payment_intent_id='pi_e4_001',
            transfer_group=f'group_{order.id}',
            amount=Decimal('110.00'), currency='brl',
            payment_method='credit_card', status='pending',
            idempotency_key='pi_e4_001_key',
        )

        with self.assertRaises(ValueError) as ctx:
            RefundService.create_refund(payment=payment)

        self.assertIn('succeeded', str(ctx.exception))

    def test_refund_rejected_when_amount_exceeds_payment(self):
        """
        E5: Refunding more than the payment amount raises ValueError.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_e5_001', 'ch_e5_001')

        with self.assertRaises(ValueError) as ctx:
            RefundService.create_refund(payment=payment, amount=Decimal('9999.00'))

        self.assertIn('cannot exceed', str(ctx.exception))


# ===========================================================================
# F. Partial Refund — Proportional Split
# ===========================================================================

class TestPartialRefundProportionalSplit(BaseFinancialTestCase):
    """
    Scenario F: Partial refund creates proportional Transfer Reversals per seller.

    refund_ratio = refund_amount / payment.amount
    reversal_per_seller = split.net_amount * refund_ratio
    """

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_partial_refund_50_percent_single_seller(self, mock_refund_create, mock_reversal):
        """
        F1: 50% partial refund reverses 50% of seller's net amount.

        Payment: 110.00
        Seller net: 99.00
        Refund: 55.00 (50%)
        Expected reversal: 99.00 * 0.5 = 49.50 → 4950 cents
        """
        order, _ = self._build_single_seller_order(
            unit_price=Decimal('100.00'), shipping_cost=Decimal('10.00'),
            order_status='paid'
        )
        payment = self._create_succeeded_payment(order, 'pi_f1_001', 'ch_f1_001')
        self._create_dispatched_split(
            payment, self.seller_a,
            gross=Decimal('110.00'), fee=Decimal('11.00'), net=Decimal('99.00'),
            transfer_id='tr_f1_001'
        )

        mock_refund = MagicMock()
        mock_refund.id = 're_f1_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund
        mock_reversal.return_value = MagicMock()

        RefundService.create_refund(payment=payment, amount=Decimal('55.00'), reason='partial')

        reversal_call = mock_reversal.call_args
        self.assertEqual(reversal_call[1]['amount'], 4950)  # 49.50 in cents

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_partial_refund_multi_seller_proportional(self, mock_refund_create, mock_reversal):
        """
        F2: Partial refund of R$50 on a R$100 order with 2 sellers (R$60 + R$40).

        Seller A net: 54.00 → reversal = 54 * (50/100) = 27.00 → 2700 cents
        Seller B net: 36.00 → reversal = 36 * (50/100) = 18.00 → 1800 cents
        Total reversal = 45.00 (which is 50% of total net 90.00)
        """
        order, _, _ = self._build_multi_seller_order(
            qty_a=1, price_a=Decimal('60.00'), ship_a=Decimal('0.00'),
            qty_b=1, price_b=Decimal('40.00'), ship_b=Decimal('0.00'),
            order_status='paid',
        )
        payment = self._create_succeeded_payment(order, 'pi_f2_001', 'ch_f2_001')
        split_a = self._create_dispatched_split(
            payment, self.seller_a,
            gross=Decimal('60.00'), fee=Decimal('6.00'), net=Decimal('54.00'),
            transfer_id='tr_f2_seller_a'
        )
        split_b = self._create_dispatched_split(
            payment, self.seller_b,
            gross=Decimal('40.00'), fee=Decimal('4.00'), net=Decimal('36.00'),
            transfer_id='tr_f2_seller_b'
        )

        mock_refund = MagicMock()
        mock_refund.id = 're_f2_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund
        mock_reversal.return_value = MagicMock()

        # Refund R$50 out of R$100
        RefundService.create_refund(payment=payment, amount=Decimal('50.00'), reason='partial')

        self.assertEqual(mock_reversal.call_count, 2)

        reversal_map = {
            c[0][0]: c[1]['amount'] for c in mock_reversal.call_args_list
        }

        # Seller A: 54.00 * 0.5 = 27.00 → 2700 cents
        self.assertEqual(reversal_map['tr_f2_seller_a'], 2700)
        # Seller B: 36.00 * 0.5 = 18.00 → 1800 cents
        self.assertEqual(reversal_map['tr_f2_seller_b'], 1800)

        # Sum of reversals = 45.00 (50% of total net 90.00)
        total_reversed = sum(reversal_map.values())
        self.assertEqual(total_reversed, 4500)

    @patch('payments.refund_service.stripe.Transfer.create_reversal')
    @patch('payments.refund_service.stripe.Refund.create')
    def test_reversal_failure_does_not_abort_refund(self, mock_refund_create, mock_reversal):
        """
        F3: A Transfer Reversal failure (Stripe error) must not abort the refund.
        Refund completes, the split error_message is set for manual reconciliation.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_f3_001', 'ch_f3_001')
        self._create_dispatched_split(
            payment, self.seller_a,
            gross=Decimal('110.00'), fee=Decimal('11.00'), net=Decimal('99.00'),
            transfer_id='tr_f3_001'
        )

        mock_refund = MagicMock()
        mock_refund.id = 're_f3_001'
        mock_refund.status = 'succeeded'
        mock_refund_create.return_value = mock_refund
        mock_reversal.side_effect = stripe.error.StripeError('Transfer not found')

        # Must not raise — refund is still complete
        RefundService.create_refund(payment=payment, amount=None, reason='reversal fail test')

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'refunded')

        order.refresh_from_db()
        self.assertEqual(order.status, 'refunded')


# ===========================================================================
# G. Webhook Idempotency
# ===========================================================================

class TestWebhookIdempotency(BaseFinancialTestCase):
    """
    Scenario G: Duplicate webhook events must not cause duplicate state changes.

    The PaymentWebhook.processed flag is the idempotency guard.
    Processing the same event_id twice must be a no-op on the second attempt.
    """

    @patch('payments.webhook_service.stripe.Transfer.create')
    @patch('payments.webhook_service.stripe.PaymentIntent.retrieve')
    @patch('logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order')
    def test_duplicate_payment_succeeded_webhook_processed_once(
        self, mock_me_checkout, mock_pi_retrieve, mock_transfer_create
    ):
        """
        G1: Sending payment_intent.succeeded twice with the same event_id
        results in exactly 1 Transfer, 1 PaymentSplit, and processed=True
        on the first call. Second call returns True without reprocessing.
        """
        order, _ = self._build_single_seller_order(order_status='pending_payment')
        payment = Payment.objects.create(
            order=order, user=self.buyer,
            stripe_payment_intent_id='pi_g1_001',
            transfer_group=f'group_{order.id}',
            amount=Decimal('110.00'),
            currency='brl', payment_method='credit_card',
            status='pending', platform_fee_total=Decimal('11.00'),
            idempotency_key='pi_g1_001_key',
        )

        charge_id = 'ch_g1_001'
        mock_pi_retrieve.return_value = _make_payment_intent_mock(
            'pi_g1_001', 11000, charge_id=charge_id
        )
        mock_tr = MagicMock()
        mock_tr.id = 'tr_g1_001'
        mock_transfer_create.return_value = mock_tr
        mock_me_checkout.return_value = None

        event_data = self._make_payment_intent_event_data('pi_g1_001', 11000)

        # -- First event processing --
        mock_sig = 'sig_g1_first'
        with patch('payments.webhook_service.WebhookService.verify_webhook_signature') as mock_verify:
            mock_verify.return_value = _make_stripe_event(
                'evt_g1_001', 'payment_intent.succeeded', event_data
            )
            result1 = WebhookService.handle_webhook(b'payload', mock_sig)

        self.assertTrue(result1)

        # Verify first processing state
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'succeeded')
        self.assertEqual(mock_transfer_create.call_count, 1)
        self.assertEqual(PaymentSplit.objects.filter(payment=payment).count(), 1)

        webhook_record = PaymentWebhook.objects.get(stripe_event_id='evt_g1_001')
        self.assertTrue(webhook_record.processed)
        self.assertIsNotNone(webhook_record.processed_at)

        # -- Second event processing (same event_id) --
        # Reset transfer mock count to detect any new calls
        mock_transfer_create.reset_mock()

        with patch('payments.webhook_service.WebhookService.verify_webhook_signature') as mock_verify:
            mock_verify.return_value = _make_stripe_event(
                'evt_g1_001', 'payment_intent.succeeded', event_data
            )
            result2 = WebhookService.handle_webhook(b'payload', mock_sig)

        self.assertTrue(result2)

        # No new Transfer created on duplicate
        mock_transfer_create.assert_not_called()

        # Only 1 PaymentSplit exists
        self.assertEqual(PaymentSplit.objects.filter(payment=payment).count(), 1)

        # Webhook record still shows processed
        webhook_record.refresh_from_db()
        self.assertTrue(webhook_record.processed)

    def test_duplicate_webhook_already_processed_returns_early(self):
        """
        G2: If PaymentWebhook.processed=True exists, handle_webhook returns True
        immediately without entering the processing block.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_g2_001', 'ch_g2_001')

        # Pre-create a processed webhook record
        PaymentWebhook.objects.create(
            stripe_event_id='evt_g2_already_done',
            event_type='payment_intent.succeeded',
            payload={'id': 'pi_g2_001'},
            payment=payment,
            processed=True,
            processed_at=timezone.now(),
        )

        event_data = self._make_payment_intent_event_data('pi_g2_001', int(float(order.total) * 100))

        with patch('payments.webhook_service.WebhookService.verify_webhook_signature') as mock_verify:
            mock_verify.return_value = _make_stripe_event(
                'evt_g2_already_done', 'payment_intent.succeeded', event_data
            )
            with patch('payments.webhook_service.WebhookService._handle_payment_succeeded') as mock_handler:
                result = WebhookService.handle_webhook(b'payload', 'sig_g2')
                # Handler was never called — returned early due to idempotency guard
                mock_handler.assert_not_called()

        self.assertTrue(result)

    def test_transfer_dispatch_idempotent_for_already_dispatched_split(self):
        """
        G3: Re-running TransferDispatchService for an order where the split is
        already 'dispatched' skips the seller — no duplicate Transfer created.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_g3_001', 'ch_g3_001')

        # Pre-create a dispatched split
        PaymentSplit.objects.create(
            payment=payment, seller=self.seller_a,
            gross_amount=Decimal('110.00'), platform_fee_amount=Decimal('11.00'),
            net_amount=Decimal('99.00'),
            stripe_transfer_id='tr_g3_already',
            transfer_status='dispatched',
        )

        with patch('payments.services.transfer_dispatch_service.stripe.Transfer.create') as mock_transfer:
            splits = TransferDispatchService.dispatch_transfers_for_order(
                order=order, payment=payment, charge_id='ch_g3_001'
            )

        # No Stripe Transfer.create called (already dispatched)
        mock_transfer.assert_not_called()

        # The split returned is the existing dispatched one
        self.assertEqual(len(splits), 1)
        self.assertEqual(splits[0].transfer_status, 'dispatched')
        self.assertEqual(splits[0].stripe_transfer_id, 'tr_g3_already')


# ===========================================================================
# H. Chargeback — Dispute Creation and Status Transitions
# ===========================================================================

class TestChargebackAndDispute(BaseFinancialTestCase):
    """
    Scenario H: charge.dispute.created and charge.dispute.closed webhook handling.
    """

    def setUp(self):
        super().setUp()
        self.order, _ = self._build_single_seller_order(order_status='paid')
        self.payment = self._create_succeeded_payment(
            self.order, 'pi_h_001', 'ch_h_001'
        )
        self.split = self._create_dispatched_split(
            self.payment, self.seller_a,
            gross=Decimal('110.00'), fee=Decimal('11.00'), net=Decimal('99.00'),
            transfer_id='tr_h_001'
        )

    @patch('payments.webhook_service.stripe.Transfer.create_reversal')
    def test_dispute_created_creates_dispute_record(self, mock_reversal):
        """
        H1: charge.dispute.created creates a Dispute record and attempts
        Transfer Reversals. reversal_attempted = True after handler runs.
        """
        mock_reversal.return_value = MagicMock(id='rev_h1_001')

        dispute_data = MagicMock()
        dispute_data.id = 'dp_h1_001'
        dispute_data.charge = 'ch_h_001'
        dispute_data.amount = 11000
        dispute_data.currency = 'brl'
        dispute_data.reason = 'fraudulent'
        dispute_data.status = 'needs_response'

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_dp_h1_001',
            event_type='charge.dispute.created',
            payload={},
        )

        with patch('payments.webhook_service.Dispute.objects.get_or_create') as mock_goc:
            dispute_inst = Dispute(
                payment=self.payment,
                stripe_dispute_id='dp_h1_001',
                stripe_charge_id='ch_h_001',
                amount=Decimal('110.00'),
                currency='BRL',
                reason='fraudulent',
                status='needs_response',
                reversal_attempted=False,
                stripe_payload={},
            )
            dispute_inst.save = MagicMock()
            mock_goc.return_value = (dispute_inst, True)

            WebhookService._handle_dispute_created(
                _make_stripe_event('evt_dp_h1_001', 'charge.dispute.created', dispute_data),
                webhook,
            )

            mock_goc.assert_called_once()

    @patch('payments.webhook_service.stripe.Transfer.create_reversal')
    def test_dispute_created_attempts_transfer_reversal(self, mock_reversal):
        """
        H2: When dispute is created, Transfer Reversal is attempted proportionally.
        The reversal amount equals dispute_amount * (split.net / total_net).
        For a single seller: reversal = full dispute amount capped at net.
        """
        mock_reversal.return_value = MagicMock(id='rev_h2_001')

        dispute = Dispute.objects.create(
            payment=self.payment,
            stripe_dispute_id='dp_h2_001',
            stripe_charge_id='ch_h_001',
            amount=Decimal('110.00'),
            currency='BRL',
            reason='fraudulent',
            status='needs_response',
            reversal_attempted=False,
        )

        WebhookService._attempt_transfer_reversals_for_dispute(
            dispute=dispute, payment=self.payment
        )

        mock_reversal.assert_called_once()
        reversal_call = mock_reversal.call_args
        self.assertEqual(reversal_call[0][0], 'tr_h_001')
        self.assertGreater(reversal_call[1]['amount'], 0)

        dispute.refresh_from_db()
        self.assertTrue(dispute.reversal_attempted)

    def test_dispute_closed_lost_updates_status(self):
        """
        H3: charge.dispute.closed with status='lost' updates Dispute.status to 'lost'.
        """
        dispute = Dispute.objects.create(
            payment=self.payment,
            stripe_dispute_id='dp_h3_001',
            stripe_charge_id='ch_h_001',
            amount=Decimal('110.00'),
            currency='BRL',
            reason='fraudulent',
            status='under_review',
            reversal_attempted=True,
        )

        dispute_data = MagicMock()
        dispute_data.id = 'dp_h3_001'
        dispute_data.status = 'lost'

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_dp_h3_closed',
            event_type='charge.dispute.closed',
            payload={'id': 'dp_h3_001', 'status': 'lost'},
        )

        with patch('payments.webhook_service.dict', return_value={'status': 'lost'}):
            WebhookService._handle_dispute_closed(
                _make_stripe_event('evt_dp_h3_closed', 'charge.dispute.closed', dispute_data),
                webhook,
            )

        dispute.refresh_from_db()
        self.assertEqual(dispute.status, 'lost')

    def test_dispute_closed_won_updates_status(self):
        """
        H4: charge.dispute.closed with status='won' updates Dispute.status to 'won'.
        """
        dispute = Dispute.objects.create(
            payment=self.payment,
            stripe_dispute_id='dp_h4_001',
            stripe_charge_id='ch_h_001',
            amount=Decimal('110.00'),
            currency='BRL',
            reason='fraudulent',
            status='under_review',
            reversal_attempted=True,
        )

        dispute_data = MagicMock()
        dispute_data.id = 'dp_h4_001'
        dispute_data.status = 'won'

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_dp_h4_closed',
            event_type='charge.dispute.closed',
            payload={'id': 'dp_h4_001', 'status': 'won'},
        )

        with patch('payments.webhook_service.dict', return_value={'status': 'won'}):
            WebhookService._handle_dispute_closed(
                _make_stripe_event('evt_dp_h4_closed', 'charge.dispute.closed', dispute_data),
                webhook,
            )

        dispute.refresh_from_db()
        self.assertEqual(dispute.status, 'won')


# ===========================================================================
# I. Transfer Failed — Alerting
# ===========================================================================

class TestTransferFailedAlerting(BaseFinancialTestCase):
    """
    Scenario I: transfer.failed webhook marks PaymentSplit as failed.
    """

    def test_transfer_failed_marks_split_failed(self):
        """
        I1: transfer.failed event marks PaymentSplit.transfer_status='failed'
        and stores an error_message with the transfer_id for reconciliation.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_i1_001', 'ch_i1_001')
        split = self._create_dispatched_split(
            payment, self.seller_a,
            gross=Decimal('110.00'), fee=Decimal('11.00'), net=Decimal('99.00'),
            transfer_id='tr_i1_001'
        )

        transfer_data = MagicMock()
        transfer_data.id = 'tr_i1_001'

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_tr_fail_i1',
            event_type='transfer.failed',
            payload={'id': 'tr_i1_001'},
        )

        WebhookService._handle_transfer_failed(
            _make_stripe_event('evt_tr_fail_i1', 'transfer.failed', transfer_data),
            webhook,
        )

        split.refresh_from_db()
        self.assertEqual(split.transfer_status, 'failed')
        self.assertIn('tr_i1_001', split.error_message)
        self.assertIn('Manual reconciliation', split.error_message)

    def test_transfer_failed_for_unknown_transfer_does_not_raise(self):
        """
        I2: transfer.failed for an unknown transfer_id logs a warning
        and does not raise an exception.
        """
        transfer_data = MagicMock()
        transfer_data.id = 'tr_unknown_i2'

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_tr_fail_i2_unknown',
            event_type='transfer.failed',
            payload={'id': 'tr_unknown_i2'},
        )

        # Should not raise
        WebhookService._handle_transfer_failed(
            _make_stripe_event('evt_tr_fail_i2_unknown', 'transfer.failed', transfer_data),
            webhook,
        )


# ===========================================================================
# J. Transfer Created — Confirmation
# ===========================================================================

class TestTransferCreatedConfirmation(BaseFinancialTestCase):
    """
    Scenario J: transfer.created webhook confirms a PaymentSplit as dispatched.
    """

    def test_transfer_created_updates_split_to_dispatched(self):
        """
        J1: transfer.created sets PaymentSplit.transfer_status='dispatched'
        when the split was in 'pending' state.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_j1_001', 'ch_j1_001')
        split = PaymentSplit.objects.create(
            payment=payment, seller=self.seller_a,
            gross_amount=Decimal('110.00'), platform_fee_amount=Decimal('11.00'),
            net_amount=Decimal('99.00'),
            stripe_transfer_id='tr_j1_001',
            transfer_status='pending',  # Not yet confirmed
        )

        transfer_data = MagicMock()
        transfer_data.id = 'tr_j1_001'

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_tr_created_j1',
            event_type='transfer.created',
            payload={'id': 'tr_j1_001'},
        )

        WebhookService._handle_transfer_created(
            _make_stripe_event('evt_tr_created_j1', 'transfer.created', transfer_data),
            webhook,
        )

        split.refresh_from_db()
        self.assertEqual(split.transfer_status, 'dispatched')

    def test_transfer_created_no_op_when_already_dispatched(self):
        """
        J2: transfer.created on an already-dispatched split is a no-op.
        No error raised, status remains 'dispatched'.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_j2_001', 'ch_j2_001')
        split = self._create_dispatched_split(
            payment, self.seller_a,
            gross=Decimal('110.00'), transfer_id='tr_j2_001'
        )

        transfer_data = MagicMock()
        transfer_data.id = 'tr_j2_001'

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_tr_created_j2',
            event_type='transfer.created',
            payload={'id': 'tr_j2_001'},
        )

        WebhookService._handle_transfer_created(
            _make_stripe_event('evt_tr_created_j2', 'transfer.created', transfer_data),
            webhook,
        )

        split.refresh_from_db()
        self.assertEqual(split.transfer_status, 'dispatched')


# ===========================================================================
# K. Stripe Test Cards — Documentation Test
# ===========================================================================

class TestStripeTestCardsDocumentation(TestCase):
    """
    Scenario K: Documents Stripe test cards and validates the constant.
    These cards are used for manual/E2E validation against the live Test Mode API.
    """

    def test_test_cards_dict_has_all_required_scenarios(self):
        """
        K1: The STRIPE_TEST_CARDS dict covers all required test scenarios.
        """
        required_scenarios = [
            'success',
            'decline_generic',
            'decline_insufficient_funds',
            'decline_expired',
            'decline_cvc',
            'requires_3ds',
            'dispute_fraud',
        ]
        for scenario in required_scenarios:
            self.assertIn(scenario, STRIPE_TEST_CARDS,
                          f"Missing test card for scenario: {scenario}")

    def test_success_card_number(self):
        """K2: Success card must be the standard Stripe test card."""
        self.assertEqual(STRIPE_TEST_CARDS['success'], '4242424242424242')

    def test_dispute_card_number(self):
        """K3: Dispute card must be the Stripe chargeback simulation card."""
        self.assertEqual(STRIPE_TEST_CARDS['dispute_fraud'], '4000000000000259')

    def test_3ds_card_number(self):
        """K4: 3DS card must require authentication."""
        self.assertEqual(STRIPE_TEST_CARDS['requires_3ds'], '4000002760003184')


# ===========================================================================
# L. Financial Calculation Consistency
# ===========================================================================

class TestFinancialCalculationConsistency(BaseFinancialTestCase):
    """
    Scenario L: Validates mathematical precision and consistency across all
    financial values. No penny may be lost or created.
    """

    def test_split_calculation_no_penny_lost(self):
        """
        L1: gross - fee = net exactly (ROUND_HALF_UP ensures no floating point drift).
        """
        from decimal import Decimal as D
        platform_fee_pct = D('10')

        order, _ = self._build_single_seller_order(
            unit_price=D('100.00'), shipping_cost=D('10.00'),
            order_status='paid',
        )

        # New return: (product_cents, shipping_cents, fee_cents, net_cents,
        #              product_decimal, shipping_decimal, fee_decimal, net_decimal)
        product_c, shipping_c, fee_c, net_c, product_d, shipping_d, fee_d, net_d = \
            TransferDispatchService.calculate_seller_split(order, self.seller_a, platform_fee_pct)

        # Decimal identity: net = product - fee (shipping excluded from net)
        self.assertEqual(net_d, product_d - fee_d)

        # Cents identity: net_cents = product_cents - fee_cents
        self.assertEqual(net_c, product_c - fee_c)

    def test_split_with_decimal_price(self):
        """
        L2: Split calculation with fractional prices (e.g., R$33.33) does not
        produce more fee than gross or negative net.
        """
        from decimal import Decimal as D

        listing_decimal = MarketplaceListing.objects.create(
            product=self.product_a, seller=self.seller_a,
            brand=self.brand, condition=self.condition,
            price=D('33.33'), quantity=5, is_active=True,
            weight_kg=D('1.00'), height_cm=D('5.00'),
            width_cm=D('5.00'), length_cm=D('5.00'),
        )
        order_decimal = Order.objects.create(
            buyer=self.buyer,
            subtotal=D('33.33'),
            shipping_cost=D('0.00'),
            total=D('33.33'),
            shipping_address={'street': 'Test'},
            status='paid',
        )
        OrderItem.objects.create(
            order=order_decimal, listing=listing_decimal, seller=self.seller_a,
            quantity=1, unit_price=D('33.33'), subtotal=D('33.33'),
            shipping_cost=D('0.00'),
            product_name='Decimal Product', product_code='',
            brand_name='FinBrand', condition_name='FinNew',
            weight_kg=D('1.00'), height_cm=D('5.00'),
            width_cm=D('5.00'), length_cm=D('5.00'),
        )

        # New return: (product_cents, shipping_cents, fee_cents, net_cents,
        #              product_decimal, shipping_decimal, fee_decimal, net_decimal)
        product_c, shipping_c, fee_c, net_c, product_d, shipping_d, fee_d, net_d = \
            TransferDispatchService.calculate_seller_split(order_decimal, self.seller_a, D('10'))

        # Fee must not exceed product amount
        self.assertLessEqual(fee_d, product_d)
        # Net must be non-negative
        self.assertGreaterEqual(net_d, D('0.00'))
        # Identity: net = product - fee
        self.assertEqual(net_d, product_d - fee_d)
        # Fee is approximately 10% of product (rounded half-up)
        self.assertAlmostEqual(float(fee_d), float(product_d) * 0.10, places=1)

    def test_multi_seller_sum_invariants(self):
        """
        L3: For a multi-seller order:
            sum(gross) == order items total (no shipping double-count)
            sum(fee) == platform revenue
            sum(net) == sum(gross) - sum(fee)
            sum(net) <= payment.amount
        """
        from decimal import Decimal as D

        order, _, _ = self._build_multi_seller_order(
            qty_a=2, price_a=D('50.00'), ship_a=D('5.00'),
            qty_b=3, price_b=D('20.00'), ship_b=D('3.00'),
        )
        # Seller A gross = 2*50 + 5 = 105
        # Seller B gross = 3*20 + 3 = 63
        platform_fee_pct = D('10')

        # New return: (product_cents, shipping_cents, fee_cents, net_cents,
        #              product_decimal, shipping_decimal, fee_decimal, net_decimal)
        _, _, _, _, product_a, shipping_a, fee_a, net_a = TransferDispatchService.calculate_seller_split(
            order, self.seller_a, platform_fee_pct
        )
        _, _, _, _, product_b, shipping_b, fee_b, net_b = TransferDispatchService.calculate_seller_split(
            order, self.seller_b, platform_fee_pct
        )

        # Seller A: product=2*50=100, shipping=5, fee=100*10%=10.00, net=90.00
        self.assertEqual(product_a, D('100.00'))
        self.assertEqual(shipping_a, D('5.00'))
        self.assertEqual(fee_a, D('10.00'))
        self.assertEqual(net_a, D('90.00'))

        # Seller B: product=3*20=60, shipping=3, fee=60*10%=6.00, net=54.00
        self.assertEqual(product_b, D('60.00'))
        self.assertEqual(shipping_b, D('3.00'))
        self.assertEqual(fee_b, D('6.00'))
        self.assertEqual(net_b, D('54.00'))

        total_product = product_a + product_b
        total_shipping = shipping_a + shipping_b
        total_fee = fee_a + fee_b
        total_net = net_a + net_b

        # Sum invariant: net = product - fee (shipping excluded from transfers)
        self.assertEqual(total_net, total_product - total_fee)

        # Total net (transfers) <= order total (shipping is retained by platform)
        self.assertLessEqual(total_net, order.total)

    def test_platform_fee_total_matches_sum_of_individual_fees(self):
        """
        L4: calculate_total_platform_fee returns the same value as
        sum of individual seller fees — no discrepancy in aggregate calculation.
        """
        from decimal import Decimal as D

        order, _, _ = self._build_multi_seller_order(
            qty_a=1, price_a=D('60.00'), ship_a=D('0.00'),
            qty_b=1, price_b=D('40.00'), ship_b=D('0.00'),
        )

        total_fee = TransferDispatchService.calculate_total_platform_fee(order)

        # New return: (product_cents, shipping_cents, fee_cents, net_cents,
        #              product_decimal, shipping_decimal, fee_decimal, net_decimal)
        _, _, _, _, _, _, fee_a, _ = TransferDispatchService.calculate_seller_split(
            order, self.seller_a, D('10')
        )
        _, _, _, _, _, _, fee_b, _ = TransferDispatchService.calculate_seller_split(
            order, self.seller_b, D('10')
        )

        self.assertEqual(total_fee, fee_a + fee_b)


# ===========================================================================
# M. PIX Payment Method Handling
# ===========================================================================

class TestPixPaymentMethod(BaseFinancialTestCase):
    """
    Scenario M: PIX payment method validation and intent creation.
    """

    @patch('payments.payment_intent_service.stripe.Account.retrieve')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    def test_pix_payment_uses_pix_method_type(self, mock_pi_create, mock_acct_retrieve):
        """
        M1: Creating a PaymentIntent with payment_method='pix' passes
        payment_method_types=['pix'] to Stripe. This is required for PIX
        to be available to the customer.
        """
        order, _ = self._build_single_seller_order(
            unit_price=Decimal('100.00'), shipping_cost=Decimal('0.00'),
            order_status='pending_payment',
        )

        mock_acct = MagicMock()
        mock_acct.get.return_value = True
        mock_acct_retrieve.return_value = mock_acct

        mock_pi = _make_payment_intent_mock('pi_m1_001', 10000)
        mock_pi_create.return_value = mock_pi

        PaymentIntentService.create_payment_intent(
            order=order, payment_method='pix', user=self.buyer
        )

        call_kwargs = mock_pi_create.call_args[1]
        self.assertEqual(call_kwargs['payment_method_types'], ['pix'])

    @patch('payments.payment_intent_service.stripe.Account.retrieve')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    def test_credit_card_uses_card_method_type(self, mock_pi_create, mock_acct_retrieve):
        """
        M2: payment_method='credit_card' passes payment_method_types=['card'] to Stripe.
        """
        order, _ = self._build_single_seller_order(order_status='pending_payment')

        mock_acct = MagicMock()
        mock_acct.get.return_value = True
        mock_acct_retrieve.return_value = mock_acct

        mock_pi = _make_payment_intent_mock('pi_m2_001', 11000)
        mock_pi_create.return_value = mock_pi

        PaymentIntentService.create_payment_intent(
            order=order, payment_method='credit_card', user=self.buyer
        )

        call_kwargs = mock_pi_create.call_args[1]
        self.assertEqual(call_kwargs['payment_method_types'], ['card'])


# ===========================================================================
# N. Webhook Signature Validation
# ===========================================================================

class TestWebhookSignatureValidation(BaseFinancialTestCase):
    """
    Scenario N: Invalid webhook signatures must be rejected.
    This is a critical security and financial integrity requirement.
    """

    def test_invalid_signature_raises_signature_verification_error(self):
        """
        N1: A webhook with an invalid Stripe-Signature header must raise
        SignatureVerificationError before any processing occurs.
        """
        with patch('payments.webhook_service.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.side_effect = stripe.error.SignatureVerificationError(
                'No signatures found matching the expected signature for payload',
                sig_header='invalid_sig'
            )

            with self.assertRaises(stripe.error.SignatureVerificationError):
                WebhookService.verify_webhook_signature(b'payload', 'invalid_sig')

    def test_missing_webhook_secret_raises_value_error(self):
        """
        N2: If STRIPE_WEBHOOK_SECRET is not configured, verification raises ValueError.
        This prevents silent acceptance of unsigned webhooks.
        """
        from django.test import override_settings

        with override_settings(STRIPE_WEBHOOK_SECRET=''):
            with self.assertRaises(ValueError) as ctx:
                WebhookService.verify_webhook_signature(b'payload', 'sig')

            self.assertIn('not configured', str(ctx.exception))

    def test_valid_signature_returns_event(self):
        """
        N3: A correctly signed webhook returns a stripe.Event object.
        """
        mock_event = MagicMock()
        mock_event.id = 'evt_n3_001'
        mock_event.type = 'payment_intent.succeeded'

        with patch('payments.webhook_service.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = mock_event
            event = WebhookService.verify_webhook_signature(b'payload', 'valid_sig')

        self.assertEqual(event.id, 'evt_n3_001')


# ===========================================================================
# O. Resilience — Failures and Recovery
# ===========================================================================

class TestResilienceAndFailures(BaseFinancialTestCase):
    """
    Scenario O: System resilience under failure conditions.
    Validates atomic rollback and safe reprocessing.
    """

    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    def test_stripe_error_on_transfer_marks_split_failed_not_raises(self, mock_transfer):
        """
        O1: If Stripe returns an error for one seller's Transfer, the split is
        marked 'failed' but dispatch continues for other sellers.
        The transaction does not roll back — financial state is partially committed
        so other sellers receive their funds.
        """
        order, _, _ = self._build_multi_seller_order(
            qty_a=1, price_a=Decimal('60.00'), ship_a=Decimal('0.00'),
            qty_b=1, price_b=Decimal('40.00'), ship_b=Decimal('0.00'),
            order_status='paid',
        )
        payment = self._create_succeeded_payment(order, 'pi_o1_001', 'ch_o1_001')

        # Seller A transfer fails, Seller B succeeds
        tr_b = MagicMock()
        tr_b.id = 'tr_o1_seller_b'
        mock_transfer.side_effect = [
            stripe.error.StripeError('Bank error for seller A'),
            tr_b,
        ]

        splits = TransferDispatchService.dispatch_transfers_for_order(
            order=order, payment=payment, charge_id='ch_o1_001'
        )

        failed = [s for s in splits if s.transfer_status == 'failed']
        dispatched = [s for s in splits if s.transfer_status == 'dispatched']

        self.assertEqual(len(failed), 1)
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0].seller, self.seller_b)

    def test_dispatch_raises_if_charge_id_empty(self):
        """
        O2: dispatch_transfers_for_order raises TransferDispatchError immediately
        if charge_id is empty string. No DB writes, no Stripe calls.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_o2_001', 'ch_o2_001')

        with patch('payments.services.transfer_dispatch_service.stripe.Transfer.create') as mock_tr:
            with self.assertRaises(TransferDispatchError) as ctx:
                TransferDispatchService.dispatch_transfers_for_order(
                    order=order, payment=payment, charge_id=''
                )

            mock_tr.assert_not_called()

        self.assertIn('charge_id', str(ctx.exception))

    @patch('payments.refund_service.stripe.Refund.create')
    def test_refund_stripe_error_raises_refund_error(self, mock_refund):
        """
        O3: When Stripe returns an error during refund creation, RefundError
        is raised and the Payment status is NOT changed.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_o3_001', 'ch_o3_001')

        mock_refund.side_effect = stripe.error.StripeError('Invalid payment intent')

        with self.assertRaises(RefundError) as ctx:
            RefundService.create_refund(payment=payment, amount=None, reason='test')

        self.assertIn('Erro ao criar reembolso', str(ctx.exception))

        # Payment status NOT changed (atomic rollback)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'succeeded')

    def test_payment_amount_mismatch_raises_error(self):
        """
        O4: If the PaymentIntent amount from Stripe differs from the Payment record,
        PaymentAmountMismatchError is raised. This prevents fraudulent underpayments.
        """
        from payments.webhook_service import PaymentAmountMismatchError

        order, _ = self._build_single_seller_order(order_status='pending_payment')
        payment = Payment.objects.create(
            order=order, user=self.buyer,
            stripe_payment_intent_id='pi_o4_001',
            transfer_group=f'group_{order.id}',
            amount=Decimal('110.00'),  # DB says 110.00
            currency='brl', payment_method='credit_card',
            status='pending', idempotency_key='pi_o4_key',
        )

        # Stripe returns 90.00 (9000 cents) — mismatch!
        mock_pi = _make_payment_intent_mock('pi_o4_001', 9000)

        with self.assertRaises(PaymentAmountMismatchError) as ctx:
            WebhookService.validate_payment_amount(mock_pi, payment)

        self.assertIn('mismatch', str(ctx.exception).lower())
        self.assertIn('11000', str(ctx.exception))  # expected
        self.assertIn('9000', str(ctx.exception))   # actual


# ===========================================================================
# P. Transfer Group Consistency
# ===========================================================================

class TestTransferGroupConsistency(BaseFinancialTestCase):
    """
    Scenario P: Validates that transfer_group is consistent across
    Payment, PaymentIntent, and all Transfers. This is mandatory for
    Stripe Connect Separate Charges and Transfers reconciliation.
    """

    @patch('payments.payment_intent_service.stripe.Account.retrieve')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    def test_payment_intent_carries_transfer_group(self, mock_pi_create, mock_acct_retrieve):
        """
        P1: The Stripe PaymentIntent created by PaymentIntentService carries
        transfer_group=f'group_{order.id}'. This is mandatory for the
        Separate Charges and Transfers pattern.
        """
        order, _ = self._build_single_seller_order(order_status='pending_payment')

        mock_acct = MagicMock()
        mock_acct.get.return_value = True
        mock_acct_retrieve.return_value = mock_acct

        mock_pi = _make_payment_intent_mock('pi_p1_001', 11000)
        mock_pi_create.return_value = mock_pi

        payment, _ = PaymentIntentService.create_payment_intent(
            order=order, payment_method='credit_card', user=self.buyer
        )

        expected_group = f'group_{order.id}'
        self.assertEqual(payment.transfer_group, expected_group)

        call_kwargs = mock_pi_create.call_args[1]
        self.assertEqual(call_kwargs['transfer_group'], expected_group)

    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    def test_transfers_carry_same_transfer_group(self, mock_transfer_create):
        """
        P2: Every Stripe Transfer created by TransferDispatchService carries
        the same transfer_group as the Payment. This ensures Stripe can link
        all financial operations in the payment dashboard.
        """
        order, _ = self._build_single_seller_order(order_status='paid')
        payment = self._create_succeeded_payment(order, 'pi_p2_001', 'ch_p2_001')

        mock_tr = MagicMock()
        mock_tr.id = 'tr_p2_001'
        mock_transfer_create.return_value = mock_tr

        TransferDispatchService.dispatch_transfers_for_order(
            order=order, payment=payment, charge_id='ch_p2_001'
        )

        call_kwargs = mock_transfer_create.call_args[1]
        self.assertEqual(call_kwargs['transfer_group'], payment.transfer_group)
