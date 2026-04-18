"""
Tests for ShipmentCreationService.checkout_shipments_for_order status guard.

Ensures that:
- Orders in 'paid' status can proceed with shipment checkout (payment just confirmed)
- Orders in 'processing' status can proceed with shipment checkout (payment already confirmed,
  order already moved forward by a previous checkout or state transition)
- Orders in 'pending_payment' or other pre-payment statuses are rejected with
  ShipmentCreationError('Pedido precisa ter pagamento confirmado')

Bug fixed: previously the guard only allowed 'paid', rejecting 'processing' orders even
though 'processing' is a valid post-payment state.
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase

from authentication.models import CustomUser
from orders.models import Order, OrderItem
from orders.services.order_state_machine import OrderStateMachine
from products.models import Products, MarketplaceListing, Brand, Condition, Category, Series
from logistics.models import Shipment
from logistics.services.shipment_creation_service import (
    ShipmentCreationService,
    ShipmentCreationError,
)


class CheckoutShipmentsStatusGuardTest(TestCase):
    """Tests for the order status guard in checkout_shipments_for_order."""

    def setUp(self):
        self.buyer = CustomUser.objects.create_user(
            email='buyer@test.com',
            password='test123',
            full_name='Buyer Test',
        )
        self.seller = CustomUser.objects.create_user(
            email='seller@test.com',
            password='test123',
            full_name='Seller Test',
        )

        category = Category.objects.create(name='Cat', slug='cat')
        series = Series.objects.create(name='Series', slug='series')
        brand = Brand.objects.create(name='Brand', slug='brand')
        condition = Condition.objects.create(name='New', slug='new')
        product = Products.objects.create(
            name='Product',
            slug='product',
            category=category,
            series=series,
        )
        self.listing = MarketplaceListing.objects.create(
            seller=self.seller,
            product=product,
            brand=brand,
            condition=condition,
            price=Decimal('200.00'),
            quantity=5,
            description='Test',
            is_active=True,
            weight_kg=Decimal('1.0'),
            height_cm=Decimal('10.0'),
            width_cm=Decimal('10.0'),
            length_cm=Decimal('10.0'),
        )

    def _make_order(self, status: str) -> Order:
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('25.00'),
            total=Decimal('225.00'),
            status=status,
            shipping_address={
                'street': 'Rua Test',
                'number': '1',
                'city': 'SP',
                'state': 'SP',
                'zipcode': '01234-567',
            },
        )
        OrderItem.objects.create(
            order=order,
            listing=self.listing,
            seller=self.seller,
            product_name='Product',
            brand_name='Brand',
            condition_name='New',
            quantity=1,
            unit_price=Decimal('200.00'),
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('25.00'),
            weight_kg=Decimal('1.0'),
            height_cm=Decimal('10.0'),
            width_cm=Decimal('10.0'),
            length_cm=Decimal('10.0'),
        )
        return order

    def _add_pending_shipment(self, order: Order) -> Shipment:
        return Shipment.objects.create(
            order=order,
            seller=self.seller,
            melhorenvio_order_id='ME-TEST-001',
            carrier_name='Correios',
            carrier_service='PAC',
            shipping_cost=Decimal('25.00'),
            status='pending',
            weight=Decimal('1.0'),
            height=Decimal('10.0'),
            width=Decimal('10.0'),
            length=Decimal('10.0'),
            origin_address={'zipcode': '01310100'},
            destination_address={'zipcode': '01234567'},
        )

    # ── Tests: status guard rejects pre-payment orders ──────────────────────────

    def test_pending_payment_order_is_rejected(self):
        """Orders in pending_payment status must be blocked."""
        order = self._make_order(OrderStateMachine.PENDING_PAYMENT)
        with self.assertRaises(ShipmentCreationError) as ctx:
            ShipmentCreationService.checkout_shipments_for_order(order)
        self.assertIn('pagamento confirmado', str(ctx.exception))

    def test_failed_order_is_rejected(self):
        """Orders with failed payment must be blocked."""
        order = self._make_order(OrderStateMachine.FAILED)
        with self.assertRaises(ShipmentCreationError) as ctx:
            ShipmentCreationService.checkout_shipments_for_order(order)
        self.assertIn('pagamento confirmado', str(ctx.exception))

    def test_cancelled_order_is_rejected(self):
        """Cancelled orders must be blocked."""
        order = self._make_order(OrderStateMachine.CANCELED)
        with self.assertRaises(ShipmentCreationError) as ctx:
            ShipmentCreationService.checkout_shipments_for_order(order)
        self.assertIn('pagamento confirmado', str(ctx.exception))

    # ── Tests: 'paid' status is allowed (existing behaviour) ───────────────────

    @patch('logistics.services.shipment_creation_service.MelhorEnvioService')
    def test_paid_order_proceeds_to_checkout(self, MockME):
        """Orders in 'paid' status must be allowed through the guard."""
        mock_instance = MockME.return_value
        mock_instance.checkout_cart.return_value = {'purchase': 'ok'}

        order = self._make_order(OrderStateMachine.PAID)
        self._add_pending_shipment(order)

        shipments, result = ShipmentCreationService.checkout_shipments_for_order(order)

        self.assertEqual(len(shipments), 1)
        mock_instance.checkout_cart.assert_called_once()
        # Order must have transitioned to PROCESSING
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStateMachine.PROCESSING)

    # ── Tests: 'processing' status is allowed (the fixed bug) ──────────────────

    @patch('logistics.services.shipment_creation_service.MelhorEnvioService')
    def test_processing_order_with_pending_shipments_proceeds(self, MockME):
        """
        Orders in 'processing' status must be allowed through the guard.

        This is the regression test for the bug: creating a shipment for an order
        that was already moved to 'processing' (payment confirmed) was failing with
        'Pedido precisa ter pagamento confirmado'.
        """
        mock_instance = MockME.return_value
        mock_instance.checkout_cart.return_value = {'purchase': 'ok'}

        order = self._make_order(OrderStateMachine.PROCESSING)
        self._add_pending_shipment(order)

        # Must not raise ShipmentCreationError
        shipments, result = ShipmentCreationService.checkout_shipments_for_order(order)

        self.assertEqual(len(shipments), 1)
        mock_instance.checkout_cart.assert_called_once()
        # Order is already PROCESSING; it should remain so (no invalid transition attempted)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStateMachine.PROCESSING)

    @patch('logistics.services.shipment_creation_service.MelhorEnvioService')
    def test_processing_order_with_already_checked_out_shipments_returns_them(self, MockME):
        """
        Orders in 'processing' with no pending shipments but existing 'created' shipments
        must return those shipments without calling ME checkout again.
        """
        order = self._make_order(OrderStateMachine.PROCESSING)
        # Create a shipment already in 'created' state (checkout already done)
        Shipment.objects.create(
            order=order,
            seller=self.seller,
            melhorenvio_order_id='ME-TEST-002',
            carrier_name='Correios',
            carrier_service='PAC',
            shipping_cost=Decimal('25.00'),
            status='created',
            weight=Decimal('1.0'),
            height=Decimal('10.0'),
            width=Decimal('10.0'),
            length=Decimal('10.0'),
            origin_address={'zipcode': '01310100'},
            destination_address={'zipcode': '01234567'},
        )

        shipments, result = ShipmentCreationService.checkout_shipments_for_order(order)

        self.assertEqual(len(shipments), 1)
        self.assertEqual(shipments[0].status, 'created')
        # ME checkout must NOT be called again (idempotent path)
        MockME.return_value.checkout_cart.assert_not_called()
        # Order stays in PROCESSING
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStateMachine.PROCESSING)
