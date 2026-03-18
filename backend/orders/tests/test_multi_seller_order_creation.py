"""
Test Multi-Seller Order Creation

Validates that when a cart contains items from multiple sellers,
one Order is created per seller.

Test Coverage:
- Single-seller cart: returns list with one Order
- Multi-seller cart: returns one Order per seller
- Each Order has only the items belonging to its seller
- Totals are correct per seller (subtotal, shipping, total)
- Order.seller FK is set correctly
- cart is cleared after all orders are created
- OrderStatusHistory is created for each order
"""

from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import timedelta

from orders.models import Order, Cart, CartItem, OrderItem, OrderStatusHistory
from orders.services.order_creation_service import OrderCreationService, OrderCreationError
from products.models import MarketplaceListing, Products, Brand, Condition, Category, Series
from authentication.models import CustomUser
from logistics.models import Address, ShippingQuote


def _make_user(email, **kwargs):
    return CustomUser.objects.create_user(
        email=email,
        password='testpass123',
        **kwargs
    )


def _make_address(user):
    return Address.objects.create(
        user=user,
        recipient_name=user.get_full_name() or user.email,
        recipient_phone='11999999999',
        zipcode='01310-100',
        street='Av Paulista',
        number='1000',
        neighborhood='Bela Vista',
        city='São Paulo',
        state='SP',
        is_active=True,
        is_shipping_address=True,
    )


def _make_catalog():
    category = Category.objects.create(name='Equipamentos', slug='equipamentos')
    series = Series.objects.create(name='Pro Series', slug='pro-series')
    brand = Brand.objects.create(name='TechGym', slug='techgym')
    condition = Condition.objects.create(name='Novo', slug='novo')
    return category, series, brand, condition


def _make_product(name, slug, code, category, series):
    return Products.objects.create(
        name=name,
        slug=slug,
        code=code,
        category=category,
        series=series,
        description=name,
    )


def _make_listing(product, seller, brand, condition, price='100.00', qty=5):
    return MarketplaceListing.objects.create(
        product=product,
        seller=seller,
        brand=brand,
        condition=condition,
        price=Decimal(price),
        quantity=qty,
        is_active=True,
        title=product.name,
        description=product.description,
        weight_kg=Decimal('5.00'),
        height_cm=Decimal('30.00'),
        width_cm=Decimal('30.00'),
        length_cm=Decimal('30.00'),
    )


def _make_shipping_quote(user, seller, service_id=1, cost='20.00'):
    """Create a valid ShippingQuote for the given user/seller pair."""
    addr = {'street': 'Av Paulista', 'city': 'São Paulo', 'state': 'SP'}
    return ShippingQuote.objects.create(
        user=user,
        seller=seller,
        origin_zipcode='01310100',
        origin_address=addr,
        destination_zipcode='04001000',
        destination_address=addr,
        weight=Decimal('5.00'),
        height=Decimal('30.00'),
        width=Decimal('30.00'),
        length=Decimal('30.00'),
        declared_value=Decimal('100.00'),
        quotes_data={
            'services': [
                {
                    'id': service_id,
                    'name': 'PAC',
                    'price': cost,
                    'custom_price': cost,
                    'company': {'name': 'Correios'},
                    'delivery_time': 5,
                }
            ]
        },
        expires_at=timezone.now() + timedelta(hours=1),
    )


class MultiSellerOrderCreationTest(TestCase):
    """Tests for create_order_from_cart with multiple sellers."""

    def setUp(self):
        self.buyer = _make_user('buyer@test.com', first_name='Buyer', last_name='Test')
        self.seller1 = _make_user('seller1@test.com', first_name='Seller', last_name='One')
        self.seller2 = _make_user('seller2@test.com', first_name='Seller', last_name='Two')

        self.buyer_address = _make_address(self.buyer)
        _make_address(self.seller1)
        _make_address(self.seller2)

        self.category, self.series, self.brand, self.condition = _make_catalog()

        self.product1 = _make_product(
            'Esteira Elite', 'esteira-elite', 'EST-001',
            self.category, self.series
        )
        self.product2 = _make_product(
            'Bike Ergométrica', 'bike-ergometrica', 'BIKE-001',
            self.category, self.series
        )
        self.product3 = _make_product(
            'Haltere 20kg', 'haltere-20kg', 'HAL-001',
            self.category, self.series
        )

        # seller1 has listing1 (R$100) and listing3 (R$50)
        self.listing1 = _make_listing(
            self.product1, self.seller1, self.brand, self.condition,
            price='100.00'
        )
        self.listing3 = _make_listing(
            self.product3, self.seller1, self.brand, self.condition,
            price='50.00'
        )
        # seller2 has listing2 (R$200)
        self.listing2 = _make_listing(
            self.product2, self.seller2, self.brand, self.condition,
            price='200.00'
        )

        # Cart with items from both sellers
        self.cart = Cart.objects.create(user=self.buyer)

    def _add_item(self, listing, quantity=1):
        """Helper to add a cart item, suppressing the ShippingQuote invalidation signal."""
        return CartItem.objects.create(cart=self.cart, listing=listing, quantity=quantity)

    def _build_in_person_shipping_services(self, seller_ids):
        """Build a shipping_services_input dict for all-in-person delivery."""
        return {
            str(sid): {
                'delivery_method': 'in_person',
                'meeting_location_name': 'Academia Central',
                'meeting_address': {},
                'seller_contact_phone': '',
                'buyer_contact_phone': '',
                'scheduled_date': None,
                'scheduled_time': None,
                'meeting_notes': '',
            }
            for sid in seller_ids
        }

    # -------------------------------------------------------------------------
    # Helper: patch all external side-effects so tests focus on order creation
    # -------------------------------------------------------------------------
    def _patch_externals(self):
        """Return a list of patches to apply in tests that don't touch ME/notifications."""
        return [
            patch(
                'orders.services.order_creation_service.OrderCreationService'
                '._add_sellers_to_me_cart_preorder',
                return_value={}
            ),
            patch(
                'orders.services.order_creation_service.OrderCreationService'
                '._check_sellers_me_balance',
            ),
            patch('notifications.services.NotificationService.notify'),
        ]

    # =========================================================================
    # Test: Single seller cart creates exactly one Order
    # =========================================================================
    def test_single_seller_creates_one_order(self):
        """A cart with one seller must produce exactly one Order."""
        self._add_item(self.listing1, quantity=1)

        shipping_services = self._build_in_person_shipping_services([self.seller1.id])

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        self.assertEqual(len(orders), 1)
        order = orders[0]
        self.assertEqual(order.buyer, self.buyer)
        self.assertEqual(order.seller, self.seller1)
        self.assertEqual(order.items.count(), 1)

    # =========================================================================
    # Test: Two-seller cart creates two Orders
    # =========================================================================
    def test_two_sellers_create_two_orders(self):
        """A cart with items from two sellers must produce two Orders."""
        self._add_item(self.listing1, quantity=1)  # seller1, R$100
        self._add_item(self.listing2, quantity=1)  # seller2, R$200

        shipping_services = self._build_in_person_shipping_services(
            [self.seller1.id, self.seller2.id]
        )

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        self.assertEqual(len(orders), 2)

        # Each order must have a distinct seller
        seller_ids = {o.seller_id for o in orders}
        self.assertEqual(seller_ids, {self.seller1.id, self.seller2.id})

    # =========================================================================
    # Test: Items are isolated per order
    # =========================================================================
    def test_order_items_are_isolated_per_seller(self):
        """Each Order must contain only items from its own seller."""
        self._add_item(self.listing1, quantity=2)  # seller1
        self._add_item(self.listing2, quantity=1)  # seller2

        shipping_services = self._build_in_person_shipping_services(
            [self.seller1.id, self.seller2.id]
        )

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        order_by_seller = {o.seller_id: o for o in orders}

        order1 = order_by_seller[self.seller1.id]
        order2 = order_by_seller[self.seller2.id]

        # seller1's order has only listing1
        self.assertEqual(order1.items.count(), 1)
        self.assertEqual(order1.items.first().listing, self.listing1)
        self.assertEqual(order1.items.first().quantity, 2)

        # seller2's order has only listing2
        self.assertEqual(order2.items.count(), 1)
        self.assertEqual(order2.items.first().listing, self.listing2)
        self.assertEqual(order2.items.first().quantity, 1)

    # =========================================================================
    # Test: Totals are correct per order
    # =========================================================================
    def test_order_totals_are_correct_per_seller(self):
        """Subtotal and total must reflect only this seller's items."""
        self._add_item(self.listing1, quantity=2)  # seller1: 2 * R$100 = R$200
        self._add_item(self.listing3, quantity=1)  # seller1: 1 * R$50  = R$50
        self._add_item(self.listing2, quantity=3)  # seller2: 3 * R$200 = R$600

        shipping_services = self._build_in_person_shipping_services(
            [self.seller1.id, self.seller2.id]
        )

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        order_by_seller = {o.seller_id: o for o in orders}

        order1 = order_by_seller[self.seller1.id]
        order2 = order_by_seller[self.seller2.id]

        # seller1: subtotal = R$200 + R$50 = R$250, shipping=0, total=R$250
        self.assertEqual(order1.subtotal, Decimal('250.00'))
        self.assertEqual(order1.shipping_cost, Decimal('0.00'))
        self.assertEqual(order1.total, Decimal('250.00'))

        # seller2: subtotal = R$600, shipping=0, total=R$600
        self.assertEqual(order2.subtotal, Decimal('600.00'))
        self.assertEqual(order2.shipping_cost, Decimal('0.00'))
        self.assertEqual(order2.total, Decimal('600.00'))

    # =========================================================================
    # Test: Order.seller FK is populated
    # =========================================================================
    def test_order_seller_fk_is_set(self):
        """Order.seller must point to the correct seller."""
        self._add_item(self.listing1, quantity=1)
        self._add_item(self.listing2, quantity=1)

        shipping_services = self._build_in_person_shipping_services(
            [self.seller1.id, self.seller2.id]
        )

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        for order in orders:
            # Order.seller must match the seller of all its items
            item_seller_ids = set(order.items.values_list('seller_id', flat=True))
            self.assertEqual(len(item_seller_ids), 1)
            self.assertEqual(order.seller_id, list(item_seller_ids)[0])

    # =========================================================================
    # Test: Cart is cleared after order creation
    # =========================================================================
    def test_cart_is_cleared_after_order_creation(self):
        """Cart items must be deleted after all orders are successfully created."""
        self._add_item(self.listing1, quantity=1)
        self._add_item(self.listing2, quantity=1)

        shipping_services = self._build_in_person_shipping_services(
            [self.seller1.id, self.seller2.id]
        )

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        self.cart.refresh_from_db()
        self.assertEqual(self.cart.items.count(), 0)

    # =========================================================================
    # Test: OrderStatusHistory is created per order
    # =========================================================================
    def test_status_history_created_for_each_order(self):
        """Each Order must have an initial OrderStatusHistory entry."""
        self._add_item(self.listing1, quantity=1)
        self._add_item(self.listing2, quantity=1)

        shipping_services = self._build_in_person_shipping_services(
            [self.seller1.id, self.seller2.id]
        )

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        for order in orders:
            history = OrderStatusHistory.objects.filter(order=order)
            self.assertEqual(history.count(), 1)
            entry = history.first()
            self.assertEqual(entry.new_status, 'pending_payment')

    # =========================================================================
    # Test: All orders start as pending_payment
    # =========================================================================
    def test_all_orders_start_as_pending_payment(self):
        """All created Orders must start in pending_payment state."""
        self._add_item(self.listing1, quantity=1)
        self._add_item(self.listing2, quantity=1)

        shipping_services = self._build_in_person_shipping_services(
            [self.seller1.id, self.seller2.id]
        )

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        for order in orders:
            self.assertEqual(order.status, 'pending_payment')

    # =========================================================================
    # Test: Empty cart raises error
    # =========================================================================
    def test_empty_cart_raises_error(self):
        """Creating an order from an empty cart must raise OrderCreationError."""
        shipping_services = {}

        with self.assertRaises(OrderCreationError) as ctx:
            OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        self.assertIn('empty', str(ctx.exception).lower())

    # =========================================================================
    # Test: Order with shipping (ME) uses correct cost per seller
    # =========================================================================
    def test_order_with_shipping_cost_per_seller(self):
        """Each Order's shipping_cost must reflect that seller's shipping quote."""
        self._add_item(self.listing1, quantity=1)  # seller1
        self._add_item(self.listing2, quantity=1)  # seller2

        # Quote for seller1: R$20 shipping
        quote1 = _make_shipping_quote(
            self.buyer, self.seller1, service_id=1, cost='20.00'
        )
        # Quote for seller2: R$35 shipping
        quote2 = _make_shipping_quote(
            self.buyer, self.seller2, service_id=2, cost='35.00'
        )

        shipping_services = {
            str(self.seller1.id): {
                'delivery_method': 'shipping',
                'per_listing': {
                    str(self.listing1.id): {'service_id': 1}
                },
            },
            str(self.seller2.id): {
                'delivery_method': 'shipping',
                'per_listing': {
                    str(self.listing2.id): {'service_id': 2}
                },
            },
        }

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._check_sellers_me_balance',
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        order_by_seller = {o.seller_id: o for o in orders}

        order1 = order_by_seller[self.seller1.id]
        order2 = order_by_seller[self.seller2.id]

        # seller1: subtotal=R$100, shipping=R$20, total=R$120
        self.assertEqual(order1.subtotal, Decimal('100.00'))
        self.assertEqual(order1.shipping_cost, Decimal('20.00'))
        self.assertEqual(order1.total, Decimal('120.00'))

        # seller2: subtotal=R$200, shipping=R$35, total=R$235
        self.assertEqual(order2.subtotal, Decimal('200.00'))
        self.assertEqual(order2.shipping_cost, Decimal('35.00'))
        self.assertEqual(order2.total, Decimal('235.00'))

    # =========================================================================
    # Test: shipping_services on each Order is scoped to its seller
    # =========================================================================
    def test_shipping_services_scoped_to_seller(self):
        """Order.shipping_services must contain only the seller's own shipping config."""
        self._add_item(self.listing1, quantity=1)
        self._add_item(self.listing2, quantity=1)

        shipping_services = self._build_in_person_shipping_services(
            [self.seller1.id, self.seller2.id]
        )

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        order_by_seller = {o.seller_id: o for o in orders}

        order1 = order_by_seller[self.seller1.id]
        order2 = order_by_seller[self.seller2.id]

        # Order1 shipping_services should only have seller1's key
        self.assertIn(str(self.seller1.id), order1.shipping_services)
        self.assertNotIn(str(self.seller2.id), order1.shipping_services)

        # Order2 shipping_services should only have seller2's key
        self.assertIn(str(self.seller2.id), order2.shipping_services)
        self.assertNotIn(str(self.seller1.id), order2.shipping_services)

    # =========================================================================
    # Test: seller1 with multiple items produces single Order
    # =========================================================================
    def test_single_seller_multiple_items_produces_one_order(self):
        """One seller with two listings must produce a single Order with both items."""
        self._add_item(self.listing1, quantity=1)
        self._add_item(self.listing3, quantity=2)

        shipping_services = self._build_in_person_shipping_services([self.seller1.id])

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping_services,
                payment_method='pix',
            )

        self.assertEqual(len(orders), 1)
        order = orders[0]
        self.assertEqual(order.seller, self.seller1)
        self.assertEqual(order.items.count(), 2)

        # Subtotal = R$100 + 2*R$50 = R$200
        self.assertEqual(order.subtotal, Decimal('200.00'))

    # =========================================================================
    # Test: atomicity — if one seller's order fails, no orders are created
    # =========================================================================
    def test_atomicity_rollback_on_failure(self):
        """If order creation fails mid-way, no Orders should persist in the DB."""
        self._add_item(self.listing1, quantity=1)
        self._add_item(self.listing2, quantity=1)

        shipping_services = self._build_in_person_shipping_services(
            [self.seller1.id, self.seller2.id]
        )

        initial_order_count = Order.objects.count()

        # Patch _create_order_record to raise on the second call
        original_create = OrderCreationService._create_order_record
        call_count = [0]

        def failing_create(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Simulated DB failure on second seller")
            return original_create(*args, **kwargs)

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._create_order_record',
            side_effect=failing_create
        ), patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            with self.assertRaises(Exception):
                OrderCreationService.create_order_from_cart(
                    user=self.buyer,
                    cart=self.cart,
                    shipping_address=self.buyer_address,
                    shipping_services_input=shipping_services,
                    payment_method='pix',
                )

        # No orders should have been persisted (atomic rollback)
        self.assertEqual(Order.objects.count(), initial_order_count)


class MultiSellerOrderNumberUniquenessTest(TestCase):
    """Ensures each Order created in a multi-seller cart gets a unique order_number."""

    def setUp(self):
        self.buyer = _make_user('buyer@test.com')
        self.seller1 = _make_user('s1@test.com')
        self.seller2 = _make_user('s2@test.com')
        self.buyer_address = _make_address(self.buyer)
        _make_address(self.seller1)
        _make_address(self.seller2)

        category, series, brand, condition = _make_catalog()
        p1 = _make_product('P1', 'p1', 'P1', category, series)
        p2 = _make_product('P2', 'p2', 'P2', category, series)
        self.l1 = _make_listing(p1, self.seller1, brand, condition)
        self.l2 = _make_listing(p2, self.seller2, brand, condition)
        self.cart = Cart.objects.create(user=self.buyer)

    def test_unique_order_numbers(self):
        CartItem.objects.create(cart=self.cart, listing=self.l1, quantity=1)
        CartItem.objects.create(cart=self.cart, listing=self.l2, quantity=1)

        shipping = {
            str(self.seller1.id): {
                'delivery_method': 'in_person',
                'meeting_location_name': '',
                'meeting_address': {},
                'seller_contact_phone': '',
                'buyer_contact_phone': '',
                'scheduled_date': None,
                'scheduled_time': None,
                'meeting_notes': '',
            },
            str(self.seller2.id): {
                'delivery_method': 'in_person',
                'meeting_location_name': '',
                'meeting_address': {},
                'seller_contact_phone': '',
                'buyer_contact_phone': '',
                'scheduled_date': None,
                'scheduled_time': None,
                'meeting_notes': '',
            },
        }

        with patch(
            'orders.services.order_creation_service.OrderCreationService'
            '._add_sellers_to_me_cart_preorder', return_value={}
        ), patch('notifications.services.NotificationService.notify'):
            orders = OrderCreationService.create_order_from_cart(
                user=self.buyer,
                cart=self.cart,
                shipping_address=self.buyer_address,
                shipping_services_input=shipping,
                payment_method='pix',
            )

        order_numbers = [o.order_number for o in orders]
        self.assertEqual(len(order_numbers), len(set(order_numbers)),
                         "Order numbers must be unique across sellers")
