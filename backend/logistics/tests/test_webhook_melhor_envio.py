"""
Comprehensive tests for Melhor Envio webhook endpoint.

Tests cover:
1. Test connection/ping requests
2. Event processing (order.posted, order.delivered, order.cancelled, order.in_transit)
3. Multi-shipment order scenarios
4. Tracking code and timestamp updates
5. Unknown shipment handling
6. HMAC signature validation
7. OrderStateMachine integration
"""

import json
import hmac
import hashlib
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from rest_framework.test import APIClient

from authentication.models import CustomUser
from orders.models import Order, OrderItem, OrderStatusHistory
from products.models import Products, MarketplaceListing, Brand, Condition, Category, Series
from logistics.models import Shipment, OrderDelivery, DeliveryStatusLog, ShipmentTracking, DeliveryMethod
from orders.services.order_state_machine import OrderStateMachine


class MelhorEnvioWebhookTest(TestCase):
    """Tests for Melhor Envio webhook endpoint"""

    def setUp(self):
        """Setup test fixtures"""
        self.client = APIClient()
        self.webhook_url = reverse('logistics:melhor-envio-webhook')

        # Create users
        self.buyer = CustomUser.objects.create_user(
            email='buyer@test.com',
            password='test123',
            full_name='Buyer Test',
            cpf='12345678901'
        )

        self.seller1 = CustomUser.objects.create_user(
            email='seller1@test.com',
            password='test123',
            full_name='Seller One',
            cpf='98765432100'
        )

        self.seller2 = CustomUser.objects.create_user(
            email='seller2@test.com',
            password='test123',
            full_name='Seller Two',
            cpf='11122233344'
        )

        # Create product catalog fixtures
        self.category = Category.objects.create(name='Test Category', slug='test-category')
        self.series = Series.objects.create(name='Test Series', slug='test-series')
        self.brand = Brand.objects.create(name='Test Brand')
        self.condition = Condition.objects.create(name='New', slug='new')

        # Create product and listing for seller1
        self.product1 = Products.objects.create(
            name='Product 1',
            slug='product-1',
            code='PROD1',
            category=self.category,
            series=self.series
        )
        self.listing1 = MarketplaceListing.objects.create(
            seller=self.seller1,
            product=self.product1,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('100.00'),
            quantity=10,
            description='Test listing 1',
            is_active=True,
            weight_kg=Decimal('1.0'),
            height_cm=Decimal('10.0'),
            width_cm=Decimal('10.0'),
            length_cm=Decimal('10.0')
        )

        # Create product and listing for seller2
        self.product2 = Products.objects.create(
            name='Product 2',
            slug='product-2',
            code='PROD2',
            category=self.category,
            series=self.series
        )
        self.listing2 = MarketplaceListing.objects.create(
            seller=self.seller2,
            product=self.product2,
            brand=self.brand,
            condition=self.condition,
            price=Decimal('150.00'),
            quantity=10,
            description='Test listing 2',
            is_active=True,
            weight_kg=Decimal('2.0'),
            height_cm=Decimal('15.0'),
            width_cm=Decimal('15.0'),
            length_cm=Decimal('15.0')
        )

        # Create a single-seller order (for single shipment tests)
        self.order_single = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('20.00'),
            total=Decimal('120.00'),
            status=OrderStateMachine.PROCESSING,
            shipping_address={
                'street': 'Test Street',
                'number': '123',
                'city': 'Test City',
                'state': 'SP',
                'zipcode': '12345678'
            }
        )
        OrderItem.objects.create(
            order=self.order_single,
            listing=self.listing1,
            seller=self.seller1,
            product_name='Product 1',
            brand_name='Test Brand',
            condition_name='New',
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('20.00'),
            weight_kg=Decimal('1.0'),
            height_cm=Decimal('10.0'),
            width_cm=Decimal('10.0'),
            length_cm=Decimal('10.0')
        )

        # Create shipment for single-seller order
        self.shipment_single = Shipment.objects.create(
            order=self.order_single,
            seller=self.seller1,
            melhorenvio_order_id='ME-SINGLE-001',
            carrier_name='Correios',
            carrier_service='PAC',
            shipping_cost=Decimal('20.00'),
            status='pending',
            weight=Decimal('1.0'),
            height=Decimal('10.0'),
            width=Decimal('10.0'),
            length=Decimal('10.0'),
            origin_address={'zipcode': '01310100'},
            destination_address={'zipcode': '12345678'}
        )

        # Create a multi-seller order (for multi-shipment tests)
        self.order_multi = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('250.00'),
            shipping_cost=Decimal('40.00'),
            total=Decimal('290.00'),
            status=OrderStateMachine.PROCESSING,
            shipping_address={
                'street': 'Test Street',
                'number': '456',
                'city': 'Test City',
                'state': 'SP',
                'zipcode': '12345678'
            }
        )
        OrderItem.objects.create(
            order=self.order_multi,
            listing=self.listing1,
            seller=self.seller1,
            product_name='Product 1',
            brand_name='Test Brand',
            condition_name='New',
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('20.00'),
            weight_kg=Decimal('1.0'),
            height_cm=Decimal('10.0'),
            width_cm=Decimal('10.0'),
            length_cm=Decimal('10.0')
        )
        OrderItem.objects.create(
            order=self.order_multi,
            listing=self.listing2,
            seller=self.seller2,
            product_name='Product 2',
            brand_name='Test Brand',
            condition_name='New',
            quantity=1,
            unit_price=Decimal('150.00'),
            subtotal=Decimal('150.00'),
            shipping_cost=Decimal('20.00'),
            weight_kg=Decimal('2.0'),
            height_cm=Decimal('15.0'),
            width_cm=Decimal('15.0'),
            length_cm=Decimal('15.0')
        )

        # Create two shipments for multi-seller order
        self.shipment_multi_1 = Shipment.objects.create(
            order=self.order_multi,
            seller=self.seller1,
            melhorenvio_order_id='ME-MULTI-001',
            carrier_name='Correios',
            carrier_service='PAC',
            shipping_cost=Decimal('20.00'),
            status='pending',
            weight=Decimal('1.0'),
            height=Decimal('10.0'),
            width=Decimal('10.0'),
            length=Decimal('10.0'),
            origin_address={'zipcode': '01310100'},
            destination_address={'zipcode': '12345678'}
        )

        self.shipment_multi_2 = Shipment.objects.create(
            order=self.order_multi,
            seller=self.seller2,
            melhorenvio_order_id='ME-MULTI-002',
            carrier_name='Correios',
            carrier_service='SEDEX',
            shipping_cost=Decimal('20.00'),
            status='pending',
            weight=Decimal('2.0'),
            height=Decimal('15.0'),
            width=Decimal('15.0'),
            length=Decimal('15.0'),
            origin_address={'zipcode': '01310100'},
            destination_address={'zipcode': '12345678'}
        )

    def _create_signature(self, payload: dict) -> str:
        """Helper to create valid HMAC-SHA256 signature for webhook"""
        webhook_secret = settings.MELHOR_ENVIO_WEBHOOK_SECRET or 'test-secret'
        body = json.dumps(payload).encode('utf-8')
        return hmac.new(
            webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()

    def test_webhook_connection_empty_body(self):
        """Test webhook responds to connection test with empty body"""
        response = self.client.post(
            self.webhook_url,
            data={},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        # Should handle gracefully even with no event/data

    def test_webhook_connection_fake_event(self):
        """Test webhook responds to connection test with fake event"""
        payload = {
            'event': 'test.connection',
            'data': {'test': True}
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        # Should return success for unknown events

    def test_order_posted_single_shipment(self):
        """Test order.posted event with single shipment transitions order to shipped"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX',
                'posted_at': '2026-02-11T10:00:00Z'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Evento order.posted processado com sucesso', response.data['message'])

        # Verify shipment status updated
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.status, 'posted')
        self.assertEqual(self.shipment_single.melhorenvio_tracking_code, 'BR123456789XX')
        self.assertIsNotNone(self.shipment_single.posted_at)

        # Verify order status transitioned to shipped
        self.order_single.refresh_from_db()
        self.assertEqual(self.order_single.status, OrderStateMachine.SHIPPED)

        # Verify audit trail created
        history = OrderStatusHistory.objects.filter(order=self.order_single).latest('created_at')
        self.assertEqual(history.old_status, OrderStateMachine.PROCESSING)
        self.assertEqual(history.new_status, OrderStateMachine.SHIPPED)
        self.assertIn('postados', history.notes.lower())

    def test_order_posted_multi_shipment_partial(self):
        """Test order.posted with multi-shipment order - only one posted, order stays processing"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-MULTI-001',
                'tracking': 'BR111111111XX',
                'posted_at': '2026-02-11T10:00:00Z'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify first shipment updated
        self.shipment_multi_1.refresh_from_db()
        self.assertEqual(self.shipment_multi_1.status, 'posted')

        # Verify order stays in processing (not all shipments posted)
        self.order_multi.refresh_from_db()
        self.assertEqual(self.order_multi.status, OrderStateMachine.PROCESSING)

    def test_order_posted_multi_shipment_all_posted(self):
        """Test order.posted when all shipments posted transitions order to shipped"""
        # Post first shipment
        payload1 = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-MULTI-001',
                'tracking': 'BR111111111XX',
                'posted_at': '2026-02-11T10:00:00Z'
            }
        }
        self.client.post(self.webhook_url, data=payload1, format='json')

        # Post second shipment
        payload2 = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-MULTI-002',
                'tracking': 'BR222222222XX',
                'posted_at': '2026-02-11T10:05:00Z'
            }
        }
        response = self.client.post(self.webhook_url, data=payload2, format='json')

        self.assertEqual(response.status_code, 200)

        # Verify both shipments posted
        self.shipment_multi_1.refresh_from_db()
        self.shipment_multi_2.refresh_from_db()
        self.assertEqual(self.shipment_multi_1.status, 'posted')
        self.assertEqual(self.shipment_multi_2.status, 'posted')

        # Verify order transitioned to shipped
        self.order_multi.refresh_from_db()
        self.assertEqual(self.order_multi.status, OrderStateMachine.SHIPPED)

    def test_order_delivered_single_shipment(self):
        """Test order.delivered event with single shipment transitions order to delivered"""
        # First mark as posted then shipped
        self.order_single.status = OrderStateMachine.SHIPPED
        self.order_single.save()
        self.shipment_single.status = 'posted'
        self.shipment_single.save()

        payload = {
            'event': 'order.delivered',
            'data': {
                'id': 'ME-SINGLE-001',
                'delivered_at': '2026-02-15T14:30:00Z'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify shipment status updated
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.status, 'delivered')
        self.assertIsNotNone(self.shipment_single.delivered_at)

        # Verify order status transitioned to delivered
        self.order_single.refresh_from_db()
        self.assertEqual(self.order_single.status, OrderStateMachine.DELIVERED)

    def test_order_delivered_multi_shipment_partial(self):
        """Test order.delivered with multi-shipment - only one delivered, order stays shipped"""
        # Set order to shipped
        self.order_multi.status = OrderStateMachine.SHIPPED
        self.order_multi.save()
        self.shipment_multi_1.status = 'posted'
        self.shipment_multi_1.save()
        self.shipment_multi_2.status = 'posted'
        self.shipment_multi_2.save()

        payload = {
            'event': 'order.delivered',
            'data': {
                'id': 'ME-MULTI-001',
                'delivered_at': '2026-02-15T14:30:00Z'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify first shipment delivered
        self.shipment_multi_1.refresh_from_db()
        self.assertEqual(self.shipment_multi_1.status, 'delivered')

        # Verify order stays shipped (not all shipments delivered)
        self.order_multi.refresh_from_db()
        self.assertEqual(self.order_multi.status, OrderStateMachine.SHIPPED)

    def test_order_delivered_multi_shipment_all_delivered(self):
        """Test order.delivered when all shipments delivered transitions order to delivered"""
        # Set order to shipped and shipments to posted
        self.order_multi.status = OrderStateMachine.SHIPPED
        self.order_multi.save()
        self.shipment_multi_1.status = 'posted'
        self.shipment_multi_1.save()
        self.shipment_multi_2.status = 'posted'
        self.shipment_multi_2.save()

        # Deliver first shipment
        payload1 = {
            'event': 'order.delivered',
            'data': {
                'id': 'ME-MULTI-001',
                'delivered_at': '2026-02-15T14:30:00Z'
            }
        }
        self.client.post(self.webhook_url, data=payload1, format='json')

        # Deliver second shipment
        payload2 = {
            'event': 'order.delivered',
            'data': {
                'id': 'ME-MULTI-002',
                'delivered_at': '2026-02-15T15:00:00Z'
            }
        }
        response = self.client.post(self.webhook_url, data=payload2, format='json')

        self.assertEqual(response.status_code, 200)

        # Verify both shipments delivered
        self.shipment_multi_1.refresh_from_db()
        self.shipment_multi_2.refresh_from_db()
        self.assertEqual(self.shipment_multi_1.status, 'delivered')
        self.assertEqual(self.shipment_multi_2.status, 'delivered')

        # Verify order transitioned to delivered
        self.order_multi.refresh_from_db()
        self.assertEqual(self.order_multi.status, OrderStateMachine.DELIVERED)

    def test_order_cancelled_event(self):
        """Test order.cancelled event updates shipment status"""
        payload = {
            'event': 'order.cancelled',
            'data': {
                'id': 'ME-SINGLE-001'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify shipment status updated to cancelled
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.status, 'cancelled')

    def test_order_paused_event(self):
        """Test order.paused event updates shipment status to in_transit"""
        self.shipment_single.status = 'posted'
        self.shipment_single.save()

        payload = {
            'event': 'order.paused',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify shipment status updated
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.status, 'in_transit')

    def test_tracking_code_update(self):
        """Test tracking code is updated when provided in webhook data"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR999999999XX'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify tracking code updated
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.melhorenvio_tracking_code, 'BR999999999XX')

    def test_posted_at_timestamp_update(self):
        """Test posted_at timestamp is set on order.posted event"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'posted_at': '2026-02-11T12:34:56Z'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify posted_at timestamp set
        self.shipment_single.refresh_from_db()
        self.assertIsNotNone(self.shipment_single.posted_at)

    def test_delivered_at_timestamp_update(self):
        """Test delivered_at timestamp is set on order.delivered event"""
        self.shipment_single.status = 'posted'
        self.shipment_single.save()

        payload = {
            'event': 'order.delivered',
            'data': {
                'id': 'ME-SINGLE-001',
                'delivered_at': '2026-02-15T16:45:30Z'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify delivered_at timestamp set
        self.shipment_single.refresh_from_db()
        self.assertIsNotNone(self.shipment_single.delivered_at)

    def test_unknown_shipment_returns_200(self):
        """Test webhook returns 200 for unknown shipment (test connection)"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'UNKNOWN-SHIPMENT-ID'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        # Should return 200 to not fail Melhor Envio connection test
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['processed'])
        self.assertIn('não encontrado', response.data['message'])

    def test_unknown_event_ignored(self):
        """Test unknown event type is ignored gracefully"""
        payload = {
            'event': 'order.unknown_event',
            'data': {
                'id': 'ME-SINGLE-001'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('não processado', response.data['message'])

        # Verify shipment status not changed
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.status, 'pending')

    @patch('django.conf.settings.MELHOR_ENVIO_WEBHOOK_SECRET', 'test-secret')
    def test_valid_signature_processed(self):
        """Test webhook with valid HMAC signature is processed"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX'
            }
        }

        # Create valid signature
        body = json.dumps(payload).encode('utf-8')
        signature = hmac.new(
            b'test-secret',
            body,
            hashlib.sha256
        ).hexdigest()

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_ME_SIGNATURE=signature
        )

        self.assertEqual(response.status_code, 200)
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.status, 'posted')

    @patch('logistics.views.logger')
    @patch('django.conf.settings.MELHOR_ENVIO_WEBHOOK_SECRET', 'test-secret')
    def test_invalid_signature_logs_warning_but_processes(self, mock_logger):
        """Test webhook with invalid signature logs warning but still processes"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX'
            }
        }

        # Use invalid signature
        invalid_signature = 'invalid-signature-here'

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_ME_SIGNATURE=invalid_signature
        )

        # Should still process (returns 200)
        self.assertEqual(response.status_code, 200)

        # Verify warning was logged
        mock_logger.warning.assert_called()
        warning_calls = [call[0][0] for call in mock_logger.warning.call_args_list]
        self.assertTrue(
            any('assinatura' in call.lower() for call in warning_calls),
            "Expected warning about invalid signature"
        )

        # Verify shipment was still processed
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.status, 'posted')

    def test_no_signature_header_logs_info(self):
        """Test webhook without signature header logs info"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001'
            }
        }

        with patch('logistics.views.logger') as mock_logger:
            response = self.client.post(
                self.webhook_url,
                data=payload,
                format='json'
            )

            self.assertEqual(response.status_code, 200)
            # Should log that no signature was provided
            mock_logger.info.assert_called()

    def test_order_state_machine_integration(self):
        """Test OrderStateMachine is called correctly for transitions"""
        # Set order to processing
        self.order_single.status = OrderStateMachine.PROCESSING
        self.order_single.save()

        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify order transitioned
        self.order_single.refresh_from_db()
        self.assertEqual(self.order_single.status, OrderStateMachine.SHIPPED)

        # Verify audit trail created
        self.assertTrue(
            OrderStatusHistory.objects.filter(
                order=self.order_single,
                old_status=OrderStateMachine.PROCESSING,
                new_status=OrderStateMachine.SHIPPED
            ).exists()
        )

    def test_order_transition_blocked_if_invalid(self):
        """Test order transition is silently skipped if state machine doesn't allow it"""
        # Set order to delivered (terminal state)
        self.order_single.status = OrderStateMachine.DELIVERED
        self.order_single.save()

        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        # Should still return 200
        self.assertEqual(response.status_code, 200)

        # Verify shipment was updated
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.status, 'posted')

        # But order status should not change (can_transition check prevents it)
        self.order_single.refresh_from_db()
        self.assertEqual(self.order_single.status, OrderStateMachine.DELIVERED)

        # Verify order_transitioned flag is False
        self.assertFalse(response.data['order_transitioned'])

    def test_audit_trail_notes_webhook_source(self):
        """Test audit trail notes indicate webhook as source"""
        self.order_single.status = OrderStateMachine.PROCESSING
        self.order_single.save()

        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify audit trail mentions webhook
        history = OrderStatusHistory.objects.filter(order=self.order_single).latest('created_at')
        self.assertIn('webhook', history.notes.lower())
        self.assertIn('melhor envio', history.notes.lower())

    def test_response_includes_transition_status(self):
        """Test response indicates whether order was transitioned"""
        self.order_single.status = OrderStateMachine.PROCESSING
        self.order_single.save()

        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001'
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=payload,
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['order_transitioned'])
        self.assertEqual(response.data['order_status'], OrderStateMachine.SHIPPED)
        self.assertEqual(response.data['shipment_status'], 'posted')

    # =================== OrderDelivery update tests ===================

    def _create_order_delivery_for_shipment(self, shipment, initial_status='confirmed'):
        """Helper: creates an OrderDelivery linked to the given shipment."""
        return OrderDelivery.objects.create(
            order=shipment.order,
            seller=shipment.seller,
            delivery_method=DeliveryMethod.SHIPPING,
            status=initial_status,
            shipment=shipment,
            delivery_cost=shipment.shipping_cost,
        )

    def test_webhook_updates_order_delivery_status_to_in_transit_on_posted(self):
        """Webhook order.posted should update linked OrderDelivery status to in_transit"""
        order_delivery = self._create_order_delivery_for_shipment(
            self.shipment_single, initial_status='confirmed'
        )

        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX',
                'posted_at': '2026-02-11T10:00:00Z'
            }
        }

        response = self.client.post(self.webhook_url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)

        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'in_transit')

    def test_webhook_updates_order_delivery_status_to_delivered(self):
        """Webhook order.delivered should update linked OrderDelivery status to delivered"""
        self.order_single.status = OrderStateMachine.SHIPPED
        self.order_single.save()
        self.shipment_single.status = 'posted'
        self.shipment_single.save()

        order_delivery = self._create_order_delivery_for_shipment(
            self.shipment_single, initial_status='in_transit'
        )

        payload = {
            'event': 'order.delivered',
            'data': {
                'id': 'ME-SINGLE-001',
                'delivered_at': '2026-02-15T14:30:00Z'
            }
        }

        response = self.client.post(self.webhook_url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)

        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'delivered')
        self.assertIsNotNone(order_delivery.completed_at)

    def test_webhook_updates_order_delivery_status_to_cancelled(self):
        """Webhook order.cancelled should update linked OrderDelivery status to cancelled"""
        order_delivery = self._create_order_delivery_for_shipment(
            self.shipment_single, initial_status='confirmed'
        )

        payload = {
            'event': 'order.cancelled',
            'data': {
                'id': 'ME-SINGLE-001'
            }
        }

        response = self.client.post(self.webhook_url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)

        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'cancelled')

    def test_webhook_does_not_fail_when_shipment_has_no_order_delivery(self):
        """Webhook should process normally when Shipment has no linked OrderDelivery"""
        # shipment_single has no OrderDelivery - ensure no DoesNotExist exception propagates
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX',
            }
        }

        response = self.client.post(self.webhook_url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)
        # Shipment should still be updated
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.status, 'posted')

    # =================== DeliveryStatusLog creation tests ===================

    def test_webhook_creates_delivery_status_log_on_status_change(self):
        """Webhook should create a DeliveryStatusLog when OrderDelivery status changes"""
        order_delivery = self._create_order_delivery_for_shipment(
            self.shipment_single, initial_status='confirmed'
        )

        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX',
                'posted_at': '2026-02-11T10:00:00Z'
            }
        }

        response = self.client.post(self.webhook_url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)

        # Exactly one DeliveryStatusLog should be created
        logs = DeliveryStatusLog.objects.filter(order_delivery=order_delivery)
        self.assertEqual(logs.count(), 1)

        log = logs.first()
        self.assertEqual(log.from_status, 'confirmed')
        self.assertEqual(log.to_status, 'in_transit')
        self.assertIsNone(log.changed_by)  # webhook has no user
        self.assertIn('webhook', log.notes.lower())
        self.assertIn('melhor envio', log.notes.lower())

    def test_webhook_log_metadata_contains_event_info(self):
        """DeliveryStatusLog metadata should contain event details"""
        order_delivery = self._create_order_delivery_for_shipment(
            self.shipment_single, initial_status='confirmed'
        )

        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX',
                'tracking_url': 'https://www.melhorrastreio.com.br/rastreio/BR123456789XX',
            }
        }

        self.client.post(self.webhook_url, data=payload, format='json')

        log = DeliveryStatusLog.objects.filter(order_delivery=order_delivery).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('event'), 'order.posted')
        self.assertEqual(log.metadata.get('melhorenvio_order_id'), 'ME-SINGLE-001')
        self.assertEqual(log.metadata.get('tracking'), 'BR123456789XX')

    def test_webhook_does_not_create_log_when_no_order_delivery(self):
        """No DeliveryStatusLog should be created when Shipment has no OrderDelivery"""
        initial_log_count = DeliveryStatusLog.objects.count()

        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX',
            }
        }

        self.client.post(self.webhook_url, data=payload, format='json')

        # No new log created (no OrderDelivery exists)
        self.assertEqual(DeliveryStatusLog.objects.count(), initial_log_count)

    def test_webhook_does_not_create_log_when_status_unchanged(self):
        """No DeliveryStatusLog when OrderDelivery status does not change"""
        # Set OrderDelivery already at in_transit (same as what posted maps to)
        order_delivery = self._create_order_delivery_for_shipment(
            self.shipment_single, initial_status='in_transit'
        )

        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX',
            }
        }

        self.client.post(self.webhook_url, data=payload, format='json')

        logs = DeliveryStatusLog.objects.filter(order_delivery=order_delivery)
        self.assertEqual(logs.count(), 0)

    # =================== ShipmentTracking creation tests ===================

    def test_webhook_creates_shipment_tracking_when_tracking_code_present(self):
        """Webhook should create ShipmentTracking entry when tracking code is in payload"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX',
                'posted_at': '2026-02-11T10:00:00Z'
            }
        }

        response = self.client.post(self.webhook_url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)

        tracking_entries = ShipmentTracking.objects.filter(shipment=self.shipment_single)
        self.assertEqual(tracking_entries.count(), 1)

        entry = tracking_entries.first()
        self.assertEqual(entry.status, 'posted')
        self.assertIn('postada', entry.description.lower())
        self.assertIsNotNone(entry.occurred_at)

    def test_webhook_creates_shipment_tracking_with_tracking_url_only(self):
        """ShipmentTracking should be created even when only tracking_url is present"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': None,
                'tracking_url': 'https://www.melhorrastreio.com.br/rastreio/BR999',
            }
        }

        self.client.post(self.webhook_url, data=payload, format='json')

        tracking_entries = ShipmentTracking.objects.filter(shipment=self.shipment_single)
        self.assertEqual(tracking_entries.count(), 1)

        entry = tracking_entries.first()
        self.assertIn('melhorrastreio', entry.description.lower())

    def test_webhook_does_not_create_shipment_tracking_when_no_tracking_data(self):
        """No ShipmentTracking should be created when payload has no tracking data"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                # No 'tracking', 'self_tracking', or 'tracking_url'
            }
        }

        self.client.post(self.webhook_url, data=payload, format='json')

        tracking_entries = ShipmentTracking.objects.filter(shipment=self.shipment_single)
        self.assertEqual(tracking_entries.count(), 0)

    def test_webhook_shipment_tracking_uses_posted_at_timestamp(self):
        """ShipmentTracking occurred_at should use posted_at from payload for posted events"""
        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX',
                'posted_at': '2026-02-11T10:00:00Z'
            }
        }

        self.client.post(self.webhook_url, data=payload, format='json')

        entry = ShipmentTracking.objects.filter(shipment=self.shipment_single).first()
        self.assertIsNotNone(entry)
        # occurred_at should match posted_at from payload (2026-02-11T10:00:00Z)
        self.assertEqual(entry.occurred_at.year, 2026)
        self.assertEqual(entry.occurred_at.month, 2)
        self.assertEqual(entry.occurred_at.day, 11)

    def test_webhook_shipment_tracking_uses_delivered_at_timestamp(self):
        """ShipmentTracking occurred_at should use delivered_at from payload for delivered events"""
        self.order_single.status = OrderStateMachine.SHIPPED
        self.order_single.save()
        self.shipment_single.status = 'posted'
        self.shipment_single.save()

        payload = {
            'event': 'order.delivered',
            'data': {
                'id': 'ME-SINGLE-001',
                'tracking': 'BR123456789XX',
                'delivered_at': '2026-02-15T14:30:00Z'
            }
        }

        self.client.post(self.webhook_url, data=payload, format='json')

        entry = ShipmentTracking.objects.filter(
            shipment=self.shipment_single,
            status='delivered'
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.occurred_at.year, 2026)
        self.assertEqual(entry.occurred_at.month, 2)
        self.assertEqual(entry.occurred_at.day, 15)

    def test_webhook_full_payload_creates_all_records(self):
        """Full webhook payload should update Shipment, OrderDelivery, create DeliveryStatusLog and ShipmentTracking"""
        order_delivery = self._create_order_delivery_for_shipment(
            self.shipment_single, initial_status='confirmed'
        )

        payload = {
            'event': 'order.posted',
            'data': {
                'id': 'ME-SINGLE-001',
                'protocol': 'ORD-2026XXXXXXXXXX',
                'status': 'posted',
                'tracking': 'BR123456789XX',
                'self_tracking': None,
                'user_id': '0000111',
                'tags': [{'tag': 'tag1', 'url': 'www.url1.com'}],
                'created_at': '2024-03-29T23:49:26+00:00',
                'paid_at': None,
                'generated_at': None,
                'posted_at': '2026-02-11T10:00:00+00:00',
                'delivered_at': None,
                'canceled_at': None,
                'expired_at': None,
                'tracking_url': 'https://www.melhorrastreio.com.br/rastreio/BR123456789XX'
            }
        }

        response = self.client.post(self.webhook_url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)

        # 1. Shipment updated
        self.shipment_single.refresh_from_db()
        self.assertEqual(self.shipment_single.status, 'posted')
        self.assertEqual(self.shipment_single.melhorenvio_tracking_code, 'BR123456789XX')
        self.assertEqual(self.shipment_single.tracking_url, 'https://www.melhorrastreio.com.br/rastreio/BR123456789XX')
        self.assertIsNotNone(self.shipment_single.posted_at)

        # 2. OrderDelivery updated
        order_delivery.refresh_from_db()
        self.assertEqual(order_delivery.status, 'in_transit')

        # 3. DeliveryStatusLog created
        log = DeliveryStatusLog.objects.filter(order_delivery=order_delivery).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.from_status, 'confirmed')
        self.assertEqual(log.to_status, 'in_transit')

        # 4. ShipmentTracking created
        tracking = ShipmentTracking.objects.filter(shipment=self.shipment_single).first()
        self.assertIsNotNone(tracking)
        self.assertEqual(tracking.status, 'posted')
