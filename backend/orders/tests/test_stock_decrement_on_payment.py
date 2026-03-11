"""
Tests for Stock Decrement on Payment Confirmation

Validates:
- reserve_stock() decrements MarketplaceListing.quantity correctly
- reserve_stock() deactivates listing (is_active=False) when quantity reaches 0
- deactivate_if_out_of_stock() is idempotent (safe to call when already inactive)
- release_stock() does NOT reactivate a listing (reactivation is a seller action)
- PaymentCallbackService.on_payment_succeeded() triggers full stock decrement flow
- Listings with quantity > 0 after reserve_stock() stay active
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model

from products.models import (
    Products, Brand, Condition, MarketplaceListing, Category, Series
)
from orders.models import Order, OrderItem
from orders.services.product_validation_service import (
    ProductValidationService,
    InsufficientStockError,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_seller(email='seller_stock@test.com'):
    return User.objects.create_user(email=email, password='testpass123')


def _make_buyer(email='buyer_stock@test.com'):
    return User.objects.create_user(email=email, password='testpass123')


def _make_listing(seller, quantity=3, is_active=True):
    brand = Brand.objects.create(name=f'Brand-{quantity}', slug=f'brand-{quantity}-{seller.pk}')
    condition = Condition.objects.create(name='New', slug=f'new-{seller.pk}')
    category = Category.objects.create(name='Cat', slug=f'cat-{seller.pk}')
    series = Series.objects.create(name='Ser', slug=f'ser-{seller.pk}')
    product = Products.objects.create(
        name='Dumbbell', slug=f'dumbbell-{seller.pk}',
        category=category, series=series,
    )
    return MarketplaceListing.objects.create(
        product=product, seller=seller,
        brand=brand, condition=condition,
        title='Dumbbell Listing',
        price=Decimal('100.00'),
        quantity=quantity,
        is_active=is_active,
        description='Test listing',
        weight_kg=Decimal('5.00'),
        height_cm=Decimal('10.00'),
        width_cm=Decimal('10.00'),
        length_cm=Decimal('10.00'),
    )


# ---------------------------------------------------------------------------
# Unit tests: ProductValidationService.reserve_stock
# ---------------------------------------------------------------------------

class TestReserveStockDecrement(TestCase):
    """reserve_stock() decrements quantity and handles edge cases."""

    def setUp(self):
        self.seller = _make_seller()
        self.listing = _make_listing(self.seller, quantity=5)

    def test_reserve_stock_decrements_quantity(self):
        ProductValidationService.reserve_stock(self.listing, 2)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 3)

    def test_reserve_stock_full_quantity_leaves_zero(self):
        ProductValidationService.reserve_stock(self.listing, 5)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 0)

    def test_reserve_stock_raises_when_insufficient(self):
        with self.assertRaises(InsufficientStockError):
            ProductValidationService.reserve_stock(self.listing, 10)

    def test_reserve_stock_raises_when_stock_is_zero(self):
        self.listing.quantity = 0
        self.listing.save()
        with self.assertRaises(InsufficientStockError):
            ProductValidationService.reserve_stock(self.listing, 1)

    def test_reserve_partial_keeps_listing_active(self):
        """Buying some units (not all) must NOT deactivate the listing."""
        ProductValidationService.reserve_stock(self.listing, 3)  # 2 remain
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 2)
        self.assertTrue(self.listing.is_active)

    def test_reserve_exact_quantity_deactivates_listing(self):
        """Buying all units must deactivate the listing."""
        ProductValidationService.reserve_stock(self.listing, 5)  # 0 remain
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 0)
        self.assertFalse(self.listing.is_active)

    def test_reserve_single_unit_from_quantity_one_deactivates(self):
        """Buying the last unit of a listing with quantity=1 must deactivate it."""
        listing = _make_listing(_make_seller('one_seller@test.com'), quantity=1)
        ProductValidationService.reserve_stock(listing, 1)
        listing.refresh_from_db()
        self.assertFalse(listing.is_active)


# ---------------------------------------------------------------------------
# Unit tests: ProductValidationService.deactivate_if_out_of_stock
# ---------------------------------------------------------------------------

class TestDeactivateIfOutOfStock(TestCase):
    """deactivate_if_out_of_stock() is safe, idempotent, and targeted."""

    def setUp(self):
        self.seller = _make_seller('deact_seller@test.com')

    def test_deactivates_active_zero_stock_listing(self):
        listing = _make_listing(self.seller, quantity=0, is_active=True)
        ProductValidationService.deactivate_if_out_of_stock(listing)
        listing.refresh_from_db()
        self.assertFalse(listing.is_active)

    def test_no_op_when_already_inactive(self):
        """Calling on an already-inactive listing must not raise and must be safe."""
        listing = _make_listing(self.seller, quantity=0, is_active=False)
        # Should not raise, and listing stays inactive
        ProductValidationService.deactivate_if_out_of_stock(listing)
        listing.refresh_from_db()
        self.assertFalse(listing.is_active)

    def test_no_op_when_quantity_greater_than_zero(self):
        """Must not deactivate if quantity > 0 (guard filter: quantity=0)."""
        listing = _make_listing(self.seller, quantity=2, is_active=True)
        ProductValidationService.deactivate_if_out_of_stock(listing)
        listing.refresh_from_db()
        # Should remain active because the filter won't match
        self.assertTrue(listing.is_active)


# ---------------------------------------------------------------------------
# Unit tests: release_stock does NOT reactivate listing
# ---------------------------------------------------------------------------

class TestReleaseStockDoesNotReactivate(TestCase):
    """
    release_stock() is purely a stock quantity restoration.
    Reactivating a deactivated listing is an explicit seller action, not
    automatic. This prevents sold-out items from reappearing due to
    cancellations without seller review.
    """

    def setUp(self):
        self.seller = _make_seller('rel_seller@test.com')
        self.listing = _make_listing(self.seller, quantity=0, is_active=False)

    def test_release_stock_increments_quantity(self):
        ProductValidationService.release_stock(self.listing, 3)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 3)

    def test_release_stock_does_not_reactivate_listing(self):
        """is_active must remain False after release_stock — seller must reactivate manually."""
        ProductValidationService.release_stock(self.listing, 3)
        self.listing.refresh_from_db()
        self.assertFalse(self.listing.is_active)


# ---------------------------------------------------------------------------
# Integration tests: full payment confirmation flow
# ---------------------------------------------------------------------------

class TestStockDecrementOnPaymentConfirmation(TestCase):
    """
    End-to-end: PaymentCallbackService.on_payment_succeeded()
    triggers OrderCreationService.confirm_payment_and_reserve_stock()
    which calls reserve_stock() for every order item.

    We mock only the parts that reach external systems (Stripe, ME shipping).
    """

    def setUp(self):
        self.seller = _make_seller('pay_seller@test.com')
        self.buyer = _make_buyer('pay_buyer@test.com')
        self.listing = _make_listing(self.seller, quantity=3)

        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('300.00'),
            shipping_cost=Decimal('20.00'),
            total=Decimal('320.00'),
            shipping_address={'street': 'Test', 'city': 'City', 'state': 'SP', 'zipcode': '00000'},
            status='pending_payment',
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            listing=self.listing,
            seller=self.seller,
            quantity=3,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('300.00'),
            shipping_cost=Decimal('20.00'),
            product_name='Dumbbell',
            product_code='',
            brand_name=self.listing.brand.name,
            condition_name=self.listing.condition.name,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('10.00'),
            width_cm=Decimal('10.00'),
            length_cm=Decimal('10.00'),
        )

    @patch('logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order')
    def test_payment_success_decrements_stock(self, mock_checkout):
        """Stock quantity is decremented when payment is confirmed."""
        from orders.services.payment_callback_service import PaymentCallbackService

        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_123',
        )

        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 0)

    @patch('logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order')
    def test_payment_success_deactivates_listing_when_stock_hits_zero(self, mock_checkout):
        """Listing is deactivated when all stock is consumed by the order."""
        from orders.services.payment_callback_service import PaymentCallbackService

        # listing.quantity == 3, order buys 3 → quantity goes to 0 → must deactivate
        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_456',
        )

        self.listing.refresh_from_db()
        self.assertFalse(self.listing.is_active)

    @patch('logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order')
    def test_payment_success_keeps_listing_active_when_stock_remains(self, mock_checkout):
        """Listing stays active when partial stock remains after order."""
        # Adjust listing to have more stock than the order buys
        self.listing.quantity = 10
        self.listing.save()

        from orders.services.payment_callback_service import PaymentCallbackService

        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_789',
        )

        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 7)  # 10 - 3
        self.assertTrue(self.listing.is_active)

    @patch('logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order')
    def test_payment_success_transitions_order_to_paid(self, mock_checkout):
        """Order must transition to 'paid' status as part of the payment success flow."""
        from orders.services.payment_callback_service import PaymentCallbackService

        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_state',
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')

    @patch('logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order')
    def test_multiple_order_items_each_decrement_their_listing(self, mock_checkout):
        """Each OrderItem's listing is decremented independently."""
        # Create a second listing with distinct quantity
        listing2 = _make_listing(_make_seller('multi_seller@test.com'), quantity=5)
        seller2 = listing2.seller

        OrderItem.objects.create(
            order=self.order,
            listing=listing2,
            seller=seller2,
            quantity=2,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('0.00'),
            product_name='Dumbbell 2',
            product_code='',
            brand_name=listing2.brand.name,
            condition_name=listing2.condition.name,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('10.00'),
            width_cm=Decimal('10.00'),
            length_cm=Decimal('10.00'),
        )

        from orders.services.payment_callback_service import PaymentCallbackService

        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_multi',
        )

        self.listing.refresh_from_db()
        listing2.refresh_from_db()

        self.assertEqual(self.listing.quantity, 0)   # 3 - 3
        self.assertEqual(listing2.quantity, 3)        # 5 - 2
        self.assertFalse(self.listing.is_active)      # depleted → deactivated
        self.assertTrue(listing2.is_active)           # still has stock
