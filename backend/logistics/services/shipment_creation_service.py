"""
Serviço de criação de shipments.
Extrai lógica de negócio da view para garantir atomicidade e separação de concerns.
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
    Cria shipments para todos os sellers de um pedido com rollback atômico.

    Se qualquer seller falhar, todos os registros locais (Shipment) são revertidos
    via @transaction.atomic. Chamadas à API Melhor Envio não são reversíveis por
    transação DB, mas garante consistência local.
    """

    @staticmethod
    @transaction.atomic
    def create_shipments_for_order(order, shipping_services_override=None):
        """
        Cria shipments para todos os sellers de um pedido.

        Args:
            order: Order instance (já buscada do banco)
            shipping_services_override: Dict opcional para sobrescrever
                shipping_services do pedido

        Returns:
            tuple: (lista de Shipment criados, lista de warnings)

        Raises:
            ShipmentCreationError: se validação falhar ou criação de shipment falhar
        """
        # Validar status do pedido
        if order.status != OrderStateMachine.PAID:
            raise ShipmentCreationError('Pedido precisa ter pagamento confirmado')

        # Obter shipping_services do pedido ou override
        shipping_services = shipping_services_override or order.shipping_services

        if not shipping_services:
            raise ShipmentCreationError(
                'shipping_services não encontrado. '
                'O pedido não possui informações de frete salvas. '
                'Isso pode ocorrer se o pedido foi criado antes da atualização do sistema.'
            )

        # Agrupar itens por vendedor
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
                created_shipments.append(existing)
                continue

            # Pegar serviço de frete escolhido do shipping_services salvo
            seller_shipping = shipping_services.get(str(seller_id))

            if not seller_shipping:
                raise ShipmentCreationError(
                    f'Serviço de frete não encontrado para vendedor '
                    f'{seller.get_full_name() or seller.email} (ID: {seller_id})'
                )

            # Extrair service_id (pode ser int ou dict)
            if isinstance(seller_shipping, dict):
                service_id = seller_shipping.get('service_id')
            else:
                service_id = seller_shipping

            if not service_id:
                raise ShipmentCreationError(
                    f'service_id não encontrado para vendedor '
                    f'{seller.get_full_name() or seller.email} (ID: {seller_id})'
                )

            try:
                shipment, insurance_warning = melhor_envio.create_shipment(
                    order=order,
                    seller=seller,
                    shipping_service_id=service_id
                )
                created_shipments.append(shipment)
                if insurance_warning:
                    warnings.append(insurance_warning)
            except Exception as e:
                raise ShipmentCreationError(
                    f'Erro ao criar envio para vendedor '
                    f'{seller.get_full_name() or seller.email} (ID: {seller_id}): {e}'
                ) from e

        # Atualizar status do pedido para PROCESSING
        OrderStateMachine.transition_to(
            order=order,
            new_status=OrderStateMachine.PROCESSING,
            notes='Shipments criados para todos os vendedores'
        )

        logger.info(
            f"Shipments criados para pedido {order.order_number}: "
            f"{len(created_shipments)} envio(s)"
        )

        return created_shipments, warnings
