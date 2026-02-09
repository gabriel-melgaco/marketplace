"""
Test Order Creation with Multiple Delivery Methods

Tests the new order creation flow that supports both shipping and in-person delivery methods.

Test Coverage:
- OrderCreateSerializer validation for legacy and new formats
- OrderCreationService shipping/in-person validation and calculation
- auto_create_shipments_on_payment signal handling both delivery methods
"""

from django.test import TestCase, RequestFactory
from django.utils import timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock, Mock
from datetime import timedelta
import uuid

from orders.serializers import OrderCreateSerializer
from orders.models import Order, Cart, CartItem, OrderItem
from orders.services.order_creation_service import OrderCreationService, OrderCreationError
from products.models import MarketplaceListing, Products, Brand, Condition, Category, Series
from authentication.models import CustomUser
from logistics.models import Address, ShippingQuote


class OrderCreateSerializerTestCase(TestCase):
    """Test OrderCreateSerializer validation and normalization"""

    def setUp(self):
        """Set up test fixtures"""
        # Create users
        self.buyer = CustomUser.objects.create_user(
            email='buyer@test.com',
            password='testpass123',
            first_name='Buyer',
            last_name='Test'
        )
        self.seller1 = CustomUser.objects.create_user(
            email='seller1@test.com',
            password='testpass123',
            first_name='Seller',
            last_name='One'
        )
        self.seller2 = CustomUser.objects.create_user(
            email='seller2@test.com',
            password='testpass123',
            first_name='Seller',
            last_name='Two'
        )

        # Create address
        self.address = Address.objects.create(
            user=self.buyer,
            recipient_name='Buyer Test',
            recipient_phone='11999999999',
            zipcode='01310-100',
            street='Av Paulista',
            number='1000',
            neighborhood='Bela Vista',
            city='São Paulo',
            state='SP',
            is_active=True
        )

        # Create product catalog
        self.category = Category.objects.create(name='Equipamentos', slug='equipamentos')
        self.series = Series.objects.create(name='Pro Series', slug='pro-series')
        self.brand = Brand.objects.create(name='TechGym', slug='techgym')
        self.condition = Condition.objects.create(name='Novo', slug='novo')

        self.product1 = Products.objects.create(
            name='Esteira Elite',
            slug='esteira-elite',
            code='EST-001',
            category=self.category,
            series=self.series,
            description='Esteira profissional'
        )
        self.product2 = Products.objects.create(
            name='Bike Ergométrica',
            slug='bike-ergometrica',
            code='BIKE-001',
            category=self.category,
            series=self.series,
            description='Bike profissional'
        )

        # Create listings
        self.listing1 = MarketplaceListing.objects.create(
            product=self.product1,
            seller=self.seller1,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('1500.00'),
            quantity=5,
            is_active=True,
            weight_kg=Decimal('50.00'),
            height_cm=Decimal('120.00'),
            width_cm=Decimal('80.00'),
            length_cm=Decimal('150.00')
        )
        self.listing2 = MarketplaceListing.objects.create(
            product=self.product2,
            seller=self.seller2,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('800.00'),
            quantity=3,
            is_active=True,
            weight_kg=Decimal('30.00'),
            height_cm=Decimal('100.00'),
            width_cm=Decimal('60.00'),
            length_cm=Decimal('120.00')
        )

        # Create cart with items
        self.cart = Cart.objects.create(user=self.buyer)
        CartItem.objects.create(cart=self.cart, listing=self.listing1, quantity=1)
        CartItem.objects.create(cart=self.cart, listing=self.listing2, quantity=1)

        # Create request factory
        self.factory = RequestFactory()
        self.request = self.factory.post('/api/orders/')
        self.request.user = self.buyer

    def test_legacy_format_accepted(self):
        """Test that legacy format (seller_id: service_id) is accepted and normalized"""
        data = {
            'shipping_address_id': self.address.id,
            'shipping_services': {
                str(self.seller1.id): 2,  # seller1: service_id 2
                str(self.seller2.id): 1   # seller2: service_id 1
            },
            'payment_method': 'pix',
            'buyer_notes': ''
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})

        # Should be valid
        self.assertTrue(serializer.is_valid(), serializer.errors)

        # Check normalization
        normalized = serializer.validated_data['shipping_services']
        self.assertEqual(normalized[self.seller1.id]['delivery_method'], 'shipping')
        self.assertEqual(normalized[self.seller1.id]['service_id'], 2)
        self.assertEqual(normalized[self.seller2.id]['delivery_method'], 'shipping')
        self.assertEqual(normalized[self.seller2.id]['service_id'], 1)

    def test_shipping_format_accepted(self):
        """Test that new shipping format is accepted"""
        data = {
            'shipping_address_id': self.address.id,
            'shipping_services': {
                str(self.seller1.id): {
                    'delivery_method': 'shipping',
                    'service_id': 2,
                    'cost': 25.90
                },
                str(self.seller2.id): {
                    'delivery_method': 'shipping',
                    'service_id': 1,
                    'cost': 15.50
                }
            },
            'payment_method': 'credit_card',
            'buyer_notes': 'Entregar após 18h'
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})

        self.assertTrue(serializer.is_valid(), serializer.errors)

        normalized = serializer.validated_data['shipping_services']
        self.assertEqual(normalized[self.seller1.id]['delivery_method'], 'shipping')
        self.assertEqual(normalized[self.seller1.id]['service_id'], 2)

    def test_in_person_format_accepted(self):
        """Test that in-person delivery format is accepted"""
        data = {
            'shipping_address_id': self.address.id,
            'shipping_services': {
                str(self.seller1.id): {
                    'delivery_method': 'in_person',
                    'meeting_location_name': 'Shopping Iguatemi',
                    'meeting_address': {
                        'street': 'Av. Brigadeiro Faria Lima',
                        'number': '2232',
                        'city': 'São Paulo',
                        'state': 'SP',
                        'zipcode': '01451-000'
                    },
                    'seller_contact_phone': '11999999999',
                    'buyer_contact_phone': '11888888888',
                    'scheduled_date': '2026-02-15',
                    'scheduled_time': '14:00',
                    'meeting_notes': 'Próximo à entrada principal'
                },
                str(self.seller2.id): {
                    'delivery_method': 'shipping',
                    'service_id': 1
                }
            },
            'payment_method': 'pix',
            'buyer_notes': ''
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})

        self.assertTrue(serializer.is_valid(), serializer.errors)

        normalized = serializer.validated_data['shipping_services']

        # Check in-person delivery
        self.assertEqual(normalized[self.seller1.id]['delivery_method'], 'in_person')
        self.assertEqual(normalized[self.seller1.id]['cost'], 0)
        self.assertEqual(normalized[self.seller1.id]['meeting_location_name'], 'Shopping Iguatemi')
        self.assertIn('meeting_address', normalized[self.seller1.id])

        # Check shipping delivery
        self.assertEqual(normalized[self.seller2.id]['delivery_method'], 'shipping')

    def test_mixed_format_accepted(self):
        """Test that mixed shipping and in-person format is accepted"""
        data = {
            'shipping_address_id': self.address.id,
            'shipping_services': {
                str(self.seller1.id): {
                    'delivery_method': 'shipping',
                    'service_id': 3
                },
                str(self.seller2.id): {
                    'delivery_method': 'in_person',
                    'meeting_location_name': 'Loja Fisica',
                    'meeting_address': {
                        'street': 'Rua Augusta',
                        'number': '100',
                        'city': 'São Paulo',
                        'state': 'SP'
                    },
                    'seller_contact_phone': '11777777777',
                    'buyer_contact_phone': '11666666666'
                }
            },
            'payment_method': 'boleto',
            'buyer_notes': ''
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_invalid_delivery_method_rejected(self):
        """Test that invalid delivery_method is rejected"""
        data = {
            'shipping_address_id': self.address.id,
            'shipping_services': {
                str(self.seller1.id): {
                    'delivery_method': 'teleport',  # Invalid
                    'service_id': 1
                }
            },
            'payment_method': 'pix'
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})

        self.assertFalse(serializer.is_valid())
        self.assertIn('shipping_services', serializer.errors)

    def test_missing_required_in_person_fields_rejected(self):
        """Test that missing required in-person fields are rejected"""
        data = {
            'shipping_address_id': self.address.id,
            'shipping_services': {
                str(self.seller1.id): {
                    'delivery_method': 'in_person',
                    'meeting_location_name': 'Shopping',
                    # Missing: meeting_address, seller_contact_phone, buyer_contact_phone
                }
            },
            'payment_method': 'pix'
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})

        self.assertFalse(serializer.is_valid())
        self.assertIn('shipping_services', serializer.errors)

    def test_missing_service_id_for_shipping_rejected(self):
        """Test that missing service_id for shipping is rejected"""
        data = {
            'shipping_address_id': self.address.id,
            'shipping_services': {
                str(self.seller1.id): {
                    'delivery_method': 'shipping',
                    # Missing service_id
                }
            },
            'payment_method': 'pix'
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})

        self.assertFalse(serializer.is_valid())
        self.assertIn('shipping_services', serializer.errors)

    def test_missing_meeting_address_fields_rejected(self):
        """Test that missing required meeting_address fields are rejected"""
        data = {
            'shipping_address_id': self.address.id,
            'shipping_services': {
                str(self.seller1.id): {
                    'delivery_method': 'in_person',
                    'meeting_location_name': 'Shopping',
                    'meeting_address': {
                        'street': 'Rua A',
                        # Missing: city, state
                    },
                    'seller_contact_phone': '11999999999',
                    'buyer_contact_phone': '11888888888'
                }
            },
            'payment_method': 'pix'
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})

        self.assertFalse(serializer.is_valid())
        self.assertIn('shipping_services', serializer.errors)


class OrderCreationServiceTestCase(TestCase):
    """Test OrderCreationService validation and calculation logic"""

    def setUp(self):
        """Set up test fixtures"""
        # Create users
        self.buyer = CustomUser.objects.create_user(
            email='buyer@test.com',
            password='testpass123',
            first_name='Buyer',
            last_name='Test'
        )
        self.seller1 = CustomUser.objects.create_user(
            email='seller1@test.com',
            password='testpass123',
            first_name='Seller',
            last_name='One'
        )
        self.seller2 = CustomUser.objects.create_user(
            email='seller2@test.com',
            password='testpass123',
            first_name='Seller',
            last_name='Two'
        )

        # Create addresses
        self.buyer_address = Address.objects.create(
            user=self.buyer,
            recipient_name='Buyer Test',
            recipient_phone='11999999999',
            zipcode='01310-100',
            street='Av Paulista',
            number='1000',
            neighborhood='Bela Vista',
            city='São Paulo',
            state='SP',
            is_active=True
        )

        self.seller1_address = Address.objects.create(
            user=self.seller1,
            recipient_name='Seller One',
            recipient_phone='11888888888',
            zipcode='02310-100',
            street='Rua A',
            number='100',
            neighborhood='Centro',
            city='São Paulo',
            state='SP',
            is_shipping_address=True,
            is_active=True
        )

        # Create product catalog
        self.category = Category.objects.create(name='Equipamentos', slug='equipamentos')
        self.series = Series.objects.create(name='Pro Series', slug='pro-series')
        self.brand = Brand.objects.create(name='TechGym', slug='techgym')
        self.condition = Condition.objects.create(name='Novo', slug='novo')

        self.product1 = Products.objects.create(
            name='Esteira Elite',
            slug='esteira-elite',
            code='EST-001',
            category=self.category,
            series=self.series
        )
        self.product2 = Products.objects.create(
            name='Bike Ergométrica',
            slug='bike-ergometrica',
            code='BIKE-001',
            category=self.category,
            series=self.series
        )

        # Create listings
        self.listing1 = MarketplaceListing.objects.create(
            product=self.product1,
            seller=self.seller1,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('1500.00'),
            quantity=5,
            is_active=True,
            weight_kg=Decimal('50.00'),
            height_cm=Decimal('120.00'),
            width_cm=Decimal('80.00'),
            length_cm=Decimal('150.00')
        )
        self.listing2 = MarketplaceListing.objects.create(
            product=self.product2,
            seller=self.seller2,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('800.00'),
            quantity=3,
            is_active=True,
            weight_kg=Decimal('30.00'),
            height_cm=Decimal('100.00'),
            width_cm=Decimal('60.00'),
            length_cm=Decimal('120.00')
        )

        # Create cart
        self.cart = Cart.objects.create(user=self.buyer)
        CartItem.objects.create(cart=self.cart, listing=self.listing1, quantity=1)
        CartItem.objects.create(cart=self.cart, listing=self.listing2, quantity=1)

    def test_shipping_calculates_cost_from_quote(self):
        """Test that shipping cost is calculated from server-side quote, not client input"""
        # Create shipping quote for seller1
        quote = ShippingQuote.objects.create(
            user=self.buyer,
            seller=self.seller1,
            origin_zipcode='02310-100',
            origin_address={},
            destination_zipcode='01310-100',
            destination_address={},
            weight=Decimal('50.00'),
            height=Decimal('120.00'),
            width=Decimal('80.00'),
            length=Decimal('150.00'),
            declared_value=Decimal('1500.00'),
            quotes_data={
                'services': [
                    {'id': 1, 'name': 'PAC', 'price': 45.90, 'company': 'Correios'},
                    {'id': 2, 'name': 'SEDEX', 'price': 75.50, 'company': 'Correios'}
                ]
            },
            expires_at=timezone.now() + timedelta(hours=24)
        )

        # Create quote for seller2 with in-person (no quote needed)
        shipping_services_input = {
            self.seller1.id: {
                'delivery_method': 'shipping',
                'service_id': 2,
                'cost': 999.99  # Client tries to send fake cost
            },
            self.seller2.id: {
                'delivery_method': 'in_person',
                'meeting_location_name': 'Loja',
                'meeting_address': {'street': 'Rua B', 'city': 'SP', 'state': 'SP'},
                'seller_contact_phone': '11777777777',
                'buyer_contact_phone': '11666666666'
            }
        }

        # Get validated items
        cart_items = self.cart.items.select_related(
            'listing__product', 'listing__seller', 'listing__brand', 'listing__condition'
        ).all()

        with patch('orders.services.product_validation_service.ProductValidationService.validate_cart_items') as mock_validate:
            mock_validate.return_value = [
                {
                    'listing': self.listing1,
                    'seller': self.seller1,
                    'quantity': 1,
                    'unit_price': self.listing1.price,
                    'product_snapshot': {
                        'name': self.product1.name,
                        'code': self.product1.code,
                        'brand': self.brand.name,
                        'condition': self.condition.name
                    },
                    'dimensions': {
                        'weight_kg': self.listing1.weight_kg,
                        'height_cm': self.listing1.height_cm,
                        'width_cm': self.listing1.width_cm,
                        'length_cm': self.listing1.length_cm
                    }
                },
                {
                    'listing': self.listing2,
                    'seller': self.seller2,
                    'quantity': 1,
                    'unit_price': self.listing2.price,
                    'product_snapshot': {
                        'name': self.product2.name,
                        'code': self.product2.code,
                        'brand': self.brand.name,
                        'condition': self.condition.name
                    },
                    'dimensions': {
                        'weight_kg': self.listing2.weight_kg,
                        'height_cm': self.listing2.height_cm,
                        'width_cm': self.listing2.width_cm,
                        'length_cm': self.listing2.length_cm
                    }
                }
            ]

            shipping_data = OrderCreationService._validate_and_calculate_shipping(
                self.buyer,
                mock_validate.return_value,
                shipping_services_input
            )

        # Cost should be from server-side quote (75.50), NOT client input (999.99)
        self.assertEqual(shipping_data['total_shipping'], Decimal('75.50'))
        self.assertEqual(shipping_data['shipping_by_seller'][self.seller1.id], Decimal('75.50'))
        self.assertEqual(shipping_data['shipping_by_seller'][self.seller2.id], Decimal('0.00'))

    def test_in_person_has_zero_shipping_cost(self):
        """Test that in-person delivery has zero shipping cost"""
        shipping_services_input = {
            self.seller1.id: {
                'delivery_method': 'in_person',
                'meeting_location_name': 'Shopping X',
                'meeting_address': {'street': 'Av A', 'city': 'São Paulo', 'state': 'SP'},
                'seller_contact_phone': '11999999999',
                'buyer_contact_phone': '11888888888',
                'cost': 100.00  # Client tries to send fake cost
            },
            self.seller2.id: {
                'delivery_method': 'in_person',
                'meeting_location_name': 'Loja Y',
                'meeting_address': {'street': 'Rua B', 'city': 'São Paulo', 'state': 'SP'},
                'seller_contact_phone': '11777777777',
                'buyer_contact_phone': '11666666666'
            }
        }

        cart_items = self.cart.items.select_related(
            'listing__product', 'listing__seller', 'listing__brand', 'listing__condition'
        ).all()

        with patch('orders.services.product_validation_service.ProductValidationService.validate_cart_items') as mock_validate:
            mock_validate.return_value = [
                {
                    'listing': self.listing1,
                    'seller': self.seller1,
                    'quantity': 1,
                    'unit_price': self.listing1.price,
                    'product_snapshot': {
                        'name': self.product1.name,
                        'code': self.product1.code,
                        'brand': self.brand.name,
                        'condition': self.condition.name
                    },
                    'dimensions': {
                        'weight_kg': self.listing1.weight_kg,
                        'height_cm': self.listing1.height_cm,
                        'width_cm': self.listing1.width_cm,
                        'length_cm': self.listing1.length_cm
                    }
                },
                {
                    'listing': self.listing2,
                    'seller': self.seller2,
                    'quantity': 1,
                    'unit_price': self.listing2.price,
                    'product_snapshot': {
                        'name': self.product2.name,
                        'code': self.product2.code,
                        'brand': self.brand.name,
                        'condition': self.condition.name
                    },
                    'dimensions': {
                        'weight_kg': self.listing2.weight_kg,
                        'height_cm': self.listing2.height_cm,
                        'width_cm': self.listing2.width_cm,
                        'length_cm': self.listing2.length_cm
                    }
                }
            ]

            shipping_data = OrderCreationService._validate_and_calculate_shipping(
                self.buyer,
                mock_validate.return_value,
                shipping_services_input
            )

        # Both should have zero shipping cost
        self.assertEqual(shipping_data['total_shipping'], Decimal('0.00'))
        self.assertEqual(shipping_data['shipping_by_seller'][self.seller1.id], Decimal('0.00'))
        self.assertEqual(shipping_data['shipping_by_seller'][self.seller2.id], Decimal('0.00'))

    def test_mixed_order_totals_shipping_correctly(self):
        """Test that mixed order (shipping + in-person) calculates total correctly"""
        # Create quote for seller1 only
        quote = ShippingQuote.objects.create(
            user=self.buyer,
            seller=self.seller1,
            origin_zipcode='02310-100',
            origin_address={},
            destination_zipcode='01310-100',
            destination_address={},
            weight=Decimal('50.00'),
            height=Decimal('120.00'),
            width=Decimal('80.00'),
            length=Decimal('150.00'),
            declared_value=Decimal('1500.00'),
            quotes_data={
                'services': [
                    {'id': 1, 'name': 'PAC', 'price': 45.90, 'company': 'Correios'}
                ]
            },
            expires_at=timezone.now() + timedelta(hours=24)
        )

        shipping_services_input = {
            self.seller1.id: {
                'delivery_method': 'shipping',
                'service_id': 1
            },
            self.seller2.id: {
                'delivery_method': 'in_person',
                'meeting_location_name': 'Loja',
                'meeting_address': {'street': 'Rua C', 'city': 'SP', 'state': 'SP'},
                'seller_contact_phone': '11555555555',
                'buyer_contact_phone': '11444444444'
            }
        }

        cart_items = self.cart.items.select_related(
            'listing__product', 'listing__seller', 'listing__brand', 'listing__condition'
        ).all()

        with patch('orders.services.product_validation_service.ProductValidationService.validate_cart_items') as mock_validate:
            mock_validate.return_value = [
                {
                    'listing': self.listing1,
                    'seller': self.seller1,
                    'quantity': 1,
                    'unit_price': self.listing1.price,
                    'product_snapshot': {
                        'name': self.product1.name,
                        'code': self.product1.code,
                        'brand': self.brand.name,
                        'condition': self.condition.name
                    },
                    'dimensions': {
                        'weight_kg': self.listing1.weight_kg,
                        'height_cm': self.listing1.height_cm,
                        'width_cm': self.listing1.width_cm,
                        'length_cm': self.listing1.length_cm
                    }
                },
                {
                    'listing': self.listing2,
                    'seller': self.seller2,
                    'quantity': 1,
                    'unit_price': self.listing2.price,
                    'product_snapshot': {
                        'name': self.product2.name,
                        'code': self.product2.code,
                        'brand': self.brand.name,
                        'condition': self.condition.name
                    },
                    'dimensions': {
                        'weight_kg': self.listing2.weight_kg,
                        'height_cm': self.listing2.height_cm,
                        'width_cm': self.listing2.width_cm,
                        'length_cm': self.listing2.length_cm
                    }
                }
            ]

            shipping_data = OrderCreationService._validate_and_calculate_shipping(
                self.buyer,
                mock_validate.return_value,
                shipping_services_input
            )

        # Only seller1 should have shipping cost
        self.assertEqual(shipping_data['total_shipping'], Decimal('45.90'))
        self.assertEqual(shipping_data['shipping_by_seller'][self.seller1.id], Decimal('45.90'))
        self.assertEqual(shipping_data['shipping_by_seller'][self.seller2.id], Decimal('0.00'))

    def test_shipping_without_valid_quote_raises_error(self):
        """Test that shipping without valid quote raises error"""
        shipping_services_input = {
            self.seller1.id: {
                'delivery_method': 'shipping',
                'service_id': 1
            }
        }

        cart_items = self.cart.items.select_related(
            'listing__product', 'listing__seller', 'listing__brand', 'listing__condition'
        ).all()

        with patch('orders.services.product_validation_service.ProductValidationService.validate_cart_items') as mock_validate:
            mock_validate.return_value = [
                {
                    'listing': self.listing1,
                    'seller': self.seller1,
                    'quantity': 1,
                    'unit_price': self.listing1.price,
                    'product_snapshot': {
                        'name': self.product1.name,
                        'code': self.product1.code,
                        'brand': self.brand.name,
                        'condition': self.condition.name
                    },
                    'dimensions': {
                        'weight_kg': self.listing1.weight_kg,
                        'height_cm': self.listing1.height_cm,
                        'width_cm': self.listing1.width_cm,
                        'length_cm': self.listing1.length_cm
                    }
                }
            ]

            with self.assertRaises(OrderCreationError) as context:
                OrderCreationService._validate_and_calculate_shipping(
                    self.buyer,
                    mock_validate.return_value,
                    shipping_services_input
                )

        self.assertIn('expired or not found', str(context.exception))

    def test_invalid_delivery_method_raises_error(self):
        """Test that invalid delivery_method raises error"""
        shipping_services_input = {
            self.seller1.id: {
                'delivery_method': 'teleport',  # Invalid
                'service_id': 1
            }
        }

        cart_items = self.cart.items.select_related(
            'listing__product', 'listing__seller', 'listing__brand', 'listing__condition'
        ).all()

        with patch('orders.services.product_validation_service.ProductValidationService.validate_cart_items') as mock_validate:
            mock_validate.return_value = [
                {
                    'listing': self.listing1,
                    'seller': self.seller1,
                    'quantity': 1,
                    'unit_price': self.listing1.price,
                    'product_snapshot': {
                        'name': self.product1.name,
                        'code': self.product1.code,
                        'brand': self.brand.name,
                        'condition': self.condition.name
                    },
                    'dimensions': {
                        'weight_kg': self.listing1.weight_kg,
                        'height_cm': self.listing1.height_cm,
                        'width_cm': self.listing1.width_cm,
                        'length_cm': self.listing1.length_cm
                    }
                }
            ]

            with self.assertRaises(OrderCreationError) as context:
                OrderCreationService._validate_and_calculate_shipping(
                    self.buyer,
                    mock_validate.return_value,
                    shipping_services_input
                )

        self.assertIn('Invalid delivery method', str(context.exception))


class OrderCreationSignalTestCase(TestCase):
    """Test auto_create_shipments_on_payment signal handling"""

    def setUp(self):
        """Set up test fixtures"""
        # Create users
        self.buyer = CustomUser.objects.create_user(
            email='buyer@test.com',
            password='testpass123',
            first_name='Buyer',
            last_name='Test'
        )
        self.seller1 = CustomUser.objects.create_user(
            email='seller1@test.com',
            password='testpass123',
            first_name='Seller',
            last_name='One'
        )
        self.seller2 = CustomUser.objects.create_user(
            email='seller2@test.com',
            password='testpass123',
            first_name='Seller',
            last_name='Two'
        )

        # Create addresses
        self.buyer_address = Address.objects.create(
            user=self.buyer,
            recipient_name='Buyer Test',
            recipient_phone='11999999999',
            zipcode='01310-100',
            street='Av Paulista',
            number='1000',
            neighborhood='Bela Vista',
            city='São Paulo',
            state='SP',
            is_active=True
        )

    @patch('logistics.services.delivery_orchestration_service.DeliveryOrchestrationService.create_order_deliveries')
    def test_signal_creates_shipping_delivery(self, mock_create_deliveries):
        """Test that signal creates shipping delivery for shipping method"""
        # Create order with shipping method
        order = Order.objects.create(
            buyer=self.buyer,
            status='pending_payment',
            subtotal=Decimal('1500.00'),
            shipping_cost=Decimal('45.90'),
            total=Decimal('1545.90'),
            shipping_address=self.buyer_address.to_dict(),
            shipping_services={
                str(self.seller1.id): {
                    'delivery_method': 'shipping',
                    'service_id': 1,
                    'service_name': 'PAC',
                    'company': 'Correios',
                    'cost': 45.90,
                    'delivery_time': 5
                }
            },
            payment_method='pix'
        )

        mock_create_deliveries.return_value = [MagicMock()]

        # Trigger signal by changing status to paid
        order.status = 'paid'
        order.save()

        # Check that create_order_deliveries was called
        mock_create_deliveries.assert_called_once()

        call_args = mock_create_deliveries.call_args
        self.assertEqual(call_args[1]['order'], order)

        delivery_choices = call_args[1]['delivery_choices']
        self.assertEqual(len(delivery_choices), 1)
        self.assertEqual(delivery_choices[0]['seller_id'], self.seller1.id)
        self.assertEqual(delivery_choices[0]['delivery_method'], 'shipping')
        self.assertEqual(delivery_choices[0]['shipping_service_id'], 1)

    @patch('logistics.services.delivery_orchestration_service.DeliveryOrchestrationService.create_order_deliveries')
    def test_signal_creates_in_person_delivery(self, mock_create_deliveries):
        """Test that signal creates in-person delivery for in-person method"""
        # Create order with in-person method
        order = Order.objects.create(
            buyer=self.buyer,
            status='pending_payment',
            subtotal=Decimal('800.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('800.00'),
            shipping_address=self.buyer_address.to_dict(),
            shipping_services={
                str(self.seller1.id): {
                    'delivery_method': 'in_person',
                    'cost': 0,
                    'meeting_location_name': 'Shopping X',
                    'meeting_address': {
                        'street': 'Av A',
                        'city': 'São Paulo',
                        'state': 'SP'
                    },
                    'seller_contact_phone': '11999999999',
                    'buyer_contact_phone': '11888888888',
                    'scheduled_date': '2026-02-15',
                    'scheduled_time': '14:00',
                    'meeting_notes': 'Entrada principal'
                }
            },
            payment_method='pix'
        )

        mock_create_deliveries.return_value = [MagicMock()]

        # Trigger signal by changing status to paid
        order.status = 'paid'
        order.save()

        # Check that create_order_deliveries was called
        mock_create_deliveries.assert_called_once()

        call_args = mock_create_deliveries.call_args
        delivery_choices = call_args[1]['delivery_choices']

        self.assertEqual(len(delivery_choices), 1)
        self.assertEqual(delivery_choices[0]['seller_id'], self.seller1.id)
        self.assertEqual(delivery_choices[0]['delivery_method'], 'in_person')
        self.assertEqual(delivery_choices[0]['meeting_location_name'], 'Shopping X')
        self.assertIn('meeting_address', delivery_choices[0])

    @patch('logistics.services.delivery_orchestration_service.DeliveryOrchestrationService.create_order_deliveries')
    def test_signal_handles_mixed_delivery_methods(self, mock_create_deliveries):
        """Test that signal handles mixed delivery methods correctly"""
        # Create order with both shipping and in-person
        order = Order.objects.create(
            buyer=self.buyer,
            status='pending_payment',
            subtotal=Decimal('2300.00'),
            shipping_cost=Decimal('45.90'),
            total=Decimal('2345.90'),
            shipping_address=self.buyer_address.to_dict(),
            shipping_services={
                str(self.seller1.id): {
                    'delivery_method': 'shipping',
                    'service_id': 1,
                    'service_name': 'PAC',
                    'company': 'Correios',
                    'cost': 45.90,
                    'delivery_time': 5
                },
                str(self.seller2.id): {
                    'delivery_method': 'in_person',
                    'cost': 0,
                    'meeting_location_name': 'Loja Física',
                    'meeting_address': {
                        'street': 'Rua B',
                        'city': 'São Paulo',
                        'state': 'SP'
                    },
                    'seller_contact_phone': '11777777777',
                    'buyer_contact_phone': '11666666666'
                }
            },
            payment_method='pix'
        )

        mock_create_deliveries.return_value = [MagicMock(), MagicMock()]

        # Trigger signal by changing status to paid
        order.status = 'paid'
        order.save()

        # Check that create_order_deliveries was called
        mock_create_deliveries.assert_called_once()

        call_args = mock_create_deliveries.call_args
        delivery_choices = call_args[1]['delivery_choices']

        # Should have 2 deliveries
        self.assertEqual(len(delivery_choices), 2)

        # Check shipping delivery
        shipping_delivery = next(d for d in delivery_choices if d['delivery_method'] == 'shipping')
        self.assertEqual(shipping_delivery['seller_id'], self.seller1.id)
        self.assertEqual(shipping_delivery['shipping_service_id'], 1)

        # Check in-person delivery
        in_person_delivery = next(d for d in delivery_choices if d['delivery_method'] == 'in_person')
        self.assertEqual(in_person_delivery['seller_id'], self.seller2.id)
        self.assertEqual(in_person_delivery['meeting_location_name'], 'Loja Física')
