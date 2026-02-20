"""
Order Creation Service

Orchestrates the complete order creation process from cart to order.
This service handles all business logic for converting a cart into an order.
"""

import logging
from typing import Dict, Optional
from decimal import Decimal
from collections import defaultdict
from django.db import transaction
from django.utils import timezone

from .product_validation_service import ProductValidationService
from .order_total_calculator import OrderTotalCalculator
from .order_state_machine import OrderStateMachine

logger = logging.getLogger(__name__)


class OrderCreationError(Exception):
    """Raised when order creation fails"""
    pass


class OrderCreationService:
    """
    Service for creating orders from cart with full validation and orchestration.

    This service:
    - Validates all cart items and stock availability
    - Validates shipping quotes
    - Calculates totals server-side
    - Creates order with snapshot data
    - Handles stock management based on configuration
    - Creates audit trail
    """

    # Stock management strategy
    # 'immediate' - decrement stock immediately (current behavior)
    # 'on_payment' - decrement stock only after payment confirmed (recommended)
    STOCK_STRATEGY = 'on_payment'

    @classmethod
    @transaction.atomic
    def create_order_from_cart(
        cls,
        user,
        cart,
        shipping_address,
        shipping_services_input: Dict,
        payment_method: str,
        buyer_notes: str = ''
    ):
        """
        Create an order from user's cart with full validation.

        Args:
            user: User creating the order
            cart: Cart instance
            shipping_address: Address instance for shipping
            shipping_services_input: Dict mapping seller_id to delivery config
                (normalized by serializer to {seller_id: {delivery_method, ...}})
            payment_method: Payment method chosen
            buyer_notes: Optional notes from buyer

        Returns:
            Order instance

        Raises:
            OrderCreationError: If order creation fails
        """
        logger.info(
            f"Creating order from cart for user {user.email}",
            extra={
                'user_id': user.id,
                'cart_id': cart.id,
                'payment_method': payment_method,
            }
        )

        # Step 1: Validate cart is not empty
        cart_items = cart.items.select_related(
            'listing__product',
            'listing__seller',
            'listing__brand',
            'listing__condition'
        ).all()

        if not cart_items.exists():
            raise OrderCreationError("Cart is empty")

        # Step 2: Validate all cart items and stock
        try:
            validated_items = ProductValidationService.validate_cart_items(cart_items)
        except Exception as e:
            logger.error(f"Product validation failed: {str(e)}")
            raise OrderCreationError(f"Product validation failed: {str(e)}")

        # Step 3: Calculate subtotal
        subtotal = OrderTotalCalculator.calculate_cart_subtotal(validated_items)

        # Step 4: Validate and calculate shipping
        shipping_data = cls._validate_and_calculate_shipping(
            user,
            validated_items,
            shipping_services_input
        )

        total_shipping = shipping_data['total_shipping']
        shipping_services_data = shipping_data['shipping_services_data']
        shipping_by_seller = shipping_data['shipping_by_seller']

        # Step 5: Calculate total
        total = OrderTotalCalculator.calculate_order_total(subtotal, total_shipping)

        # Step 5.5: Add freight to Melhor Envio cart BEFORE creating order in DB.
        # Fail fast: if ME API rejects the payload, we never persist an inconsistent order.
        me_cart_results = cls._add_sellers_to_me_cart_preorder(
            user=user,
            validated_items=validated_items,
            shipping_services_data=shipping_services_data,
            shipping_address=shipping_address,
        )

        # Step 6: Create order
        order = cls._create_order_record(
            user=user,
            subtotal=subtotal,
            shipping_cost=total_shipping,
            total=total,
            shipping_address=shipping_address,
            shipping_services_data=shipping_services_data,
            payment_method=payment_method,
            buyer_notes=buyer_notes
        )

        # Step 7: Create order items with snapshots
        cls._create_order_items(
            order=order,
            validated_items=validated_items,
            shipping_by_seller=shipping_by_seller
        )

        # Step 7.5: Create Shipment DB records from cart IDs collected in step 5.5.
        # order.items now exist so create_shipment_record() can read dimensions.
        if me_cart_results:
            cls._create_shipment_records_from_cart(order, me_cart_results)

        # Step 8: Handle stock management based on strategy
        if cls.STOCK_STRATEGY == 'immediate':
            cls._reserve_stock_immediate(validated_items)
        # If 'on_payment', stock will be decremented after payment confirmation

        # Step 9: Create initial status history (order already created as pending_payment)
        from orders.models import OrderStatusHistory
        OrderStatusHistory.objects.create(
            order=order,
            old_status='',
            new_status='pending_payment',
            changed_by=user,
            notes='Order created from cart'
        )

        # Step 10: Clear cart
        cart.items.all().delete()

        logger.info(
            f"Order {order.order_number} created successfully",
            extra={
                'order_id': str(order.id),
                'order_number': order.order_number,
                'total': float(order.total),
            }
        )

        return order

    @staticmethod
    def _add_sellers_to_me_cart_preorder(user, validated_items, shipping_services_data, shipping_address):
        """
        Adiciona fretes ao carrinho do Melhor Envio ANTES de criar o pedido no banco.

        Usa dados brutos (validated_items) em vez de order.items para não depender
        de registros no banco. Se a API do ME rejeitar, o pedido jamais é criado.

        Args:
            user: Usuário comprador
            validated_items: Lista de validated_items de todos os sellers
            shipping_services_data: Dict {str(seller_id): {'delivery_method', 'service_id', ...}}
            shipping_address: Address instance (ainda não convertida para dict)

        Returns:
            dict: {seller_id(int): {'cart_response', 'sent_payload', 'insurance_warning', 'seller'}}

        Raises:
            OrderCreationError: Se a chamada à API do ME falhar
        """
        from collections import defaultdict
        from logistics.services.melhor_envio_service import MelhorEnvioService, ShippingValidationError

        melhor_envio = MelhorEnvioService()
        shipping_address_dict = shipping_address.to_dict()

        # Agrupar validated_items por seller_id
        items_by_seller = defaultdict(list)
        for item in validated_items:
            items_by_seller[item['seller'].id].append(item)

        me_cart_results = {}

        for seller_id_str, seller_config in shipping_services_data.items():
            if not isinstance(seller_config, dict):
                continue
            if seller_config.get('delivery_method', 'shipping') != 'shipping':
                continue
            service_id = seller_config.get('service_id')
            if not service_id:
                continue

            seller_id = int(seller_id_str)
            seller_items = items_by_seller.get(seller_id, [])
            if not seller_items:
                continue

            seller = seller_items[0]['seller']

            try:
                cart_response, sent_payload = melhor_envio.add_to_cart_raw(
                    buyer=user,
                    seller=seller,
                    seller_validated_items=seller_items,
                    shipping_address_dict=shipping_address_dict,
                    service_id=service_id,
                )
                insurance_warning = cart_response.pop('_insurance_warning', None)
                me_cart_results[seller_id] = {
                    'cart_response': cart_response,
                    'sent_payload': sent_payload,
                    'insurance_warning': insurance_warning,
                    'seller': seller,
                }
                logger.info(
                    f'Frete adicionado ao carrinho ME para vendedor {seller.email}: '
                    f'cart_id={cart_response.get("id")}'
                )
            except (ShippingValidationError, Exception) as e:
                logger.error(
                    f'Erro ao adicionar frete ao carrinho ME para vendedor '
                    f'{seller.email}: {str(e)}',
                    exc_info=True,
                )
                raise OrderCreationError(
                    f'Erro ao adicionar frete ao carrinho Melhor Envio '
                    f'para vendedor {seller.email}: {str(e)}'
                ) from e

        return me_cart_results

    @staticmethod
    def _create_shipment_records_from_cart(order, me_cart_results):
        """
        Cria registros de Shipment no banco usando os cart_ids coletados antes
        da criação do pedido. Chamado APÓS order.items existirem no banco.

        Args:
            order: Order instance já persistida com items
            me_cart_results: retorno de _add_sellers_to_me_cart_preorder()
        """
        from logistics.services.melhor_envio_service import MelhorEnvioService

        me_service = MelhorEnvioService()
        for seller_id, data in me_cart_results.items():
            seller = data['seller']
            cart_response = data['cart_response']
            sent_payload = data['sent_payload']
            insurance_warning = data['insurance_warning']

            # Reinjeta o warning temporariamente para create_shipment_record() limpá-lo
            if insurance_warning:
                cart_response['_insurance_warning'] = insurance_warning

            shipment, _ = me_service.create_shipment_record(
                order=order,
                seller=seller,
                cart_data=cart_response,
                sent_payload=sent_payload,
            )
            logger.info(
                f'Shipment criado para pedido {order.order_number}, '
                f'vendedor {seller.email}: id={shipment.id}, '
                f'melhorenvio_order_id={shipment.melhorenvio_order_id}'
            )
            if insurance_warning:
                logger.warning(
                    f'Pedido {order.order_number}: {insurance_warning.get("message", "")}'
                )

    @staticmethod
    def _validate_and_calculate_shipping(
        user,
        validated_items: list,
        shipping_services_input: Dict
    ) -> Dict:
        """
        Validate shipping/delivery options and calculate total shipping cost.

        Supports both shipping (via carrier) and in-person delivery methods.

        Args:
            user: User instance
            validated_items: List of validated cart items
            shipping_services_input: Dict mapping seller_id to delivery config
                (normalized format: {seller_id: {delivery_method, ...}})

        Returns:
            Dict with shipping data

        Raises:
            OrderCreationError: If shipping validation fails
        """
        from logistics.models import ShippingQuote

        # Group items by seller
        items_by_seller = defaultdict(list)
        for item in validated_items:
            seller_id = item['seller'].id
            items_by_seller[seller_id].append(item)

        total_shipping = Decimal('0.00')
        shipping_services_data = {}
        shipping_by_seller = {}

        for seller_id, delivery_config in shipping_services_input.items():
            # Validate seller has items in cart
            if seller_id not in items_by_seller:
                raise OrderCreationError(
                    f"Seller {seller_id} not found in cart items"
                )

            delivery_method = delivery_config.get('delivery_method', 'shipping')

            if delivery_method == 'shipping':
                # --- Shipping via carrier ---
                service_id = delivery_config.get('service_id')
                if not service_id:
                    raise OrderCreationError(
                        f"service_id is required for shipping delivery of seller {seller_id}"
                    )

                # Find valid shipping quote
                quote = ShippingQuote.objects.filter(
                    user=user,
                    seller_id=seller_id,
                    expires_at__gt=timezone.now()
                ).order_by('-created_at').first()

                if not quote:
                    raise OrderCreationError(
                        f"Shipping quote for seller {seller_id} expired or not found. "
                        f"Please recalculate shipping."
                    )

                # Find selected service in quote
                quotes_list = quote.quotes_data
                if isinstance(quotes_list, dict):
                    quotes_list = quotes_list.get('services', [])

                service_found = None
                for service in quotes_list:
                    if isinstance(service, dict) and service.get('id') == service_id:
                        service_found = service
                        break

                if not service_found:
                    raise OrderCreationError(
                        f"Shipping service {service_id} not found for seller {seller_id}"
                    )

                # Extract shipping cost from quote (server-side, trusted)
                shipping_cost = Decimal(str(
                    service_found.get('custom_price', service_found.get('price', 0))
                ))

                total_shipping += shipping_cost

                # Store service data
                company = service_found.get('company', '')
                company_name = company.get('name', '') if isinstance(company, dict) else str(company)
                shipping_services_data[str(seller_id)] = {
                    'delivery_method': 'shipping',
                    'service_id': service_id,
                    'service_name': service_found.get('name', ''),
                    'company': company_name,
                    'cost': float(shipping_cost),
                    'delivery_time': service_found.get('delivery_time', 0)
                }

                shipping_by_seller[seller_id] = shipping_cost

            elif delivery_method == 'in_person':
                # --- In-person delivery ---
                logger.info(
                    f"In-person delivery configured for seller {seller_id}",
                    extra={'seller_id': seller_id, 'order_user': user.email}
                )

                # In-person delivery has zero shipping cost
                shipping_by_seller[seller_id] = Decimal('0.00')

                # Store in-person delivery data for signal to process
                shipping_services_data[str(seller_id)] = {
                    'delivery_method': 'in_person',
                    'cost': 0,
                    'meeting_location_name': delivery_config.get('meeting_location_name', ''),
                    'meeting_address': delivery_config.get('meeting_address', {}),
                    'seller_contact_phone': delivery_config.get('seller_contact_phone', ''),
                    'buyer_contact_phone': delivery_config.get('buyer_contact_phone', ''),
                    'scheduled_date': delivery_config.get('scheduled_date'),
                    'scheduled_time': delivery_config.get('scheduled_time'),
                    'meeting_notes': delivery_config.get('meeting_notes', ''),
                }

            else:
                raise OrderCreationError(
                    f"Invalid delivery method '{delivery_method}' for seller {seller_id}"
                )

        return {
            'total_shipping': total_shipping,
            'shipping_services_data': shipping_services_data,
            'shipping_by_seller': shipping_by_seller,
        }

    @staticmethod
    def _create_order_record(
        user,
        subtotal: Decimal,
        shipping_cost: Decimal,
        total: Decimal,
        shipping_address,
        shipping_services_data: Dict,
        payment_method: str,
        buyer_notes: str
    ):
        """
        Create Order database record.

        Args:
            user: User instance
            subtotal: Order subtotal
            shipping_cost: Total shipping cost
            total: Order total
            shipping_address: Address instance
            shipping_services_data: Shipping services data
            payment_method: Payment method
            buyer_notes: Buyer notes

        Returns:
            Order instance
        """
        from orders.models import Order

        order = Order.objects.create(
            buyer=user,
            status='pending_payment',
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            total=total,
            shipping_address=shipping_address.to_dict(),
            shipping_services=shipping_services_data,
            payment_method=payment_method,
            buyer_notes=buyer_notes
        )

        return order

    @staticmethod
    def _create_order_items(
        order,
        validated_items: list,
        shipping_by_seller: Dict[int, Decimal]
    ):
        """
        Create OrderItem records with complete snapshots.

        Args:
            order: Order instance
            validated_items: List of validated cart items
            shipping_by_seller: Dict mapping seller_id to shipping cost
        """
        from orders.models import OrderItem
        from logistics.models import Address

        for item_data in validated_items:
            listing = item_data['listing']
            seller = item_data['seller']
            seller_id = seller.id

            # Get seller address
            seller_address = Address.objects.filter(
                user=seller,
                is_shipping_address=True,
                is_active=True
            ).first()

            # Create order item with full snapshot
            OrderItem.objects.create(
                order=order,
                listing=listing,
                seller=seller,
                product_name=item_data['product_snapshot']['name'],
                product_code=item_data['product_snapshot']['code'],
                brand_name=item_data['product_snapshot']['brand'],
                condition_name=item_data['product_snapshot']['condition'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                shipping_cost=shipping_by_seller.get(seller_id, Decimal('0.00')),
                weight_kg=item_data['dimensions']['weight_kg'],
                height_cm=item_data['dimensions']['height_cm'],
                width_cm=item_data['dimensions']['width_cm'],
                length_cm=item_data['dimensions']['length_cm'],
                seller_address=seller_address.to_dict() if seller_address else {}
            )

    @staticmethod
    def _reserve_stock_immediate(validated_items: list):
        """
        Reserve stock immediately (old behavior).

        Args:
            validated_items: List of validated cart items
        """
        for item_data in validated_items:
            listing = item_data['listing']
            quantity = item_data['quantity']

            ProductValidationService.reserve_stock(listing, quantity)
            ProductValidationService.mark_as_sold(listing)

    @staticmethod
    @transaction.atomic
    def confirm_payment_and_reserve_stock(order):
        """
        Confirm payment and reserve stock (for on_payment strategy).

        This should be called by payment webhook after payment succeeds.

        Args:
            order: Order instance

        Raises:
            OrderCreationError: If stock reservation fails
        """
        logger.info(
            f"Confirming payment and reserving stock for order {order.order_number}",
            extra={'order_id': str(order.id)}
        )

        for item in order.items.select_related('listing').all():
            try:
                ProductValidationService.reserve_stock(item.listing, item.quantity)
                ProductValidationService.mark_as_sold(item.listing)
            except Exception as e:
                logger.error(
                    f"Failed to reserve stock for item {item.id}: {str(e)}",
                    extra={
                        'order_id': str(order.id),
                        'item_id': item.id,
                        'listing_id': item.listing.id,
                    }
                )
                raise OrderCreationError(
                    f"Failed to reserve stock: {str(e)}"
                )

    @staticmethod
    @transaction.atomic
    def cancel_order_and_release_stock(order, canceled_by, reason: str = ''):
        """
        Cancel order and release reserved stock.

        Args:
            order: Order instance
            canceled_by: User canceling the order
            reason: Cancellation reason

        Raises:
            OrderCreationError: If cancellation fails
        """
        logger.info(
            f"Canceling order {order.order_number} and releasing stock",
            extra={
                'order_id': str(order.id),
                'canceled_by': str(canceled_by),
            }
        )

        # Transition to canceled state
        OrderStateMachine.transition_to(
            order=order,
            new_status=OrderStateMachine.CANCELED,
            changed_by=canceled_by,
            notes=reason or 'Order cancelled'
        )

        # Release stock if it was reserved
        for item in order.items.select_related('listing').all():
            ProductValidationService.release_stock(item.listing, item.quantity)

        logger.info(
            f"Order {order.order_number} cancelled and stock released",
            extra={'order_id': str(order.id)}
        )
