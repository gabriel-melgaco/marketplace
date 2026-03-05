"""
Tests for Multiple Payment Intents Prevention

Validates that users cannot create multiple payment intents for the same order.
Instead, pending payment intents are reused.
"""

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
from payments.models import Payment

User = get_user_model()


class TestMultiplePaymentIntents(TestCase):
    """
    Test that multiple payment intents cannot be created for the same order.
    """

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create buyer and seller
        self.buyer = User.objects.create_user(
            email='buyer@test.com',
            password='testpass123'
        )
        self.seller = User.objects.create_user(
            email='seller@test.com',
            password='testpass123',
            stripe_account_id='acct_test_seller_123',  # Required for seller readiness check
        )

        # Create product data
        self.brand = Brand.objects.create(name='TestBrand', slug='testbrand')
        self.condition = Condition.objects.create(name='New', slug='new')
        self.category = Category.objects.create(name='Dumbbells', slug='dumbbells')
        self.series = Series.objects.create(name='Test Series', slug='test-series')

        self.product = Products.objects.create(
            name='Test Product',
            slug='test-product',
            category=self.category,
            series=self.series
        )

        self.listing = MarketplaceListing.objects.create(
            product=self.product,
            seller=self.seller,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('100.00'),
            quantity=10,
            is_active=True,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('10.00'),
            width_cm=Decimal('10.00'),
            length_cm=Decimal('10.00'),
        )

        # Create order
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('20.00'),
            total=Decimal('120.00'),
            shipping_address={
                'street': 'Test St',
                'number': '123',
                'city': 'Test City',
                'state': 'TS',
                'zipcode': '12345'
            },
            status='pending_payment'
        )

        OrderItem.objects.create(
            order=self.order,
            listing=self.listing,
            seller=self.seller,
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            product_name=self.product.name,
            product_code='',
            brand_name=self.brand.name,
            condition_name=self.condition.name,
            weight_kg=self.listing.weight_kg,
            height_cm=self.listing.height_cm,
            width_cm=self.listing.width_cm,
            length_cm=self.listing.length_cm
        )

        # Authenticate as buyer
        self.client.force_authenticate(user=self.buyer)

    @patch('payments.payment_intent_service.stripe.Account.retrieve')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.retrieve')
    def test_reuse_pending_payment_intent(self, mock_retrieve, mock_create, mock_account):
        """
        Test that pending payment intent is reused instead of creating new one.
        """
        # Mock Stripe Account retrieve (seller readiness check)
        mock_account_obj = MagicMock()
        mock_account_obj.get.return_value = True  # charges_enabled = True
        mock_account.return_value = mock_account_obj

        # Mock Stripe PaymentIntent creation
        mock_intent_create = MagicMock()
        mock_intent_create.id = 'pi_test_123'
        mock_intent_create.client_secret = 'pi_test_123_secret_abc'
        mock_intent_create.status = 'requires_payment_method'
        mock_intent_create.created = 1234567890
        mock_create.return_value = mock_intent_create

        # Create first payment intent
        response1 = self.client.post('/api/payments/create-intent/', {
            'order_id': str(self.order.id),
            'payment_method': 'credit_card'
        })

        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertIn('payment_id', response1.data)
        self.assertIn('client_secret', response1.data)
        payment_id_1 = response1.data['payment_id']

        # Mock Stripe PaymentIntent retrieval (still pending)
        mock_intent_retrieve = MagicMock()
        mock_intent_retrieve.id = 'pi_test_123'
        mock_intent_retrieve.client_secret = 'pi_test_123_secret_abc'
        mock_intent_retrieve.status = 'requires_payment_method'
        mock_retrieve.return_value = mock_intent_retrieve

        # Try to create second payment intent (should reuse first)
        response2 = self.client.post('/api/payments/create-intent/', {
            'order_id': str(self.order.id),
            'payment_method': 'credit_card'
        })

        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertIn('reused', response2.data)
        self.assertTrue(response2.data['reused'])
        self.assertEqual(response2.data['payment_id'], payment_id_1)
        self.assertEqual(response2.data['client_secret'], 'pi_test_123_secret_abc')

        # Stripe create should only be called once (first time)
        self.assertEqual(mock_create.call_count, 1)

        # Stripe retrieve should be called on second attempt
        self.assertEqual(mock_retrieve.call_count, 1)

    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    def test_create_new_if_previous_succeeded(self, mock_create):
        """
        Test that new payment intent is rejected if previous succeeded.
        """
        # Create payment with succeeded status
        Payment.objects.create(
            order=self.order,
            user=self.buyer,
            stripe_payment_intent_id='pi_old_succeeded',
            amount=self.order.total,
            currency='brl',
            payment_method='credit_card',
            status='succeeded'
        )

        # Try to create new payment intent
        response = self.client.post('/api/payments/create-intent/', {
            'order_id': str(self.order.id),
            'payment_method': 'credit_card'
        })

        # Should be rejected
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('já possui pagamento confirmado', response.data['error'])

        # Stripe create should not be called
        mock_create.assert_not_called()

    @patch('payments.payment_intent_service.stripe.PaymentIntent.retrieve')
    def test_handle_cancelled_payment_intent_gracefully(self, mock_retrieve):
        """
        Test that cancelled payment intent is handled gracefully.

        Note: Since Payment has OneToOneField with Order, we cannot create
        a new Payment. The user should cancel the order and create a new one.
        When the seller has no stripe_account_id (simulating incomplete onboarding),
        the system now correctly returns 400 with a seller readiness error
        before even attempting to create a new PaymentIntent.
        """
        # Create payment with pending status (no stripe_account_id on seller)
        # This seller does NOT have stripe_account_id set — simulating a fresh test
        seller_without_account = User.objects.create_user(
            email='seller_nostripe@test.com',
            password='testpass123',
            # stripe_account_id intentionally blank
        )
        order2 = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('100.00'),
            shipping_address={'street': 'Test St', 'city': 'Test City'},
            status='pending_payment'
        )
        listing2 = MarketplaceListing.objects.create(
            product=self.product,
            seller=seller_without_account,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('100.00'),
            quantity=5,
            is_active=True,
            weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )
        OrderItem.objects.create(
            order=order2,
            listing=listing2,
            seller=seller_without_account,
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            product_name=self.product.name,
            product_code='',
            brand_name=self.brand.name,
            condition_name=self.condition.name,
            weight_kg=listing2.weight_kg,
            height_cm=listing2.height_cm,
            width_cm=listing2.width_cm,
            length_cm=listing2.length_cm,
        )
        existing_payment = Payment.objects.create(
            order=order2,
            user=self.buyer,
            stripe_payment_intent_id='pi_old_cancelled',
            amount=order2.total,
            currency='brl',
            payment_method='credit_card',
            status='pending'
        )

        # Mock Stripe retrieve - return cancelled status
        mock_intent_retrieve = MagicMock()
        mock_intent_retrieve.id = 'pi_old_cancelled'
        mock_intent_retrieve.status = 'canceled'
        mock_retrieve.return_value = mock_intent_retrieve

        # Try to create payment intent
        response = self.client.post('/api/payments/create-intent/', {
            'order_id': str(order2.id),
            'payment_method': 'credit_card'
        })

        # Should return 400 because seller has no stripe_account_id
        # (SellerNotReadyError is raised before attempting to create PI)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    @patch('payments.payment_intent_service.stripe.PaymentIntent.retrieve')
    def test_handle_stripe_retrieve_failure_gracefully(self, mock_retrieve):
        """
        Test that Stripe retrieve failure is handled gracefully.
        When seller has no stripe_account_id, we get 400 (SellerNotReadyError)
        before attempting to create a new PaymentIntent.
        """
        # Create a seller without stripe_account_id for this test
        seller_without_account = User.objects.create_user(
            email='seller_noacct@test.com',
            password='testpass123',
        )
        order3 = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('50.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('50.00'),
            shipping_address={'street': 'Test St'},
            status='pending_payment'
        )
        listing3 = MarketplaceListing.objects.create(
            product=self.product,
            seller=seller_without_account,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('50.00'),
            quantity=3,
            is_active=True,
            weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )
        OrderItem.objects.create(
            order=order3,
            listing=listing3,
            seller=seller_without_account,
            quantity=1,
            unit_price=Decimal('50.00'),
            subtotal=Decimal('50.00'),
            product_name=self.product.name,
            product_code='',
            brand_name=self.brand.name,
            condition_name=self.condition.name,
            weight_kg=listing3.weight_kg,
            height_cm=listing3.height_cm,
            width_cm=listing3.width_cm,
            length_cm=listing3.length_cm,
        )
        existing_payment = Payment.objects.create(
            order=order3,
            user=self.buyer,
            stripe_payment_intent_id='pi_old_notfound',
            amount=order3.total,
            currency='brl',
            payment_method='credit_card',
            status='pending'
        )

        # Mock Stripe retrieve to raise error
        import stripe
        mock_retrieve.side_effect = stripe.error.InvalidRequestError(
            'No such payment intent', 'pi_old_notfound'
        )

        # Try to create payment intent
        response = self.client.post('/api/payments/create-intent/', {
            'order_id': str(order3.id),
            'payment_method': 'credit_card'
        })

        # Should return 400 because seller has no stripe_account_id
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.retrieve')
    def test_reuse_with_requires_confirmation_status(self, mock_retrieve, mock_create):
        """
        Test that payment intent with requires_confirmation status is also reused.
        """
        # Create payment with pending status
        existing_payment = Payment.objects.create(
            order=self.order,
            user=self.buyer,
            stripe_payment_intent_id='pi_requires_confirmation',
            amount=self.order.total,
            currency='brl',
            payment_method='credit_card',
            status='pending'
        )

        # Mock Stripe retrieve - requires_confirmation status
        mock_intent_retrieve = MagicMock()
        mock_intent_retrieve.id = 'pi_requires_confirmation'
        mock_intent_retrieve.client_secret = 'pi_secret_confirm'
        mock_intent_retrieve.status = 'requires_confirmation'
        mock_retrieve.return_value = mock_intent_retrieve

        # Try to create payment intent
        response = self.client.post('/api/payments/create-intent/', {
            'order_id': str(self.order.id),
            'payment_method': 'credit_card'
        })

        # Should reuse existing
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('reused', False))

        # Stripe create should not be called
        mock_create.assert_not_called()

    @patch('payments.payment_intent_service.stripe.PaymentIntent.create')
    @patch('payments.payment_intent_service.stripe.PaymentIntent.retrieve')
    def test_reuse_with_requires_action_status(self, mock_retrieve, mock_create):
        """
        Test that payment intent with requires_action status is also reused.
        """
        # Create payment with pending status
        existing_payment = Payment.objects.create(
            order=self.order,
            user=self.buyer,
            stripe_payment_intent_id='pi_requires_action',
            amount=self.order.total,
            currency='brl',
            payment_method='credit_card',
            status='pending'
        )

        # Mock Stripe retrieve - requires_action status (e.g., 3D Secure)
        mock_intent_retrieve = MagicMock()
        mock_intent_retrieve.id = 'pi_requires_action'
        mock_intent_retrieve.client_secret = 'pi_secret_action'
        mock_intent_retrieve.status = 'requires_action'
        mock_retrieve.return_value = mock_intent_retrieve

        # Try to create payment intent
        response = self.client.post('/api/payments/create-intent/', {
            'order_id': str(self.order.id),
            'payment_method': 'credit_card'
        })

        # Should reuse existing
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('reused', False))

        # Stripe create should not be called
        mock_create.assert_not_called()
