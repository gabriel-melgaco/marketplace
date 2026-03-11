"""
Product Validation Service

Provides interface for validating products from the products app without tight coupling.
This service acts as a boundary between orders and products apps.
"""

import logging
from typing import Dict, List, Tuple, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class ProductValidationError(Exception):
    """Raised when product validation fails"""
    pass


class InsufficientStockError(ProductValidationError):
    """Raised when requested quantity exceeds available stock"""
    pass


class ProductValidationService:
    """
    Service for validating products and managing stock.

    This service encapsulates all interactions with the products app,
    preventing tight coupling and circular dependencies.
    """

    @staticmethod
    def validate_listing_availability(listing, quantity: int) -> None:
        """
        Validate that a listing is available and has sufficient stock.

        Args:
            listing: MarketplaceListing instance
            quantity: Requested quantity

        Raises:
            ProductValidationError: If listing is not available
            InsufficientStockError: If insufficient stock
        """
        if not listing.is_active:
            raise ProductValidationError(
                f"Product listing {listing.id} is not active"
            )

        if listing.quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {listing.product.name}. "
                f"Available: {listing.quantity}, Requested: {quantity}"
            )

        logger.debug(
            f"Listing {listing.id} validated successfully",
            extra={
                'listing_id': listing.id,
                'product_name': listing.product.name,
                'requested_qty': quantity,
                'available_qty': listing.quantity,
            }
        )

    @staticmethod
    def validate_cart_items(cart_items) -> List[Dict]:
        """
        Validate all items in cart and return validated data.

        Args:
            cart_items: QuerySet or list of CartItem instances

        Returns:
            List of dictionaries with validated item data

        Raises:
            ProductValidationError: If any validation fails
        """
        validated_items = []

        for cart_item in cart_items:
            listing = cart_item.listing

            # Validate availability and stock
            ProductValidationService.validate_listing_availability(
                listing, cart_item.quantity
            )

            # Build validated item data
            # Dimensions: prefer legacy fields on listing; fall back to aggregated packages
            packages = list(listing.packages.all())
            if listing.weight_kg is not None:
                dims = {
                    'weight_kg': listing.weight_kg,
                    'height_cm': listing.height_cm,
                    'width_cm': listing.width_cm,
                    'length_cm': listing.length_cm,
                }
            elif packages:
                dims = {
                    'weight_kg': sum(float(p.weight_kg) for p in packages),
                    'height_cm': max(float(p.height_cm) for p in packages),
                    'width_cm': max(float(p.width_cm) for p in packages),
                    'length_cm': sum(float(p.length_cm) for p in packages),
                }
            else:
                dims = {
                    'weight_kg': None,
                    'height_cm': None,
                    'width_cm': None,
                    'length_cm': None,
                }

            validated_items.append({
                'cart_item': cart_item,
                'listing': listing,
                'seller': listing.seller,
                'quantity': cart_item.quantity,
                'unit_price': listing.price,
                'product_snapshot': {
                    'name': listing.product.name,
                    'code': listing.product.code or '',
                    'brand': listing.brand.name,
                    'condition': listing.condition.name,
                },
                'dimensions': dims,
            })

        logger.info(
            f"Validated {len(validated_items)} cart items",
            extra={'item_count': len(validated_items)}
        )

        return validated_items

    @staticmethod
    def reserve_stock(listing, quantity: int) -> None:
        """
        Reserve stock for a listing (decrement quantity).

        This should be called only after payment confirmation or
        in an atomic transaction with order creation.

        Uses atomic F() expression to prevent race conditions where
        multiple users could buy the same item simultaneously.

        After decrementing, automatically deactivates the listing if
        quantity reaches zero to prevent further purchases.

        Args:
            listing: MarketplaceListing instance
            quantity: Quantity to reserve

        Raises:
            InsufficientStockError: If insufficient stock
        """
        from django.db.models import F
        from products.models import MarketplaceListing

        # Atomic decrement with validation
        # This prevents race conditions by doing the check and update in one DB operation
        updated_count = MarketplaceListing.objects.filter(
            id=listing.id,
            quantity__gte=quantity  # Only update if enough stock
        ).update(quantity=F('quantity') - quantity)

        if updated_count == 0:
            # Either listing doesn't exist or insufficient stock
            # Refresh to get current quantity
            listing.refresh_from_db()
            raise InsufficientStockError(
                f"Cannot reserve {quantity} units. Available: {listing.quantity}"
            )

        # Refresh listing to get updated quantity
        listing.refresh_from_db()

        logger.info(
            f"Reserved {quantity} units of listing {listing.id}",
            extra={
                'listing_id': listing.id,
                'reserved_qty': quantity,
                'remaining_qty': listing.quantity,
            }
        )

        # Deactivate listing if stock reached zero
        if listing.quantity == 0:
            ProductValidationService.deactivate_if_out_of_stock(listing)

    @staticmethod
    def release_stock(listing, quantity: int) -> None:
        """
        Release reserved stock back to listing (increment quantity).

        This should be called when an order is cancelled.

        Uses atomic F() expression for consistency with reserve_stock.

        Args:
            listing: MarketplaceListing instance
            quantity: Quantity to release
        """
        from django.db.models import F
        from products.models import MarketplaceListing

        # Atomic increment
        MarketplaceListing.objects.filter(
            id=listing.id
        ).update(quantity=F('quantity') + quantity)

        # Refresh listing to get updated quantity
        listing.refresh_from_db()

        logger.info(
            f"Released {quantity} units back to listing {listing.id}",
            extra={
                'listing_id': listing.id,
                'released_qty': quantity,
                'new_qty': listing.quantity,
            }
        )

    @staticmethod
    def deactivate_if_out_of_stock(listing) -> None:
        """
        Deactivate a listing when its stock reaches zero.

        Called automatically by reserve_stock() after a successful decrement
        that leaves quantity == 0. Uses a filtered update (is_active=True guard)
        to avoid unnecessary writes and to be safe against concurrent calls.

        The listing instance is refreshed after the update so callers always
        see the current state.

        Args:
            listing: MarketplaceListing instance (quantity already refreshed)
        """
        from products.models import MarketplaceListing

        updated_count = MarketplaceListing.objects.filter(
            id=listing.id,
            quantity=0,
            is_active=True,
        ).update(is_active=False)

        # Reflect the DB state on the in-memory instance
        listing.refresh_from_db()

        if updated_count > 0:
            logger.info(
                f"Listing {listing.id} deactivated because stock reached zero",
                extra={
                    'listing_id': listing.id,
                    'product_name': listing.product.name,
                    'seller_id': listing.seller_id,
                }
            )
        else:
            # Already deactivated by another process, or quantity was restored
            # before this update ran — log for observability
            logger.debug(
                f"deactivate_if_out_of_stock: listing {listing.id} was already "
                "inactive or quantity changed before update — no-op",
                extra={'listing_id': listing.id}
            )

    @staticmethod
    def mark_as_sold(listing) -> None:
        """
        Mark a listing as sold (set sold_at timestamp).

        This should only be called after payment is confirmed.

        Args:
            listing: MarketplaceListing instance
        """
        from django.utils import timezone

        listing.sold_at = timezone.now()
        listing.save(update_fields=['sold_at'])

        logger.info(
            f"Marked listing {listing.id} as sold",
            extra={'listing_id': listing.id}
        )

    @staticmethod
    def get_listing_by_id(listing_id: int):
        """
        Retrieve a listing by ID.

        Args:
            listing_id: Listing ID

        Returns:
            MarketplaceListing instance or None

        Raises:
            ProductValidationError: If listing not found
        """
        from products.models import MarketplaceListing

        try:
            listing = MarketplaceListing.objects.select_related(
                'product', 'seller', 'brand', 'condition'
            ).get(id=listing_id)

            return listing

        except MarketplaceListing.DoesNotExist:
            raise ProductValidationError(f"Listing {listing_id} not found")

    @staticmethod
    def validate_price_consistency(
        listing,
        expected_price: Decimal
    ) -> None:
        """
        Validate that listing price matches expected price.

        This prevents price manipulation from frontend.

        Args:
            listing: MarketplaceListing instance
            expected_price: Expected price from frontend

        Raises:
            ProductValidationError: If prices don't match
        """
        if listing.price != expected_price:
            logger.warning(
                f"Price mismatch for listing {listing.id}",
                extra={
                    'listing_id': listing.id,
                    'db_price': float(listing.price),
                    'expected_price': float(expected_price),
                }
            )

            raise ProductValidationError(
                f"Price mismatch for {listing.product.name}. "
                f"Current price: {listing.price}, Expected: {expected_price}"
            )
