"""
Tests for multi-seller PaymentIntent creation.

Validates that:
1. Two sellers in cart → two Orders → two PaymentIntents (via batch endpoint)
2. Each PaymentIntent amount = total of its Order (not the entire cart)
3. metadata["order_id"] is correct on each PI
4. Webhook payment_intent.succeeded updates only the correct Order
5. Refund operates on the correct Order's PaymentIntent
6. Batch endpoint correctly isolates failures (one failed Order does not abort others)
"""

import json
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from products.models import (
    Products, Brand, Condition, MarketplaceListing, Category, Series
)
from orders.models import Order, OrderItem
from payments.models import Payment, PaymentSplit, PaymentWebhook
from payments.payment_intent_service import PaymentIntentService
from payments.webhook_service import WebhookService

User = get_user_model()


def _make_mock_stripe_event(event_type, data_object):
    """Helper to create a mock Stripe event."""
    event = MagicMock()
    event.id = f'evt_{event_type.replace(".", "_")}_test'
    event.type = event_type
    event.data = MagicMock()
    event.data.object = data_object
    return event


class MultiSellerPaymentIntentSetupMixin:
    """
    Common setUp for multi-seller tests.

    Creates:
    - buyer
    - seller_a (with stripe_account_id)
    - seller_b (with stripe_account_id)
    - Two listings (one per seller)
    - Two Orders (one per seller, simulating the new per-seller order model)
    """

    def setUp(self):
        self.client = APIClient()

        self.buyer = User.objects.create_user(
            email='buyer_ms@test.com',
            password='testpass',
        )
        self.seller_a = User.objects.create_user(
            email='seller_a@test.com',
            password='testpass',
            stripe_account_id='acct_seller_a_123',
        )
        self.seller_b = User.objects.create_user(
            email='seller_b@test.com',
            password='testpass',
            stripe_account_id='acct_seller_b_456',
        )

        self.brand = Brand.objects.create(name='Brand MS', slug='brand-ms')
        self.condition = Condition.objects.create(name='New MS', slug='new-ms')
        self.category = Category.objects.create(name='Cat MS', slug='cat-ms')
        self.series = Series.objects.create(name='Series MS', slug='series-ms')

        product_a = Products.objects.create(
            name='Product A', slug='product-a',
            category=self.category, series=self.series,
        )
        product_b = Products.objects.create(
            name='Product B', slug='product-b',
            category=self.category, series=self.series,
        )

        self.listing_a = MarketplaceListing.objects.create(
            product=product_a, seller=self.seller_a,
            brand=self.brand, condition=self.condition,
            price=Decimal('150.00'), quantity=10, is_active=True,
            weight_kg=Decimal('2.00'), height_cm=Decimal('10.00'),
            width_cm=Decimal('10.00'), length_cm=Decimal('10.00'),
        )
        self.listing_b = MarketplaceListing.objects.create(
            product=product_b, seller=self.seller_b,
            brand=self.brand, condition=self.condition,
            price=Decimal('200.00'), quantity=10, is_active=True,
            weight_kg=Decimal('3.00'), height_cm=Decimal('15.00'),
            width_cm=Decimal('15.00'), length_cm=Decimal('15.00'),
        )

        common_address = {
            'street': 'Rua Teste', 'number': '100',
            'city': 'São Paulo', 'state': 'SP', 'zipcode': '01310-100',
        }

        # Order A — seller_a only, total = 150 + 10 (shipping) = 160
        self.order_a = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller_a,
            subtotal=Decimal('150.00'),
            shipping_cost=Decimal('10.00'),
            total=Decimal('160.00'),
            shipping_address=common_address,
            status='pending_payment',
        )
        OrderItem.objects.create(
            order=self.order_a,
            listing=self.listing_a,
            seller=self.seller_a,
            quantity=1,
            unit_price=Decimal('150.00'),
            subtotal=Decimal('150.00'),
            shipping_cost=Decimal('10.00'),
            product_name='Product A',
            product_code='',
            brand_name=self.brand.name,
            condition_name=self.condition.name,
            weight_kg=Decimal('2.00'),
            height_cm=Decimal('10.00'),
            width_cm=Decimal('10.00'),
            length_cm=Decimal('10.00'),
        )

        # Order B — seller_b only, total = 200 + 15 (shipping) = 215
        self.order_b = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller_b,
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('15.00'),
            total=Decimal('215.00'),
            shipping_address=common_address,
            status='pending_payment',
        )
        OrderItem.objects.create(
            order=self.order_b,
            listing=self.listing_b,
            seller=self.seller_b,
            quantity=1,
            unit_price=Decimal('200.00'),
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('15.00'),
            product_name='Product B',
            product_code='',
            brand_name=self.brand.name,
            condition_name=self.condition.name,
            weight_kg=Decimal('3.00'),
            height_cm=Decimal('15.00'),
            width_cm=Decimal('15.00'),
            length_cm=Decimal('15.00'),
        )

        self.client.force_authenticate(user=self.buyer)


class TestMultiSellerBatchEndpoint(MultiSellerPaymentIntentSetupMixin, TestCase):
    """
    Tests for POST /api/payments/create-intents-batch/
    """

    def _mock_account(self):
        """Return a mock Account with charges_enabled=True."""
        mock = MagicMock()
        mock.get.return_value = True
        return mock

    def _mock_pi(self, pi_id, client_secret):
        """Return a minimal mock PaymentIntent."""
        mock = MagicMock()
        mock.id = pi_id
        mock.client_secret = client_secret
        mock.status = 'requires_payment_method'
        mock.created = 1700000000
        return mock

    @patch('payments.payment_intent_service.stripe.Account.retrieve')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    def test_two_sellers_create_two_payment_intents(self, mock_pi_create, mock_account):
        """
        Two Orders from different sellers → batch endpoint creates two PaymentIntents.
        """
        mock_account.return_value = self._mock_account()

        call_counter = {'n': 0}

        def pi_create_side_effect(**kwargs):
            call_counter['n'] += 1
            pi_id = f'pi_seller_{call_counter["n"]}'
            return self._mock_pi(pi_id, f'{pi_id}_secret')

        mock_pi_create.side_effect = pi_create_side_effect

        response = self.client.post(
            '/api/payments/create-intents-batch/',
            data={
                'order_ids': [str(self.order_a.id), str(self.order_b.id)],
                'payment_method': 'credit_card',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(len(data['succeeded']), 2)
        self.assertEqual(len(data['failed']), 0)

        # stripe.PaymentIntent.create must be called exactly twice
        self.assertEqual(mock_pi_create.call_count, 2)

        # Exactly two Payment records created in DB
        self.assertEqual(Payment.objects.filter(user=self.buyer).count(), 2)

    @patch('payments.payment_intent_service.stripe.Account.retrieve')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    def test_each_payment_intent_amount_matches_order_total(
        self, mock_pi_create, mock_account
    ):
        """
        Each PaymentIntent amount must equal the total of its Order,
        NOT the combined total of both orders.
        """
        mock_account.return_value = self._mock_account()

        call_counter = {'n': 0}

        def pi_create_side_effect(**kwargs):
            call_counter['n'] += 1
            pi_id = f'pi_amount_test_{call_counter["n"]}'
            return self._mock_pi(pi_id, f'{pi_id}_secret')

        mock_pi_create.side_effect = pi_create_side_effect

        response = self.client.post(
            '/api/payments/create-intents-batch/',
            data={
                'order_ids': [str(self.order_a.id), str(self.order_b.id)],
                'payment_method': 'credit_card',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Extract amounts from stripe.PaymentIntent.create call args
        calls = mock_pi_create.call_args_list
        amounts_cents = {c.kwargs['amount'] for c in calls}

        # order_a total = 160.00 → 16000 cents
        # order_b total = 215.00 → 21500 cents
        self.assertIn(16000, amounts_cents)
        self.assertIn(21500, amounts_cents)

        # Combined total (37500) must NOT be among the amounts
        self.assertNotIn(37500, amounts_cents)

    @patch('payments.payment_intent_service.stripe.Account.retrieve')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    def test_metadata_order_id_is_correct_per_intent(
        self, mock_pi_create, mock_account
    ):
        """
        Each PaymentIntent must carry metadata['order_id'] equal to its own Order's UUID.
        """
        mock_account.return_value = self._mock_account()

        recorded_metadata = []

        def pi_create_side_effect(**kwargs):
            recorded_metadata.append(kwargs.get('metadata', {}))
            n = len(recorded_metadata)
            pi_id = f'pi_meta_{n}'
            return self._mock_pi(pi_id, f'{pi_id}_secret')

        mock_pi_create.side_effect = pi_create_side_effect

        response = self.client.post(
            '/api/payments/create-intents-batch/',
            data={
                'order_ids': [str(self.order_a.id), str(self.order_b.id)],
                'payment_method': 'pix',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(recorded_metadata), 2)

        order_ids_in_metadata = {m['order_id'] for m in recorded_metadata}
        self.assertIn(str(self.order_a.id), order_ids_in_metadata)
        self.assertIn(str(self.order_b.id), order_ids_in_metadata)

    @patch('payments.payment_intent_service.stripe.Account.retrieve')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    def test_failed_order_does_not_abort_other_orders(
        self, mock_pi_create, mock_account
    ):
        """
        If one Order's PI creation fails (e.g., seller not ready),
        the other Order should still get its PI created.
        """
        # seller_b has no Stripe account for this test
        self.seller_b.stripe_account_id = ''
        self.seller_b.save()

        mock_account.return_value = self._mock_account()

        def pi_create_side_effect(**kwargs):
            return self._mock_pi('pi_only_seller_a', 'pi_only_seller_a_secret')

        mock_pi_create.side_effect = pi_create_side_effect

        response = self.client.post(
            '/api/payments/create-intents-batch/',
            data={
                'order_ids': [str(self.order_a.id), str(self.order_b.id)],
                'payment_method': 'credit_card',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        # order_a succeeds, order_b fails
        self.assertEqual(len(data['succeeded']), 1)
        self.assertEqual(len(data['failed']), 1)

        succeeded_order_ids = {str(item['order_id']) for item in data['succeeded']}
        failed_order_ids = {str(item['order_id']) for item in data['failed']}

        self.assertIn(str(self.order_a.id), succeeded_order_ids)
        self.assertIn(str(self.order_b.id), failed_order_ids)

    @patch('payments.payment_intent_service.stripe.Account.retrieve')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    def test_batch_endpoint_reuses_pending_payment_intent(
        self, mock_pi_create, mock_account
    ):
        """
        If a pending PI already exists for an Order, the batch endpoint
        reuses it (reused=True) without calling stripe.PaymentIntent.create again.
        """
        mock_account.return_value = self._mock_account()

        # Pre-create a Payment for order_a with a pending PI
        existing_payment = Payment.objects.create(
            order=self.order_a,
            user=self.buyer,
            stripe_payment_intent_id='pi_existing_pending',
            amount=self.order_a.total,
            currency='brl',
            payment_method='credit_card',
            status='pending',
        )

        # Make order_b's PI creation succeed
        mock_pi_create.return_value = self._mock_pi('pi_new_b', 'pi_new_b_secret')

        with patch(
            'payments.payment_intent_service.stripe.PaymentIntent.retrieve'
        ) as mock_retrieve:
            mock_retrieve.return_value = self._mock_pi(
                'pi_existing_pending', 'pi_existing_pending_secret'
            )

            response = self.client.post(
                '/api/payments/create-intents-batch/',
                data={
                    'order_ids': [str(self.order_a.id), str(self.order_b.id)],
                    'payment_method': 'credit_card',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(len(data['succeeded']), 2)
        self.assertEqual(len(data['failed']), 0)

        # PI create called only once (for order_b)
        self.assertEqual(mock_pi_create.call_count, 1)

        # order_a result must have reused=True
        order_a_result = next(
            item for item in data['succeeded']
            if str(item['order_id']) == str(self.order_a.id)
        )
        self.assertTrue(order_a_result['reused'])

        # order_b result must have reused=False
        order_b_result = next(
            item for item in data['succeeded']
            if str(item['order_id']) == str(self.order_b.id)
        )
        self.assertFalse(order_b_result['reused'])

    def test_batch_endpoint_rejects_unknown_order(self):
        """
        Order IDs that don't belong to the buyer must appear in failed.
        """
        import uuid
        fake_order_id = str(uuid.uuid4())

        with patch('payments.payment_intent_service.stripe.Account.retrieve'), \
             patch('payments.payment_intent_service.stripe.PaymentIntent.create'):

            response = self.client.post(
                '/api/payments/create-intents-batch/',
                data={
                    'order_ids': [fake_order_id],
                    'payment_method': 'credit_card',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['failed']), 1)
        self.assertEqual(str(response.data['failed'][0]['order_id']), fake_order_id)

    def test_batch_endpoint_rejects_already_succeeded_order(self):
        """
        Order with a succeeded Payment must appear in failed.
        """
        Payment.objects.create(
            order=self.order_a,
            user=self.buyer,
            stripe_payment_intent_id='pi_already_succeeded',
            amount=self.order_a.total,
            currency='brl',
            payment_method='credit_card',
            status='succeeded',
        )

        with patch('payments.payment_intent_service.stripe.Account.retrieve'), \
             patch('payments.payment_intent_service.stripe.PaymentIntent.create'):

            response = self.client.post(
                '/api/payments/create-intents-batch/',
                data={
                    'order_ids': [str(self.order_a.id)],
                    'payment_method': 'credit_card',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['failed']), 1)
        self.assertIn('confirmado', response.data['failed'][0]['error'])

    def test_batch_requires_at_least_one_order_id(self):
        """Sending empty order_ids list must return 400."""
        response = self.client.post(
            '/api/payments/create-intents-batch/',
            data={'order_ids': [], 'payment_method': 'credit_card'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestWebhookUpdatesCorrectOrder(MultiSellerPaymentIntentSetupMixin, TestCase):
    """
    Validates that payment_intent.succeeded webhook updates ONLY the
    Order that corresponds to the webhook's PaymentIntent.
    """

    def setUp(self):
        super().setUp()

        # Create one Payment per Order (simulate batch endpoint having been called)
        self.payment_a = Payment.objects.create(
            order=self.order_a,
            user=self.buyer,
            stripe_payment_intent_id='pi_order_a_wh',
            amount=self.order_a.total,
            currency='brl',
            payment_method='credit_card',
            status='pending',
            transfer_group='group_order_a',
        )
        self.payment_b = Payment.objects.create(
            order=self.order_b,
            user=self.buyer,
            stripe_payment_intent_id='pi_order_b_wh',
            amount=self.order_b.total,
            currency='brl',
            payment_method='credit_card',
            status='pending',
            transfer_group='group_order_b',
        )

    @patch('payments.webhook_service.stripe.PaymentIntent.retrieve')
    @patch('payments.services.transfer_dispatch_service.stripe.Transfer.create')
    @patch(
        'logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order'
    )
    def test_webhook_succeeded_updates_only_correct_order(
        self, mock_checkout, mock_transfer_create, mock_pi_retrieve
    ):
        """
        payment_intent.succeeded for order_a must:
        - mark payment_a as succeeded
        - mark order_a as paid
        - NOT touch payment_b or order_b
        """
        # ShipmentCreationService is a no-op for this test (no real shipments)
        mock_checkout.return_value = None

        # Mock the PI retrieve with latest_charge expanded
        mock_charge = MagicMock()
        mock_charge.id = 'ch_test_a'
        mock_charge.receipt_url = 'https://receipt.stripe.com/test_a'

        mock_pi = MagicMock()
        mock_pi.id = 'pi_order_a_wh'
        mock_pi.amount = 16000  # 160.00 BRL in cents
        mock_pi.status = 'succeeded'
        mock_pi.latest_charge = mock_charge
        mock_pi_retrieve.return_value = mock_pi

        # Mock transfer creation (seller_a has stripe_account_id)
        mock_transfer_create.return_value = MagicMock(id='tr_test_a')

        pi_data = MagicMock()
        pi_data.id = 'pi_order_a_wh'
        pi_data.amount = 16000
        pi_data.status = 'succeeded'
        pi_data.latest_charge = mock_charge

        event = _make_mock_stripe_event('payment_intent.succeeded', pi_data)

        with patch(
            'payments.webhook_service.WebhookService.verify_webhook_signature',
            return_value=event,
        ):
            WebhookService.handle_webhook(b'{}', 'sig_test')

        # Reload from DB
        self.payment_a.refresh_from_db()
        self.payment_b.refresh_from_db()
        self.order_a.refresh_from_db()
        self.order_b.refresh_from_db()

        # payment_a → succeeded
        self.assertEqual(self.payment_a.status, 'succeeded')
        # order_a → paid
        self.assertEqual(self.order_a.status, 'paid')

        # payment_b and order_b must remain untouched
        self.assertEqual(self.payment_b.status, 'pending')
        self.assertEqual(self.order_b.status, 'pending_payment')

    def test_webhook_failed_updates_only_correct_order(self):
        """
        payment_intent.payment_failed for order_b must:
        - mark payment_b as failed
        - mark order_b as failed
        - NOT touch payment_a or order_a
        """
        # Build a pi_data with concrete (non-MagicMock) values to avoid JSON
        # serialization failures when the webhook handler stores metadata.
        last_error = MagicMock()
        last_error.message = 'Card declined'
        last_error.code = 'card_declined'  # must be a plain string

        pi_data = MagicMock()
        pi_data.id = 'pi_order_b_wh'
        pi_data.status = 'requires_payment_method'  # must be a plain string
        pi_data.last_payment_error = last_error

        event = _make_mock_stripe_event('payment_intent.payment_failed', pi_data)

        with patch(
            'payments.webhook_service.WebhookService.verify_webhook_signature',
            return_value=event,
        ):
            WebhookService.handle_webhook(b'{}', 'sig_test')

        self.payment_a.refresh_from_db()
        self.payment_b.refresh_from_db()
        self.order_a.refresh_from_db()
        self.order_b.refresh_from_db()

        self.assertEqual(self.payment_b.status, 'failed')
        self.assertEqual(self.order_b.status, 'failed')

        self.assertEqual(self.payment_a.status, 'pending')
        self.assertEqual(self.order_a.status, 'pending_payment')


class TestRefundOperatesOnCorrectOrder(MultiSellerPaymentIntentSetupMixin, TestCase):
    """
    Validates that RefundRequest references the correct Order's Payment,
    ensuring refund of seller_a does not affect seller_b's Payment.
    """

    def setUp(self):
        super().setUp()

        # Simulate payments already succeeded
        self.payment_a = Payment.objects.create(
            order=self.order_a,
            user=self.buyer,
            stripe_payment_intent_id='pi_a_refund_test',
            stripe_charge_id='ch_a_refund',
            amount=self.order_a.total,
            currency='brl',
            payment_method='credit_card',
            status='succeeded',
            transfer_group='group_a',
        )
        self.payment_b = Payment.objects.create(
            order=self.order_b,
            user=self.buyer,
            stripe_payment_intent_id='pi_b_refund_test',
            stripe_charge_id='ch_b_refund',
            amount=self.order_b.total,
            currency='brl',
            payment_method='credit_card',
            status='succeeded',
            transfer_group='group_b',
        )

        # Mark orders as paid
        self.order_a.status = 'paid'
        self.order_a.save()
        self.order_b.status = 'paid'
        self.order_b.save()

        # Create PaymentSplit for seller_a (for refund reversal testing)
        self.split_a = PaymentSplit.objects.create(
            payment=self.payment_a,
            seller=self.seller_a,
            gross_amount=Decimal('160.00'),
            product_amount=Decimal('150.00'),
            shipping_amount=Decimal('10.00'),
            platform_fee_amount=Decimal('15.00'),
            net_amount=Decimal('145.00'),
            shipping_status='released',
            transfer_status='dispatched',
            stripe_transfer_id='tr_a_test',
        )

    def test_refund_request_references_correct_payment(self):
        """
        RefundRequest for order_a must reference payment_a (not payment_b).
        """
        from payments.refund_request_service import RefundRequestService

        refund_request = RefundRequestService.create_request(
            buyer=self.buyer,
            payment=self.payment_a,
            refund_type='remorse',
            amount=Decimal('160.00'),
            reason='Não preciso mais do produto A comprado do seller_a',
            evidence_urls=[],
        )

        self.assertEqual(refund_request.payment_id, self.payment_a.id)
        self.assertEqual(refund_request.order_id, self.order_a.id)

        # payment_b must be untouched
        self.payment_b.refresh_from_db()
        self.assertEqual(self.payment_b.status, 'succeeded')

    def test_each_order_has_independent_payment_record(self):
        """
        Two Orders must have two independent Payment records.
        Each Payment references its own Order and its own PI.
        """
        self.assertNotEqual(self.payment_a.id, self.payment_b.id)
        self.assertNotEqual(
            self.payment_a.stripe_payment_intent_id,
            self.payment_b.stripe_payment_intent_id,
        )
        self.assertEqual(str(self.payment_a.order_id), str(self.order_a.id))
        self.assertEqual(str(self.payment_b.order_id), str(self.order_b.id))

        # Amounts are independent (not combined)
        self.assertEqual(self.payment_a.amount, Decimal('160.00'))
        self.assertEqual(self.payment_b.amount, Decimal('215.00'))

    def test_single_intent_endpoint_still_works_per_order(self):
        """
        The existing POST /payments/create-intent/ (single order) must still
        work correctly when called individually for each order.

        This test uses fresh orders (not the ones in setUp that already have
        succeeded payments) to avoid PROTECT FK conflicts.
        This confirms backward compatibility after the batch endpoint was added.
        """
        address = {
            'street': 'Rua Compat', 'number': '1',
            'city': 'SP', 'state': 'SP', 'zipcode': '01310-000',
        }

        # Create two fresh orders without any Payment attached yet
        order_c = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller_a,
            subtotal=Decimal('50.00'),
            shipping_cost=Decimal('5.00'),
            total=Decimal('55.00'),
            shipping_address=address,
            status='pending_payment',
        )
        OrderItem.objects.create(
            order=order_c,
            listing=self.listing_a,
            seller=self.seller_a,
            quantity=1,
            unit_price=Decimal('50.00'),
            subtotal=Decimal('50.00'),
            shipping_cost=Decimal('5.00'),
            product_name='Product A',
            product_code='',
            brand_name=self.brand.name,
            condition_name=self.condition.name,
            weight_kg=Decimal('2.00'),
            height_cm=Decimal('10.00'),
            width_cm=Decimal('10.00'),
            length_cm=Decimal('10.00'),
        )

        order_d = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller_b,
            subtotal=Decimal('80.00'),
            shipping_cost=Decimal('8.00'),
            total=Decimal('88.00'),
            shipping_address=address,
            status='pending_payment',
        )
        OrderItem.objects.create(
            order=order_d,
            listing=self.listing_b,
            seller=self.seller_b,
            quantity=1,
            unit_price=Decimal('80.00'),
            subtotal=Decimal('80.00'),
            shipping_cost=Decimal('8.00'),
            product_name='Product B',
            product_code='',
            brand_name=self.brand.name,
            condition_name=self.condition.name,
            weight_kg=Decimal('3.00'),
            height_cm=Decimal('15.00'),
            width_cm=Decimal('15.00'),
            length_cm=Decimal('15.00'),
        )

        with patch(
            'payments.payment_intent_service.stripe.Account.retrieve'
        ) as mock_account, patch(
            'payments.payment_intent_service.stripe.PaymentIntent.create'
        ) as mock_pi_create:
            mock_account_obj = MagicMock()
            mock_account_obj.get.return_value = True
            mock_account.return_value = mock_account_obj

            call_n = {'n': 0}

            def side_effect(**kwargs):
                call_n['n'] += 1
                m = MagicMock()
                m.id = f'pi_single_{call_n["n"]}'
                m.client_secret = f'pi_single_{call_n["n"]}_secret'
                m.status = 'requires_payment_method'
                m.created = 1700000000
                return m

            mock_pi_create.side_effect = side_effect

            # Call single endpoint for order_c
            resp_c = self.client.post(
                '/api/payments/create-intent/',
                data={
                    'order_id': str(order_c.id),
                    'payment_method': 'credit_card',
                },
                format='json',
            )
            self.assertEqual(resp_c.status_code, status.HTTP_200_OK)
            self.assertIn('client_secret', resp_c.data)

            # Call single endpoint for order_d
            resp_d = self.client.post(
                '/api/payments/create-intent/',
                data={
                    'order_id': str(order_d.id),
                    'payment_method': 'credit_card',
                },
                format='json',
            )
            self.assertEqual(resp_d.status_code, status.HTTP_200_OK)
            self.assertIn('client_secret', resp_d.data)

        # Two separate PI creates
        self.assertEqual(mock_pi_create.call_count, 2)

        # Each new payment points to its own order
        payment_c = Payment.objects.get(order=order_c)
        payment_d = Payment.objects.get(order=order_d)

        self.assertNotEqual(payment_c.stripe_payment_intent_id, payment_d.stripe_payment_intent_id)
        self.assertEqual(payment_c.amount, Decimal('55.00'))
        self.assertEqual(payment_d.amount, Decimal('88.00'))
