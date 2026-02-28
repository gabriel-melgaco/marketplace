"""
Tests for Auto-Create Shipments Signal

Validates that shipments are automatically created when order payment is confirmed.
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from products.models import (
    Products, Brand, Condition, MarketplaceListing, Category, Series
)
from orders.models import Order, OrderItem
from orders.services.order_state_machine import OrderStateMachine
from logistics.models import OrderDelivery

User = get_user_model()


class TestAutoCreateShipments(TestCase):
    """
    Test that shipments are automatically created when payment is confirmed.
    """

    def setUp(self):
        """Set up test data"""
        # Create buyer and seller
        self.buyer = User.objects.create_user(
            email='buyer@test.com',
            password='testpass123'
        )
        self.seller = User.objects.create_user(
            email='seller@test.com',
            password='testpass123'
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

    @override_settings(AUTO_CREATE_SHIPMENTS=True)
    @patch('logistics.services.delivery_orchestration_service.DeliveryOrchestrationService.create_order_deliveries')
    def test_shipments_created_automatically_on_payment(self, mock_create_deliveries):
        """
        Test that shipments are automatically created when order status changes to PAID.
        """
        # Mock the delivery creation
        mock_delivery = MagicMock()
        mock_create_deliveries.return_value = [mock_delivery]

        # Create order with pending_payment status
        order = Order.objects.create(
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
            shipping_services={
                str(self.seller.id): {
                    'delivery_method': 'shipping',
                    'service_id': 1,
                    'service_name': 'PAC',
                    'cost': 20.00
                }
            },
            status='pending_payment'
        )

        OrderItem.objects.create(
            order=order,
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

        # Verify no deliveries created yet
        self.assertFalse(mock_create_deliveries.called)

        # Change status to PAID (this should trigger the signal)
        order.status = OrderStateMachine.PAID
        order.save()

        # Verify deliveries were created
        self.assertTrue(mock_create_deliveries.called)
        self.assertEqual(mock_create_deliveries.call_count, 1)

        # Verify correct delivery choices were passed
        call_args = mock_create_deliveries.call_args
        self.assertEqual(call_args[1]['order'], order)
        delivery_choices = call_args[1]['delivery_choices']
        self.assertEqual(len(delivery_choices), 1)
        self.assertEqual(delivery_choices[0]['seller_id'], self.seller.id)
        self.assertEqual(delivery_choices[0]['delivery_method'], 'shipping')

    @override_settings(AUTO_CREATE_SHIPMENTS=False)
    @patch('logistics.services.delivery_orchestration_service.DeliveryOrchestrationService.create_order_deliveries')
    def test_shipments_not_created_when_disabled(self, mock_create_deliveries):
        """
        Test that shipments are NOT created when AUTO_CREATE_SHIPMENTS is False.
        """
        # Create order and change to PAID
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('20.00'),
            total=Decimal('120.00'),
            shipping_address={'street': 'Test St'},
            shipping_services={
                str(self.seller.id): {
                    'delivery_method': 'shipping',
                    'service_id': 1,
                    'cost': 20.00
                }
            },
            status='pending_payment'
        )

        order.status = OrderStateMachine.PAID
        order.save()

        # Verify deliveries were NOT created (feature disabled)
        self.assertFalse(mock_create_deliveries.called)

    @override_settings(AUTO_CREATE_SHIPMENTS=True)
    @patch('logistics.services.delivery_orchestration_service.DeliveryOrchestrationService.create_order_deliveries')
    def test_shipments_not_created_for_non_paid_status(self, mock_create_deliveries):
        """
        Test that shipments are NOT created for statuses other than PAID.
        """
        # Create order
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('20.00'),
            total=Decimal('120.00'),
            shipping_address={'street': 'Test St'},
            shipping_services={
                str(self.seller.id): {
                    'delivery_method': 'shipping',
                    'service_id': 1,
                    'cost': 20.00
                }
            },
            status='pending_payment'
        )

        # Change to PROCESSING (not PAID)
        order.status = OrderStateMachine.PROCESSING
        order.save()

        # Verify deliveries were NOT created
        self.assertFalse(mock_create_deliveries.called)

    @override_settings(AUTO_CREATE_SHIPMENTS=True)
    @patch('logistics.models.OrderDelivery.objects.filter')
    @patch('logistics.services.delivery_orchestration_service.DeliveryOrchestrationService.create_order_deliveries')
    def test_shipments_not_created_if_already_exist(self, mock_create_deliveries, mock_filter):
        """
        Test that shipments are NOT created if they already exist for the order.
        """
        # Mock existing deliveries: values_list returns the seller's ID,
        # indicating an OrderDelivery already exists for that seller.
        mock_filter.return_value.values_list.return_value = [self.seller.id]

        # Create order and change to PAID
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('20.00'),
            total=Decimal('120.00'),
            shipping_address={'street': 'Test St'},
            shipping_services={
                str(self.seller.id): {
                    'delivery_method': 'shipping',
                    'service_id': 1,
                    'cost': 20.00
                }
            },
            status='pending_payment'
        )

        order.status = OrderStateMachine.PAID
        order.save()

        # Verify deliveries were NOT created (seller already has an OrderDelivery)
        self.assertFalse(mock_create_deliveries.called)

    @override_settings(AUTO_CREATE_SHIPMENTS=True)
    @patch('logistics.services.delivery_orchestration_service.DeliveryOrchestrationService.create_order_deliveries')
    def test_signal_handles_failure_gracefully(self, mock_create_deliveries):
        """
        Test that signal handles delivery creation failure gracefully.

        The signal should log the error but not raise an exception,
        preventing the order save operation from failing.
        """
        # Mock delivery creation to raise an exception
        mock_create_deliveries.side_effect = Exception("Delivery service error")

        # Create order and change to PAID
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('20.00'),
            total=Decimal('120.00'),
            shipping_address={'street': 'Test St'},
            shipping_services={
                str(self.seller.id): {
                    'delivery_method': 'shipping',
                    'service_id': 1,
                    'cost': 20.00
                }
            },
            status='pending_payment'
        )

        # This should NOT raise an exception (failure is logged)
        order.status = OrderStateMachine.PAID
        order.save()

        # Verify order was saved successfully despite delivery failure
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStateMachine.PAID)

        # Verify delivery creation was attempted
        self.assertTrue(mock_create_deliveries.called)

    @override_settings(AUTO_CREATE_SHIPMENTS=True)
    @patch('logistics.services.delivery_orchestration_service.DeliveryOrchestrationService.create_order_deliveries')
    def test_handles_in_person_delivery(self, mock_create_deliveries):
        """
        Test that signal handles in-person delivery correctly.
        """
        mock_delivery = MagicMock()
        mock_create_deliveries.return_value = [mock_delivery]

        # Create order with in-person delivery
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('100.00'),
            shipping_address={'street': 'Test St'},
            shipping_services={
                str(self.seller.id): {
                    'delivery_method': 'in_person',
                    'meeting_location_name': 'Shopping Center',
                    'scheduled_date': '2026-02-10',
                    'scheduled_time': '14:00'
                }
            },
            status='pending_payment'
        )

        # Change to PAID
        order.status = OrderStateMachine.PAID
        order.save()

        # Verify deliveries were created with in-person method
        self.assertTrue(mock_create_deliveries.called)
        call_args = mock_create_deliveries.call_args
        delivery_choices = call_args[1]['delivery_choices']
        self.assertEqual(delivery_choices[0]['delivery_method'], 'in_person')
        self.assertIn('meeting_location_name', delivery_choices[0])

    @override_settings(AUTO_CREATE_SHIPMENTS=True)
    @patch('logistics.services.delivery_orchestration_service.DeliveryOrchestrationService.create_order_deliveries')
    def test_handles_order_without_shipping_services(self, mock_create_deliveries):
        """
        Test that signal handles orders without shipping_services gracefully.
        """
        # Create order WITHOUT shipping_services
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('100.00'),
            shipping_address={'street': 'Test St'},
            # No shipping_services
            status='pending_payment'
        )

        # Change to PAID
        order.status = OrderStateMachine.PAID
        order.save()

        # Verify deliveries were NOT created (no shipping services)
        self.assertFalse(mock_create_deliveries.called)
