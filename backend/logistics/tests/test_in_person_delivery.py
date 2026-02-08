"""
Testes para o serviço de entrega presencial.
"""

from django.test import TestCase
from django.utils import timezone
from datetime import datetime, timedelta, time
from decimal import Decimal

from authentication.models import CustomUser
from orders.models import Order, OrderItem
from products.models import Products, MarketplaceListing, Brand, Condition, Category, Series
from logistics.models import (
    InPersonDelivery,
    OrderDelivery,
    DeliveryMethod
)
from logistics.services.in_person_delivery_service import InPersonDeliveryService


class InPersonDeliveryServiceTest(TestCase):
    """Testes para InPersonDeliveryService"""

    def setUp(self):
        """Setup inicial para os testes"""

        # Criar usuários
        self.buyer = CustomUser.objects.create_user(
            email='buyer@test.com',
            password='test123',
            full_name='Buyer Test'
        )

        self.seller = CustomUser.objects.create_user(
            email='seller@test.com',
            password='test123',
            full_name='Seller Test'
        )

        # Criar categoria e série
        self.category = Category.objects.create(
            name='Test Category',
            slug='test-category'
        )

        self.series = Series.objects.create(
            name='Test Series',
            slug='test-series'
        )

        # Criar produto
        self.product = Products.objects.create(
            name='Test Product',
            slug='test-product',
            category=self.category,
            series=self.series
        )

        # Criar marca e condição
        self.brand = Brand.objects.create(
            name='Test Brand',
            slug='test-brand',
            logo='http://example.com/logo.png'
        )

        self.condition = Condition.objects.create(
            name='Novo',
            slug='novo'
        )

        # Criar listing
        self.listing = MarketplaceListing.objects.create(
            product=self.product,
            seller=self.seller,
            price=Decimal('100.00'),
            brand=self.brand,
            condition=self.condition,
            quantity=1,
            description='Test listing',
            weight_kg=Decimal('1.5'),
            height_cm=Decimal('10'),
            width_cm=Decimal('10'),
            length_cm=Decimal('10')
        )

        # Criar pedido
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('100.00'),
            shipping_address={
                'street': 'Rua Test',
                'number': '123',
                'city': 'São Paulo',
                'state': 'SP',
                'zipcode': '01234-567'
            }
        )

        # Criar item do pedido
        OrderItem.objects.create(
            order=self.order,
            listing=self.listing,
            seller=self.seller,
            product_name=self.product.name,
            brand_name=self.brand.name,
            condition_name=self.condition.name,
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            weight_kg=Decimal('1.5'),
            height_cm=Decimal('10'),
            width_cm=Decimal('10'),
            length_cm=Decimal('10')
        )

    def test_create_in_person_delivery(self):
        """Testa criação de entrega presencial"""

        scheduled_date = (timezone.now() + timedelta(days=3)).date()
        scheduled_time = time(14, 0)

        in_person_delivery = InPersonDeliveryService.create_in_person_delivery(
            order=self.order,
            seller=self.seller,
            buyer=self.buyer,
            meeting_location_name='Shopping Test',
            meeting_address={
                'street': 'Av Test',
                'number': '456',
                'city': 'São Paulo',
                'state': 'SP'
            },
            seller_contact_phone='11999999999',
            buyer_contact_phone='11888888888',
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            meeting_notes='Próximo à entrada principal'
        )

        # Verificações
        self.assertIsNotNone(in_person_delivery)
        self.assertEqual(in_person_delivery.seller, self.seller)
        self.assertEqual(in_person_delivery.buyer, self.buyer)
        self.assertEqual(in_person_delivery.meeting_location_name, 'Shopping Test')
        self.assertEqual(in_person_delivery.meeting_status, 'scheduled')
        self.assertFalse(in_person_delivery.seller_confirmed)
        self.assertFalse(in_person_delivery.buyer_confirmed)

    def test_create_order_delivery_in_person(self):
        """Testa criação de OrderDelivery com entrega presencial"""

        scheduled_date = (timezone.now() + timedelta(days=3)).date()
        scheduled_time = time(14, 0)

        order_delivery = InPersonDeliveryService.create_order_delivery_in_person(
            order=self.order,
            seller=self.seller,
            meeting_location_name='Shopping Test',
            meeting_address={
                'street': 'Av Test',
                'number': '456',
                'city': 'São Paulo',
                'state': 'SP'
            },
            seller_contact_phone='11999999999',
            buyer_contact_phone='11888888888',
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time
        )

        # Verificações
        self.assertIsNotNone(order_delivery)
        self.assertEqual(order_delivery.order, self.order)
        self.assertEqual(order_delivery.seller, self.seller)
        self.assertEqual(order_delivery.delivery_method, DeliveryMethod.IN_PERSON)
        self.assertEqual(order_delivery.delivery_cost, 0)
        self.assertIsNotNone(order_delivery.in_person_delivery)

    def test_confirm_meeting_by_seller(self):
        """Testa confirmação do encontro pelo vendedor"""

        scheduled_date = (timezone.now() + timedelta(days=3)).date()
        scheduled_time = time(14, 0)

        in_person_delivery = InPersonDeliveryService.create_in_person_delivery(
            order=self.order,
            seller=self.seller,
            buyer=self.buyer,
            meeting_location_name='Shopping Test',
            meeting_address={'city': 'São Paulo'},
            seller_contact_phone='11999999999',
            buyer_contact_phone='11888888888',
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time
        )

        # Vendedor confirma
        updated = InPersonDeliveryService.confirm_meeting(
            in_person_delivery=in_person_delivery,
            user=self.seller
        )

        self.assertTrue(updated.seller_confirmed)
        self.assertIsNotNone(updated.seller_confirmed_at)
        self.assertFalse(updated.buyer_confirmed)

    def test_confirm_meeting_by_both_parties(self):
        """Testa confirmação do encontro por ambas as partes"""

        scheduled_date = (timezone.now() + timedelta(days=3)).date()
        scheduled_time = time(14, 0)

        order_delivery = InPersonDeliveryService.create_order_delivery_in_person(
            order=self.order,
            seller=self.seller,
            meeting_location_name='Shopping Test',
            meeting_address={'city': 'São Paulo'},
            seller_contact_phone='11999999999',
            buyer_contact_phone='11888888888',
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time
        )

        in_person_delivery = order_delivery.in_person_delivery

        # Vendedor confirma
        InPersonDeliveryService.confirm_meeting(
            in_person_delivery=in_person_delivery,
            user=self.seller
        )

        # Comprador confirma
        updated = InPersonDeliveryService.confirm_meeting(
            in_person_delivery=in_person_delivery,
            user=self.buyer
        )

        # Verificações
        self.assertTrue(updated.seller_confirmed)
        self.assertTrue(updated.buyer_confirmed)
        self.assertTrue(updated.is_fully_confirmed())
        self.assertEqual(updated.meeting_status, 'confirmed')

        # Verificar OrderDelivery
        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'confirmed')

    def test_complete_delivery(self):
        """Testa conclusão da entrega presencial"""

        scheduled_date = (timezone.now() + timedelta(days=3)).date()
        scheduled_time = time(14, 0)

        order_delivery = InPersonDeliveryService.create_order_delivery_in_person(
            order=self.order,
            seller=self.seller,
            meeting_location_name='Shopping Test',
            meeting_address={'city': 'São Paulo'},
            seller_contact_phone='11999999999',
            buyer_contact_phone='11888888888',
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time
        )

        in_person_delivery = order_delivery.in_person_delivery

        # Ambos confirmam
        InPersonDeliveryService.confirm_meeting(in_person_delivery, self.seller)
        InPersonDeliveryService.confirm_meeting(in_person_delivery, self.buyer)

        # Concluir entrega
        completed = InPersonDeliveryService.complete_delivery(
            in_person_delivery=in_person_delivery,
            user=self.seller,
            completion_notes='Produto entregue com sucesso'
        )

        # Verificações
        self.assertEqual(completed.meeting_status, 'completed')
        self.assertEqual(completed.completed_by, self.seller)
        self.assertIsNotNone(completed.completed_at)

        # Verificar OrderDelivery
        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'delivered')

    def test_cancel_delivery(self):
        """Testa cancelamento da entrega presencial"""

        scheduled_date = (timezone.now() + timedelta(days=3)).date()
        scheduled_time = time(14, 0)

        order_delivery = InPersonDeliveryService.create_order_delivery_in_person(
            order=self.order,
            seller=self.seller,
            meeting_location_name='Shopping Test',
            meeting_address={'city': 'São Paulo'},
            seller_contact_phone='11999999999',
            buyer_contact_phone='11888888888',
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time
        )

        in_person_delivery = order_delivery.in_person_delivery

        # Cancelar
        cancelled = InPersonDeliveryService.cancel_delivery(
            in_person_delivery=in_person_delivery,
            user=self.buyer,
            cancellation_reason='Mudança de planos'
        )

        # Verificações
        self.assertEqual(cancelled.meeting_status, 'cancelled')
        self.assertIn('Mudança de planos', cancelled.completion_notes)

        # Verificar OrderDelivery
        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'cancelled')

    def test_update_meeting_details(self):
        """Testa atualização dos detalhes do encontro"""

        scheduled_date = (timezone.now() + timedelta(days=3)).date()
        scheduled_time = time(14, 0)

        in_person_delivery = InPersonDeliveryService.create_in_person_delivery(
            order=self.order,
            seller=self.seller,
            buyer=self.buyer,
            meeting_location_name='Shopping Test',
            meeting_address={'city': 'São Paulo'},
            seller_contact_phone='11999999999',
            buyer_contact_phone='11888888888',
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time
        )

        # Atualizar local
        new_date = (timezone.now() + timedelta(days=5)).date()
        new_time = time(16, 0)

        updated = InPersonDeliveryService.update_meeting_details(
            in_person_delivery=in_person_delivery,
            user=self.seller,
            meeting_location_name='Novo Shopping',
            scheduled_date=new_date,
            scheduled_time=new_time
        )

        # Verificações
        self.assertEqual(updated.meeting_location_name, 'Novo Shopping')
        self.assertEqual(updated.scheduled_date, new_date)
        self.assertEqual(updated.scheduled_time, new_time)

    def test_cannot_create_duplicate_delivery(self):
        """Testa que não é possível criar entrega duplicada"""

        scheduled_date = (timezone.now() + timedelta(days=3)).date()
        scheduled_time = time(14, 0)

        # Criar primeira entrega
        InPersonDeliveryService.create_in_person_delivery(
            order=self.order,
            seller=self.seller,
            buyer=self.buyer,
            meeting_location_name='Shopping Test',
            meeting_address={'city': 'São Paulo'},
            seller_contact_phone='11999999999',
            buyer_contact_phone='11888888888',
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time
        )

        # Tentar criar segunda entrega
        with self.assertRaises(ValueError):
            InPersonDeliveryService.create_in_person_delivery(
                order=self.order,
                seller=self.seller,
                buyer=self.buyer,
                meeting_location_name='Outro Shopping',
                meeting_address={'city': 'São Paulo'},
                seller_contact_phone='11999999999',
                buyer_contact_phone='11888888888',
                scheduled_date=scheduled_date,
                scheduled_time=scheduled_time
            )
