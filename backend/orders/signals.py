"""
Order Signals

Handles automatic actions triggered by order state changes.
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings

from .models import Order, CartItem
from .services.order_state_machine import OrderStateMachine

logger = logging.getLogger(__name__)


@receiver(post_save, sender=CartItem)
@receiver(post_delete, sender=CartItem)
def invalidate_shipping_quotes_on_cart_change(sender, instance, **kwargs):
    """
    Invalidate shipping quotes when cart items are added or removed.

    If a buyer adds/removes items after calculating shipping, the existing
    quote no longer reflects the actual package dimensions and must be recalculated.
    Only the quote for the affected seller is invalidated.
    """
    from logistics.models import ShippingQuote

    try:
        user = instance.cart.user
        seller = instance.listing.seller
        deleted_count, _ = ShippingQuote.objects.filter(
            user=user,
            seller=seller
        ).delete()
        if deleted_count:
            logger.info(
                f"Invalidated {deleted_count} ShippingQuote(s) for "
                f"user={user.id} seller={seller.id} on cart change"
            )
    except Exception as e:
        logger.warning(f"Failed to invalidate shipping quotes on cart change: {e}")


@receiver(post_save, sender=Order)
def auto_create_shipments_on_payment(sender, instance, created, **kwargs):
    """
    Automatically create shipments when order payment is confirmed.

    This signal is triggered after an Order is saved. If the order status
    is PAID and no shipments exist yet, it will automatically create
    shipments for all sellers in the order.

    Args:
        sender: Order model class
        instance: Order instance that was saved
        created: Boolean indicating if this is a new object
        **kwargs: Additional keyword arguments
    """
    # Check feature flag
    auto_create_enabled = getattr(
        settings, 'AUTO_CREATE_SHIPMENTS', True
    )

    if not auto_create_enabled:
        logger.debug("Auto-create shipments is disabled via settings")
        return

    # Only process if order is PAID
    if instance.status != OrderStateMachine.PAID:
        return

    # Import here to avoid circular imports
    from logistics.models import OrderDelivery

    # Build delivery choices for this order, skipping sellers that already have
    # an OrderDelivery (in_person ones are created at order creation time).
    existing_seller_ids = set(
        OrderDelivery.objects.filter(order=instance).values_list('seller_id', flat=True)
    )

    # Auto-create shipments
    logger.info(
        f"Auto-creating shipments for order {instance.order_number}",
        extra={
            'order_id': str(instance.id),
            'order_number': instance.order_number,
            'status': instance.status
        }
    )

    try:
        # Import service here to avoid circular imports
        from logistics.services.delivery_orchestration_service import (
            DeliveryOrchestrationService
        )

        # Attempt to create shipments/deliveries
        # This will create OrderDelivery records based on order's shipping_services
        if instance.shipping_services:
            # Create deliveries for each seller that doesn't have one yet
            delivery_choices = []

            for seller_id, shipping_info in instance.shipping_services.items():
                if not isinstance(shipping_info, dict):
                    continue

                seller_id_int = int(seller_id)

                # Skip sellers whose OrderDelivery was already created at order creation
                if seller_id_int in existing_seller_ids:
                    logger.debug(
                        f"OrderDelivery already exists for seller {seller_id_int} "
                        f"in order {instance.order_number}, skipping."
                    )
                    continue

                delivery_method = shipping_info.get('delivery_method', 'shipping')

                if delivery_method == 'shipping':
                    delivery_choices.append({
                        'seller_id': seller_id_int,
                        'delivery_method': 'shipping',
                        'shipping_service_id': shipping_info.get('service_id'),
                        'delivery_cost': shipping_info.get('cost', 0)
                    })
                elif delivery_method == 'split':
                    # split: shipping OrderDelivery created here; in_person already created at order creation
                    shipping_sub = shipping_info.get('shipping', {})
                    delivery_choices.append({
                        'seller_id': seller_id_int,
                        'delivery_method': 'shipping',
                        'shipping_service_id': shipping_sub.get('service_id'),
                        'delivery_cost': shipping_sub.get('cost', 0),
                    })
                elif delivery_method == 'in_person':
                    # in_person already created at order creation — only as fallback
                    delivery_choices.append({
                        'seller_id': seller_id_int,
                        'delivery_method': 'in_person',
                        **shipping_info
                    })

            if delivery_choices:
                created_deliveries = DeliveryOrchestrationService.create_order_deliveries(
                    order=instance,
                    delivery_choices=delivery_choices
                )

                logger.info(
                    f"Auto-created {len(created_deliveries)} deliveries for order {instance.order_number}",
                    extra={
                        'order_id': str(instance.id),
                        'delivery_count': len(created_deliveries)
                    }
                )
            elif not existing_seller_ids:
                logger.warning(
                    f"No valid delivery choices found for order {instance.order_number}",
                    extra={
                        'order_id': str(instance.id),
                        'shipping_services': instance.shipping_services
                    }
                )
        else:
            logger.warning(
                f"Order {instance.order_number} has no shipping_services data",
                extra={'order_id': str(instance.id)}
            )

    except Exception as e:
        # Log error but don't raise - signal failures should not break the flow
        logger.error(
            f"Failed to auto-create shipments for order {instance.order_number}: {str(e)}",
            extra={
                'order_id': str(instance.id),
                'order_number': instance.order_number,
                'error': str(e),
                'error_type': type(e).__name__
            },
            exc_info=True
        )

        # TODO: Send alert to ops team for manual intervention
        # For now, just log the error
        # In production, this should trigger an alert (Sentry, email, Slack, etc.)
