"""
Tests for OrderStateMachine

Tests state transitions, validation, and audit trail.
"""

import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal

from orders.models import Order, OrderStatusHistory
from orders.services import OrderStateMachine, OrderStatusTransitionError

User = get_user_model()


@pytest.mark.django_db
class TestOrderStateMachine(TestCase):
    """Test cases for OrderStateMachine"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )

        self.order = Order.objects.create(
            buyer=self.user,
            status=OrderStateMachine.PENDING_PAYMENT,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('10.00'),
            total=Decimal('110.00'),
            shipping_address={'street': 'Test St', 'city': 'Test City'},
            payment_method='credit_card'
        )

    def test_valid_transition_pending_to_paid(self):
        """Test valid transition from PENDING_PAYMENT to PAID"""
        self.assertTrue(
            OrderStateMachine.can_transition(
                OrderStateMachine.PENDING_PAYMENT,
                OrderStateMachine.PAID
            )
        )

    def test_valid_transition_pending_to_failed(self):
        """Test valid transition from PENDING_PAYMENT to FAILED"""
        self.assertTrue(
            OrderStateMachine.can_transition(
                OrderStateMachine.PENDING_PAYMENT,
                OrderStateMachine.FAILED
            )
        )

    def test_invalid_transition_pending_to_delivered(self):
        """Test invalid transition from PENDING_PAYMENT to DELIVERED"""
        self.assertFalse(
            OrderStateMachine.can_transition(
                OrderStateMachine.PENDING_PAYMENT,
                OrderStateMachine.DELIVERED
            )
        )

    def test_validate_transition_success(self):
        """Test validate_transition with valid transition"""
        try:
            OrderStateMachine.validate_transition(
                OrderStateMachine.PENDING_PAYMENT,
                OrderStateMachine.PAID,
                is_payment_system=True
            )
        except OrderStatusTransitionError:
            self.fail("validate_transition raised OrderStatusTransitionError unexpectedly")

    def test_validate_transition_invalid(self):
        """Test validate_transition with invalid transition"""
        with self.assertRaises(OrderStatusTransitionError):
            OrderStateMachine.validate_transition(
                OrderStateMachine.DELIVERED,
                OrderStateMachine.PENDING_PAYMENT
            )

    def test_payment_only_transition_requires_payment_system(self):
        """Test that payment-only transitions require is_payment_system=True"""
        with self.assertRaises(OrderStatusTransitionError) as context:
            OrderStateMachine.validate_transition(
                OrderStateMachine.PENDING_PAYMENT,
                OrderStateMachine.PAID,
                is_payment_system=False
            )

        self.assertIn('payment system', str(context.exception).lower())

    def test_transition_to_success(self):
        """Test successful state transition with audit trail"""
        history = OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.PAID,
            changed_by=self.user,
            notes='Payment confirmed',
            is_payment_system=True
        )

        # Refresh order from database
        self.order.refresh_from_db()

        # Check order status updated
        self.assertEqual(self.order.status, OrderStateMachine.PAID)

        # Check history created
        self.assertIsNotNone(history)
        self.assertEqual(history.old_status, OrderStateMachine.PENDING_PAYMENT)
        self.assertEqual(history.new_status, OrderStateMachine.PAID)
        self.assertEqual(history.changed_by, self.user)

    def test_transition_to_invalid_raises_error(self):
        """Test that invalid transition raises error"""
        with self.assertRaises(OrderStatusTransitionError):
            OrderStateMachine.transition_to(
                order=self.order,
                new_status=OrderStateMachine.DELIVERED,
                changed_by=self.user
            )

    def test_transition_updates_cancelled_at(self):
        """Test that cancellation sets cancelled_at timestamp"""
        OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.CANCELED,
            changed_by=self.user
        )

        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.cancelled_at)

    def test_get_available_transitions(self):
        """Test getting available transitions for a status"""
        transitions = OrderStateMachine.get_available_transitions(
            OrderStateMachine.PENDING_PAYMENT
        )

        self.assertIn(OrderStateMachine.PAID, transitions)
        self.assertIn(OrderStateMachine.FAILED, transitions)
        self.assertIn(OrderStateMachine.CANCELED, transitions)

    def test_is_terminal_state_delivered(self):
        """Test that DELIVERED is a terminal state"""
        self.assertTrue(OrderStateMachine.is_terminal_state(OrderStateMachine.DELIVERED))

    def test_is_terminal_state_paid(self):
        """Test that PAID is not a terminal state"""
        self.assertFalse(OrderStateMachine.is_terminal_state(OrderStateMachine.PAID))

    def test_complete_workflow_success(self):
        """Test complete successful order workflow"""
        # PENDING_PAYMENT → PAID
        OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.PAID,
            is_payment_system=True
        )

        # PAID → PROCESSING
        OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.PROCESSING,
            changed_by=self.user
        )

        # PROCESSING → SHIPPED
        OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.SHIPPED,
            changed_by=self.user
        )

        # SHIPPED → DELIVERED
        OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.DELIVERED,
            changed_by=self.user
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStateMachine.DELIVERED)

        # Check history records
        history_count = OrderStatusHistory.objects.filter(order=self.order).count()
        self.assertEqual(history_count, 4)

    def test_complete_workflow_payment_failure(self):
        """Test workflow when payment fails"""
        # PENDING_PAYMENT → FAILED
        OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.FAILED,
            is_payment_system=True,
            notes='Payment declined'
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStateMachine.FAILED)

        # Verify terminal state
        self.assertTrue(OrderStateMachine.is_terminal_state(self.order.status))

    def test_complete_workflow_cancellation(self):
        """Test workflow with order cancellation"""
        # PENDING_PAYMENT → CANCELED
        OrderStateMachine.transition_to(
            order=self.order,
            new_status=OrderStateMachine.CANCELED,
            changed_by=self.user,
            notes='User cancelled order'
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStateMachine.CANCELED)
        self.assertIsNotNone(self.order.cancelled_at)
