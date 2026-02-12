"""
Tests for Cart functionality
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal

from authentication.models import CustomUser
from products.models import Products, MarketplaceListing, Brand, Condition, Category, Series
from orders.models import Cart, CartItem


class CartTestCase(TestCase):
    """Test case for cart functionality"""

    def setUp(self):
        """Set up test data"""
        # Create users
        self.buyer = CustomUser.objects.create_user(
            email='buyer@test.com',
            password='testpass123',
            full_name='Buyer User'
        )
        self.seller = CustomUser.objects.create_user(
            email='seller@test.com',
            password='testpass123',
            full_name='Seller User'
        )

        # Create category, series, brand and condition
        self.category = Category.objects.create(
            name='Weights',
            slug='weights',
            is_active=True
        )
        self.series = Series.objects.create(
            name='Test Series',
            slug='test-series'
        )
        self.brand = Brand.objects.create(
            name='Test Brand',
            slug='test-brand'
        )
        self.condition = Condition.objects.create(
            name='Novo',
            slug='novo'
        )

        # Create product
        self.product = Products.objects.create(
            name='Test Product',
            slug='test-product',
            description='Test description',
            category=self.category,
            series=self.series
        )

        # Create listing owned by seller
        self.listing = MarketplaceListing.objects.create(
            product=self.product,
            seller=self.seller,
            price=Decimal('100.00'),
            brand=self.brand,
            condition=self.condition,
            quantity=10,
            is_active=True,
            description='Test listing description',
            weight_kg=Decimal('10.00'),
            height_cm=Decimal('20.00'),
            width_cm=Decimal('30.00'),
            length_cm=Decimal('40.00')
        )

        # Set up API client
        self.client = APIClient()

    def test_buyer_can_add_listing_to_cart(self):
        """Test that a buyer can add another seller's listing to cart"""
        self.client.force_authenticate(user=self.buyer)

        url = reverse('orders:cart-add')
        data = {
            'listing': self.listing.id,
            'quantity': 2
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CartItem.objects.filter(cart__user=self.buyer).count(), 1)

        cart_item = CartItem.objects.get(cart__user=self.buyer)
        self.assertEqual(cart_item.listing, self.listing)
        self.assertEqual(cart_item.quantity, 2)

    def test_seller_cannot_add_own_listing_to_cart(self):
        """Test that a seller cannot add their own listing to cart"""
        self.client.force_authenticate(user=self.seller)

        url = reverse('orders:cart-add')
        data = {
            'listing': self.listing.id,
            'quantity': 1
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertEqual(
            response.data['error'],
            'Você não pode adicionar ao carrinho um produto que você mesmo está vendendo'
        )

        # Verify no cart item was created
        self.assertEqual(CartItem.objects.filter(cart__user=self.seller).count(), 0)

    def test_unauthenticated_user_cannot_add_to_cart(self):
        """Test that unauthenticated users cannot add to cart"""
        url = reverse('orders:cart-add')
        data = {
            'listing': self.listing.id,
            'quantity': 1
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
