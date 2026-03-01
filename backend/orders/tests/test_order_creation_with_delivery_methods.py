"""
Test Order Creation with Multiple Delivery Methods

Tests the order creation flow using per-item delivery method selection.

Test Coverage:
- OrderCreateSerializer validation for new items_delivery + in_person_by_seller format
- Internal conversion from per-item to per-seller shipping_services format
- OrderCreationService shipping/in-person validation and calculation (unchanged internals)
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
    """
    Test OrderCreateSerializer validation and conversion.

    Uses the new per-item delivery format:
      items_delivery: list of {listing_id, delivery_method, [service_id]}
      in_person_by_seller: optional dict of seller_id → meeting details
    """

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

        # Create listings (default shipping_method='both')
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
            length_cm=Decimal('150.00'),
            shipping_method='both',
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
            length_cm=Decimal('120.00'),
            shipping_method='both',
        )

        # Create cart with items
        self.cart = Cart.objects.create(user=self.buyer)
        CartItem.objects.create(cart=self.cart, listing=self.listing1, quantity=1)
        CartItem.objects.create(cart=self.cart, listing=self.listing2, quantity=1)

        # Create a valid ShippingQuote for seller1 (needed when choosing melhor_envio)
        self.quote1 = ShippingQuote.objects.create(
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
                    {
                        'id': 1,
                        'name': 'PAC',
                        'price': '45.90',
                        'custom_price': '45.90',
                        'delivery_time': 5,
                        'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                    },
                    {
                        'id': 2,
                        'name': 'SEDEX',
                        'price': '75.50',
                        'custom_price': '75.50',
                        'delivery_time': 2,
                        'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                    },
                ],
                'melhor_envio_listing_ids': [self.listing1.id],
            },
            expires_at=timezone.now() + timedelta(hours=24),
        )
        self.quote2 = ShippingQuote.objects.create(
            user=self.buyer,
            seller=self.seller2,
            origin_zipcode='03310-100',
            origin_address={},
            destination_zipcode='01310-100',
            destination_address={},
            weight=Decimal('30.00'),
            height=Decimal('100.00'),
            width=Decimal('60.00'),
            length=Decimal('120.00'),
            declared_value=Decimal('800.00'),
            quotes_data={
                'services': [
                    {
                        'id': 1,
                        'name': 'PAC',
                        'price': '30.00',
                        'custom_price': '30.00',
                        'delivery_time': 7,
                        'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                    },
                ],
                'melhor_envio_listing_ids': [self.listing2.id],
            },
            expires_at=timezone.now() + timedelta(hours=24),
        )

        # Create request factory
        self.factory = RequestFactory()
        self.request = self.factory.post('/api/orders/')
        self.request.user = self.buyer

    # ---- Happy path tests ----

    def test_all_melhor_envio_accepted_and_converts_to_shipping_services(self):
        """Both items via Melhor Envio → shipping_services has 'shipping' for each seller."""
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'melhor_envio', 'service_id': 1},
                {'listing_id': self.listing2.id, 'delivery_method': 'melhor_envio', 'service_id': 1},
            ],
            'in_person_by_seller': {},
            'payment_method': 'pix',
            'buyer_notes': '',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

        ss = serializer.validated_data['shipping_services']
        self.assertEqual(ss[str(self.seller1.id)]['delivery_method'], 'shipping')
        self.assertEqual(ss[str(self.seller1.id)]['service_id'], 1)
        self.assertEqual(ss[str(self.seller2.id)]['delivery_method'], 'shipping')
        self.assertEqual(ss[str(self.seller2.id)]['service_id'], 1)

    def test_all_in_person_accepted_and_converts_to_shipping_services(self):
        """Both items in-person → shipping_services has 'in_person' for each seller."""
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'in_person'},
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'in_person_by_seller': {
                str(self.seller1.id): {
                    'meeting_location_name': 'Shopping Iguatemi',
                    'meeting_address': {
                        'street': 'Av. Brigadeiro Faria Lima',
                        'number': '2232',
                        'city': 'São Paulo',
                        'state': 'SP',
                        'zipcode': '01451-000',
                    },
                    'seller_contact_phone': '11999999999',
                    'buyer_contact_phone': '11888888888',
                    'scheduled_date': '2026-03-10',
                    'scheduled_time': '14:00',
                    'meeting_notes': 'Próximo à entrada principal',
                },
                str(self.seller2.id): {},
            },
            'payment_method': 'pix',
            'buyer_notes': '',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

        ss = serializer.validated_data['shipping_services']
        self.assertEqual(ss[str(self.seller1.id)]['delivery_method'], 'in_person')
        self.assertEqual(ss[str(self.seller1.id)]['cost'], 0)
        self.assertEqual(ss[str(self.seller1.id)]['meeting_location_name'], 'Shopping Iguatemi')
        self.assertIn('meeting_address', ss[str(self.seller1.id)])
        self.assertEqual(ss[str(self.seller2.id)]['delivery_method'], 'in_person')

    def test_mixed_delivery_accepted_and_converts_to_shipping_services(self):
        """Seller1 via ME, seller2 in-person → correct per-seller shipping_services."""
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'melhor_envio', 'service_id': 2},
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'in_person_by_seller': {
                str(self.seller2.id): {
                    'meeting_location_name': 'Loja Física',
                    'seller_contact_phone': '11777777777',
                    'buyer_contact_phone': '11666666666',
                },
            },
            'payment_method': 'credit_card',
            'buyer_notes': 'Entregar após 18h',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

        ss = serializer.validated_data['shipping_services']
        self.assertEqual(ss[str(self.seller1.id)]['delivery_method'], 'shipping')
        self.assertEqual(ss[str(self.seller1.id)]['service_id'], 2)
        self.assertEqual(ss[str(self.seller2.id)]['delivery_method'], 'in_person')
        self.assertEqual(ss[str(self.seller2.id)]['cost'], 0)
        self.assertEqual(ss[str(self.seller2.id)]['meeting_location_name'], 'Loja Física')

    def test_in_person_with_no_details_accepted(self):
        """in_person items with empty in_person_by_seller → all optional fields blank."""
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'in_person'},
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

        ss = serializer.validated_data['shipping_services']
        for seller_id in [str(self.seller1.id), str(self.seller2.id)]:
            self.assertEqual(ss[seller_id]['delivery_method'], 'in_person')
            self.assertEqual(ss[seller_id]['cost'], 0)
            self.assertEqual(ss[seller_id]['meeting_location_name'], '')

    def test_split_delivery_produces_split_format(self):
        """
        Seller1 has two listings: one chosen melhor_envio, one in_person.
        Result should be delivery_method='split' for that seller.
        """
        # Create a second listing for seller1 with shipping_method=in_person
        listing1b = MarketplaceListing.objects.create(
            product=self.product2,
            seller=self.seller1,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('200.00'),
            quantity=2,
            is_active=True,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('20.00'),
            width_cm=Decimal('20.00'),
            length_cm=Decimal('20.00'),
            shipping_method='in_person',
        )
        # Adding this cart item fires the invalidation signal and deletes seller1's quote.
        CartItem.objects.create(cart=self.cart, listing=listing1b, quantity=1)

        # Recreate seller1's quote after cart change, including listing1 in melhor_envio_listing_ids.
        # listing1b is in_person-only so it does not appear in the ME listing ids.
        ShippingQuote.objects.filter(user=self.buyer, seller=self.seller1).delete()
        ShippingQuote.objects.create(
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
                    {
                        'id': 1,
                        'name': 'PAC',
                        'price': '45.90',
                        'custom_price': '45.90',
                        'delivery_time': 5,
                        'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                    },
                    {
                        'id': 2,
                        'name': 'SEDEX',
                        'price': '75.50',
                        'custom_price': '75.50',
                        'delivery_time': 2,
                        'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                    },
                ],
                'melhor_envio_listing_ids': [self.listing1.id],
            },
            expires_at=timezone.now() + timedelta(hours=24),
        )

        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'melhor_envio', 'service_id': 1},
                {'listing_id': listing1b.id, 'delivery_method': 'in_person'},
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'in_person_by_seller': {
                str(self.seller1.id): {
                    'meeting_location_name': 'Portaria do Prédio',
                    'seller_contact_phone': '11911111111',
                },
            },
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

        ss = serializer.validated_data['shipping_services']
        # seller1 has mixed → split
        self.assertEqual(ss[str(self.seller1.id)]['delivery_method'], 'split')
        self.assertEqual(ss[str(self.seller1.id)]['shipping']['service_id'], 1)
        self.assertEqual(
            ss[str(self.seller1.id)]['in_person']['meeting_location_name'],
            'Portaria do Prédio'
        )
        # seller2 → in_person only
        self.assertEqual(ss[str(self.seller2.id)]['delivery_method'], 'in_person')

    def test_split_same_seller_both_listing_me_and_in_person_listing(self):
        """
        Replicates the exact scenario described in the calculate_shipping response update:

        Seller has two listings:
        - listing_30 (shipping_method='both') → buyer chooses melhor_envio, service_id=3
        - listing_31 (shipping_method='in_person') → forced to in_person (no service_id)

        Expected result: delivery_method='split' for that seller, with:
          shipping.service_id == 3
          in_person present (meeting details optional)

        This validates the full flow from calculate_shipping response → order creation:
          1. calculate_shipping returns melhor_envio_items=[listing_30] and in_person_items=[listing_31]
          2. Buyer builds items_delivery using listing_id from each group
          3. service_id=3 comes from services[].id in the calculate_shipping response
          4. OrderCreateSerializer validates, converts, and produces split format
        """
        # Create the two listings belonging to the same seller
        listing_both = MarketplaceListing.objects.create(
            product=self.product1,
            seller=self.seller1,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('500.00'),
            quantity=2,
            is_active=True,
            weight_kg=Decimal('10.00'),
            height_cm=Decimal('40.00'),
            width_cm=Decimal('30.00'),
            length_cm=Decimal('30.00'),
            shipping_method='both',  # buyer may choose either method
        )
        listing_in_person = MarketplaceListing.objects.create(
            product=self.product2,
            seller=self.seller1,  # same seller as listing_both
            brand=self.brand,
            condition=self.condition,
            price=Decimal('300.00'),
            quantity=3,
            is_active=True,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('20.00'),
            width_cm=Decimal('20.00'),
            length_cm=Decimal('20.00'),
            shipping_method='in_person',  # forces delivery_method='in_person'
        )

        # Add both listings to the cart (replacing existing cart items)
        self.cart.items.all().delete()
        CartItem.objects.create(cart=self.cart, listing=listing_both, quantity=1)
        CartItem.objects.create(cart=self.cart, listing=listing_in_person, quantity=1)

        # Create a ShippingQuote for seller1 that contains service_id=3 (.Package)
        # This mirrors what calculate_shipping would return in the updated response format.
        ShippingQuote.objects.filter(user=self.buyer, seller=self.seller1).delete()
        ShippingQuote.objects.create(
            user=self.buyer,
            seller=self.seller1,
            origin_zipcode='02310-100',
            origin_address={},
            destination_zipcode='01310-100',
            destination_address={},
            weight=Decimal('10.00'),
            height=Decimal('40.00'),
            width=Decimal('30.00'),
            length=Decimal('30.00'),
            declared_value=Decimal('500.00'),
            quotes_data={
                'services': [
                    {
                        'id': 1,
                        'name': 'PAC',
                        'price': '109.38',
                        'custom_price': '109.38',
                        'delivery_time': 7,
                        'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                    },
                    {
                        'id': 3,
                        'name': '.Package',
                        'price': '45.15',
                        'custom_price': '45.15',
                        'delivery_time': 3,
                        'company': {'id': 2, 'name': 'Loggi', 'picture': ''},
                    },
                ],
                'melhor_envio_listing_ids': [listing_both.id],
            },
            expires_at=timezone.now() + timedelta(hours=24),
        )

        # Buyer payload built from calculate_shipping response:
        #   melhor_envio_items → listing_both (both) with service_id=3 from services[].id
        #   in_person_items    → listing_in_person (in_person)
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {
                    'listing_id': listing_both.id,
                    'delivery_method': 'melhor_envio',
                    'service_id': 3,  # chosen from services[].id in calculate_shipping response
                },
                {
                    'listing_id': listing_in_person.id,
                    'delivery_method': 'in_person',  # forced by shipping_method='in_person'
                },
            ],
            'in_person_by_seller': {
                str(self.seller1.id): {}  # meeting details optional
            },
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

        ss = serializer.validated_data['shipping_services']

        # seller1 has both melhor_envio and in_person items → split
        self.assertEqual(ss[str(self.seller1.id)]['delivery_method'], 'split')
        self.assertEqual(ss[str(self.seller1.id)]['shipping']['service_id'], 3)
        self.assertIn('in_person', ss[str(self.seller1.id)])

    # ---- Validation rejection tests ----

    def test_invalid_delivery_method_rejected(self):
        """delivery_method must be 'melhor_envio' or 'in_person'."""
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'teleport', 'service_id': 1},
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)

    def test_missing_service_id_for_melhor_envio_rejected(self):
        """delivery_method='melhor_envio' without service_id must be rejected."""
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'melhor_envio'},
                # Missing service_id ^
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)

    def test_listing_not_in_cart_rejected(self):
        """listing_id not in buyer's cart must be rejected."""
        other_listing = MarketplaceListing.objects.create(
            product=self.product1,
            seller=self.seller2,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('500.00'),
            quantity=1,
            is_active=True,
            weight_kg=Decimal('10.00'),
            height_cm=Decimal('30.00'),
            width_cm=Decimal('30.00'),
            length_cm=Decimal('30.00'),
            shipping_method='both',
        )
        # other_listing is NOT added to the cart

        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'in_person'},
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
                {'listing_id': other_listing.id, 'delivery_method': 'in_person'},  # extra
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)

    def test_missing_cart_item_in_items_delivery_rejected(self):
        """If a cart listing has no entry in items_delivery, must be rejected."""
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                # listing2 is missing
                {'listing_id': self.listing1.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)

    def test_duplicate_listing_id_rejected(self):
        """Same listing_id appearing twice in items_delivery must be rejected."""
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'in_person'},
                {'listing_id': self.listing1.id, 'delivery_method': 'in_person'},  # duplicate
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)

    def test_shipping_method_in_person_only_listing_rejects_melhor_envio(self):
        """Listing with shipping_method='in_person' must not accept delivery_method='melhor_envio'."""
        self.listing1.shipping_method = 'in_person'
        self.listing1.save()

        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {
                    'listing_id': self.listing1.id,
                    'delivery_method': 'melhor_envio',  # conflict: listing is in_person-only
                    'service_id': 1,
                },
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)

    def test_shipping_method_melhor_envio_only_listing_rejects_in_person(self):
        """Listing with shipping_method='melhor_envio' must not accept delivery_method='in_person'."""
        self.listing1.shipping_method = 'melhor_envio'
        self.listing1.save()

        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {
                    'listing_id': self.listing1.id,
                    'delivery_method': 'in_person',  # conflict: listing is melhor_envio-only
                },
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)

    def test_expired_shipping_quote_rejected(self):
        """Choosing melhor_envio with an expired quote must be rejected."""
        self.quote1.expires_at = timezone.now() - timedelta(hours=1)
        self.quote1.save()

        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'melhor_envio', 'service_id': 1},
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)

    def test_service_id_not_in_quote_rejected(self):
        """Choosing a service_id not present in the ShippingQuote must be rejected."""
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {
                    'listing_id': self.listing1.id,
                    'delivery_method': 'melhor_envio',
                    'service_id': 999,  # not in quote
                },
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)

    def test_in_person_fields_all_optional(self):
        """in_person delivery requires NO additional fields — all optional."""
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'in_person'},
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            # in_person_by_seller completely omitted
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_different_service_ids_per_item_same_seller_rejected(self):
        """
        Two items from the same seller via melhor_envio must use the same service_id,
        because there is only one carrier shipment per seller.
        """
        listing1b = MarketplaceListing.objects.create(
            product=self.product2,
            seller=self.seller1,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('300.00'),
            quantity=1,
            is_active=True,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('20.00'),
            width_cm=Decimal('20.00'),
            length_cm=Decimal('20.00'),
            shipping_method='both',
        )
        CartItem.objects.create(cart=self.cart, listing=listing1b, quantity=1)

        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'melhor_envio', 'service_id': 1},
                {'listing_id': listing1b.id, 'delivery_method': 'melhor_envio', 'service_id': 2},
                # ^^ different service_id for same seller → should be rejected
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)

    def test_listing_not_in_original_quote_rejected(self):
        """
        If a buyer adds a new listing AFTER calculating shipping and tries to create an order
        using the old quote, the order must be rejected.

        The ShippingQuote was generated with listing1 only (melhor_envio_listing_ids=[listing1.id]).
        Buyer then adds listing_new (same seller) to the cart, keeps the old quote, and sends
        both listing1 and listing_new as melhor_envio. The listing_new was not included in the
        original quote so the order must be rejected.
        """
        # Create a second listing belonging to seller1
        listing_new = MarketplaceListing.objects.create(
            product=self.product2,
            seller=self.seller1,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('300.00'),
            quantity=2,
            is_active=True,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('20.00'),
            width_cm=Decimal('20.00'),
            length_cm=Decimal('20.00'),
            shipping_method='both',
        )
        # Add listing_new to the cart AFTER the quote was created (simulating the risk scenario)
        CartItem.objects.create(cart=self.cart, listing=listing_new, quantity=1)

        # Re-create quote1 with melhor_envio_listing_ids containing ONLY listing1 (old quote)
        self.quote1.delete()
        ShippingQuote.objects.create(
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
                    {
                        'id': 1,
                        'name': 'PAC',
                        'price': '45.90',
                        'custom_price': '45.90',
                        'delivery_time': 5,
                        'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                    },
                ],
                'melhor_envio_listing_ids': [self.listing1.id],  # listing_new NOT included
            },
            expires_at=timezone.now() + timedelta(hours=24),
        )

        # Buyer sends both listing1 and listing_new as melhor_envio with service_id=1
        data = {
            'shipping_address_id': self.address.id,
            'items_delivery': [
                {'listing_id': self.listing1.id, 'delivery_method': 'melhor_envio', 'service_id': 1},
                {'listing_id': listing_new.id, 'delivery_method': 'melhor_envio', 'service_id': 1},
                {'listing_id': self.listing2.id, 'delivery_method': 'in_person'},
            ],
            'payment_method': 'pix',
        }

        serializer = OrderCreateSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('items_delivery', serializer.errors)
        error_text = str(serializer.errors['items_delivery'])
        self.assertIn('Recalcule o frete', error_text)

    def test_cart_change_invalidates_shipping_quote(self):
        """
        Adding a CartItem for a seller must delete that seller's ShippingQuote.

        This test verifies the invalidate_shipping_quotes_on_cart_change signal works
        correctly: when a cart item is saved (post_save), the quote is deleted.
        """
        # At this point self.quote1 and self.quote2 exist from setUp.
        # Verify they're in the DB.
        self.assertTrue(
            ShippingQuote.objects.filter(user=self.buyer, seller=self.seller1).exists()
        )

        # Create a new listing for seller1 and add it to the cart → triggers post_save signal
        listing_extra = MarketplaceListing.objects.create(
            product=self.product2,
            seller=self.seller1,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('100.00'),
            quantity=1,
            is_active=True,
            weight_kg=Decimal('2.00'),
            height_cm=Decimal('10.00'),
            width_cm=Decimal('10.00'),
            length_cm=Decimal('10.00'),
            shipping_method='both',
        )
        CartItem.objects.create(cart=self.cart, listing=listing_extra, quantity=1)

        # seller1's quote must have been deleted by the signal
        self.assertFalse(
            ShippingQuote.objects.filter(user=self.buyer, seller=self.seller1).exists(),
            "ShippingQuote for seller1 should have been invalidated after adding a cart item."
        )

        # seller2's quote must NOT have been affected
        self.assertTrue(
            ShippingQuote.objects.filter(user=self.buyer, seller=self.seller2).exists(),
            "ShippingQuote for seller2 should not be affected by a cart change for seller1."
        )


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
        """Test that shipping cost is calculated from server-side quote, not client input.

        quotes_data is stored as a flat list by MelhorEnvioService (one entry per service).
        Each entry has 'custom_price' (string) set by the aggregation logic, with 'price' as
        fallback. The service_id lookup compares integer-to-integer.
        """
        # Create shipping quote for seller1 — flat list format (real production format)
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
            quotes_data=[
                {
                    'id': 1,
                    'name': 'PAC',
                    'price': '45.90',
                    'custom_price': '45.90',
                    'delivery_time': 5,
                    'custom_delivery_time': 5,
                    'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                },
                {
                    'id': 2,
                    'name': 'SEDEX',
                    'price': '75.50',
                    'custom_price': '75.50',
                    'delivery_time': 2,
                    'custom_delivery_time': 2,
                    'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                },
            ],
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
        """Test that mixed order (shipping + in-person) calculates total correctly.

        Uses flat-list quotes_data format matching real MelhorEnvioService output.
        """
        # Create quote for seller1 only — flat list format
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
            quotes_data=[
                {
                    'id': 1,
                    'name': 'PAC',
                    'price': '45.90',
                    'custom_price': '45.90',
                    'delivery_time': 5,
                    'custom_delivery_time': 5,
                    'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                },
            ],
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

    def test_shipping_uses_custom_price_over_price(self):
        """Test that custom_price (string) takes precedence over price when both present.

        MelhorEnvioService stores custom_price as a string (e.g. '45.90').
        _validate_and_calculate_shipping must handle both string and numeric values
        when constructing the Decimal shipping cost.
        """
        # custom_price differs from price to verify which one is used
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
            quotes_data=[
                {
                    'id': 1,
                    'name': 'PAC',
                    'price': '40.00',        # raw price
                    'custom_price': '45.90', # custom_price should win
                    'delivery_time': 5,
                    'custom_delivery_time': 5,
                    'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                },
            ],
            expires_at=timezone.now() + timedelta(hours=24)
        )

        shipping_services_input = {
            self.seller1.id: {
                'delivery_method': 'shipping',
                'service_id': 1,
            }
        }

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

            shipping_data = OrderCreationService._validate_and_calculate_shipping(
                self.buyer,
                mock_validate.return_value,
                shipping_services_input
            )

        # custom_price ('45.90') must be used, not price ('40.00')
        self.assertEqual(shipping_data['total_shipping'], Decimal('45.90'))
        self.assertEqual(shipping_data['shipping_by_seller'][self.seller1.id], Decimal('45.90'))

    def test_shipping_falls_back_to_price_when_no_custom_price(self):
        """Test that price is used as fallback when custom_price is absent."""
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
            quotes_data=[
                {
                    'id': 1,
                    'name': 'PAC',
                    'price': '38.00',   # no custom_price present
                    'delivery_time': 6,
                    'company': {'id': 1, 'name': 'Correios', 'picture': ''},
                },
            ],
            expires_at=timezone.now() + timedelta(hours=24)
        )

        shipping_services_input = {
            self.seller1.id: {
                'delivery_method': 'shipping',
                'service_id': 1,
            }
        }

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

            shipping_data = OrderCreationService._validate_and_calculate_shipping(
                self.buyer,
                mock_validate.return_value,
                shipping_services_input
            )

        self.assertEqual(shipping_data['total_shipping'], Decimal('38.00'))

    def test_legacy_dict_wrapped_quotes_data_still_supported(self):
        """Regression test: quotes_data stored as {'services': [...]} (old format) must still work.

        Before the per-volume refactor, quotes_data was stored as a dict with a 'services' key.
        The _validate_and_calculate_shipping guard handles this for existing DB records.
        """
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
                    {'id': 1, 'name': 'PAC', 'price': 22.00, 'company': 'Correios'},
                ]
            },
            expires_at=timezone.now() + timedelta(hours=24)
        )

        shipping_services_input = {
            self.seller1.id: {
                'delivery_method': 'shipping',
                'service_id': 1,
            }
        }

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

            shipping_data = OrderCreationService._validate_and_calculate_shipping(
                self.buyer,
                mock_validate.return_value,
                shipping_services_input
            )

        self.assertEqual(shipping_data['total_shipping'], Decimal('22.00'))


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
