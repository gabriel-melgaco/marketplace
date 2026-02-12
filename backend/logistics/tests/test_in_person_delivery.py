"""
Testes abrangentes para o fluxo de entrega presencial (in-person delivery).

Cobre:
- Model: InPersonDelivery (is_fully_confirmed, is_fully_completed, can_be_completed, save auto-transitions)
- Service: InPersonDeliveryService (confirm_meeting, complete_delivery, update_meeting_details)
- Views/API: Endpoints de confirm, complete, deliveries/create
- Integracao: Fluxo completo end-to-end
"""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta, time
from decimal import Decimal

from rest_framework.test import APIClient

from authentication.models import CustomUser
from orders.models import Order, OrderItem
from products.models import Products, MarketplaceListing, Brand, Condition, Category, Series
from logistics.models import (
    InPersonDelivery,
    OrderDelivery,
    DeliveryMethod,
    DeliveryStatusLog,
)
from logistics.services.in_person_delivery_service import InPersonDeliveryService


class InPersonDeliveryTestMixin:
    """Mixin com setUp compartilhado entre as classes de teste."""

    def _create_base_data(self):
        """Cria dados base: usuarios, produto, listing, pedido e order item."""
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

        self.other_user = CustomUser.objects.create_user(
            email='other@test.com',
            password='test123',
            full_name='Other User'
        )

        self.category = Category.objects.create(
            name='Test Category',
            slug='test-category'
        )
        self.series = Series.objects.create(
            name='Test Series',
            slug='test-series'
        )
        self.product = Products.objects.create(
            name='Test Product',
            slug='test-product',
            category=self.category,
            series=self.series
        )
        self.brand = Brand.objects.create(
            name='Test Brand',
            slug='test-brand',
            logo='http://example.com/logo.png'
        )
        self.condition = Condition.objects.create(
            name='Novo',
            slug='novo'
        )
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

        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('100.00'),
            status='paid',
            shipping_address={
                'street': 'Rua Test',
                'number': '123',
                'city': 'Sao Paulo',
                'state': 'SP',
                'zipcode': '01234-567'
            }
        )

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

        # Dados padrao para criar entregas presenciais
        self.scheduled_date = (timezone.now() + timedelta(days=3)).date()
        self.scheduled_time = time(14, 0)
        self.meeting_defaults = {
            'meeting_location_name': 'Shopping Test',
            'meeting_address': {
                'street': 'Av Test',
                'number': '456',
                'city': 'Sao Paulo',
                'state': 'SP'
            },
            'seller_contact_phone': '11999999999',
            'buyer_contact_phone': '11888888888',
        }

    def _create_in_person_delivery(self, scheduled=True):
        """Helper para criar InPersonDelivery diretamente."""
        kwargs = {
            'order': self.order,
            'seller': self.seller,
            'buyer': self.buyer,
            **self.meeting_defaults,
        }
        if scheduled:
            kwargs['scheduled_date'] = self.scheduled_date
            kwargs['scheduled_time'] = self.scheduled_time
        return InPersonDeliveryService.create_in_person_delivery(**kwargs)

    def _create_order_delivery_in_person(self, scheduled=True):
        """Helper para criar OrderDelivery com InPersonDelivery associado."""
        kwargs = {
            'order': self.order,
            'seller': self.seller,
            **self.meeting_defaults,
        }
        if scheduled:
            kwargs['scheduled_date'] = self.scheduled_date
            kwargs['scheduled_time'] = self.scheduled_time
        return InPersonDeliveryService.create_order_delivery_in_person(**kwargs)


# ==============================================================================
# MODEL TESTS
# ==============================================================================

class InPersonDeliveryModelTest(InPersonDeliveryTestMixin, TestCase):
    """Testes unitarios para o modelo InPersonDelivery."""

    def setUp(self):
        self._create_base_data()

    # --- is_fully_confirmed ---

    def test_is_fully_confirmed_returns_false_when_no_confirmations(self):
        """is_fully_confirmed retorna False quando ninguem confirmou."""
        delivery = self._create_in_person_delivery()
        self.assertFalse(delivery.is_fully_confirmed())

    def test_is_fully_confirmed_returns_false_when_only_seller_confirmed(self):
        """is_fully_confirmed retorna False quando so o vendedor confirmou."""
        delivery = self._create_in_person_delivery()
        delivery.seller_confirmed = True
        delivery.save()
        self.assertFalse(delivery.is_fully_confirmed())

    def test_is_fully_confirmed_returns_false_when_only_buyer_confirmed(self):
        """is_fully_confirmed retorna False quando so o comprador confirmou."""
        delivery = self._create_in_person_delivery()
        delivery.buyer_confirmed = True
        delivery.save()
        self.assertFalse(delivery.is_fully_confirmed())

    def test_is_fully_confirmed_returns_true_when_both_confirmed(self):
        """is_fully_confirmed retorna True quando ambos confirmaram."""
        delivery = self._create_in_person_delivery()
        delivery.seller_confirmed = True
        delivery.buyer_confirmed = True
        delivery.save()
        self.assertTrue(delivery.is_fully_confirmed())

    # --- is_fully_completed ---

    def test_is_fully_completed_returns_false_when_no_completions(self):
        """is_fully_completed retorna False quando ninguem completou."""
        delivery = self._create_in_person_delivery()
        self.assertFalse(delivery.is_fully_completed())

    def test_is_fully_completed_returns_false_when_only_seller_completed(self):
        """is_fully_completed retorna False quando so o vendedor completou."""
        delivery = self._create_in_person_delivery()
        delivery.seller_completed = True
        delivery.save()
        self.assertFalse(delivery.is_fully_completed())

    def test_is_fully_completed_returns_false_when_only_buyer_completed(self):
        """is_fully_completed retorna False quando so o comprador completou."""
        delivery = self._create_in_person_delivery()
        delivery.buyer_completed = True
        delivery.save()
        self.assertFalse(delivery.is_fully_completed())

    def test_is_fully_completed_returns_true_when_both_completed(self):
        """is_fully_completed retorna True quando ambos completaram."""
        delivery = self._create_in_person_delivery()
        delivery.seller_completed = True
        delivery.buyer_completed = True
        delivery.save()
        self.assertTrue(delivery.is_fully_completed())

    # --- can_be_completed ---

    def test_can_be_completed_accepts_pending_schedule(self):
        """can_be_completed aceita status pending_schedule."""
        delivery = self._create_in_person_delivery(scheduled=False)
        self.assertEqual(delivery.meeting_status, 'pending_schedule')
        self.assertTrue(delivery.can_be_completed())

    def test_can_be_completed_accepts_scheduled(self):
        """can_be_completed aceita status scheduled."""
        delivery = self._create_in_person_delivery(scheduled=True)
        self.assertEqual(delivery.meeting_status, 'scheduled')
        self.assertTrue(delivery.can_be_completed())

    def test_can_be_completed_accepts_confirmed(self):
        """can_be_completed aceita status confirmed."""
        delivery = self._create_in_person_delivery()
        delivery.seller_confirmed = True
        delivery.buyer_confirmed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'confirmed')
        self.assertTrue(delivery.can_be_completed())

    def test_can_be_completed_accepts_in_progress(self):
        """can_be_completed aceita status in_progress."""
        delivery = self._create_in_person_delivery()
        delivery.meeting_status = 'in_progress'
        delivery.save()
        self.assertTrue(delivery.can_be_completed())

    def test_can_be_completed_rejects_completed(self):
        """can_be_completed rejeita status completed."""
        delivery = self._create_in_person_delivery()
        delivery.seller_completed = True
        delivery.buyer_completed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'completed')
        self.assertFalse(delivery.can_be_completed())

    def test_can_be_completed_rejects_cancelled(self):
        """can_be_completed rejeita status cancelled."""
        delivery = self._create_in_person_delivery()
        delivery.meeting_status = 'cancelled'
        delivery.save()
        self.assertFalse(delivery.can_be_completed())

    def test_can_be_completed_rejects_no_show(self):
        """can_be_completed rejeita status no_show."""
        delivery = self._create_in_person_delivery()
        delivery.meeting_status = 'no_show'
        delivery.save()
        self.assertFalse(delivery.can_be_completed())

    # --- save() auto-transitions ---

    def test_save_auto_transitions_to_confirmed_from_pending_schedule(self):
        """save() transiciona para confirmed quando ambos confirmam a partir de pending_schedule."""
        delivery = self._create_in_person_delivery(scheduled=False)
        self.assertEqual(delivery.meeting_status, 'pending_schedule')
        delivery.seller_confirmed = True
        delivery.buyer_confirmed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'confirmed')

    def test_save_auto_transitions_to_confirmed_from_scheduled(self):
        """save() transiciona para confirmed quando ambos confirmam a partir de scheduled."""
        delivery = self._create_in_person_delivery(scheduled=True)
        self.assertEqual(delivery.meeting_status, 'scheduled')
        delivery.seller_confirmed = True
        delivery.buyer_confirmed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'confirmed')

    def test_save_does_not_auto_transition_to_confirmed_from_in_progress(self):
        """save() NAO transiciona para confirmed se status for in_progress."""
        delivery = self._create_in_person_delivery()
        delivery.meeting_status = 'in_progress'
        delivery.seller_confirmed = True
        delivery.buyer_confirmed = True
        delivery.save()
        # in_progress nao esta na lista de auto-transicao para confirmed
        self.assertEqual(delivery.meeting_status, 'in_progress')

    def test_save_auto_transitions_to_completed_from_confirmed(self):
        """save() transiciona para completed quando ambos completam a partir de confirmed."""
        delivery = self._create_in_person_delivery()
        delivery.seller_confirmed = True
        delivery.buyer_confirmed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'confirmed')

        delivery.seller_completed = True
        delivery.buyer_completed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'completed')

    def test_save_auto_transitions_to_completed_from_scheduled(self):
        """save() transiciona para completed quando ambos completam a partir de scheduled."""
        delivery = self._create_in_person_delivery(scheduled=True)
        delivery.seller_completed = True
        delivery.buyer_completed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'completed')

    def test_save_auto_transitions_to_completed_from_in_progress(self):
        """save() transiciona para completed quando ambos completam a partir de in_progress."""
        delivery = self._create_in_person_delivery()
        delivery.meeting_status = 'in_progress'
        delivery.save()

        delivery.seller_completed = True
        delivery.buyer_completed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'completed')

    def test_save_auto_transitions_to_completed_from_pending_schedule(self):
        """save() transiciona para completed quando ambos completam a partir de pending_schedule."""
        delivery = self._create_in_person_delivery(scheduled=False)
        self.assertEqual(delivery.meeting_status, 'pending_schedule')
        delivery.seller_completed = True
        delivery.buyer_completed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'completed')

    def test_save_sets_completed_at_when_transitioning_to_completed(self):
        """save() define completed_at ao transicionar para completed."""
        delivery = self._create_in_person_delivery()
        self.assertIsNone(delivery.completed_at)

        delivery.seller_completed = True
        delivery.buyer_completed = True
        delivery.save()

        self.assertEqual(delivery.meeting_status, 'completed')
        self.assertIsNotNone(delivery.completed_at)

    def test_save_does_not_overwrite_completed_at_on_second_save(self):
        """save() nao sobrescreve completed_at se ja estiver preenchido."""
        delivery = self._create_in_person_delivery()
        delivery.seller_completed = True
        delivery.buyer_completed = True
        delivery.save()

        first_completed_at = delivery.completed_at
        self.assertIsNotNone(first_completed_at)

        # Salvar novamente nao deve mudar completed_at
        delivery.meeting_notes = 'Nota extra'
        delivery.save()
        self.assertEqual(delivery.completed_at, first_completed_at)

    def test_save_does_not_transition_to_completed_from_cancelled(self):
        """save() NAO transiciona para completed se status for cancelled."""
        delivery = self._create_in_person_delivery()
        delivery.meeting_status = 'cancelled'
        delivery.seller_completed = True
        delivery.buyer_completed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'cancelled')


# ==============================================================================
# SERVICE TESTS
# ==============================================================================

class InPersonDeliveryServiceTest(InPersonDeliveryTestMixin, TestCase):
    """Testes para InPersonDeliveryService."""

    def setUp(self):
        self._create_base_data()

    # --- create_in_person_delivery ---

    def test_create_in_person_delivery_with_schedule(self):
        """Cria entrega presencial com data/hora agendada (status = scheduled)."""
        delivery = self._create_in_person_delivery(scheduled=True)
        self.assertIsNotNone(delivery)
        self.assertEqual(delivery.seller, self.seller)
        self.assertEqual(delivery.buyer, self.buyer)
        self.assertEqual(delivery.meeting_location_name, 'Shopping Test')
        self.assertEqual(delivery.meeting_status, 'scheduled')
        self.assertFalse(delivery.seller_confirmed)
        self.assertFalse(delivery.buyer_confirmed)

    def test_create_in_person_delivery_without_schedule(self):
        """Cria entrega presencial sem data/hora (status = pending_schedule)."""
        delivery = self._create_in_person_delivery(scheduled=False)
        self.assertEqual(delivery.meeting_status, 'pending_schedule')

    def test_create_order_delivery_in_person(self):
        """Cria OrderDelivery com InPersonDelivery associado."""
        order_delivery = self._create_order_delivery_in_person()
        self.assertIsNotNone(order_delivery)
        self.assertEqual(order_delivery.order, self.order)
        self.assertEqual(order_delivery.seller, self.seller)
        self.assertEqual(order_delivery.delivery_method, DeliveryMethod.IN_PERSON)
        self.assertEqual(order_delivery.delivery_cost, 0)
        self.assertIsNotNone(order_delivery.in_person_delivery)

    def test_cannot_create_duplicate_delivery(self):
        """Nao e possivel criar entrega duplicada para mesmo seller/buyer."""
        self._create_in_person_delivery()
        with self.assertRaises(ValueError):
            self._create_in_person_delivery()

    # --- confirm_meeting ---

    def test_confirm_meeting_seller_only(self):
        """Vendedor confirma; apenas seller_confirmed = True."""
        delivery = self._create_in_person_delivery()
        updated = InPersonDeliveryService.confirm_meeting(delivery, self.seller)

        self.assertTrue(updated.seller_confirmed)
        self.assertIsNotNone(updated.seller_confirmed_at)
        self.assertFalse(updated.buyer_confirmed)
        self.assertIsNone(updated.buyer_confirmed_at)
        # Status nao deve mudar para confirmed ainda
        self.assertEqual(updated.meeting_status, 'scheduled')

    def test_confirm_meeting_buyer_only(self):
        """Comprador confirma; apenas buyer_confirmed = True."""
        delivery = self._create_in_person_delivery()
        updated = InPersonDeliveryService.confirm_meeting(delivery, self.buyer)

        self.assertFalse(updated.seller_confirmed)
        self.assertTrue(updated.buyer_confirmed)
        self.assertIsNotNone(updated.buyer_confirmed_at)
        self.assertEqual(updated.meeting_status, 'scheduled')

    def test_confirm_meeting_both_parties_transitions_status(self):
        """Ambos confirmam; meeting_status = confirmed e OrderDelivery.status = confirmed."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        InPersonDeliveryService.confirm_meeting(delivery, self.seller)
        updated = InPersonDeliveryService.confirm_meeting(delivery, self.buyer)

        self.assertTrue(updated.seller_confirmed)
        self.assertTrue(updated.buyer_confirmed)
        self.assertTrue(updated.is_fully_confirmed())
        self.assertEqual(updated.meeting_status, 'confirmed')

        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'confirmed')

    def test_confirm_meeting_both_parties_creates_log(self):
        """Confirmacao de ambos cria log de status com nota 'Ambas as partes confirmaram'."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        InPersonDeliveryService.confirm_meeting(delivery, self.seller)
        InPersonDeliveryService.confirm_meeting(delivery, self.buyer)

        logs = DeliveryStatusLog.objects.filter(
            order_delivery=order_delivery,
            to_status='confirmed'
        )
        self.assertEqual(logs.count(), 1)
        self.assertIn('Ambas as partes confirmaram', logs.first().notes)

    def test_confirm_meeting_duplicate_seller_raises_error(self):
        """Vendedor confirmar duas vezes levanta ValueError."""
        delivery = self._create_in_person_delivery()
        InPersonDeliveryService.confirm_meeting(delivery, self.seller)

        with self.assertRaises(ValueError) as ctx:
            InPersonDeliveryService.confirm_meeting(delivery, self.seller)
        self.assertIn('Vendedor', str(ctx.exception))

    def test_confirm_meeting_duplicate_buyer_raises_error(self):
        """Comprador confirmar duas vezes levanta ValueError."""
        delivery = self._create_in_person_delivery()
        InPersonDeliveryService.confirm_meeting(delivery, self.buyer)

        with self.assertRaises(ValueError) as ctx:
            InPersonDeliveryService.confirm_meeting(delivery, self.buyer)
        self.assertIn('Comprador', str(ctx.exception))

    def test_confirm_meeting_non_participant_raises_error(self):
        """Usuario que nao e seller nem buyer levanta ValueError."""
        delivery = self._create_in_person_delivery()

        with self.assertRaises(ValueError) as ctx:
            InPersonDeliveryService.confirm_meeting(delivery, self.other_user)
        self.assertIn('parte deste encontro', str(ctx.exception))

    # --- complete_delivery ---

    def test_complete_delivery_seller_only(self):
        """Vendedor completa; apenas seller_completed = True, status nao muda para completed."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        updated = InPersonDeliveryService.complete_delivery(delivery, self.seller)

        self.assertTrue(updated.seller_completed)
        self.assertIsNotNone(updated.seller_completed_at)
        self.assertFalse(updated.buyer_completed)
        # Status nao deve ser completed pois falta o buyer
        self.assertNotEqual(updated.meeting_status, 'completed')

    def test_complete_delivery_buyer_only(self):
        """Comprador completa; apenas buyer_completed = True, status nao muda para completed."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        updated = InPersonDeliveryService.complete_delivery(delivery, self.buyer)

        self.assertFalse(updated.seller_completed)
        self.assertTrue(updated.buyer_completed)
        self.assertIsNotNone(updated.buyer_completed_at)
        self.assertNotEqual(updated.meeting_status, 'completed')

    def test_complete_delivery_both_parties_transitions_status(self):
        """Ambos completam; meeting_status = completed e OrderDelivery.status = delivered."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        InPersonDeliveryService.complete_delivery(delivery, self.seller)
        updated = InPersonDeliveryService.complete_delivery(delivery, self.buyer)

        self.assertTrue(updated.is_fully_completed())
        self.assertEqual(updated.meeting_status, 'completed')
        self.assertIsNotNone(updated.completed_at)

        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'delivered')
        self.assertIsNotNone(order_delivery.completed_at)

    def test_complete_delivery_both_parties_creates_log(self):
        """Conclusao por ambos cria log de status com nota 'Ambas as partes confirmaram a conclusao'."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        InPersonDeliveryService.complete_delivery(delivery, self.seller)
        InPersonDeliveryService.complete_delivery(delivery, self.buyer)

        logs = DeliveryStatusLog.objects.filter(
            order_delivery=order_delivery,
            to_status='delivered'
        )
        self.assertEqual(logs.count(), 1)
        self.assertIn('Ambas as partes confirmaram a conclus', logs.first().notes)

    def test_complete_delivery_duplicate_seller_raises_error(self):
        """Vendedor completar duas vezes levanta ValueError."""
        delivery = self._create_in_person_delivery()
        InPersonDeliveryService.complete_delivery(delivery, self.seller)

        with self.assertRaises(ValueError) as ctx:
            InPersonDeliveryService.complete_delivery(delivery, self.seller)
        self.assertIn('Vendedor', str(ctx.exception))

    def test_complete_delivery_duplicate_buyer_raises_error(self):
        """Comprador completar duas vezes levanta ValueError."""
        delivery = self._create_in_person_delivery()
        InPersonDeliveryService.complete_delivery(delivery, self.buyer)

        with self.assertRaises(ValueError) as ctx:
            InPersonDeliveryService.complete_delivery(delivery, self.buyer)
        self.assertIn('Comprador', str(ctx.exception))

    def test_complete_delivery_non_participant_raises_error(self):
        """Usuario que nao e participante levanta ValueError."""
        delivery = self._create_in_person_delivery()

        with self.assertRaises(ValueError) as ctx:
            InPersonDeliveryService.complete_delivery(delivery, self.other_user)
        self.assertIn('permiss', str(ctx.exception))

    def test_complete_delivery_cancelled_raises_error(self):
        """Nao pode completar entrega cancelada."""
        delivery = self._create_in_person_delivery()
        delivery.meeting_status = 'cancelled'
        delivery.save()

        with self.assertRaises(ValueError) as ctx:
            InPersonDeliveryService.complete_delivery(delivery, self.seller)
        self.assertIn('cancelado', str(ctx.exception).lower().replace('ã', 'a'))

    def test_complete_delivery_with_notes(self):
        """Notas de conclusao sao salvas no InPersonDelivery."""
        delivery = self._create_in_person_delivery()
        InPersonDeliveryService.complete_delivery(
            delivery, self.seller, completion_notes='Produto entregue com sucesso'
        )
        self.assertEqual(delivery.completion_notes, 'Produto entregue com sucesso')

    # --- update_meeting_details ---

    def test_update_meeting_details_changes_location(self):
        """Atualiza nome do local do encontro."""
        delivery = self._create_in_person_delivery()
        updated = InPersonDeliveryService.update_meeting_details(
            delivery, self.seller, meeting_location_name='Novo Shopping'
        )
        self.assertEqual(updated.meeting_location_name, 'Novo Shopping')

    def test_update_meeting_details_date_time_changes_status_to_scheduled(self):
        """Atualizar data/hora muda status para scheduled e reseta confirmacoes."""
        delivery = self._create_in_person_delivery()
        # Confirmar primeiro
        InPersonDeliveryService.confirm_meeting(delivery, self.seller)
        InPersonDeliveryService.confirm_meeting(delivery, self.buyer)
        self.assertEqual(delivery.meeting_status, 'confirmed')
        self.assertTrue(delivery.seller_confirmed)

        # Atualizar data/hora
        new_date = (timezone.now() + timedelta(days=5)).date()
        new_time = time(16, 0)
        updated = InPersonDeliveryService.update_meeting_details(
            delivery, self.seller,
            scheduled_date=new_date,
            scheduled_time=new_time
        )

        self.assertEqual(updated.scheduled_date, new_date)
        self.assertEqual(updated.scheduled_time, new_time)
        self.assertEqual(updated.meeting_status, 'scheduled')
        # Confirmacoes devem ser resetadas
        self.assertFalse(updated.seller_confirmed)
        self.assertFalse(updated.buyer_confirmed)
        self.assertIsNone(updated.seller_confirmed_at)
        self.assertIsNone(updated.buyer_confirmed_at)

    def test_update_meeting_details_resets_confirmations_on_date_change(self):
        """Mudar apenas a data reseta confirmacoes."""
        delivery = self._create_in_person_delivery()
        InPersonDeliveryService.confirm_meeting(delivery, self.seller)
        self.assertTrue(delivery.seller_confirmed)

        new_date = (timezone.now() + timedelta(days=7)).date()
        updated = InPersonDeliveryService.update_meeting_details(
            delivery, self.seller, scheduled_date=new_date
        )
        self.assertFalse(updated.seller_confirmed)
        self.assertFalse(updated.buyer_confirmed)

    def test_update_meeting_details_non_participant_raises_error(self):
        """Usuario que nao e participante nao pode atualizar."""
        delivery = self._create_in_person_delivery()
        with self.assertRaises(ValueError):
            InPersonDeliveryService.update_meeting_details(
                delivery, self.other_user, meeting_location_name='Outro local'
            )

    # --- cancel_delivery ---

    def test_cancel_delivery(self):
        """Cancelar entrega muda status para cancelled."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        cancelled = InPersonDeliveryService.cancel_delivery(
            delivery, self.buyer, cancellation_reason='Mudanca de planos'
        )
        self.assertEqual(cancelled.meeting_status, 'cancelled')
        self.assertIn('Mudanca de planos', cancelled.completion_notes)

        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'cancelled')

    def test_cancel_completed_delivery_raises_error(self):
        """Nao pode cancelar entrega ja concluida."""
        delivery = self._create_in_person_delivery()
        delivery.seller_completed = True
        delivery.buyer_completed = True
        delivery.save()
        self.assertEqual(delivery.meeting_status, 'completed')

        with self.assertRaises(ValueError):
            InPersonDeliveryService.cancel_delivery(
                delivery, self.seller, cancellation_reason='Tentando cancelar'
            )

    def test_cancel_delivery_non_participant_raises_error(self):
        """Nao participante nao pode cancelar."""
        delivery = self._create_in_person_delivery()
        with self.assertRaises(ValueError):
            InPersonDeliveryService.cancel_delivery(
                delivery, self.other_user, cancellation_reason='Nao autorizado'
            )


# ==============================================================================
# API / VIEW TESTS
# ==============================================================================

class InPersonDeliveryAPITest(InPersonDeliveryTestMixin, TestCase):
    """Testes para os endpoints de API de entrega presencial."""

    def setUp(self):
        self._create_base_data()
        self.client = APIClient()

    # --- Confirm Meeting API ---

    def test_confirm_meeting_api_seller_success(self):
        """POST /api/logistics/in-person/{id}/confirm/ - vendedor confirma."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        self.client.force_authenticate(user=self.seller)
        response = self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('message', response.data)
        self.assertTrue(response.data['delivery']['seller_confirmed'])
        self.assertFalse(response.data['delivery']['buyer_confirmed'])

    def test_confirm_meeting_api_buyer_success(self):
        """POST /api/logistics/in-person/{id}/confirm/ - comprador confirma."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['delivery']['seller_confirmed'])
        self.assertTrue(response.data['delivery']['buyer_confirmed'])

    def test_confirm_meeting_api_both_parties_status_change(self):
        """POST /api/logistics/in-person/{id}/confirm/ - ambos confirmam, status muda."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        # Seller confirma
        self.client.force_authenticate(user=self.seller)
        self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')

        # Buyer confirma
        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['delivery']['meeting_status'], 'confirmed')
        self.assertTrue(response.data['delivery']['is_fully_confirmed'])

        # Verificar OrderDelivery
        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'confirmed')

    def test_confirm_meeting_api_non_participant_returns_403(self):
        """POST /api/logistics/in-person/{id}/confirm/ - nao participante retorna 403."""
        delivery = self._create_in_person_delivery()

        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')

        self.assertEqual(response.status_code, 403)
        self.assertIn('error', response.data)

    def test_confirm_meeting_api_duplicate_returns_400(self):
        """POST /api/logistics/in-person/{id}/confirm/ - confirmacao duplicada retorna 400."""
        delivery = self._create_in_person_delivery()

        self.client.force_authenticate(user=self.seller)
        self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')
        response = self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')

        self.assertEqual(response.status_code, 400)

    def test_confirm_meeting_api_unauthenticated_returns_401(self):
        """POST /api/logistics/in-person/{id}/confirm/ - nao autenticado retorna 401."""
        delivery = self._create_in_person_delivery()
        response = self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')
        self.assertIn(response.status_code, [401, 403])

    # --- Complete Delivery API ---

    def test_complete_delivery_api_seller_success(self):
        """POST /api/logistics/in-person/{id}/complete/ - vendedor completa."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        self.client.force_authenticate(user=self.seller)
        response = self.client.post(
            f'/api/logistics/in-person/{delivery.id}/complete/',
            {'completion_notes': 'Tudo certo'},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Aguardando', response.data['message'])
        self.assertTrue(response.data['delivery']['seller_completed'])
        self.assertFalse(response.data['delivery']['buyer_completed'])

    def test_complete_delivery_api_buyer_success(self):
        """POST /api/logistics/in-person/{id}/complete/ - comprador completa."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(
            f'/api/logistics/in-person/{delivery.id}/complete/',
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['delivery']['seller_completed'])
        self.assertTrue(response.data['delivery']['buyer_completed'])

    def test_complete_delivery_api_both_parties_status_change(self):
        """POST /api/logistics/in-person/{id}/complete/ - ambos completam, status muda."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        # Seller completa
        self.client.force_authenticate(user=self.seller)
        self.client.post(
            f'/api/logistics/in-person/{delivery.id}/complete/',
            format='json'
        )

        # Buyer completa
        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(
            f'/api/logistics/in-person/{delivery.id}/complete/',
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('ambas as partes', response.data['message'].lower())
        self.assertEqual(response.data['delivery']['meeting_status'], 'completed')
        self.assertTrue(response.data['delivery']['is_fully_completed'])

        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'delivered')

    def test_complete_delivery_api_non_participant_returns_403(self):
        """POST /api/logistics/in-person/{id}/complete/ - nao participante retorna 403."""
        delivery = self._create_in_person_delivery()

        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(
            f'/api/logistics/in-person/{delivery.id}/complete/',
            format='json'
        )
        self.assertEqual(response.status_code, 403)

    def test_complete_delivery_api_duplicate_returns_400(self):
        """POST /api/logistics/in-person/{id}/complete/ - completar duplicado retorna 400."""
        delivery = self._create_in_person_delivery()

        self.client.force_authenticate(user=self.seller)
        self.client.post(f'/api/logistics/in-person/{delivery.id}/complete/', format='json')
        response = self.client.post(f'/api/logistics/in-person/{delivery.id}/complete/', format='json')

        self.assertEqual(response.status_code, 400)

    # --- Create Order Deliveries API ---

    def test_create_deliveries_rejected_when_order_pending_payment(self):
        """POST /api/logistics/deliveries/create/ - rejeita quando order esta pending_payment."""
        self.order.status = 'pending_payment'
        self.order.save()

        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(
            '/api/logistics/deliveries/create/',
            {
                'order_id': str(self.order.id),
                'deliveries': [
                    {
                        'seller_id': self.seller.id,
                        'delivery_method': 'in_person',
                        'meeting_location_name': 'Shopping Test',
                        'meeting_address': {'city': 'SP'},
                        'seller_contact_phone': '11999999999',
                        'buyer_contact_phone': '11888888888',
                    }
                ]
            },
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('pagamento', response.data['error'].lower())

    def test_create_deliveries_works_with_order_shipping_services(self):
        """POST /api/logistics/deliveries/create/ - funciona so com order_id usando shipping_services."""
        self.order.status = 'paid'
        self.order.shipping_services = {
            str(self.seller.id): {
                'delivery_method': 'in_person',
                'meeting_location_name': 'Shopping via Services',
                'meeting_address': {'city': 'Sao Paulo', 'state': 'SP'},
                'seller_contact_phone': '11999999999',
                'buyer_contact_phone': '11888888888',
            }
        }
        self.order.save()

        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(
            '/api/logistics/deliveries/create/',
            {'order_id': str(self.order.id)},
            format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(str(response.data['order_id']), str(self.order.id))

    def test_create_deliveries_with_explicit_delivery_data(self):
        """POST /api/logistics/deliveries/create/ - funciona com deliveries explicitas."""
        self.order.status = 'paid'
        self.order.save()

        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(
            '/api/logistics/deliveries/create/',
            {
                'order_id': str(self.order.id),
                'deliveries': [
                    {
                        'seller_id': self.seller.id,
                        'delivery_method': 'in_person',
                        'meeting_location_name': 'Shopping Direto',
                        'meeting_address': {'city': 'Sao Paulo'},
                        'seller_contact_phone': '11999999999',
                        'buyer_contact_phone': '11888888888',
                    }
                ]
            },
            format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['count'], 1)

    def test_create_deliveries_only_buyer_can_create(self):
        """POST /api/logistics/deliveries/create/ - so o comprador pode criar entregas."""
        self.order.status = 'paid'
        self.order.save()

        self.client.force_authenticate(user=self.seller)
        response = self.client.post(
            '/api/logistics/deliveries/create/',
            {
                'order_id': str(self.order.id),
                'deliveries': [
                    {
                        'seller_id': self.seller.id,
                        'delivery_method': 'in_person',
                        'meeting_location_name': 'Shopping',
                        'meeting_address': {'city': 'SP'},
                        'seller_contact_phone': '11999999999',
                        'buyer_contact_phone': '11888888888',
                    }
                ]
            },
            format='json'
        )

        self.assertEqual(response.status_code, 403)

    def test_create_deliveries_missing_order_id_returns_400(self):
        """POST /api/logistics/deliveries/create/ - retorna 400 sem order_id."""
        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(
            '/api/logistics/deliveries/create/',
            {},
            format='json'
        )
        self.assertEqual(response.status_code, 400)

    def test_create_deliveries_no_deliveries_no_shipping_services_returns_400(self):
        """POST /api/logistics/deliveries/create/ - retorna 400 sem deliveries e sem shipping_services."""
        self.order.status = 'paid'
        self.order.shipping_services = {}
        self.order.save()

        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(
            '/api/logistics/deliveries/create/',
            {'order_id': str(self.order.id)},
            format='json'
        )
        self.assertEqual(response.status_code, 400)

    # --- Get In-Person Delivery Detail API ---

    def test_get_detail_seller_success(self):
        """GET /api/logistics/in-person/{id}/ - vendedor pode ver detalhes."""
        delivery = self._create_in_person_delivery()

        self.client.force_authenticate(user=self.seller)
        response = self.client.get(f'/api/logistics/in-person/{delivery.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], delivery.id)

    def test_get_detail_buyer_success(self):
        """GET /api/logistics/in-person/{id}/ - comprador pode ver detalhes."""
        delivery = self._create_in_person_delivery()

        self.client.force_authenticate(user=self.buyer)
        response = self.client.get(f'/api/logistics/in-person/{delivery.id}/')

        self.assertEqual(response.status_code, 200)

    def test_get_detail_non_participant_returns_403(self):
        """GET /api/logistics/in-person/{id}/ - nao participante retorna 403."""
        delivery = self._create_in_person_delivery()

        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(f'/api/logistics/in-person/{delivery.id}/')

        self.assertEqual(response.status_code, 403)

    # --- Update Meeting Details API ---

    def test_update_meeting_api_seller_success(self):
        """PATCH /api/logistics/in-person/{id}/update/ - vendedor atualiza detalhes."""
        delivery = self._create_in_person_delivery()

        self.client.force_authenticate(user=self.seller)
        response = self.client.patch(
            f'/api/logistics/in-person/{delivery.id}/update/',
            {'meeting_location_name': 'Local Atualizado'},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['delivery']['meeting_location_name'], 'Local Atualizado')

    def test_update_meeting_api_non_participant_returns_403(self):
        """PATCH /api/logistics/in-person/{id}/update/ - nao participante retorna 403."""
        delivery = self._create_in_person_delivery()

        self.client.force_authenticate(user=self.other_user)
        response = self.client.patch(
            f'/api/logistics/in-person/{delivery.id}/update/',
            {'meeting_location_name': 'Local'},
            format='json'
        )

        self.assertEqual(response.status_code, 403)

    # --- Cancel Delivery API ---

    def test_cancel_delivery_api_success(self):
        """POST /api/logistics/in-person/{id}/cancel/ - cancela entrega."""
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(
            f'/api/logistics/in-person/{delivery.id}/cancel/',
            {'cancellation_reason': 'Nao consigo ir'},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['delivery']['meeting_status'], 'cancelled')

    def test_cancel_delivery_api_non_participant_returns_403(self):
        """POST /api/logistics/in-person/{id}/cancel/ - nao participante retorna 403."""
        delivery = self._create_in_person_delivery()

        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(
            f'/api/logistics/in-person/{delivery.id}/cancel/',
            format='json'
        )

        self.assertEqual(response.status_code, 403)

    # --- List In-Person Deliveries API ---

    def test_list_in_person_deliveries_seller(self):
        """GET /api/logistics/in-person/ - vendedor ve suas entregas."""
        self._create_in_person_delivery()

        self.client.force_authenticate(user=self.seller)
        response = self.client.get('/api/logistics/in-person/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_list_in_person_deliveries_buyer(self):
        """GET /api/logistics/in-person/ - comprador ve suas entregas."""
        self._create_in_person_delivery()

        self.client.force_authenticate(user=self.buyer)
        response = self.client.get('/api/logistics/in-person/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_list_in_person_deliveries_other_user_sees_nothing(self):
        """GET /api/logistics/in-person/ - usuario sem entregas ve lista vazia."""
        self._create_in_person_delivery()

        self.client.force_authenticate(user=self.other_user)
        response = self.client.get('/api/logistics/in-person/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)

    def test_list_in_person_deliveries_filter_by_status(self):
        """GET /api/logistics/in-person/?status=scheduled - filtra por status."""
        self._create_in_person_delivery(scheduled=True)

        self.client.force_authenticate(user=self.seller)
        response = self.client.get('/api/logistics/in-person/?status=scheduled')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

        response_empty = self.client.get('/api/logistics/in-person/?status=confirmed')
        self.assertEqual(response_empty.data['count'], 0)


# ==============================================================================
# FULL FLOW INTEGRATION TEST
# ==============================================================================

class InPersonDeliveryFullFlowTest(InPersonDeliveryTestMixin, TestCase):
    """Teste de integracao do fluxo completo de entrega presencial."""

    def setUp(self):
        self._create_base_data()
        self.client = APIClient()

    def test_full_flow_create_confirm_complete(self):
        """
        Fluxo completo end-to-end:
        1. Criar order (paid)
        2. Criar delivery via API
        3. Confirmar meeting (ambas as partes) via API
        4. Completar delivery (ambas as partes) via API
        5. Verificar todos os status finais
        """
        # 1. Order ja esta criada com status 'paid' no setUp
        self.assertEqual(self.order.status, 'paid')

        # 2. Criar delivery via API
        self.client.force_authenticate(user=self.buyer)
        create_response = self.client.post(
            '/api/logistics/deliveries/create/',
            {
                'order_id': str(self.order.id),
                'deliveries': [
                    {
                        'seller_id': self.seller.id,
                        'delivery_method': 'in_person',
                        'meeting_location_name': 'Shopping Integracao',
                        'meeting_address': {
                            'street': 'Av Paulista',
                            'number': '1000',
                            'city': 'Sao Paulo',
                            'state': 'SP'
                        },
                        'seller_contact_phone': '11999999999',
                        'buyer_contact_phone': '11888888888',
                        'scheduled_date': str(self.scheduled_date),
                        'scheduled_time': '14:00',
                    }
                ]
            },
            format='json'
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data['count'], 1)

        # Extrair IDs
        delivery_data = create_response.data['deliveries'][0]
        in_person_id = delivery_data['in_person_delivery']
        order_delivery_id = delivery_data['id']

        # Verificar status inicial
        in_person = InPersonDelivery.objects.get(id=in_person_id)
        order_delivery = OrderDelivery.objects.get(id=order_delivery_id)
        self.assertEqual(in_person.meeting_status, 'scheduled')
        self.assertEqual(order_delivery.status, 'pending')
        self.assertEqual(order_delivery.delivery_method, DeliveryMethod.IN_PERSON)

        # 3. Confirmar meeting - seller
        self.client.force_authenticate(user=self.seller)
        confirm_seller_response = self.client.post(
            f'/api/logistics/in-person/{in_person_id}/confirm/'
        )
        self.assertEqual(confirm_seller_response.status_code, 200)
        self.assertTrue(confirm_seller_response.data['delivery']['seller_confirmed'])
        self.assertFalse(confirm_seller_response.data['delivery']['buyer_confirmed'])
        self.assertEqual(confirm_seller_response.data['delivery']['meeting_status'], 'scheduled')

        # 3. Confirmar meeting - buyer
        self.client.force_authenticate(user=self.buyer)
        confirm_buyer_response = self.client.post(
            f'/api/logistics/in-person/{in_person_id}/confirm/'
        )
        self.assertEqual(confirm_buyer_response.status_code, 200)
        self.assertTrue(confirm_buyer_response.data['delivery']['seller_confirmed'])
        self.assertTrue(confirm_buyer_response.data['delivery']['buyer_confirmed'])
        self.assertEqual(confirm_buyer_response.data['delivery']['meeting_status'], 'confirmed')

        # Verificar OrderDelivery transicionou para confirmed
        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'confirmed')
        self.assertIsNotNone(order_delivery.confirmed_at)

        # 4. Completar delivery - seller
        self.client.force_authenticate(user=self.seller)
        complete_seller_response = self.client.post(
            f'/api/logistics/in-person/{in_person_id}/complete/',
            {'completion_notes': 'Entregue pelo vendedor'},
            format='json'
        )
        self.assertEqual(complete_seller_response.status_code, 200)
        self.assertTrue(complete_seller_response.data['delivery']['seller_completed'])
        self.assertFalse(complete_seller_response.data['delivery']['buyer_completed'])
        # Ainda nao completou pois falta o buyer
        self.assertIn('Aguardando', complete_seller_response.data['message'])

        # 4. Completar delivery - buyer
        self.client.force_authenticate(user=self.buyer)
        complete_buyer_response = self.client.post(
            f'/api/logistics/in-person/{in_person_id}/complete/',
            {'completion_notes': 'Recebido pelo comprador'},
            format='json'
        )
        self.assertEqual(complete_buyer_response.status_code, 200)
        self.assertTrue(complete_buyer_response.data['delivery']['seller_completed'])
        self.assertTrue(complete_buyer_response.data['delivery']['buyer_completed'])
        self.assertEqual(complete_buyer_response.data['delivery']['meeting_status'], 'completed')
        self.assertIn('ambas as partes', complete_buyer_response.data['message'].lower())

        # 5. Verificar todos os status finais
        in_person.refresh_from_db()
        order_delivery.refresh_from_db()

        # InPersonDelivery
        self.assertEqual(in_person.meeting_status, 'completed')
        self.assertTrue(in_person.is_fully_confirmed())
        self.assertTrue(in_person.is_fully_completed())
        self.assertIsNotNone(in_person.completed_at)
        self.assertIsNotNone(in_person.seller_confirmed_at)
        self.assertIsNotNone(in_person.buyer_confirmed_at)
        self.assertIsNotNone(in_person.seller_completed_at)
        self.assertIsNotNone(in_person.buyer_completed_at)

        # OrderDelivery
        self.assertEqual(order_delivery.status, 'delivered')
        self.assertIsNotNone(order_delivery.completed_at)
        self.assertEqual(order_delivery.delivery_cost, 0)

        # DeliveryStatusLog (deve ter logs: pending, confirmed, delivered)
        logs = DeliveryStatusLog.objects.filter(
            order_delivery=order_delivery
        ).order_by('created_at')
        status_transitions = [(log.from_status, log.to_status) for log in logs]
        self.assertIn(('', 'pending'), status_transitions)
        self.assertIn(('pending', 'confirmed'), status_transitions)
        self.assertIn(('confirmed', 'delivered'), status_transitions)

    def test_full_flow_create_then_cancel(self):
        """
        Fluxo de cancelamento:
        1. Criar delivery
        2. Confirmar (vendedor)
        3. Cancelar (comprador)
        4. Verificar status
        """
        # Criar delivery
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        # Confirmar (vendedor)
        self.client.force_authenticate(user=self.seller)
        self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')

        # Cancelar (comprador)
        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(
            f'/api/logistics/in-person/{delivery.id}/cancel/',
            {'cancellation_reason': 'Desisti da compra'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)

        delivery.refresh_from_db()
        order_delivery.refresh_from_db()
        self.assertEqual(delivery.meeting_status, 'cancelled')
        self.assertEqual(order_delivery.status, 'cancelled')

    def test_full_flow_reschedule_resets_confirmations(self):
        """
        Fluxo de reagendamento:
        1. Criar delivery agendada
        2. Ambos confirmam
        3. Atualizar data (reagendar)
        4. Verificar que confirmacoes foram resetadas
        5. Ambos confirmam novamente
        """
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        # Ambos confirmam
        self.client.force_authenticate(user=self.seller)
        self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')
        self.client.force_authenticate(user=self.buyer)
        self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')

        delivery.refresh_from_db()
        self.assertEqual(delivery.meeting_status, 'confirmed')

        # Reagendar
        new_date = (timezone.now() + timedelta(days=10)).date()
        self.client.force_authenticate(user=self.seller)
        update_response = self.client.patch(
            f'/api/logistics/in-person/{delivery.id}/update/',
            {
                'scheduled_date': str(new_date),
                'scheduled_time': '16:00'
            },
            format='json'
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data['delivery']['meeting_status'], 'scheduled')
        self.assertFalse(update_response.data['delivery']['seller_confirmed'])
        self.assertFalse(update_response.data['delivery']['buyer_confirmed'])

        # Ambos confirmam novamente
        self.client.force_authenticate(user=self.seller)
        self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')
        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(f'/api/logistics/in-person/{delivery.id}/confirm/')

        self.assertEqual(response.data['delivery']['meeting_status'], 'confirmed')
        self.assertTrue(response.data['delivery']['is_fully_confirmed'])

    def test_full_flow_complete_without_prior_confirmation(self):
        """
        Completar sem confirmar antes: ambos completam diretamente
        (a confirmacao nao e pre-requisito para completar).
        """
        order_delivery = self._create_order_delivery_in_person()
        delivery = order_delivery.in_person_delivery

        # Seller completa
        self.client.force_authenticate(user=self.seller)
        self.client.post(
            f'/api/logistics/in-person/{delivery.id}/complete/',
            format='json'
        )

        # Buyer completa
        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(
            f'/api/logistics/in-person/{delivery.id}/complete/',
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['delivery']['meeting_status'], 'completed')

        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'delivered')
