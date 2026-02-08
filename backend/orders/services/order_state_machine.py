"""
Order State Machine

Implements deterministic state transitions for orders with validation and audit trail.
This ensures order status changes are authorized and traceable.
"""

import logging
from typing import Optional, Dict, List
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class OrderStatusTransitionError(Exception):
    """Raised when an invalid order status transition is attempted"""
    pass


class OrderStateMachine:
    """
    Manages order status transitions with validation and audit trail.

    State Machine Flow:
    -------------------
    PENDING_PAYMENT → PAID (payment confirmed via webhook)
    PENDING_PAYMENT → FAILED (payment failed via webhook)
    PENDING_PAYMENT → CANCELED (user/system cancellation)
    PAID → PROCESSING (seller starts processing)
    PAID → CANCELED (cancellation with refund required)
    PROCESSING → SHIPPED (seller ships order)
    SHIPPED → DELIVERED (delivery confirmed)
    PAID → REFUNDED (refund processed)
    PROCESSING → REFUNDED
    CANCELED → REFUNDED (if payment was made)

    Key Principles:
    ---------------
    - All transitions must be explicitly allowed
    - State changes are atomic and create audit trail
    - Only authorized actors can trigger specific transitions
    - Payment-driven transitions can only come from payment system
    """

    # Order status constants
    PENDING_PAYMENT = 'pending_payment'
    PAID = 'paid'
    PROCESSING = 'processing'
    SHIPPED = 'shipped'
    DELIVERED = 'delivered'
    CANCELED = 'cancelled'
    FAILED = 'failed'
    REFUNDED = 'refunded'

    # Valid status transitions
    # Format: current_status → [allowed_next_statuses]
    VALID_TRANSITIONS: Dict[str, List[str]] = {
        PENDING_PAYMENT: [PAID, FAILED, CANCELED],
        PAID: [PROCESSING, CANCELED, REFUNDED],
        PROCESSING: [SHIPPED, REFUNDED],
        SHIPPED: [DELIVERED],
        CANCELED: [REFUNDED],
        # Terminal states (no transitions allowed)
        DELIVERED: [],
        FAILED: [],
        REFUNDED: [],
    }

    # Transitions that can only be triggered by payment system
    PAYMENT_ONLY_TRANSITIONS = {
        (PENDING_PAYMENT, PAID),
        (PENDING_PAYMENT, FAILED),
    }

    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        """
        Check if a status transition is valid.

        Args:
            from_status: Current order status
            to_status: Target order status

        Returns:
            bool: True if transition is allowed, False otherwise
        """
        allowed_statuses = cls.VALID_TRANSITIONS.get(from_status, [])
        return to_status in allowed_statuses

    @classmethod
    def validate_transition(
        cls,
        from_status: str,
        to_status: str,
        is_payment_system: bool = False
    ) -> None:
        """
        Validate a status transition and raise exception if invalid.

        Args:
            from_status: Current order status
            to_status: Target order status
            is_payment_system: Whether this transition is from payment system

        Raises:
            OrderStatusTransitionError: If transition is not allowed
        """
        # Check if transition is valid
        if not cls.can_transition(from_status, to_status):
            raise OrderStatusTransitionError(
                f"Invalid transition from '{from_status}' to '{to_status}'. "
                f"Allowed transitions: {cls.VALID_TRANSITIONS.get(from_status, [])}"
            )

        # Check if this is a payment-only transition
        transition = (from_status, to_status)
        if transition in cls.PAYMENT_ONLY_TRANSITIONS and not is_payment_system:
            raise OrderStatusTransitionError(
                f"Transition from '{from_status}' to '{to_status}' can only be "
                f"triggered by the payment system (webhook events)"
            )

    @classmethod
    @transaction.atomic
    def transition_to(
        cls,
        order,
        new_status: str,
        changed_by=None,
        notes: str = '',
        is_payment_system: bool = False,
        metadata: Optional[Dict] = None
    ):
        """
        Transition order to new status with validation and audit trail.

        Args:
            order: Order instance
            new_status: Target status
            changed_by: User/system making the change (optional)
            notes: Additional notes about the transition
            is_payment_system: Whether this is a payment system transition
            metadata: Additional metadata to store (optional)

        Returns:
            OrderStatusHistory: Created history record

        Raises:
            OrderStatusTransitionError: If transition is invalid
        """
        from orders.models import OrderStatusHistory

        old_status = order.status

        # Validate transition
        cls.validate_transition(old_status, new_status, is_payment_system)

        logger.info(
            f"Transitioning order {order.order_number} from {old_status} to {new_status}",
            extra={
                'order_id': str(order.id),
                'order_number': order.order_number,
                'old_status': old_status,
                'new_status': new_status,
                'changed_by': str(changed_by) if changed_by else 'system',
                'is_payment_system': is_payment_system,
            }
        )

        # Update order status
        order.status = new_status

        # Update timestamps for specific statuses
        if new_status == cls.CANCELED:
            order.cancelled_at = timezone.now()

        order.save(update_fields=['status', 'cancelled_at', 'updated_at'])

        # Create audit trail
        history = OrderStatusHistory.objects.create(
            order=order,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            notes=notes or f"Status changed by {'payment system' if is_payment_system else 'user/system'}"
        )

        logger.info(
            f"Order {order.order_number} transitioned successfully",
            extra={
                'order_id': str(order.id),
                'history_id': history.id,
                'new_status': new_status,
            }
        )

        return history

    @classmethod
    def get_available_transitions(cls, current_status: str) -> List[str]:
        """
        Get list of available transitions from current status.

        Args:
            current_status: Current order status

        Returns:
            List of allowed target statuses
        """
        return cls.VALID_TRANSITIONS.get(current_status, [])

    @classmethod
    def is_terminal_state(cls, status: str) -> bool:
        """
        Check if a status is terminal (no more transitions allowed).

        Args:
            status: Order status to check

        Returns:
            bool: True if status is terminal
        """
        return len(cls.VALID_TRANSITIONS.get(status, [])) == 0
