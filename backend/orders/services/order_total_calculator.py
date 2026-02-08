"""
Order Total Calculator Service

Handles all order total calculations with proper decimal precision.
Ensures totals are always calculated server-side and never trusted from frontend.
"""

import logging
from decimal import Decimal
from typing import Dict, List

logger = logging.getLogger(__name__)


class OrderTotalCalculator:
    """
    Service for calculating order totals with proper decimal precision.

    All calculations use Decimal to avoid floating point precision issues.
    """

    @staticmethod
    def calculate_item_subtotal(unit_price: Decimal, quantity: int) -> Decimal:
        """
        Calculate subtotal for an order item.

        Args:
            unit_price: Price per unit
            quantity: Number of units

        Returns:
            Decimal: Item subtotal
        """
        subtotal = unit_price * Decimal(quantity)

        logger.debug(
            f"Item subtotal calculated: {subtotal}",
            extra={
                'unit_price': float(unit_price),
                'quantity': quantity,
                'subtotal': float(subtotal),
            }
        )

        return subtotal

    @staticmethod
    def calculate_cart_subtotal(validated_items: List[Dict]) -> Decimal:
        """
        Calculate total for all items in cart (without shipping).

        Args:
            validated_items: List of validated item dictionaries

        Returns:
            Decimal: Cart subtotal
        """
        subtotal = Decimal('0.00')

        for item in validated_items:
            item_subtotal = OrderTotalCalculator.calculate_item_subtotal(
                item['unit_price'],
                item['quantity']
            )
            subtotal += item_subtotal

        logger.info(
            f"Cart subtotal calculated: {subtotal}",
            extra={
                'item_count': len(validated_items),
                'subtotal': float(subtotal),
            }
        )

        return subtotal

    @staticmethod
    def calculate_total_shipping(shipping_by_seller: Dict[int, Decimal]) -> Decimal:
        """
        Calculate total shipping cost from all sellers.

        Args:
            shipping_by_seller: Dictionary mapping seller_id to shipping cost

        Returns:
            Decimal: Total shipping cost
        """
        total_shipping = sum(
            Decimal(str(cost)) for cost in shipping_by_seller.values()
        )

        logger.info(
            f"Total shipping calculated: {total_shipping}",
            extra={
                'seller_count': len(shipping_by_seller),
                'total_shipping': float(total_shipping),
            }
        )

        return total_shipping

    @staticmethod
    def calculate_order_total(
        subtotal: Decimal,
        shipping_cost: Decimal,
        tax: Decimal = Decimal('0.00')
    ) -> Decimal:
        """
        Calculate final order total.

        Args:
            subtotal: Items subtotal
            shipping_cost: Total shipping cost
            tax: Tax amount (future use)

        Returns:
            Decimal: Order total
        """
        total = subtotal + shipping_cost + tax

        logger.info(
            f"Order total calculated: {total}",
            extra={
                'subtotal': float(subtotal),
                'shipping': float(shipping_cost),
                'tax': float(tax),
                'total': float(total),
            }
        )

        return total

    @staticmethod
    def validate_totals(
        order,
        expected_subtotal: Decimal = None,
        expected_total: Decimal = None
    ) -> bool:
        """
        Validate order totals match expected values.

        Args:
            order: Order instance
            expected_subtotal: Expected subtotal (optional)
            expected_total: Expected total (optional)

        Returns:
            bool: True if validation passes

        Raises:
            ValueError: If totals don't match
        """
        # Calculate actual subtotal from items
        actual_subtotal = sum(
            Decimal(str(item.subtotal))
            for item in order.items.all()
        )

        if expected_subtotal and actual_subtotal != expected_subtotal:
            raise ValueError(
                f"Subtotal mismatch. Expected: {expected_subtotal}, "
                f"Actual: {actual_subtotal}"
            )

        if order.subtotal != actual_subtotal:
            raise ValueError(
                f"Order subtotal doesn't match items. "
                f"Order: {order.subtotal}, Items: {actual_subtotal}"
            )

        # Calculate actual total
        actual_total = actual_subtotal + Decimal(str(order.shipping_cost))

        if expected_total and actual_total != expected_total:
            raise ValueError(
                f"Total mismatch. Expected: {expected_total}, "
                f"Actual: {actual_total}"
            )

        if order.total != actual_total:
            raise ValueError(
                f"Order total doesn't match calculation. "
                f"Order: {order.total}, Calculated: {actual_total}"
            )

        logger.info(
            f"Order {order.order_number} totals validated",
            extra={
                'order_id': str(order.id),
                'subtotal': float(order.subtotal),
                'shipping': float(order.shipping_cost),
                'total': float(order.total),
            }
        )

        return True
