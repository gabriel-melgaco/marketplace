"""
Order Creation Service

Orchestrates the complete order creation process from cart to orders.
When a cart contains items from multiple sellers, one Order is created
per seller. This simplifies refunds and logistics since each Order
belongs to exactly one seller.
"""

import logging
from typing import Dict, List, Optional
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


class InsufficientMEBalanceError(OrderCreationError):
    """
    Raised when one or more sellers have insufficient ME wallet balance
    to cover the shipping cost of this order.

    Attributes:
        sellers_info: list of dicts with seller details and balance gap
    """

    def __init__(self, message: str, sellers_info: list):
        super().__init__(message)
        self.sellers_info = sellers_info
        # sellers_info format:
        # [{"seller_email": str, "required": Decimal, "available": Decimal, "missing": Decimal}]


class OrderCreationService:
    """
    Service for creating orders from cart with full validation and orchestration.

    One Order is created per seller in the cart. If the cart has items from
    two sellers, two separate Orders are returned. This design choice:

    - Simplifies refunds: each Order belongs to one seller, so a partial
      refund (for one seller's items) does not touch the other seller's Order.
    - Simplifies logistics: each Order has its own shipping_services scoped
      to one seller, with exactly one Shipment relationship.
    - Simplifies payment splits: PaymentSplit.unique_together=(payment, seller)
      already handles the accounting; the split just maps to a single Order.

    NOTE: Because Payment has OneToOneField(Order), each seller's Order gets
    its own Payment record and its own Stripe PaymentIntent. The buyer will
    be charged once per seller — this is the expected behaviour for a
    marketplace with per-vendor fulfilment.
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
    ) -> List:
        """
        Create one Order per seller from user's cart with full validation.

        Args:
            user: User creating the order
            cart: Cart instance
            shipping_address: Address instance for shipping
            shipping_services_input: Dict mapping seller_id to delivery config
                (normalized by serializer to {seller_id: {delivery_method, ...}})
            payment_method: Payment method chosen
            buyer_notes: Optional notes from buyer

        Returns:
            List[Order]: One Order instance per seller in the cart.

        Raises:
            OrderCreationError: If order creation fails
        """
        logger.info(
            f"Creating orders from cart for user {user.email}",
            extra={
                'user_id': user.id,
                'cart_id': cart.id,
                'payment_method': payment_method,
            }
        )

        # Step 1a: Block if buyer already has a pending_payment order
        from orders.models import Order as OrderModel
        pending = OrderModel.objects.filter(buyer=user, status='pending_payment').first()
        if pending:
            raise OrderCreationError(
                f"Você já possui um pedido aguardando pagamento ({pending.order_number}). "
                f"Conclua ou cancele-o antes de criar um novo."
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

        # Step 3: Group validated items by seller
        items_by_seller: dict = defaultdict(list)
        for item in validated_items:
            items_by_seller[item['seller'].id].append(item)

        # Step 4: Validate and calculate shipping per seller
        shipping_data = cls._validate_and_calculate_shipping(
            user,
            validated_items,
            shipping_services_input
        )

        total_shipping_global = shipping_data['total_shipping']
        shipping_services_data = shipping_data['shipping_services_data']
        shipping_by_seller = shipping_data['shipping_by_seller']

        # Step 4.5: Verify seller ME wallet balances before touching ME API or DB.
        logger.info(
            "Step 4.5: Verificando saldo ME dos vendedores",
            extra={
                'user_id': user.id,
                'sellers_to_check': {
                    str(sid): float(cost)
                    for sid, cost in shipping_by_seller.items()
                    if cost > 0
                },
            }
        )
        if any(cost > 0 for cost in shipping_by_seller.values()):
            cls._check_sellers_me_balance(
                items_by_seller=dict(items_by_seller),
                shipping_by_seller=shipping_by_seller,
            )

        # Step 5: Add freight to Melhor Envio cart BEFORE creating orders in DB.
        me_cart_results = cls._add_sellers_to_me_cart_preorder(
            user=user,
            validated_items=validated_items,
            shipping_services_data=shipping_services_data,
            shipping_address=shipping_address,
        )

        # Step 6: Create one Order per seller
        created_orders: List = []

        for seller_id, seller_items in items_by_seller.items():
            seller = seller_items[0]['seller']

            # Subtotal for this seller's items only
            seller_subtotal = OrderTotalCalculator.calculate_cart_subtotal(seller_items)

            # Shipping cost for this seller
            seller_shipping = shipping_by_seller.get(seller_id, Decimal('0.00'))

            # Total for this seller's order
            seller_total = OrderTotalCalculator.calculate_order_total(
                seller_subtotal, seller_shipping
            )

            # shipping_services scoped to this seller only
            seller_shipping_services = {
                str(seller_id): shipping_services_data.get(str(seller_id), {})
            }

            # Create the Order record for this seller
            order = cls._create_order_record(
                user=user,
                seller=seller,
                subtotal=seller_subtotal,
                shipping_cost=seller_shipping,
                total=seller_total,
                shipping_address=shipping_address,
                shipping_services_data=seller_shipping_services,
                payment_method=payment_method,
                buyer_notes=buyer_notes
            )

            # Create OrderItems for this seller
            cls._create_order_items(
                order=order,
                validated_items=seller_items,
                shipping_by_seller=shipping_by_seller
            )

            # Create initial status history
            from orders.models import OrderStatusHistory
            OrderStatusHistory.objects.create(
                order=order,
                old_status='',
                new_status='pending_payment',
                changed_by=user,
                notes='Order created from cart'
            )

            created_orders.append(order)
            logger.info(
                f"Order {order.order_number} created for seller {seller.email}",
                extra={
                    'order_id': str(order.id),
                    'seller_id': seller_id,
                    'items': len(seller_items),
                    'total': float(seller_total),
                }
            )

        # Step 7: Create Shipment DB records from ME cart IDs
        if me_cart_results:
            # Pass all created orders — _create_shipment_records_from_cart
            # identifies the right order by seller
            cls._create_shipment_records_from_cart_multi(created_orders, me_cart_results)

        # Step 8: Handle stock management based on strategy
        if cls.STOCK_STRATEGY == 'immediate':
            cls._reserve_stock_immediate(validated_items)

        # Step 9: Clear cart
        cart.items.all().delete()

        # Step 10: Notify buyer and sellers
        try:
            from notifications.services import NotificationService
            from notifications.models import NotificationType

            # Notify buyer once with the list of order numbers
            order_numbers = ', '.join(f'#{o.order_number}' for o in created_orders)
            total_all = sum(o.total for o in created_orders)
            NotificationService.notify(
                recipient=user,
                event_type=NotificationType.ORDER_CREATED,
                title=f'{len(created_orders)} pedido(s) criado(s)',
                body=(
                    f'Seus pedidos foram criados com sucesso. '
                    f'Pedidos: {order_numbers}. '
                    f'Total: R$ {total_all:.2f}. '
                    f'Aguardando confirmação do pagamento.'
                ),
                metadata={
                    'order_ids': [str(o.id) for o in created_orders],
                    'order_numbers': [o.order_number for o in created_orders],
                    'total': str(total_all),
                },
                idempotency_key=f'orders_created_buyer_{user.id}_{created_orders[0].id}',
            )

            # Notify each seller
            for order in created_orders:
                seller = order.seller
                if seller is None:
                    continue
                seller_subtotal = sum(i.subtotal for i in order.items.all())
                NotificationService.notify(
                    recipient=seller,
                    event_type=NotificationType.ORDER_CREATED,
                    title=f'Nova venda — Pedido #{order.order_number}',
                    body=(
                        f'Você recebeu um novo pedido! '
                        f'Pedido #{order.order_number}. '
                        f'Total dos seus itens: R$ {seller_subtotal:.2f}. '
                        f'Aguardando confirmação do pagamento.'
                    ),
                    metadata={
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'seller_subtotal': str(seller_subtotal),
                        'buyer_id': user.id,
                    },
                    idempotency_key=f'order_created_seller_{order.id}_{seller.id}',
                )
        except Exception as _notify_exc:
            logger.warning(
                'Falha ao enfileirar notificações de order_created: %s',
                _notify_exc,
            )

        logger.info(
            f"Created {len(created_orders)} order(s) from cart for user {user.email}",
            extra={
                'user_id': user.id,
                'order_count': len(created_orders),
                'order_ids': [str(o.id) for o in created_orders],
            }
        )

        return created_orders

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

        # me_cart_results keyed by (seller_id, listing_id) — one entry per listing
        me_cart_results = {}

        for seller_id_str, seller_config in shipping_services_data.items():
            if not isinstance(seller_config, dict):
                continue
            delivery_method = seller_config.get('delivery_method', 'shipping')
            if delivery_method == 'split':
                per_listing = seller_config.get('shipping', {}).get('per_listing', {})
            elif delivery_method == 'shipping':
                per_listing = seller_config.get('per_listing', {})
            else:
                continue  # in_person — skip

            if not per_listing:
                continue

            seller_id = int(seller_id_str)
            all_items = items_by_seller.get(seller_id, [])

            # For split: exclude in_person-only listings from ME cart
            if delivery_method == 'split':
                from products.models import ShippingMethodChoices as SMC
                shippable_items = [
                    i for i in all_items
                    if i['listing'].shipping_method != SMC.IN_PERSON
                ]
            else:
                shippable_items = all_items

            if not shippable_items:
                continue

            seller = shippable_items[0]['seller']

            # Group shippable items by listing_id
            items_by_listing: dict = {}
            for item in shippable_items:
                lid = item['listing'].id
                items_by_listing.setdefault(lid, []).append(item)

            # One ME cart call per listing (each may use a different service)
            for listing_id_str, listing_cfg in per_listing.items():
                listing_id = int(listing_id_str)
                service_id = listing_cfg.get('service_id')
                if not service_id:
                    continue

                listing_items = items_by_listing.get(listing_id, [])
                if not listing_items:
                    logger.warning(
                        f'Listing {listing_id} presente em per_listing mas sem itens '
                        f'no carrinho para vendedor {seller.email} — ignorado.'
                    )
                    continue

                try:
                    cart_results, sent_payload = melhor_envio.add_to_cart_raw(
                        buyer=user,
                        seller=seller,
                        seller_validated_items=listing_items,
                        shipping_address_dict=shipping_address_dict,
                        service_id=service_id,
                    )
                    # Extrair insurance_warning (injetado no primeiro item quando presente)
                    insurance_warning = None
                    if isinstance(cart_results, list) and cart_results:
                        insurance_warning = cart_results[0].pop('_insurance_warning', None)
                    elif isinstance(cart_results, dict):
                        insurance_warning = cart_results.pop('_insurance_warning', None)

                    me_cart_results[(seller_id, listing_id)] = {
                        'cart_response': cart_results,
                        'sent_payload': sent_payload,
                        'insurance_warning': insurance_warning,
                        'seller': seller,
                        'listing_id': listing_id,
                    }
                    logger.info(
                        f'Frete adicionado ao carrinho ME — vendedor {seller.email}, '
                        f'listing {listing_id}, serviço {service_id}: '
                        f'cart_ids={[r.get("id") for r in cart_results] if isinstance(cart_results, list) else "n/a"}'
                    )
                except (ShippingValidationError, Exception) as e:
                    logger.error(
                        f'Erro ao adicionar frete ME para vendedor {seller.email}, '
                        f'listing {listing_id}: {str(e)}',
                        exc_info=True,
                    )
                    raise OrderCreationError(
                        f'Erro ao adicionar frete ao carrinho Melhor Envio '
                        f'para vendedor {seller.email}, listing {listing_id}: {str(e)}'
                    ) from e

        return me_cart_results

    @staticmethod
    def _create_shipment_records_from_cart(order, me_cart_results):
        """
        Cria registros de Shipment para um único Order usando os cart_ids coletados.

        Filtra me_cart_results para incluir somente entradas do seller deste Order.

        Args:
            order: Order instance já persistida com items
            me_cart_results: retorno de _add_sellers_to_me_cart_preorder()
        """
        from logistics.services.melhor_envio_service import MelhorEnvioService

        me_service = MelhorEnvioService()
        seller_id = order.seller_id if order.seller_id else None

        for (result_seller_id, listing_id), data in me_cart_results.items():
            # Only process ME results belonging to this order's seller
            if seller_id is not None and result_seller_id != seller_id:
                continue

            seller = data['seller']
            cart_response = data['cart_response']
            sent_payload = data['sent_payload']
            insurance_warning = data['insurance_warning']

            # Reinjeta o warning no primeiro item para create_shipment_record() limpá-lo
            if insurance_warning:
                if isinstance(cart_response, list) and cart_response:
                    cart_response[0]['_insurance_warning'] = insurance_warning
                elif isinstance(cart_response, dict):
                    cart_response['_insurance_warning'] = insurance_warning

            shipment, _ = me_service.create_shipment_record(
                order=order,
                seller=seller,
                cart_data=cart_response,
                sent_payload=sent_payload,
            )
            logger.info(
                f'Shipment criado para pedido {order.order_number}, '
                f'vendedor {seller.email}, listing {listing_id}: '
                f'id={shipment.id}, melhorenvio_order_id={shipment.melhorenvio_order_id}'
            )
            if insurance_warning:
                logger.warning(
                    f'Pedido {order.order_number}: {insurance_warning.get("message", "")}'
                )

    @staticmethod
    def _create_shipment_records_from_cart_multi(orders: List, me_cart_results: dict):
        """
        Cria registros de Shipment para cada Order na lista, roteando entradas
        do me_cart_results para o Order do seller correspondente.

        Args:
            orders: Lista de Order instances já persistidas com items
            me_cart_results: retorno de _add_sellers_to_me_cart_preorder()
        """
        # Build seller_id -> order lookup
        order_by_seller = {
            o.seller_id: o for o in orders if o.seller_id is not None
        }

        from logistics.services.melhor_envio_service import MelhorEnvioService
        me_service = MelhorEnvioService()

        for (result_seller_id, listing_id), data in me_cart_results.items():
            order = order_by_seller.get(result_seller_id)
            if order is None:
                logger.warning(
                    f'ME cart result para seller_id={result_seller_id} não encontrou '
                    f'Order correspondente na lista criada. Ignorado.'
                )
                continue

            seller = data['seller']
            cart_response = data['cart_response']
            sent_payload = data['sent_payload']
            insurance_warning = data['insurance_warning']

            if insurance_warning:
                if isinstance(cart_response, list) and cart_response:
                    cart_response[0]['_insurance_warning'] = insurance_warning
                elif isinstance(cart_response, dict):
                    cart_response['_insurance_warning'] = insurance_warning

            shipment, _ = me_service.create_shipment_record(
                order=order,
                seller=seller,
                cart_data=cart_response,
                sent_payload=sent_payload,
            )
            logger.info(
                f'Shipment criado para pedido {order.order_number}, '
                f'vendedor {seller.email}, listing {listing_id}: '
                f'id={shipment.id}'
            )
            if insurance_warning:
                logger.warning(
                    f'Pedido {order.order_number}: {insurance_warning.get("message", "")}'
                )

    @staticmethod
    def _create_in_person_delivery_records(order, shipping_services_data):
        """
        Create OrderDelivery records for in_person sellers at order creation time.

        Called immediately after order and order items are persisted, so that
        in_person delivery details are visible in admin before payment confirmation.
        Shipping OrderDelivery records are created later by the payment signal.

        Args:
            order: Order instance already saved to DB
            shipping_services_data: Dict {str(seller_id): shipping_info}
        """
        from logistics.services.delivery_orchestration_service import DeliveryOrchestrationService

        delivery_choices = []
        for seller_id, shipping_info in shipping_services_data.items():
            if not isinstance(shipping_info, dict):
                continue
            dm = shipping_info.get('delivery_method')
            if dm == 'in_person':
                delivery_choices.append({'seller_id': int(seller_id), **shipping_info})
            elif dm == 'split':
                delivery_choices.append({
                    'seller_id': int(seller_id),
                    'delivery_method': 'split',
                    'shipping': shipping_info.get('shipping', {}),
                    'in_person': shipping_info.get('in_person', {}),
                })

        if not delivery_choices:
            return

        DeliveryOrchestrationService.create_order_deliveries(
            order=order,
            delivery_choices=delivery_choices,
        )
        logger.info(
            f'OrderDelivery criado para {len(delivery_choices)} vendedor(es) in_person '
            f'no pedido {order.order_number}'
        )

    @staticmethod
    def _check_sellers_me_balance(items_by_seller: dict, shipping_by_seller: dict):
        """
        Verifica se todos os vendedores com envio via ME têm saldo suficiente
        na carteira Melhor Envio para cobrir o custo do frete.

        Chamado ANTES de adicionar ao carrinho ME e de criar o pedido no banco.

        Política de falha:
        - 401 (token inválido/conta não conectada): levanta InsufficientMEBalanceError
          com mensagem indicando que o token precisa ser renovado.
        - Timeout / 5xx / erro de rede: loga o erro e pula a verificação para aquele
          vendedor (fail-open — instabilidade da ME API não deve bloquear o pedido).
        - Sem SellerMelhorEnvioToken: pula silenciosamente (o step 5.5 falhará depois
          com o erro original se necessário).

        Args:
            items_by_seller: dict {seller_id: [validated_items]}
            shipping_by_seller: dict {seller_id: Decimal(shipping_cost)}

        Raises:
            InsufficientMEBalanceError: se qualquer vendedor tiver saldo insuficiente
                ou token inválido/expirado (401)
        """
        from logistics.services.melhor_envio_service import MelhorEnvioService, ShippingValidationError
        from logistics.models import SellerMelhorEnvioToken
        from authentication.models import CustomUser

        me_service = MelhorEnvioService()
        environment = 'sandbox' if me_service.is_sandbox else 'production'

        insufficient_sellers = []

        for seller_id, shipping_cost in shipping_by_seller.items():
            if shipping_cost <= Decimal('0.00'):
                # In-person delivery — no ME balance needed
                continue

            # Get a seller instance from items_by_seller or query DB
            seller_items = items_by_seller.get(seller_id, [])
            if seller_items:
                seller = seller_items[0]['seller']
            else:
                try:
                    seller = CustomUser.objects.get(pk=seller_id)
                except CustomUser.DoesNotExist:
                    logger.warning(
                        f'_check_sellers_me_balance: seller_id={seller_id} não encontrado no DB. '
                        'Pulando verificação de saldo.'
                    )
                    continue

            # Skip if seller has no ME token (step 5.5 will handle this properly)
            has_token = SellerMelhorEnvioToken.objects.filter(
                seller=seller,
                environment=environment,
            ).exists()
            if not has_token:
                logger.debug(
                    f'Vendedor {seller.email} não tem SellerMelhorEnvioToken '
                    f'({environment}) — pulando verificação de saldo.'
                )
                continue

            try:
                balance = me_service.get_seller_balance(seller)
                logger.info(
                    "Step 4.5: Saldo ME do vendedor consultado",
                    extra={
                        'seller_email': seller.email,
                        'seller_id': seller.id,
                        'balance_available': float(balance),
                        'shipping_required': float(shipping_cost),
                        'sufficient': balance >= shipping_cost,
                    }
                )
            except ShippingValidationError as e:
                # 401 or token not found — treat as zero balance with clear error message
                logger.warning(
                    f'Saldo ME não verificável para vendedor {seller.email} '
                    f'(token inválido/expirado): {e}'
                )
                insufficient_sellers.append({
                    'seller_email': seller.email,
                    'required': shipping_cost,
                    'available': Decimal('0.00'),
                    'missing': shipping_cost,
                    'reason': str(e),
                })
                continue
            except Exception as e:
                # Timeout, 5xx, network error — fail open, do not block order
                logger.warning(
                    f'Erro ao consultar saldo ME do vendedor {seller.email}: {e}. '
                    'Verificação de saldo ignorada (fail-open).',
                    exc_info=True,
                )
                continue

            if balance < shipping_cost:
                missing = shipping_cost - balance
                logger.warning(
                    f'Saldo insuficiente: vendedor {seller.email} tem R$ {balance} '
                    f'mas precisa de R$ {shipping_cost} (faltam R$ {missing})'
                )
                insufficient_sellers.append({
                    'seller_email': seller.email,
                    'required': shipping_cost,
                    'available': balance,
                    'missing': missing,
                })

        if insufficient_sellers:
            raise InsufficientMEBalanceError(
                message=(
                    'Um ou mais vendedores não possuem saldo suficiente na carteira '
                    'Melhor Envio para cobrir o custo do frete.'
                ),
                sellers_info=insufficient_sellers,
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

        for seller_id_str, delivery_config in shipping_services_input.items():
            seller_id = int(seller_id_str)

            # Validate seller has items in cart
            if seller_id not in items_by_seller:
                raise OrderCreationError(
                    f"Seller {seller_id} not found in cart items"
                )

            delivery_method = delivery_config.get('delivery_method', 'shipping')

            # Validate shipping_method constraints on listings
            from products.models import ShippingMethodChoices as SMC
            seller_items = items_by_seller[seller_id]
            has_in_person_only = any(
                item['listing'].shipping_method == SMC.IN_PERSON
                for item in seller_items
            )
            has_me_only = any(
                item['listing'].shipping_method == SMC.MELHOR_ENVIO
                for item in seller_items
            )

            if has_in_person_only and delivery_method == 'shipping':
                in_person_titles = [
                    item['listing'].title
                    for item in seller_items
                    if item['listing'].shipping_method == SMC.IN_PERSON
                ]
                raise OrderCreationError(
                    f"Produto(s) do vendedor {seller_id} aceitam somente entrega "
                    f"presencial e não podem ser enviados via transportadora: "
                    f"{', '.join(in_person_titles)}"
                )

            if has_me_only and delivery_method == 'in_person':
                me_only_titles = [
                    item['listing'].title
                    for item in seller_items
                    if item['listing'].shipping_method == SMC.MELHOR_ENVIO
                ]
                raise OrderCreationError(
                    f"Produto(s) do vendedor {seller_id} aceitam somente envio via "
                    f"transportadora (Melhor Envio) e não podem ser entregues "
                    f"presencialmente: {', '.join(me_only_titles)}"
                )

            if delivery_method in ('shipping', 'split'):
                # --- Shipping via carrier (or split: shipping part) ---
                # Per-listing service selection: each listing may choose a different service.
                if delivery_method == 'split':
                    shipping_sub = delivery_config.get('shipping', {})
                    per_listing_input = shipping_sub.get('per_listing', {})
                else:
                    per_listing_input = delivery_config.get('per_listing', {})

                if not per_listing_input:
                    raise OrderCreationError(
                        f"per_listing is required for shipping delivery of seller {seller_id}"
                    )

                # Find valid shipping quote (one per seller)
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

                quotes_data = quote.quotes_data
                by_listing_data = (
                    quotes_data.get('by_listing', {}) if isinstance(quotes_data, dict) else {}
                )
                aggregate_services = (
                    quotes_data.get('services', []) if isinstance(quotes_data, dict)
                    else (quotes_data if isinstance(quotes_data, list) else [])
                )

                # Build per-listing result with costs (server-side, trusted)
                seller_shipping_cost = Decimal('0.00')
                per_listing_result: dict = {}

                for listing_id_str, listing_cfg in per_listing_input.items():
                    service_id = listing_cfg.get('service_id')
                    if not service_id:
                        raise OrderCreationError(
                            f"service_id missing for listing {listing_id_str} of seller {seller_id}"
                        )

                    # Find cost: prefer per-listing quote, fall back to aggregate
                    listing_quote_services = (
                        by_listing_data.get(str(listing_id_str), {}).get('services', [])
                        if by_listing_data else []
                    )
                    service_found = next(
                        (s for s in listing_quote_services
                         if isinstance(s, dict) and s.get('id') == service_id),
                        None
                    )
                    if service_found is None:
                        # Fallback to aggregate
                        service_found = next(
                            (s for s in aggregate_services
                             if isinstance(s, dict) and s.get('id') == service_id),
                            None
                        )
                    if service_found is None:
                        raise OrderCreationError(
                            f"Shipping service {service_id} not found for listing "
                            f"{listing_id_str} of seller {seller_id}"
                        )

                    listing_cost = Decimal(str(
                        service_found.get('custom_price', service_found.get('price', 0))
                    ))
                    seller_shipping_cost += listing_cost

                    company = service_found.get('company', '')
                    company_name = (
                        company.get('name', '') if isinstance(company, dict) else str(company)
                    )
                    per_listing_result[str(listing_id_str)] = {
                        'service_id': service_id,
                        'service_name': service_found.get('name', ''),
                        'company': company_name,
                        'cost': float(listing_cost),
                        'delivery_time': service_found.get('delivery_time', 0),
                    }

                total_shipping += seller_shipping_cost

                if delivery_method == 'split':
                    shipping_services_data[str(seller_id)] = {
                        'delivery_method': 'split',
                        'shipping': {'per_listing': per_listing_result},
                        'in_person': delivery_config.get('in_person', {}),
                    }
                else:
                    shipping_services_data[str(seller_id)] = {
                        'delivery_method': 'shipping',
                        'per_listing': per_listing_result,
                    }

                shipping_by_seller[seller_id] = seller_shipping_cost

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
        seller,
        subtotal: Decimal,
        shipping_cost: Decimal,
        total: Decimal,
        shipping_address,
        shipping_services_data: Dict,
        payment_method: str,
        buyer_notes: str
    ):
        """
        Create Order database record for a single seller.

        Args:
            user: Buyer user instance
            seller: Seller user instance (owner of all items in this order)
            subtotal: Order subtotal (this seller's items only)
            shipping_cost: Shipping cost for this seller
            total: Order total (subtotal + shipping)
            shipping_address: Address instance
            shipping_services_data: Shipping services data (scoped to this seller)
            payment_method: Payment method
            buyer_notes: Buyer notes

        Returns:
            Order instance
        """
        from orders.models import Order

        order = Order.objects.create(
            buyer=user,
            seller=seller,
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
            validated_items: List of validated cart items (all from the same seller)
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
