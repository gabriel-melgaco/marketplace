"""
Serviço de orquestração de entregas.
Coordena a criação de entregas (shipping ou in-person) durante o checkout.
"""

from django.db import transaction
from typing import Dict, List, Any
from decimal import Decimal

from ..models import (
    OrderDelivery,
    DeliveryMethod,
    ShippingQuote,
    DeliveryStatusLog
)
from .in_person_delivery_service import InPersonDeliveryService
from ..services import MelhorEnvioService
from orders.models import Order
from authentication.models import CustomUser


class DeliveryOrchestrationService:
    """
    Serviço principal para orquestrar entregas durante o checkout.
    Responsável por criar OrderDelivery baseado na escolha do usuário.
    """

    @staticmethod
    @transaction.atomic
    def create_order_deliveries(
        order: Order,
        delivery_choices: List[Dict[str, Any]]
    ) -> List[OrderDelivery]:
        """
        Cria entregas para o pedido baseado nas escolhas do usuário.

        Args:
            order: Pedido criado
            delivery_choices: Lista de escolhas de entrega por vendedor
                [
                    {
                        "seller_id": 1,
                        "delivery_method": "shipping",
                        "shipping_service_id": 3,
                        "delivery_cost": 25.90
                    },
                    {
                        "seller_id": 2,
                        "delivery_method": "in_person",
                        "meeting_location_name": "Shopping X",
                        "meeting_address": {...},
                        "seller_contact_phone": "11999999999",
                        "buyer_contact_phone": "11888888888",
                        "scheduled_date": "2026-02-10",
                        "scheduled_time": "14:00",
                        "meeting_notes": "Próximo à entrada principal"
                    }
                ]

        Returns:
            Lista de OrderDelivery criados
        """

        created_deliveries = []
        errors = []

        for choice in delivery_choices:
            seller_id = choice.get('seller_id')
            delivery_method = choice.get('delivery_method')

            # Buscar vendedor
            try:
                seller = CustomUser.objects.get(id=seller_id)
            except CustomUser.DoesNotExist:
                errors.append({
                    'seller_id': seller_id,
                    'error': 'Vendedor não encontrado'
                })
                continue

            # Verificar se há itens deste vendedor no pedido
            seller_items = order.items.filter(seller=seller)
            if not seller_items.exists():
                errors.append({
                    'seller_id': seller_id,
                    'error': 'Nenhum item deste vendedor no pedido'
                })
                continue

            try:
                if delivery_method == DeliveryMethod.SHIPPING:
                    # Criar entrega via transportadora
                    delivery = DeliveryOrchestrationService._create_shipping_delivery(
                        order=order,
                        seller=seller,
                        choice=choice
                    )
                    created_deliveries.append(delivery)

                elif delivery_method == DeliveryMethod.IN_PERSON:
                    # Criar entrega presencial
                    delivery = DeliveryOrchestrationService._create_in_person_delivery(
                        order=order,
                        seller=seller,
                        choice=choice
                    )
                    created_deliveries.append(delivery)

                else:
                    errors.append({
                        'seller_id': seller_id,
                        'error': f'Método de entrega inválido: {delivery_method}'
                    })

            except Exception as e:
                errors.append({
                    'seller_id': seller_id,
                    'error': str(e)
                })

        if errors:
            # Se houver erros, fazer rollback
            raise ValueError(f'Erros ao criar entregas: {errors}')

        return created_deliveries

    @staticmethod
    def _create_shipping_delivery(
        order: Order,
        seller: CustomUser,
        choice: Dict[str, Any]
    ) -> OrderDelivery:
        """
        Cria OrderDelivery do tipo SHIPPING.

        Args:
            order: Pedido
            seller: Vendedor
            choice: Dados da escolha (shipping_service_id, delivery_cost)

        Returns:
            OrderDelivery criado
        """

        shipping_service_id = choice.get('shipping_service_id')
        delivery_cost = Decimal(str(choice.get('delivery_cost', 0)))

        if not shipping_service_id:
            raise ValueError('shipping_service_id é obrigatório para envio via transportadora')

        # Criar OrderDelivery (sem Shipment ainda)
        # O Shipment será criado depois que o pagamento for confirmado
        order_delivery = OrderDelivery.objects.create(
            order=order,
            seller=seller,
            delivery_method=DeliveryMethod.SHIPPING,
            status='pending',
            delivery_cost=delivery_cost,
            shipment=None  # Será criado após pagamento confirmado
        )

        # Criar log
        DeliveryStatusLog.objects.create(
            order_delivery=order_delivery,
            from_status='',
            to_status='pending',
            notes=f'Entrega via transportadora criada. Service ID: {shipping_service_id}'
        )

        return order_delivery

    @staticmethod
    def _create_in_person_delivery(
        order: Order,
        seller: CustomUser,
        choice: Dict[str, Any]
    ) -> OrderDelivery:
        """
        Cria OrderDelivery do tipo IN_PERSON.

        Args:
            order: Pedido
            seller: Vendedor
            choice: Dados da escolha (meeting_location_name, etc)

        Returns:
            OrderDelivery criado
        """

        # Extrair dados do encontro
        meeting_location_name = choice.get('meeting_location_name')
        meeting_address = choice.get('meeting_address', {})
        seller_contact_phone = choice.get('seller_contact_phone')
        buyer_contact_phone = choice.get('buyer_contact_phone')
        scheduled_date = choice.get('scheduled_date')
        scheduled_time = choice.get('scheduled_time')
        meeting_notes = choice.get('meeting_notes', '')

        # Validar campos obrigatórios
        if not all([meeting_location_name, seller_contact_phone, buyer_contact_phone]):
            raise ValueError('Dados obrigatórios ausentes para entrega presencial')

        # Criar entrega presencial usando o serviço dedicado
        order_delivery = InPersonDeliveryService.create_order_delivery_in_person(
            order=order,
            seller=seller,
            meeting_location_name=meeting_location_name,
            meeting_address=meeting_address,
            seller_contact_phone=seller_contact_phone,
            buyer_contact_phone=buyer_contact_phone,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            meeting_notes=meeting_notes
        )

        return order_delivery

    @staticmethod
    def get_delivery_options_summary(order: Order) -> Dict[str, Any]:
        """
        Retorna resumo das opções de entrega configuradas para um pedido.

        Args:
            order: Pedido

        Returns:
            Dict com resumo das entregas por vendedor
        """

        deliveries = OrderDelivery.objects.filter(order=order).select_related(
            'seller', 'shipment', 'in_person_delivery'
        )

        summary = {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'total_delivery_cost': 0,
            'deliveries_by_seller': {}
        }

        for delivery in deliveries:
            seller_id = str(delivery.seller.id)
            delivery_info = delivery.get_delivery_info()

            summary['deliveries_by_seller'][seller_id] = {
                'seller_id': delivery.seller.id,
                'seller_name': delivery.seller.get_full_name() or delivery.seller.email,
                'delivery_method': delivery.get_delivery_method_display(),
                'status': delivery.get_status_display(),
                'cost': float(delivery.delivery_cost),
                'details': delivery_info
            }

            summary['total_delivery_cost'] += float(delivery.delivery_cost)

        return summary

    @staticmethod
    @transaction.atomic
    def update_delivery_status(
        order_delivery: OrderDelivery,
        new_status: str,
        user: CustomUser,
        notes: str = ""
    ) -> OrderDelivery:
        """
        Atualiza status de uma entrega com validação e log.

        Args:
            order_delivery: OrderDelivery a ser atualizado
            new_status: Novo status
            user: Usuário fazendo a atualização
            notes: Observações

        Returns:
            OrderDelivery atualizado
        """

        old_status = order_delivery.status

        if old_status == new_status:
            return order_delivery

        # Validar transição
        valid_transitions = {
            'pending': ['confirmed', 'cancelled'],
            'confirmed': ['ready', 'cancelled'],
            'ready': ['in_transit', 'delivered', 'cancelled'],
            'in_transit': ['delivered', 'failed'],
            'delivered': [],  # Estado final
            'cancelled': [],  # Estado final
            'failed': ['pending'],  # Pode tentar novamente
        }

        if new_status not in valid_transitions.get(old_status, []):
            raise ValueError(
                f'Transição inválida de {old_status} para {new_status}'
            )

        # Atualizar status
        order_delivery.status = new_status

        # Atualizar timestamps
        from django.utils import timezone
        if new_status == 'confirmed':
            order_delivery.confirmed_at = timezone.now()
        elif new_status == 'delivered':
            order_delivery.completed_at = timezone.now()

        order_delivery.save()

        # Criar log
        DeliveryStatusLog.objects.create(
            order_delivery=order_delivery,
            from_status=old_status,
            to_status=new_status,
            changed_by=user,
            notes=notes
        )

        return order_delivery
