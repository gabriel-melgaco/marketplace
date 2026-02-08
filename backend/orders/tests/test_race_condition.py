"""
Test for Atomic Stock Operations

This test validates that the atomic F() expression in reserve_stock
prevents data inconsistencies and validates stock properly.

Note: True concurrent tests require a production database (PostgreSQL/MySQL).
SQLite has limitations with concurrent writes in test environment.
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from products.models import (
    Products, Brand, Condition, MarketplaceListing, Category, Series
)
from orders.services.product_validation_service import (
    ProductValidationService, InsufficientStockError
)

User = get_user_model()


class TestAtomicStockOperations(TestCase):
    """
    Test atomic stock operations with F() expressions.

    These tests validate that the atomic update logic works correctly,
    preventing overselling and data inconsistencies.
    """

    def setUp(self):
        """Set up test data"""
        # Create seller
        self.seller = User.objects.create_user(
            email='seller@test.com',
            password='testpass123'
        )

        # Create brand and condition
        self.brand = Brand.objects.create(
            name='TestBrand',
            slug='testbrand'
        )
        self.condition = Condition.objects.create(
            name='New',
            slug='new'
        )

        # Create category and series
        self.category = Category.objects.create(
            name='Dumbbells',
            slug='dumbbells'
        )
        self.series = Series.objects.create(
            name='Test Series',
            slug='test-series'
        )

        # Create product
        self.product = Products.objects.create(
            name='Test Product',
            slug='test-product',
            category=self.category,
            series=self.series
        )

        # Create listing with quantity = 1 (only one available)
        self.listing = MarketplaceListing.objects.create(
            product=self.product,
            seller=self.seller,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('100.00'),
            quantity=1,
            is_active=True,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('10.00'),
            width_cm=Decimal('10.00'),
            length_cm=Decimal('10.00'),
        )

    def test_reserve_stock_success(self):
        """Test successful stock reservation"""
        # Reserve 1 unit
        ProductValidationService.reserve_stock(self.listing, 1)

        # Verify stock was decremented
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 0)

    def test_reserve_stock_insufficient_stock(self):
        """Test that reservation fails when stock is insufficient"""
        # Try to reserve more than available
        with self.assertRaises(InsufficientStockError) as context:
            ProductValidationService.reserve_stock(self.listing, 2)

        # Verify error message
        self.assertIn("Cannot reserve 2 units", str(context.exception))

        # Verify stock wasn't changed
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 1)

    def test_reserve_exact_stock_amount(self):
        """Test reserving exactly the available stock"""
        # Update to 5 units
        self.listing.quantity = 5
        self.listing.save()

        # Reserve exactly 5 units
        ProductValidationService.reserve_stock(self.listing, 5)

        # Verify stock is now 0
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 0)

    def test_multiple_sequential_reservations(self):
        """Test multiple sequential stock reservations"""
        # Update to 10 units
        self.listing.quantity = 10
        self.listing.save()

        # Reserve 3 units
        ProductValidationService.reserve_stock(self.listing, 3)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 7)

        # Reserve 2 more
        ProductValidationService.reserve_stock(self.listing, 2)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 5)

        # Reserve 5 more (exactly remaining)
        ProductValidationService.reserve_stock(self.listing, 5)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 0)

        # Try to reserve more (should fail)
        with self.assertRaises(InsufficientStockError):
            ProductValidationService.reserve_stock(self.listing, 1)

    def test_release_stock_success(self):
        """Test successful stock release"""
        # First reserve some stock
        self.listing.quantity = 5
        self.listing.save()

        ProductValidationService.reserve_stock(self.listing, 3)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 2)

        # Now release it back
        ProductValidationService.release_stock(self.listing, 3)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 5)

    def test_release_more_than_reserved(self):
        """Test that release can add any amount (order cancellation)"""
        # Start with 5
        self.listing.quantity = 5
        self.listing.save()

        # Release 10 (simulating cancelled orders)
        ProductValidationService.release_stock(self.listing, 10)

        # Verify stock increased correctly
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 15)

    def test_reserve_after_failed_attempt(self):
        """Test that failed reservation doesn't affect subsequent operations"""
        self.listing.quantity = 5
        self.listing.save()

        # First attempt - should fail
        with self.assertRaises(InsufficientStockError):
            ProductValidationService.reserve_stock(self.listing, 10)

        # Stock should remain unchanged
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 5)

        # Second attempt with valid quantity - should succeed
        ProductValidationService.reserve_stock(self.listing, 3)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 2)

    def test_atomic_update_consistency(self):
        """
        Test that the atomic F() expression ensures consistency.

        This validates that the update query uses the database value,
        not the in-memory value.
        """
        self.listing.quantity = 10
        self.listing.save()

        # Modify in-memory value (simulating stale data)
        self.listing.quantity = 100  # Stale data

        # The atomic update should use DB value (10), not in-memory value (100)
        ProductValidationService.reserve_stock(self.listing, 5)

        # Verify it used the correct DB value
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 5,
            "Should use database value (10), not stale in-memory value (100)")

    def test_zero_stock_prevents_reservation(self):
        """Test that reservation fails when stock is zero"""
        self.listing.quantity = 0
        self.listing.save()

        with self.assertRaises(InsufficientStockError) as context:
            ProductValidationService.reserve_stock(self.listing, 1)

        self.assertIn("Cannot reserve 1 units", str(context.exception))
        self.assertIn("Available: 0", str(context.exception))
