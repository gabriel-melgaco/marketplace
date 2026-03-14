"""
Serviço de criação de shipments.
Extrai lógica de negócio da view para garantir atomicidade e separação de concerns.

Fluxo de dois passos:
  1. create_shipments_for_order() → chamado na criação do pedido (orders/create/)
     - Adiciona ao carrinho do Melhor Envio (POST /api/v2/me/cart)
     - Cria registro de Shipment no banco com status 'pending'
     - Salva o melhorenvio_order_id (ID do carrinho ME) no Shipment

  2. checkout_shipments_for_order() → chamado no endpoint de criação de shipments
     (POST /api/logistics/shipments/create/)
     - Lê os melhorenvio_order_id dos Shipments existentes
     - Chama checkout do Melhor Envio (POST /api/v2/me/shipment/checkout)
     - Atualiza status dos Shipments para 'created'
"""

import logging
from django.db import transaction

from ..models import Shipment
from .melhor_envio_service import MelhorEnvioService
from orders.services.order_state_machine import OrderStateMachine

logger = logging.getLogger(__name__)


class ShipmentCreationError(Exception):
    """Raised when shipment creation fails"""
    pass


class ShipmentCreationService:
    """
    Gerencia o ciclo de vida de criação de shipments em dois passos.

    Passo 1 - create_shipments_for_order():
        Chamado durante a criação do pedido. Adiciona cada envio ao carrinho
        do Melhor Envio e cria os registros de Shipment (status='pending').
        Se qualquer seller falhar, todos os registros locais são revertidos
        via @transaction.atomic. Chamadas à API Melhor Envio não são reversíveis
        por transação DB, mas a consistência local é garantida.

    Passo 2 - checkout_shipments_for_order():
        Chamado no endpoint /api/logistics/shipments/create/ após o pagamento
        ser confirmado. Lê os melhorenvio_order_id dos Shipments já criados
        e realiza o checkout no Melhor Envio.
    """

    @staticmethod
    @transaction.atomic
    def create_shipments_for_order(order, shipping_services_override=None):
        """
        PASSO 1: Adiciona envios ao carrinho do Melhor Envio e cria registros
        de Shipment no banco de dados para todos os sellers de um pedido.

        Este método é chamado durante a criação do pedido em orders/create/.
        Não faz checkout - apenas adiciona ao carrinho e salva o cart_id.

        Args:
            order: Order instance (já buscada do banco)
            shipping_services_override: Dict opcional para sobrescrever
                shipping_services do pedido

        Returns:
            tuple: (lista de Shipment criados, lista de warnings)

        Raises:
            ShipmentCreationError: se validação falhar ou adição ao carrinho falhar
        """
        # Obter shipping_services do pedido ou override
        shipping_services = shipping_services_override or order.shipping_services

        if not shipping_services:
            raise ShipmentCreationError(
                'shipping_services não encontrado. '
                'O pedido não possui informações de frete salvas. '
                'Isso pode ocorrer se o pedido foi criado antes da atualização do sistema.'
            )

        # Agrupar itens por vendedor (apenas os que usam shipping, não in_person)
        sellers = order.items.values_list('seller', flat=True).distinct()

        created_shipments = []
        warnings = []
        melhor_envio = MelhorEnvioService()

        for seller_id in sellers:
            seller_items = order.items.filter(seller_id=seller_id)
            seller = seller_items.first().seller

            # Verificar se já existe envio para este vendedor
            existing = Shipment.objects.filter(order=order, seller=seller).first()
            if existing:
                logger.info(
                    f'Shipment já existe para vendedor {seller.email} no pedido '
                    f'{order.order_number}. Pulando.'
                )
                created_shipments.append(existing)
                continue

            # Pegar configuração de entrega do shipping_services salvo
            seller_shipping = shipping_services.get(str(seller_id))

            if not seller_shipping:
                logger.info(
                    f'Nenhuma configuração de frete para vendedor {seller_id} '
                    f'no pedido {order.order_number}. Pulando (pode ser entrega presencial).'
                )
                continue

            # Extrair delivery_method e service_id
            if isinstance(seller_shipping, dict):
                delivery_method = seller_shipping.get('delivery_method', 'shipping')
                if delivery_method == 'split':
                    # Split: use the shipping sub-config for the ME Shipment
                    service_id = seller_shipping.get('shipping', {}).get('service_id')
                    delivery_method = 'shipping'  # treat as shipping from here on
                else:
                    service_id = seller_shipping.get('service_id')
            else:
                # Formato legado: inteiro diretamente
                delivery_method = 'shipping'
                service_id = seller_shipping

            # Apenas criar shipment para entregas via transportadora
            if delivery_method != 'shipping':
                logger.info(
                    f'Entrega presencial configurada para vendedor {seller_id}. '
                    f'Pulando criação de Shipment.'
                )
                continue

            if not service_id:
                raise ShipmentCreationError(
                    f'service_id não encontrado para vendedor '
                    f'{seller.get_full_name() or seller.email} (ID: {seller_id})'
                )

            try:
                # PASSO 1: Adicionar ao carrinho e criar registro de Shipment (sem checkout)
                shipment, insurance_warning = melhor_envio.add_to_cart_and_create_shipment(
                    order=order,
                    seller=seller,
                    shipping_service_id=service_id
                )
                created_shipments.append(shipment)
                if insurance_warning:
                    warnings.append(insurance_warning)

                logger.info(
                    f'Shipment criado para vendedor {seller.email}: '
                    f'melhorenvio_order_id={shipment.melhorenvio_order_id}, '
                    f'status={shipment.status}'
                )

            except Exception as e:
                raise ShipmentCreationError(
                    f'Erro ao adicionar ao carrinho para vendedor '
                    f'{seller.get_full_name() or seller.email} (ID: {seller_id}): {e}'
                ) from e

        logger.info(
            f"Shipments adicionados ao carrinho para pedido {order.order_number}: "
            f"{len(created_shipments)} envio(s)"
        )

        return created_shipments, warnings

    @staticmethod
    @transaction.atomic
    def checkout_shipments_for_order(order):
        """
        PASSO 2: Faz checkout dos shipments já adicionados ao carrinho.

        Este método é chamado no endpoint /api/logistics/shipments/create/
        após a confirmação do pagamento.

        Lê os melhorenvio_order_id dos Shipments existentes (status='pending')
        e realiza o checkout no Melhor Envio. Atualiza o status para 'created'
        após o checkout bem-sucedido.

        Args:
            order: Order instance (já buscada do banco)

        Returns:
            tuple: (lista de Shipment atualizados, resultado do checkout)

        Raises:
            ShipmentCreationError: se validação falhar ou checkout falhar
        """
        # Validar status do pedido
        if order.status != OrderStateMachine.PAID:
            raise ShipmentCreationError('Pedido precisa ter pagamento confirmado')

        # Buscar shipments existentes com status 'pending' (aguardando checkout)
        pending_shipments = Shipment.objects.filter(
            order=order,
            status='pending'
        ).select_related('seller')

        if not pending_shipments.exists():
            # Verificar se já existem shipments com status 'created' (checkout já feito)
            existing_checked_out = Shipment.objects.filter(
                order=order,
                status__in=['created', 'released', 'generated', 'posted',
                            'in_transit', 'out_for_delivery', 'delivered']
            )
            if existing_checked_out.exists():
                logger.info(
                    f'Checkout já foi realizado para o pedido {order.order_number}. '
                    f'Retornando shipments existentes.'
                )
                # Atualizar status do pedido para PROCESSING se necessário
                if OrderStateMachine.can_transition(order.status, OrderStateMachine.PROCESSING):
                    OrderStateMachine.transition_to(
                        order=order,
                        new_status=OrderStateMachine.PROCESSING,
                        notes='Checkout de shipments já realizado anteriormente'
                    )
                return list(existing_checked_out), {}

            raise ShipmentCreationError(
                f'Nenhum shipment pendente encontrado para o pedido {order.order_number}. '
                f'Verifique se os shipments foram criados durante a criação do pedido.'
            )

        # Agrupar shipments pendentes por vendedor para chamar checkout com o token correto
        from collections import defaultdict
        shipments_by_seller = defaultdict(list)
        for shipment in pending_shipments:
            has_ids = bool(shipment.melhorenvio_order_ids or shipment.melhorenvio_order_id)
            if not has_ids:
                raise ShipmentCreationError(
                    f'Shipment {shipment.id} não possui melhorenvio_order_id. '
                    f'O carrinho não foi adicionado corretamente.'
                )
            shipments_by_seller[shipment.seller].append(shipment)

        def _all_me_ids(shipment):
            """Retorna todos os IDs ME do shipment (suporte a multi-pacote)."""
            return shipment.melhorenvio_order_ids or [shipment.melhorenvio_order_id]

        all_cart_ids = [mid for s in pending_shipments for mid in _all_me_ids(s)]
        logger.info(
            f'Fazendo checkout de {len(all_cart_ids)} ID(s) ME para pedido '
            f'{order.order_number}: {all_cart_ids}'
        )

        # Chamar checkout do Melhor Envio por vendedor (usa token OAuth do vendedor)
        melhor_envio = MelhorEnvioService()
        checkout_result = {}
        try:
            for seller, seller_shipments in shipments_by_seller.items():
                seller_cart_ids = [mid for s in seller_shipments for mid in _all_me_ids(s)]
                logger.info(
                    f'Checkout para vendedor {seller.email}: '
                    f'cart_ids={seller_cart_ids}'
                )
                result = melhor_envio.checkout_cart(seller_cart_ids, seller=seller)
                checkout_result[str(seller.id)] = result
        except Exception as e:
            raise ShipmentCreationError(
                f'Erro no checkout do Melhor Envio para pedido {order.order_number}: {e}'
            ) from e

        # Atualizar status dos Shipments para 'created' após checkout bem-sucedido
        checkedout_shipments = []
        for shipment in pending_shipments:
            shipment.status = 'created'
            shipment.save(update_fields=['status', 'updated_at'])
            checkedout_shipments.append(shipment)

            logger.info(
                f'Shipment {shipment.id} atualizado para status=created '
                f'após checkout. melhorenvio_order_id={shipment.melhorenvio_order_id}'
            )

        # Atualizar status do pedido para PROCESSING
        OrderStateMachine.transition_to(
            order=order,
            new_status=OrderStateMachine.PROCESSING,
            notes='Checkout de shipments realizado com sucesso no Melhor Envio'
        )

        logger.info(
            f"Checkout realizado para pedido {order.order_number}: "
            f"{len(checkedout_shipments)} envio(s)"
        )

        # Notify buyer about shipment creation.
        try:
            from notifications.services import NotificationService
            from notifications.models import NotificationType
            NotificationService.notify(
                recipient=order.buyer,
                event_type=NotificationType.SHIPMENT_CREATED,
                title=f'Envio criado — Pedido #{order.order_number}',
                body=(
                    f'O envio do seu pedido #{order.order_number} foi criado. '
                    f'{len(checkedout_shipments)} pacote(s) serão enviados.'
                ),
                metadata={
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'shipment_count': len(checkedout_shipments),
                },
                idempotency_key=f'shipment_created_{order.id}',
            )
        except Exception as _notify_exc:
            logger.warning(
                'Falha ao enfileirar notificação shipment_created para pedido %s: %s',
                order.order_number,
                _notify_exc,
            )

        return checkedout_shipments, checkout_result
