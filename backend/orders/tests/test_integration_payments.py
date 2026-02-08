"""
Integration tests for Orders and Payments apps

Tests the callback mechanism and state transitions triggered by payment events.
"""

import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal

from orders.models import Order, OrderItem, OrderStatusHistory
from orders.services import (
    OrderStateMachine,
    PaymentCallbackService,
    PaymentCallbackError
)

User = get_user_model()


@pytest.mark.django_db
class TestOrdersPaymentsIntegration(TestCase):
    """Test integration between orders and payments apps"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='buyer@example.com',
            password='testpass123',
            first_name='Test',
            last_name='Buyer'
        )

        self.order = Order.objects.create(
            buyer=self.user,
            status=OrderStateMachine.PENDING_PAYMENT,
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('20.00'),
            total=Decimal('220.00'),
            shipping_address={'street': 'Test St', 'city': 'Test City'},
            payment_method='credit_card'
        )

    def test_on_payment_succeeded_updates_order_status(self):
        """Test that payment success callback updates order to PAID"""
        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_123',
            metadata={'test': 'data'}
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStateMachine.PAID)

    def test_on_payment_succeeded_creates_history(self):
        """Test that payment success creates audit trail"""
        initial_count = OrderStatusHistory.objects.filter(order=self.order).count()

        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_123'
        )

        new_count = OrderStatusHistory.objects.filter(order=self.order).count()
        self.assertEqual(new_count, initial_count + 1)

        # Check history details
        history = OrderStatusHistory.objects.filter(order=self.order).latest('created_at')
        self.assertEqual(history.old_status, OrderStateMachine.PENDING_PAYMENT)
        self.assertEqual(history.new_status, OrderStateMachine.PAID)
        self.assertIn('pi_test_123', history.notes)

    def test_on_payment_failed_updates_order_status(self):
        """Test that payment failure callback updates order to FAILED"""
        PaymentCallbackService.on_payment_failed(
            order=self.order,
            payment_intent_id='pi_test_123',
            failure_message='Card declined'
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStateMachine.FAILED)

    def test_on_payment_failed_includes_failure_message(self):
        """Test that failure message is included in history"""
        failure_msg = 'Insufficient funds'

        PaymentCallbackService.on_payment_failed(
            order=self.order,
            payment_intent_id='pi_test_123',
            failure_message=failure_msg
        )

        history = OrderStatusHistory.objects.filter(order=self.order).latest('created_at')
        self.assertIn(failure_msg, history.notes)

    def test_on_payment_canceled_updates_order_status(self):
        """Test that payment cancellation callback updates order to CANCELED"""
        PaymentCallbackService.on_payment_canceled(
            order=self.order,
            payment_intent_id='pi_test_123',
            cancellation_reason='User cancelled'
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStateMachine.CANCELED)
        self.assertIsNotNone(self.order.cancelled_at)

    def test_on_refund_processed_updates_order_status(self):
        """Test that refund callback updates order to REFUNDED"""
        # First move order to PAID
        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_123'
        )

        # Then process refund
        PaymentCallbackService.on_refund_processed(
            order=self.order,
            refund_amount=220.00,
            refund_reason='Product defect'
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStateMachine.REFUNDED)

    def test_invalid_transition_raises_error(self):
        """Test that invalid state transition raises error"""
        # Try to transition to PAID from DELIVERED (invalid)
        self.order.status = OrderStateMachine.DELIVERED
        self.order.save()

        with self.assertRaises(PaymentCallbackError):
            PaymentCallbackService.on_payment_succeeded(
                order=self.order,
                payment_intent_id='pi_test_123'
            )

    def test_callback_is_idempotent(self):
        """Test that calling callback twice doesn't break"""
        # First call
        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_123'
        )

        initial_status = self.order.status

        # Second call should raise error (can't transition from PAID to PAID)
        with self.assertRaises(PaymentCallbackError):
            PaymentCallbackService.on_payment_succeeded(
                order=self.order,
                payment_intent_id='pi_test_123'
            )

        # Status should remain unchanged
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, initial_status)

    def test_payment_system_can_trigger_restricted_transitions(self):
        """Test that payment system can trigger payment-only transitions"""
        # This should succeed because is_payment_system=True internally
        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_123'
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStateMachine.PAID)

    def test_complete_payment_workflow(self):
        """Test complete payment workflow from pending to delivered"""
        # Step 1: Payment succeeds
        PaymentCallbackService.on_payment_succeeded(
            order=self.order,
            payment_intent_id='pi_test_123'
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStateMachine.PAID)

        # Step 2: Seller processes order
        OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.PROCESSING,
            changed_by=self.user,
            notes='Order being prepared'
        )

        # Step 3: Order is shipped
        OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.SHIPPED,
            changed_by=self.user,
            notes='Order shipped via courier'
        )

        # Step 4: Order is delivered
        OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.DELIVERED,
            changed_by=self.user,
            notes='Delivered successfully'
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStateMachine.DELIVERED)

        # Verify history trail
        history = OrderStatusHistory.objects.filter(order=self.order).order_by('created_at')
        statuses = [h.new_status for h in history]

        expected_flow = [
            OrderStateMachine.PAID,
            OrderStateMachine.PROCESSING,
            OrderStateMachine.SHIPPED,
            OrderStateMachine.DELIVERED
        ]

        self.assertEqual(statuses, expected_flow)
