"""
Payment Callback Service

Handles callbacks from the payments app when payment events occur.
This provides a clean interface for the payments app to update order status
without tight coupling or circular dependencies.
"""

import logging
from django.db import transaction

from .order_state_machine import OrderStateMachine, OrderStatusTransitionError
from .order_creation_service import OrderCreationService

logger = logging.getLogger(__name__)


class PaymentCallbackError(Exception):
    """Raised when payment callback processing fails"""
    pass


class PaymentCallbackService:
    """
    Service for handling payment system callbacks.

    This service is called by the payments app webhook service when
    payment events occur. It ensures proper order state transitions
    and stock management based on payment status.
    """

    @staticmethod
    @transaction.atomic
    def on_payment_succeeded(order, payment_intent_id: str, metadata: dict = None):
        """
        Handle successful payment notification from payment system.

        This is called by webhook service when payment_intent.succeeded event occurs.

        Args:
            order: Order instance
            payment_intent_id: Stripe Payment Intent ID
            metadata: Additional metadata from payment system

        Raises:
            PaymentCallbackError: If processing fails
        """
        logger.info(
            f"Processing payment success for order {order.order_number}",
            extra={
                'order_id': str(order.id),
                'order_number': order.order_number,
                'payment_intent_id': payment_intent_id,
                'current_status': order.status,
            }
        )

        try:
            # Transition order to PAID status
            OrderStateMachine.transition_to(
                order=order,
                new_status=OrderStateMachine.PAID,
                changed_by=None,  # System event
                notes=f'Payment confirmed via Stripe PaymentIntent {payment_intent_id}',
                is_payment_system=True,
                metadata=metadata
            )

            # Reserve stock if using on_payment strategy
            if OrderCreationService.STOCK_STRATEGY == 'on_payment':
                OrderCreationService.confirm_payment_and_reserve_stock(order)

            # Trigger Melhor Envio checkout now that payment is confirmed
            try:
                from logistics.services.shipment_creation_service import ShipmentCreationService
                ShipmentCreationService.checkout_shipments_for_order(order)
                logger.info(
                    f"ME checkout triggered automatically for order {order.order_number}",
                    extra={'order_id': str(order.id)}
                )
            except Exception as e:
                # ME checkout failure must not roll back the PAID transition
                logger.error(
                    f"ME checkout failed for order {order.order_number}: {str(e)}",
                    extra={'order_id': str(order.id)},
                    exc_info=True
                )

            logger.info(
                f"Payment succeeded processed for order {order.order_number}",
                extra={
                    'order_id': str(order.id),
                    'new_status': order.status,
                }
            )

        except OrderStatusTransitionError as e:
            logger.error(
                f"Invalid state transition for payment success: {str(e)}",
                extra={
                    'order_id': str(order.id),
                    'current_status': order.status,
                    'target_status': OrderStateMachine.PAID,
                },
                exc_info=True
            )
            raise PaymentCallbackError(f"State transition failed: {str(e)}")

        except Exception as e:
            logger.error(
                f"Error processing payment success: {str(e)}",
                extra={
                    'order_id': str(order.id),
                    'payment_intent_id': payment_intent_id,
                },
                exc_info=True
            )
            raise PaymentCallbackError(f"Payment success processing failed: {str(e)}")

    @staticmethod
    @transaction.atomic
    def on_payment_failed(order, payment_intent_id: str, failure_message: str = ''):
        """
        Handle failed payment notification from payment system.

        This is called by webhook service when payment_intent.payment_failed event occurs.

        Args:
            order: Order instance
            payment_intent_id: Stripe Payment Intent ID
            failure_message: Failure reason from payment system

        Raises:
            PaymentCallbackError: If processing fails
        """
        logger.warning(
            f"Processing payment failure for order {order.order_number}",
            extra={
                'order_id': str(order.id),
                'order_number': order.order_number,
                'payment_intent_id': payment_intent_id,
                'failure_message': failure_message,
            }
        )

        try:
            # Transition order to FAILED status
            OrderStateMachine.transition_to(
                order=order,
                new_status=OrderStateMachine.FAILED,
                changed_by=None,  # System event
                notes=f'Payment failed: {failure_message}',
                is_payment_system=True
            )

            # Release stock if it was reserved
            if OrderCreationService.STOCK_STRATEGY == 'immediate':
                # Stock was already decremented, need to release it
                for item in order.items.select_related('listing').all():
                    from .product_validation_service import ProductValidationService
                    ProductValidationService.release_stock(item.listing, item.quantity)

            logger.warning(
                f"Payment failure processed for order {order.order_number}",
                extra={
                    'order_id': str(order.id),
                    'new_status': order.status,
                }
            )

        except OrderStatusTransitionError as e:
            logger.error(
                f"Invalid state transition for payment failure: {str(e)}",
                extra={
                    'order_id': str(order.id),
                    'current_status': order.status,
                    'target_status': OrderStateMachine.FAILED,
                },
                exc_info=True
            )
            raise PaymentCallbackError(f"State transition failed: {str(e)}")

        except Exception as e:
            logger.error(
                f"Error processing payment failure: {str(e)}",
                extra={
                    'order_id': str(order.id),
                    'payment_intent_id': payment_intent_id,
                },
                exc_info=True
            )
            raise PaymentCallbackError(f"Payment failure processing failed: {str(e)}")

    @staticmethod
    @transaction.atomic
    def on_payment_canceled(order, payment_intent_id: str, cancellation_reason: str = ''):
        """
        Handle payment cancellation notification from payment system.

        This is called by webhook service when payment_intent.canceled event occurs.

        Args:
            order: Order instance
            payment_intent_id: Stripe Payment Intent ID
            cancellation_reason: Reason for cancellation

        Raises:
            PaymentCallbackError: If processing fails
        """
        logger.info(
            f"Processing payment cancellation for order {order.order_number}",
            extra={
                'order_id': str(order.id),
                'order_number': order.order_number,
                'payment_intent_id': payment_intent_id,
                'reason': cancellation_reason,
            }
        )

        try:
            # Transition order to CANCELED status
            OrderStateMachine.transition_to(
                order=order,
                new_status=OrderStateMachine.CANCELED,
                changed_by=None,  # System event
                notes=f'Payment cancelled: {cancellation_reason}',
                is_payment_system=True
            )

            # Release stock if it was reserved
            if OrderCreationService.STOCK_STRATEGY == 'immediate':
                for item in order.items.select_related('listing').all():
                    from .product_validation_service import ProductValidationService
                    ProductValidationService.release_stock(item.listing, item.quantity)

            logger.info(
                f"Payment cancellation processed for order {order.order_number}",
                extra={
                    'order_id': str(order.id),
                    'new_status': order.status,
                }
            )

        except OrderStatusTransitionError as e:
            logger.error(
                f"Invalid state transition for payment cancellation: {str(e)}",
                extra={
                    'order_id': str(order.id),
                    'current_status': order.status,
                    'target_status': OrderStateMachine.CANCELED,
                },
                exc_info=True
            )
            raise PaymentCallbackError(f"State transition failed: {str(e)}")

        except Exception as e:
            logger.error(
                f"Error processing payment cancellation: {str(e)}",
                extra={
                    'order_id': str(order.id),
                    'payment_intent_id': payment_intent_id,
                },
                exc_info=True
            )
            raise PaymentCallbackError(f"Payment cancellation processing failed: {str(e)}")

    @staticmethod
    def on_refund_processed(order, refund_amount: float, refund_reason: str = ''):
        """
        Handle refund notification from payment system.

        This is called when a refund is successfully processed.

        Args:
            order: Order instance
            refund_amount: Amount refunded
            refund_reason: Reason for refund

        Raises:
            PaymentCallbackError: If processing fails
        """
        logger.info(
            f"Processing refund for order {order.order_number}",
            extra={
                'order_id': str(order.id),
                'order_number': order.order_number,
                'refund_amount': refund_amount,
                'reason': refund_reason,
            }
        )

        try:
            # Transition order to REFUNDED status
            OrderStateMachine.transition_to(
                order=order,
                new_status=OrderStateMachine.REFUNDED,
                changed_by=None,  # System event
                notes=f'Refund processed: ${refund_amount}. Reason: {refund_reason}',
                is_payment_system=True
            )

            logger.info(
                f"Refund processed for order {order.order_number}",
                extra={
                    'order_id': str(order.id),
                    'new_status': order.status,
                }
            )

        except Exception as e:
            logger.error(
                f"Error processing refund: {str(e)}",
                extra={
                    'order_id': str(order.id),
                    'refund_amount': refund_amount,
                },
                exc_info=True
            )
            raise PaymentCallbackError(f"Refund processing failed: {str(e)}")
