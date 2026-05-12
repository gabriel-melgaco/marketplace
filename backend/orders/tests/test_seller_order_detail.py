from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import CustomUser
from orders.models import Order, OrderItem
from products.models import Brand, Category, Condition, MarketplaceListing, Products, Series


class SellerOrderDetailAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.buyer = CustomUser.objects.create_user(
            email='buyer-detail@test.com',
            password='testpass123',
            first_name='Buyer',
            last_name='Detail',
        )
        self.seller = CustomUser.objects.create_user(
            email='seller-detail@test.com',
            password='testpass123',
            first_name='Seller',
            last_name='Detail',
        )

        category = Category.objects.create(name='Equipamentos', slug='equipamentos-detail')
        series = Series.objects.create(name='Pro Series', slug='pro-series-detail')
        brand = Brand.objects.create(name='TechGym', slug='techgym-detail')
        condition = Condition.objects.create(name='Novo', slug='novo-detail')
        product = Products.objects.create(
            name='Esteira Detail',
            slug='esteira-detail',
            code='EST-DETAIL',
            category=category,
            series=series,
            description='Esteira para teste de detalhe',
        )
        self.listing = MarketplaceListing.objects.create(
            product=product,
            seller=self.seller,
            brand=brand,
            condition=condition,
            price=Decimal('1000.00'),
            quantity=1,
            is_active=True,
            title=product.name,
            description=product.description,
            weight_kg=Decimal('50.00'),
            height_cm=Decimal('120.00'),
            width_cm=Decimal('80.00'),
            length_cm=Decimal('150.00'),
        )

    def test_seller_order_detail_includes_delivery_method_flags(self):
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            status='pending_payment',
            subtotal=Decimal('1000.00'),
            shipping_cost=Decimal('45.90'),
            total=Decimal('1045.90'),
            shipping_address={'zipcode': '01310-100'},
            shipping_services={
                str(self.seller.id): {
                    'delivery_method': 'split',
                    'shipping': {
                        'per_listing': {
                            str(self.listing.id): {'service_id': 1, 'cost': 45.90},
                        },
                    },
                    'in_person': {
                        'meeting_location_name': 'Loja Seller',
                    },
                },
            },
            payment_method='pix',
        )
        OrderItem.objects.create(
            order=order,
            listing=self.listing,
            seller=self.seller,
            product_name='Esteira Detail',
            product_code='EST-DETAIL',
            brand_name='TechGym',
            condition_name='Novo',
            quantity=1,
            unit_price=Decimal('1000.00'),
            shipping_cost=Decimal('45.90'),
            weight_kg=Decimal('50.00'),
            height_cm=Decimal('120.00'),
            width_cm=Decimal('80.00'),
            length_cm=Decimal('150.00'),
            seller_address={},
        )

        self.client.force_authenticate(user=self.seller)
        response = self.client.get(f'/api/orders/sales/{order.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('has_in_person', response.data)
        self.assertIn('has_melhor_envio', response.data)
        self.assertTrue(response.data['has_in_person'])
        self.assertTrue(response.data['has_melhor_envio'])
