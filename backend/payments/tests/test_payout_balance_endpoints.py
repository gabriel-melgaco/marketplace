"""
Payout & Balance Endpoint Test Suite
=====================================

Validates the three seller-facing financial read endpoints:
  GET /api/payments/payouts/          -> SellerPayoutListView
  GET /api/payments/payouts/<id>/     -> SellerPayoutDetailView
  GET /api/payments/balance/          -> seller_balance

ACTUAL IMPLEMENTATION (discovered via test failures — views were updated):
  - SellerPayoutListView  -> uses PaymentSplitSerializer, queries PaymentSplit
  - SellerPayoutDetailView -> uses PaymentSplitSerializer, queries PaymentSplit
  - seller_balance -> aggregates PaymentSplit.net_amount by transfer_status
                   + calls stripe.Balance.retrieve(stripe_account=...) for real-time data

SellerPayout model is explicitly marked as legacy and is NEVER queried by any of
these endpoints. It exists in the codebase but is dead code from a functional standpoint.

Findings from audit:

  [FINDING-1] SellerPayout model is never created or read in the actual flow.
              Its admin registration and migration history are the only traces.
              Frontend teams must use PaymentSplit data, not SellerPayout.

  [FINDING-2] seller_balance.total_dispatched is a duplicate of dispatched_transfers.
              The response has BOTH 'dispatched_transfers' and 'total_dispatched'
              pointing to the same value. One of them is redundant.

  [FINDING-3] seller_balance calls stripe.Balance.retrieve(stripe_account=...).
              This is a live Stripe API call on every request. There is no caching.
              A Stripe API failure is silently caught — returns stripe_available=0
              with no error field to inform the client that the data is stale.

  [FINDING-4] SellerPayoutListView serializer is PaymentSplitSerializer, but the
              URL name is 'payout-list' and the view class is 'SellerPayoutListView'.
              The naming mismatch creates confusion between PaymentSplit and SellerPayout.

  [FINDING-5] PaymentSplitSerializer does NOT include product_amount, shipping_amount,
              or shipping_status — fields added in migration 0004. Sellers cannot see
              the split between product value and shipping amount from the API.

  [FINDING-6] seller_balance has no 'total_available' field (unlike what the previous
              view version returned). Frontend code relying on 'total_available' will
              receive 'undefined'. The correct field is now 'stripe_available'.

Fixture pattern mirrors BaseFinancialTestCase from test_financial_flows.py.
"""

import stripe
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from orders.models import Order, OrderItem
from products.models import Products, Brand, Condition, MarketplaceListing, Category, Series
from payments.models import SellerPayout, PaymentSplit, Payment

User = get_user_model()

# Sentinel for mocked Stripe balance response
def _make_stripe_balance_mock(available_brl_cents=0, pending_brl_cents=0):
    """Returns a MagicMock that mimics stripe.Balance.retrieve() response."""
    mock_balance = MagicMock()
    mock_balance.available = [{'currency': 'brl', 'amount': available_brl_cents}]
    mock_balance.pending = [{'currency': 'brl', 'amount': pending_brl_cents}]
    return mock_balance


# ---------------------------------------------------------------------------
# Shared fixture base
# ---------------------------------------------------------------------------

class BasePayoutTestCase(TestCase):
    """
    Shared test fixtures for payout/balance endpoint tests.
    Mirrors the BaseFinancialTestCase pattern from test_financial_flows.py.
    """

    def setUp(self):
        self.client = APIClient()

        # Users
        self.seller = User.objects.create_user(
            email='seller_payout@test.com',
            password='testpass123',
            stripe_account_id='acct_test_seller_pb',
        )
        self.other_seller = User.objects.create_user(
            email='other_seller_payout@test.com',
            password='testpass123',
            stripe_account_id='acct_test_other_pb',
        )
        self.buyer = User.objects.create_user(
            email='buyer_payout@test.com',
            password='testpass123',
        )

        # Product taxonomy (brand is on MarketplaceListing, NOT on Products)
        self.category = Category.objects.create(name='PayoutCat', slug='payoutcat')
        self.series = Series.objects.create(name='PayoutSeries', slug='payoutseries')
        self.brand = Brand.objects.create(name='PayoutBrand', slug='payoutbrand')
        self.condition = Condition.objects.create(name='PayoutNew', slug='payoutnew')

        self.product = Products.objects.create(
            name='Payout Product',
            slug='payout-product',
            category=self.category,
            series=self.series,
        )
        self.listing = MarketplaceListing.objects.create(
            product=self.product,
            seller=self.seller,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('100.00'),
            quantity=10,
            is_active=True,
            weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )

        # Order
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('100.00'),
            shipping_address={'street': 'Test St', 'city': 'Sao Paulo'},
            status='paid',
        )
        OrderItem.objects.create(
            order=self.order,
            listing=self.listing,
            seller=self.seller,
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'),
            product_name=self.product.name,
            product_code='',
            brand_name=self.brand.name,
            condition_name=self.condition.name,
            weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )

        # Payment
        self.payment = Payment.objects.create(
            order=self.order,
            user=self.buyer,
            stripe_payment_intent_id='pi_test_payout_pb',
            amount=Decimal('100.00'),
            currency='BRL',
            status='succeeded',
            payment_method='credit_card',
            transfer_group='tg_test_payout_pb',
            stripe_charge_id='ch_test_payout_pb',
        )

        # PaymentSplit — the authoritative record for repasses
        self.split = PaymentSplit.objects.create(
            payment=self.payment,
            seller=self.seller,
            gross_amount=Decimal('100.00'),
            product_amount=Decimal('100.00'),
            shipping_amount=Decimal('0.00'),
            platform_fee_amount=Decimal('10.00'),
            net_amount=Decimal('90.00'),
            stripe_transfer_id='tr_test_split_pb',
            transfer_status='dispatched',
        )

    def _auth_as(self, user):
        self.client.force_authenticate(user=user)

    def _mock_stripe_balance(self, available_cents=0, pending_cents=0):
        """Context manager that mocks stripe.Balance.retrieve."""
        return patch(
            'stripe.Balance.retrieve',
            return_value=_make_stripe_balance_mock(available_cents, pending_cents)
        )

    def _mock_stripe_payout_list(self, payout_amounts_cents=None):
        """
        Context manager that mocks stripe.Payout.list for in_transit payouts.
        payout_amounts_cents: list of int amounts in cents; defaults to empty list.
        """
        amounts = payout_amounts_cents or []
        mock_list = MagicMock()
        mock_list.auto_paging_iter.return_value = iter(
            [{'amount': a} for a in amounts]
        )
        return patch('stripe.Payout.list', return_value=mock_list)

    def _mock_stripe_balance_and_payouts(self, available_cents=0, pending_cents=0, in_transit_cents=None):
        """
        Stacked context manager that mocks both stripe.Balance.retrieve and
        stripe.Payout.list simultaneously.
        in_transit_cents: list of int payout amounts in cents; defaults to empty list (0 in transit).
        Returns a single context manager via patch.multiple for convenience.
        """
        amounts = in_transit_cents or []
        mock_payout_list = MagicMock()
        mock_payout_list.auto_paging_iter.return_value = iter(
            [{'amount': a} for a in amounts]
        )
        from unittest.mock import patch as _patch
        import unittest.mock as _mock

        class _StackedMock:
            def __init__(self, balance_mock, payout_mock):
                self._p1 = _patch('stripe.Balance.retrieve', return_value=balance_mock)
                self._p2 = _patch('stripe.Payout.list', return_value=payout_mock)

            def __enter__(self):
                self._p1.__enter__()
                self._p2.__enter__()
                return self

            def __exit__(self, *args):
                self._p2.__exit__(*args)
                self._p1.__exit__(*args)

        return _StackedMock(
            _make_stripe_balance_mock(available_cents, pending_cents),
            mock_payout_list,
        )


# ===========================================================================
# 1. Authentication & Authorization
# ===========================================================================

class TestPayoutEndpointAuth(BasePayoutTestCase):
    """Endpoints must reject unauthenticated requests."""

    def test_payout_list_requires_auth(self):
        """GET /payouts/ returns 401 without authentication."""
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse('payments:payout-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_payout_detail_requires_auth(self):
        """GET /payouts/<id>/ returns 401 without authentication."""
        self.client.force_authenticate(user=None)
        response = self.client.get(
            reverse('payments:payout-detail', kwargs={'pk': self.split.pk})
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_balance_requires_auth(self):
        """GET /balance/ returns 401 without authentication."""
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse('payments:seller-balance'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ===========================================================================
# 2. SellerPayoutListView -> GET /payouts/ (actually returns PaymentSplit)
# ===========================================================================

class TestSellerPayoutListView(BasePayoutTestCase):
    """
    Tests for GET /api/payments/payouts/

    IMPORTANT: Despite the name 'SellerPayoutListView', this endpoint returns
    PaymentSplit records serialized via PaymentSplitSerializer.
    SellerPayout model is never queried.
    """

    def test_seller_sees_own_splits(self):
        """Seller receives their own PaymentSplit records."""
        self._auth_as(self.seller)
        response = self.client.get(reverse('payments:payout-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.split.pk)

    def test_other_seller_sees_empty_list(self):
        """Other seller cannot see this seller's splits."""
        self._auth_as(self.other_seller)
        response = self.client.get(reverse('payments:payout-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertEqual(len(results), 0)

    def test_buyer_sees_empty_list(self):
        """Buyer with no splits gets empty list (no role check, FINDING-7 analog)."""
        self._auth_as(self.buyer)
        response = self.client.get(reverse('payments:payout-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertEqual(len(results), 0)

    def test_list_response_contains_payment_split_fields(self):
        """Response fields match PaymentSplitSerializer, NOT SellerPayoutSerializer."""
        self._auth_as(self.seller)
        response = self.client.get(reverse('payments:payout-list'))
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        item = results[0]

        # Fields from PaymentSplitSerializer
        for field in ['id', 'payment', 'seller', 'seller_email',
                      'gross_amount', 'platform_fee_amount', 'net_amount',
                      'stripe_transfer_id', 'transfer_status',
                      'error_message', 'created_at', 'updated_at']:
            self.assertIn(field, item,
                          f"PaymentSplitSerializer field '{field}' missing from response")

    def test_FINDING4_seller_payout_fields_absent_from_response(self):
        """
        FINDING-4: Despite the URL name 'payout-list', response contains PaymentSplit
        fields, NOT SellerPayout fields. The field 'platform_fee' (SellerPayout)
        is absent; instead 'platform_fee_amount' (PaymentSplit) is present.
        """
        self._auth_as(self.seller)
        response = self.client.get(reverse('payments:payout-list'))
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        item = results[0]

        # SellerPayout fields that are NOT in PaymentSplitSerializer
        self.assertNotIn('platform_fee', item,
                         "FINDING-4: 'platform_fee' (SellerPayout field) must NOT be present")
        self.assertNotIn('scheduled_for', item,
                         "FINDING-4: 'scheduled_for' (SellerPayout field) must NOT be present")
        self.assertNotIn('paid_at', item,
                         "FINDING-4: 'paid_at' (SellerPayout field) must NOT be present")

        # PaymentSplit fields that ARE present
        self.assertIn('platform_fee_amount', item,
                      "PaymentSplit field 'platform_fee_amount' must be present")
        self.assertIn('transfer_status', item,
                      "PaymentSplit field 'transfer_status' must be present")

    def test_product_shipping_fields_present_in_serializer(self):
        """
        PaymentSplitSerializer exposes product_amount, shipping_amount, and
        shipping_status (added in migration 0004). Sellers can see the full
        product/shipping breakdown from the API.
        Note: initial audit suspected these were absent — they have since been added.
        """
        self._auth_as(self.seller)
        response = self.client.get(reverse('payments:payout-list'))
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        item = results[0]

        self.assertIn('product_amount', item,
                      "'product_amount' must be present in PaymentSplitSerializer response")
        self.assertIn('shipping_amount', item,
                      "'shipping_amount' must be present in PaymentSplitSerializer response")
        self.assertIn('shipping_status', item,
                      "'shipping_status' must be present in PaymentSplitSerializer response")
        self.assertIn('order_number', item,
                      "'order_number' (via payment.order) must be present")

        # Validate the values
        self.assertEqual(Decimal(item['product_amount']), Decimal('100.00'))
        self.assertEqual(Decimal(item['shipping_amount']), Decimal('0.00'))
        self.assertEqual(item['shipping_status'], 'held')

    def test_list_financial_values_are_correct(self):
        """Gross, fee, net amounts match the PaymentSplit record."""
        self._auth_as(self.seller)
        response = self.client.get(reverse('payments:payout-list'))
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        item = results[0]
        self.assertEqual(Decimal(item['gross_amount']), Decimal('100.00'))
        self.assertEqual(Decimal(item['platform_fee_amount']), Decimal('10.00'))
        self.assertEqual(Decimal(item['net_amount']), Decimal('90.00'))
        self.assertEqual(item['transfer_status'], 'dispatched')

    def test_list_order_is_newest_first(self):
        """Splits are returned newest first (-created_at).
        PaymentSplit.unique_together = (payment, seller), so a new payment is
        required for each additional split for the same seller."""
        # Create a second order + payment + split for the same seller
        order2 = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('200.00'),
            shipping_address={'street': 'Test2', 'city': 'RJ'},
            status='paid',
        )
        payment2 = Payment.objects.create(
            order=order2,
            user=self.buyer,
            stripe_payment_intent_id='pi_test_split_pb_2',
            amount=Decimal('200.00'),
            currency='BRL',
            status='succeeded',
            payment_method='credit_card',
            transfer_group='tg_test_split_pb_2',
        )
        split2 = PaymentSplit.objects.create(
            payment=payment2,
            seller=self.seller,
            gross_amount=Decimal('200.00'),
            product_amount=Decimal('200.00'),
            shipping_amount=Decimal('0.00'),
            platform_fee_amount=Decimal('20.00'),
            net_amount=Decimal('180.00'),
            stripe_transfer_id='tr_test_split_pb_2',
            transfer_status='pending',
        )

        self._auth_as(self.seller)
        response = self.client.get(reverse('payments:payout-list'))
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['id'], split2.pk,
                         "Most recently created split must appear first")

    def test_list_only_accepts_get(self):
        """POST returns 405."""
        self._auth_as(self.seller)
        response = self.client.post(reverse('payments:payout-list'), {})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# ===========================================================================
# 3. SellerPayoutDetailView -> GET /payouts/<id>/
# ===========================================================================

class TestSellerPayoutDetailView(BasePayoutTestCase):
    """Tests for GET /api/payments/payouts/<id>/ (returns PaymentSplit)."""

    def test_seller_can_retrieve_own_split(self):
        """Seller can retrieve their own PaymentSplit record by ID."""
        self._auth_as(self.seller)
        response = self.client.get(
            reverse('payments:payout-detail', kwargs={'pk': self.split.pk})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['id'], self.split.pk)
        self.assertEqual(data['stripe_transfer_id'], 'tr_test_split_pb')
        self.assertEqual(data['transfer_status'], 'dispatched')

    def test_other_seller_cannot_access_split_returns_404(self):
        """Another seller gets 404 (queryset filtered by seller)."""
        self._auth_as(self.other_seller)
        response = self.client.get(
            reverse('payments:payout-detail', kwargs={'pk': self.split.pk})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_buyer_cannot_access_split(self):
        """Buyer gets 404 when accessing a seller's split."""
        self._auth_as(self.buyer)
        response = self.client.get(
            reverse('payments:payout-detail', kwargs={'pk': self.split.pk})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_split_returns_404(self):
        """Non-existent ID returns 404."""
        self._auth_as(self.seller)
        response = self.client.get(
            reverse('payments:payout-detail', kwargs={'pk': 99999})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_financial_values_match_split_record(self):
        """Detail response values match the stored PaymentSplit."""
        self._auth_as(self.seller)
        response = self.client.get(
            reverse('payments:payout-detail', kwargs={'pk': self.split.pk})
        )
        data = response.json()
        self.assertEqual(Decimal(data['gross_amount']), Decimal('100.00'))
        self.assertEqual(Decimal(data['platform_fee_amount']), Decimal('10.00'))
        self.assertEqual(Decimal(data['net_amount']), Decimal('90.00'))
        self.assertEqual(data['seller_email'], 'seller_payout@test.com')

    def test_detail_error_message_is_empty_for_dispatched_split(self):
        """error_message is empty for a successfully dispatched split."""
        self._auth_as(self.seller)
        response = self.client.get(
            reverse('payments:payout-detail', kwargs={'pk': self.split.pk})
        )
        data = response.json()
        self.assertEqual(data['error_message'], '')

    def test_detail_failed_split_has_error_message(self):
        """A failed split's error_message is visible in the detail response."""
        order2 = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('50.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('50.00'),
            shipping_address={'street': 'Err St', 'city': 'SP'},
            status='paid',
        )
        payment2 = Payment.objects.create(
            order=order2,
            user=self.buyer,
            stripe_payment_intent_id='pi_test_failed_split_pb',
            amount=Decimal('50.00'),
            currency='BRL',
            status='succeeded',
            payment_method='credit_card',
            transfer_group='tg_test_failed_pb',
        )
        failed_split = PaymentSplit.objects.create(
            payment=payment2,
            seller=self.seller,
            gross_amount=Decimal('50.00'),
            product_amount=Decimal('50.00'),
            shipping_amount=Decimal('0.00'),
            platform_fee_amount=Decimal('5.00'),
            net_amount=Decimal('45.00'),
            stripe_transfer_id='',
            transfer_status='failed',
            error_message='Seller has no stripe_account_id.',
        )
        self._auth_as(self.seller)
        response = self.client.get(
            reverse('payments:payout-detail', kwargs={'pk': failed_split.pk})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['transfer_status'], 'failed')
        self.assertIn('stripe_account_id', data['error_message'])


# ===========================================================================
# 4. seller_balance -> GET /balance/
# ===========================================================================

class TestSellerBalanceView(BasePayoutTestCase):
    """
    Tests for GET /api/payments/balance/

    This endpoint:
    1. Aggregates PaymentSplit.net_amount by transfer_status (local DB)
    2. Calls stripe.Balance.retrieve(stripe_account=...) for real-time balance
    """

    def test_balance_returns_correct_structure(self):
        """Balance response has all expected keys."""
        with self._mock_stripe_balance_and_payouts(available_cents=9000, pending_cents=0):
            self._auth_as(self.seller)
            response = self.client.get(reverse('payments:seller-balance'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        for key in ['stripe_available', 'stripe_pending', 'stripe_in_transit',
                    'stripe_balance_error',
                    'pending_transfers', 'dispatched_transfers',
                    'failed_transfers', 'splits_count']:
            self.assertIn(key, data,
                          f"Balance response missing key '{key}'")
        self.assertNotIn('total_dispatched', data,
                         "total_dispatched was removed as redundant — use dispatched_transfers")

    def test_FINDING6_total_available_absent_from_response(self):
        """
        FINDING-6: The old 'total_available' field no longer exists in the response.
        Any frontend code relying on response['total_available'] will get undefined.
        The correct fields are now 'stripe_available' (live) and 'dispatched_transfers' (local).
        """
        with self._mock_stripe_balance_and_payouts():
            self._auth_as(self.seller)
            response = self.client.get(reverse('payments:seller-balance'))
        data = response.json()
        self.assertNotIn('total_available', data,
                         "FINDING-6: 'total_available' removed — must NOT be in response")

    def test_FINDING2_total_dispatched_removed(self):
        """
        FINDING-2 fixed: 'total_dispatched' was removed because it duplicated 'dispatched_transfers'.
        Frontend must use 'dispatched_transfers' as the canonical field.
        """
        with self._mock_stripe_balance_and_payouts():
            self._auth_as(self.seller)
            response = self.client.get(reverse('payments:seller-balance'))
        data = response.json()
        self.assertNotIn('total_dispatched', data,
                         "FINDING-2 fixed: total_dispatched must be absent — use dispatched_transfers")
        self.assertIn('dispatched_transfers', data)

    def test_dispatched_split_appears_in_dispatched_transfers(self):
        """The setUp dispatched split of 90 BRL must appear in dispatched_transfers."""
        with self._mock_stripe_balance_and_payouts(available_cents=9000):
            self._auth_as(self.seller)
            response = self.client.get(reverse('payments:seller-balance'))
        data = response.json()
        self.assertAlmostEqual(float(data['dispatched_transfers']), 90.00, places=2)
        self.assertEqual(data['splits_count'], 1)

    def test_stripe_available_reflects_mock_balance(self):
        """stripe_available is correctly derived from Stripe API response (in BRL)."""
        with self._mock_stripe_balance_and_payouts(available_cents=150000, pending_cents=30000):
            self._auth_as(self.seller)
            response = self.client.get(reverse('payments:seller-balance'))
        data = response.json()
        self.assertAlmostEqual(data['stripe_available'], 1500.00, places=2,
                               msg="150000 cents = 1500.00 BRL")
        self.assertAlmostEqual(data['stripe_pending'], 300.00, places=2,
                               msg="30000 cents = 300.00 BRL")

    def test_stripe_in_transit_reflects_payout_list(self):
        """
        stripe_in_transit is the sum of in_transit payouts from stripe.Payout.list.
        A single payout of 255160 cents must yield stripe_in_transit = 2551.60.
        """
        with self._mock_stripe_balance_and_payouts(
            available_cents=0,
            pending_cents=0,
            in_transit_cents=[255160],
        ):
            self._auth_as(self.seller)
            response = self.client.get(reverse('payments:seller-balance'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertAlmostEqual(data['stripe_in_transit'], 2551.60, places=2,
                               msg="255160 cents = 2551.60 BRL in transit")
        self.assertFalse(data['stripe_balance_error'])

    def test_FINDING3_stripe_api_failure_sets_error_flag(self):
        """
        FINDING-3 fixed: When stripe.Balance.retrieve raises a StripeError,
        the endpoint returns stripe_balance_error=True and stripe_available=None,
        allowing the frontend to show a 'balance unavailable' state instead of R$0.
        stripe_in_transit must also be None in this case.
        """
        with patch('stripe.Balance.retrieve', side_effect=stripe.error.StripeError("API down")):
            self._auth_as(self.seller)
            response = self.client.get(reverse('payments:seller-balance'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['stripe_balance_error'],
                        "FINDING-3 fixed: stripe_balance_error must be True on Stripe failure")
        self.assertIsNone(data['stripe_available'],
                          "FINDING-3 fixed: stripe_available must be None (not 0) when unavailable")
        self.assertIsNone(data['stripe_pending'],
                          "FINDING-3 fixed: stripe_pending must be None (not 0) when unavailable")
        self.assertIsNone(data['stripe_in_transit'],
                          "stripe_in_transit must be None when Stripe API fails")

    def test_seller_without_stripe_account_skips_stripe_call(self):
        """A seller with no stripe_account_id gets stripe_available=None, no API call."""
        user_no_stripe = User.objects.create_user(
            email='no_stripe_seller@test.com',
            password='pass',
            stripe_account_id='',
        )
        with patch('stripe.Balance.retrieve') as mock_retrieve, \
             patch('stripe.Payout.list') as mock_payout_list:
            self._auth_as(user_no_stripe)
            response = self.client.get(reverse('payments:seller-balance'))
            mock_retrieve.assert_not_called()
            mock_payout_list.assert_not_called()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIsNone(data['stripe_available'])
        self.assertIsNone(data['stripe_pending'])
        self.assertIsNone(data['stripe_in_transit'])
        self.assertFalse(data['stripe_balance_error'])

    def test_balance_aggregates_multiple_splits_correctly(self):
        """Multiple splits in different statuses are aggregated into the correct buckets."""
        order2 = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('200.00'),
            shipping_address={'street': 'Test2', 'city': 'RJ'},
            status='paid',
        )
        payment2 = Payment.objects.create(
            order=order2, user=self.buyer,
            stripe_payment_intent_id='pi_agg_test_pb',
            amount=Decimal('200.00'), currency='BRL',
            status='succeeded', payment_method='credit_card',
            transfer_group='tg_agg_test_pb',
        )
        # pending split: net=180
        PaymentSplit.objects.create(
            payment=payment2, seller=self.seller,
            gross_amount=Decimal('200.00'), product_amount=Decimal('200.00'),
            shipping_amount=Decimal('0.00'), platform_fee_amount=Decimal('20.00'),
            net_amount=Decimal('180.00'),
            stripe_transfer_id='', transfer_status='pending',
        )
        order3 = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('300.00'), shipping_cost=Decimal('0.00'),
            total=Decimal('300.00'),
            shipping_address={'street': 'Test3', 'city': 'BH'},
            status='paid',
        )
        payment3 = Payment.objects.create(
            order=order3, user=self.buyer,
            stripe_payment_intent_id='pi_agg_test_pb_3',
            amount=Decimal('300.00'), currency='BRL',
            status='succeeded', payment_method='credit_card',
            transfer_group='tg_agg_test_pb_3',
        )
        # failed split: net=270
        PaymentSplit.objects.create(
            payment=payment3, seller=self.seller,
            gross_amount=Decimal('300.00'), product_amount=Decimal('300.00'),
            shipping_amount=Decimal('0.00'), platform_fee_amount=Decimal('30.00'),
            net_amount=Decimal('270.00'),
            stripe_transfer_id='', transfer_status='failed',
            error_message='Stripe error',
        )

        with self._mock_stripe_balance_and_payouts():
            self._auth_as(self.seller)
            response = self.client.get(reverse('payments:seller-balance'))
        data = response.json()

        # dispatched=90, pending=180, failed=270, splits_count=3
        self.assertAlmostEqual(float(data['dispatched_transfers']), 90.00, places=2)
        self.assertAlmostEqual(float(data['pending_transfers']), 180.00, places=2)
        self.assertAlmostEqual(float(data['failed_transfers']), 270.00, places=2)
        self.assertEqual(data['splits_count'], 3)

    def test_balance_is_isolated_to_authenticated_seller(self):
        """Balance does not include other sellers' splits."""
        order2 = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('1000.00'), shipping_cost=Decimal('0.00'),
            total=Decimal('1000.00'),
            shipping_address={'street': 'Other', 'city': 'SP'},
            status='paid',
        )
        payment2 = Payment.objects.create(
            order=order2, user=self.buyer,
            stripe_payment_intent_id='pi_other_seller_pb',
            amount=Decimal('1000.00'), currency='BRL',
            status='succeeded', payment_method='credit_card',
            transfer_group='tg_other_seller_pb',
        )
        PaymentSplit.objects.create(
            payment=payment2, seller=self.other_seller,
            gross_amount=Decimal('1000.00'), product_amount=Decimal('1000.00'),
            shipping_amount=Decimal('0.00'), platform_fee_amount=Decimal('100.00'),
            net_amount=Decimal('900.00'),
            stripe_transfer_id='tr_other_seller_pb',
            transfer_status='dispatched',
        )

        with self._mock_stripe_balance_and_payouts(available_cents=9000):
            self._auth_as(self.seller)
            response = self.client.get(reverse('payments:seller-balance'))
        data = response.json()

        # seller sees only their 90, not other_seller's 900
        self.assertAlmostEqual(float(data['dispatched_transfers']), 90.00, places=2,
                               msg="Balance must be isolated to the authenticated seller")
        self.assertEqual(data['splits_count'], 1)

    def test_balance_only_accepts_get(self):
        """POST returns 405."""
        self._auth_as(self.seller)
        response = self.client.post(reverse('payments:seller-balance'), {})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_balance_zero_for_seller_with_no_splits(self):
        """A seller with no splits gets zeros for all buckets."""
        with self._mock_stripe_balance_and_payouts(available_cents=0, pending_cents=0):
            self._auth_as(self.other_seller)
            response = self.client.get(reverse('payments:seller-balance'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertAlmostEqual(float(data['dispatched_transfers']), 0.0, places=2)
        self.assertAlmostEqual(float(data['pending_transfers']), 0.0, places=2)
        self.assertAlmostEqual(float(data['failed_transfers']), 0.0, places=2)
        self.assertEqual(data['splits_count'], 0)


# ===========================================================================
# 5. SellerPayout Legacy Model
# ===========================================================================

class TestSellerPayoutLegacyModel(BasePayoutTestCase):
    """
    FINDING-1: SellerPayout is never used by any current endpoint.
    Documents the dead code state of the model.
    """

    def test_FINDING1_payout_list_endpoint_does_not_query_seller_payout(self):
        """
        FINDING-1: The 'payout-list' endpoint (SellerPayoutListView) queries
        PaymentSplit, not SellerPayout. Even if SellerPayout records exist for
        a seller, they are NOT returned by this endpoint.
        """
        # Create a SellerPayout for the seller
        SellerPayout.objects.create(
            seller=self.seller,
            order=self.order,
            gross_amount=Decimal('100.00'),
            platform_fee=Decimal('10.00'),
            net_amount=Decimal('90.00'),
            status='pending',
            stripe_transfer_id='tr_legacy_pb',
            scheduled_for=timezone.now(),
        )

        self._auth_as(self.seller)
        response = self.client.get(reverse('payments:payout-list'))
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data

        # Only PaymentSplit records should appear (1 from setUp)
        self.assertEqual(len(results), 1,
                         "FINDING-1: SellerPayout (legacy) records do NOT appear "
                         "in payout-list — only PaymentSplit records")

        # Confirm the one result is the PaymentSplit, not SellerPayout
        item = results[0]
        self.assertIn('transfer_status', item,
                      "Result is a PaymentSplit (has transfer_status)")
        self.assertNotIn('scheduled_for', item,
                         "Result is NOT a SellerPayout (no scheduled_for)")

    def test_FINDING1_balance_does_not_aggregate_seller_payout(self):
        """
        FINDING-1 consequence for balance: Adding SellerPayout records does NOT
        affect seller_balance. The balance aggregates PaymentSplit only.
        """
        SellerPayout.objects.create(
            seller=self.seller,
            order=self.order,
            gross_amount=Decimal('500.00'),
            platform_fee=Decimal('50.00'),
            net_amount=Decimal('450.00'),
            status='pending',
            stripe_transfer_id='tr_legacy_balance_pb',
            scheduled_for=timezone.now(),
        )

        with self._mock_stripe_balance_and_payouts():
            self._auth_as(self.seller)
            response = self.client.get(reverse('payments:seller-balance'))
        data = response.json()

        # dispatched_transfers still reflects only PaymentSplit (90), not SellerPayout (450)
        self.assertAlmostEqual(float(data['dispatched_transfers']), 90.00, places=2,
                               msg="FINDING-1: SellerPayout.net_amount NOT added to balance")
        # No 'pending' key from old SellerPayout aggregate
        self.assertNotIn('pending', data,
                         "FINDING-1: Old 'pending' key (from SellerPayout) is absent")
