"""
Serviço para gerenciar entregas presenciais (in-person delivery).
Responsável por criar, atualizar e confirmar entregas presenciais.
"""

from django.db import transaction
from django.utils import timezone
from typing import Dict, Any, Optional
from datetime import datetime, time

from ..models import (
    InPersonDelivery,
    OrderDelivery,
    DeliveryMethod,
    DeliveryStatusLog
)
from orders.models import Order
from authentication.models import CustomUser


class InPersonDeliveryService:
    """Serviço para operações de entrega presencial"""

    @staticmethod
    @transaction.atomic
    def create_in_person_delivery(
        order: Order,
        seller: CustomUser,
        buyer: CustomUser,
        meeting_location_name: str = "",
        meeting_address: Optional[Dict[str, Any]] = None,
        seller_contact_phone: str = "",
        buyer_contact_phone: str = "",
        scheduled_date: Optional[datetime] = None,
        scheduled_time: Optional[time] = None,
        meeting_notes: str = ""
    ) -> InPersonDelivery:
        """
        Cria uma entrega presencial.

        Args:
            order: Pedido associado
            seller: Vendedor
            buyer: Comprador
            meeting_location_name: Nome do local de encontro
            meeting_address: Endereço do local (dict com street, city, etc)
            seller_contact_phone: Telefone do vendedor
            buyer_contact_phone: Telefone do comprador
            scheduled_date: Data agendada (opcional)
            scheduled_time: Horário agendado (opcional)
            meeting_notes: Observações adicionais

        Returns:
            InPersonDelivery criado
        """

        # Validar se já existe entrega presencial para este pedido/seller/buyer
        existing = InPersonDelivery.objects.filter(
            order=order,
            seller=seller,
            buyer=buyer,
            meeting_status__in=['pending_schedule', 'scheduled', 'confirmed']
        ).first()

        if existing:
            raise ValueError(
                f'Já existe uma entrega presencial pendente para o pedido {order.id}'
            )

        # Definir status inicial
        initial_status = 'pending_schedule'
        if scheduled_date and scheduled_time:
            initial_status = 'scheduled'

        # Criar entrega presencial
        in_person_delivery = InPersonDelivery.objects.create(
            seller=seller,
            buyer=buyer,
            meeting_status=initial_status,
            meeting_location_name=meeting_location_name or '',
            meeting_address=meeting_address or {},
            meeting_notes=meeting_notes,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            seller_contact_phone=seller_contact_phone or '',
            buyer_contact_phone=buyer_contact_phone or '',
        )

        # Notificar ambas as partes se a entrega já foi agendada na criação
        if initial_status == 'scheduled':
            try:
                from notifications.services.notification_service import NotificationService
                from notifications.models import NotificationType
                _scheduled = f'{scheduled_date} às {scheduled_time}'
                for _recipient in [seller, buyer]:
                    NotificationService.notify(
                        recipient=_recipient,
                        event_type=NotificationType.DELIVERY_SCHEDULED,
                        title='Entrega presencial agendada',
                        body=f'A entrega presencial foi agendada para {_scheduled} em {meeting_location_name or "local a definir"}.',
                        metadata={
                            'in_person_delivery_id': str(in_person_delivery.id),
                            'location': meeting_location_name,
                            'scheduled_date': str(scheduled_date),
                            'scheduled_time': str(scheduled_time),
                        },
                        idempotency_key=f'delivery_scheduled_{in_person_delivery.id}_created_{_recipient.pk}',
                    )
            except Exception:
                pass

        return in_person_delivery

    @staticmethod
    @transaction.atomic
    def create_order_delivery_in_person(
        order: Order,
        seller: CustomUser,
        meeting_location_name: str = "",
        meeting_address: Optional[Dict[str, Any]] = None,
        seller_contact_phone: str = "",
        buyer_contact_phone: str = "",
        scheduled_date: Optional[datetime] = None,
        scheduled_time: Optional[time] = None,
        meeting_notes: str = ""
    ) -> OrderDelivery:
        """
        Cria OrderDelivery do tipo IN_PERSON com InPersonDelivery associado.

        Args:
            order: Pedido
            seller: Vendedor
            meeting_location_name: Nome do local
            meeting_address: Endereço completo do local
            seller_contact_phone: Telefone do vendedor
            buyer_contact_phone: Telefone do comprador
            scheduled_date: Data agendada (opcional)
            scheduled_time: Horário agendado (opcional)
            meeting_notes: Observações

        Returns:
            OrderDelivery criado
        """

        buyer = order.buyer

        # Verificar se já existe OrderDelivery para este seller
        existing_delivery = OrderDelivery.objects.filter(
            order=order,
            seller=seller
        ).first()

        if existing_delivery:
            raise ValueError(
                f'Já existe uma entrega configurada para o vendedor {seller.email} neste pedido'
            )

        # Criar InPersonDelivery
        in_person_delivery = InPersonDeliveryService.create_in_person_delivery(
            order=order,
            seller=seller,
            buyer=buyer,
            meeting_location_name=meeting_location_name,
            meeting_address=meeting_address,
            seller_contact_phone=seller_contact_phone,
            buyer_contact_phone=buyer_contact_phone,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            meeting_notes=meeting_notes
        )

        # Criar OrderDelivery
        order_delivery = OrderDelivery.objects.create(
            order=order,
            seller=seller,
            delivery_method=DeliveryMethod.IN_PERSON,
            status='pending',
            delivery_cost=0,  # Entrega presencial não tem custo
            in_person_delivery=in_person_delivery
        )

        # Criar log
        DeliveryStatusLog.objects.create(
            order_delivery=order_delivery,
            from_status='',
            to_status='pending',
            notes='Entrega presencial criada'
        )

        return order_delivery

    @staticmethod
    @transaction.atomic
    def confirm_meeting(
        in_person_delivery: InPersonDelivery,
        user: CustomUser
    ) -> InPersonDelivery:
        """
        Confirma o encontro por uma das partes (seller ou buyer).

        Args:
            in_person_delivery: Entrega presencial
            user: Usuário que está confirmando (seller ou buyer)

        Returns:
            InPersonDelivery atualizado
        """

        # Verificar se o usuário é parte do encontro
        if user == in_person_delivery.seller:
            if in_person_delivery.seller_confirmed:
                raise ValueError('Vendedor já confirmou este encontro')

            in_person_delivery.seller_confirmed = True
            in_person_delivery.seller_confirmed_at = timezone.now()

        elif user == in_person_delivery.buyer:
            if in_person_delivery.buyer_confirmed:
                raise ValueError('Comprador já confirmou este encontro')

            in_person_delivery.buyer_confirmed = True
            in_person_delivery.buyer_confirmed_at = timezone.now()

        else:
            raise ValueError('Usuário não é parte deste encontro')

        # Salvar confirmação
        in_person_delivery.save()

        # Se ambos confirmaram, atualizar OrderDelivery
        if in_person_delivery.is_fully_confirmed():
            try:
                order_delivery = in_person_delivery.order_delivery
                if order_delivery.status == 'pending':
                    order_delivery.status = 'confirmed'
                    order_delivery.confirmed_at = timezone.now()
                    order_delivery.save()

                    # Log
                    DeliveryStatusLog.objects.create(
                        order_delivery=order_delivery,
                        from_status='pending',
                        to_status='confirmed',
                        changed_by=user,
                        notes='Ambas as partes confirmaram o encontro'
                    )

                    # Notificar ambas as partes sobre a confirmação da entrega
                    try:
                        from notifications.services.notification_service import NotificationService
                        from notifications.models import NotificationType
                        for _recipient in [in_person_delivery.seller, in_person_delivery.buyer]:
                            NotificationService.notify(
                                recipient=_recipient,
                                event_type=NotificationType.DELIVERY_CONFIRMED,
                                title='Entrega presencial confirmada',
                                body='Ambas as partes confirmaram a entrega presencial. O encontro está confirmado.',
                                metadata={
                                    'in_person_delivery_id': str(in_person_delivery.id),
                                    'order_delivery_id': str(order_delivery.id),
                                    'location': in_person_delivery.meeting_location_name,
                                    'scheduled_date': str(in_person_delivery.scheduled_date),
                                    'scheduled_time': str(in_person_delivery.scheduled_time),
                                },
                                idempotency_key=f'delivery_confirmed_{in_person_delivery.id}_{_recipient.pk}',
                            )
                    except Exception:
                        pass
            except OrderDelivery.DoesNotExist:
                pass

        return in_person_delivery

    @staticmethod
    @transaction.atomic
    def update_meeting_details(
        in_person_delivery: InPersonDelivery,
        user: CustomUser,
        **kwargs
    ) -> InPersonDelivery:
        """
        Atualiza detalhes do encontro.

        Args:
            in_person_delivery: Entrega presencial
            user: Usuário fazendo a atualização
            **kwargs: Campos a serem atualizados

        Returns:
            InPersonDelivery atualizado
        """

        # Verificar permissão
        if user not in [in_person_delivery.seller, in_person_delivery.buyer]:
            raise ValueError('Usuário não tem permissão para atualizar este encontro')

        # Campos permitidos para atualização
        allowed_fields = [
            'meeting_location_name', 'meeting_address', 'meeting_notes',
            'scheduled_date', 'scheduled_time', 'meeting_status'
        ]

        updated = False
        for field, value in kwargs.items():
            if field in allowed_fields:
                setattr(in_person_delivery, field, value)
                updated = True

        if updated:
            # Se data/hora foram atualizados, resetar confirmações e agendar
            if 'scheduled_date' in kwargs or 'scheduled_time' in kwargs:
                if in_person_delivery.seller_confirmed or in_person_delivery.buyer_confirmed:
                    in_person_delivery.seller_confirmed = False
                    in_person_delivery.buyer_confirmed = False
                    in_person_delivery.seller_confirmed_at = None
                    in_person_delivery.buyer_confirmed_at = None

                if in_person_delivery.scheduled_date and in_person_delivery.scheduled_time:
                    in_person_delivery.meeting_status = 'scheduled'

            in_person_delivery.save()

            # Notificar ambas as partes quando encontro for agendado/reagendado
            if (
                ('scheduled_date' in kwargs or 'scheduled_time' in kwargs)
                and in_person_delivery.scheduled_date
                and in_person_delivery.scheduled_time
            ):
                try:
                    from notifications.services.notification_service import NotificationService
                    from notifications.models import NotificationType
                    _scheduled = f'{in_person_delivery.scheduled_date} às {in_person_delivery.scheduled_time}'
                    for _recipient in [in_person_delivery.seller, in_person_delivery.buyer]:
                        NotificationService.notify(
                            recipient=_recipient,
                            event_type=NotificationType.DELIVERY_SCHEDULED,
                            title='Entrega presencial agendada',
                            body=f'A entrega presencial foi agendada para {_scheduled}.',
                            metadata={
                                'in_person_delivery_id': str(in_person_delivery.id),
                                'location': in_person_delivery.meeting_location_name,
                                'scheduled_date': str(in_person_delivery.scheduled_date),
                                'scheduled_time': str(in_person_delivery.scheduled_time),
                            },
                            idempotency_key=(
                                f'delivery_scheduled_{in_person_delivery.id}'
                                f'_{in_person_delivery.scheduled_date}_{_recipient.pk}'
                            ),
                        )
                except Exception:
                    pass

        return in_person_delivery

    @staticmethod
    @transaction.atomic
    def complete_delivery(
        in_person_delivery: InPersonDelivery,
        user: CustomUser,
        completion_notes: str = ""
    ) -> InPersonDelivery:
        """
        Confirma a conclusão da entrega por uma das partes (seller ou buyer).
        Ambas as partes precisam confirmar para que o status mude para 'completed'.

        Args:
            in_person_delivery: Entrega presencial
            user: Usuário confirmando a conclusão (seller ou buyer)
            completion_notes: Observações sobre a conclusão

        Returns:
            InPersonDelivery atualizado
        """

        if user not in [in_person_delivery.seller, in_person_delivery.buyer]:
            raise ValueError('Usuário não tem permissão para concluir esta entrega')

        if not in_person_delivery.can_be_completed():
            raise ValueError(
                f'Entrega com status {in_person_delivery.meeting_status} não pode ser concluída'
            )

        if user == in_person_delivery.seller:
            if in_person_delivery.seller_completed:
                raise ValueError('Vendedor já confirmou a conclusão desta entrega')
            in_person_delivery.seller_completed = True
            in_person_delivery.seller_completed_at = timezone.now()

        elif user == in_person_delivery.buyer:
            if in_person_delivery.buyer_completed:
                raise ValueError('Comprador já confirmou a conclusão desta entrega')
            in_person_delivery.buyer_completed = True
            in_person_delivery.buyer_completed_at = timezone.now()

        if completion_notes:
            in_person_delivery.completion_notes = completion_notes

        # save() do modelo muda meeting_status para 'completed' se ambos confirmaram
        in_person_delivery.save()

        # Se ambos confirmaram, atualizar OrderDelivery e verificar Order
        if in_person_delivery.is_fully_completed():
            try:
                order_delivery = in_person_delivery.order_delivery
                old_status = order_delivery.status
                order_delivery.status = 'delivered'
                order_delivery.completed_at = timezone.now()
                order_delivery.save()

                DeliveryStatusLog.objects.create(
                    order_delivery=order_delivery,
                    from_status=old_status,
                    to_status='delivered',
                    changed_by=user,
                    notes=f'Ambas as partes confirmaram a conclusão. {completion_notes}'
                )

                # Se TODAS as entregas do pedido estão entregues, marcar order como delivered
                order = order_delivery.order
                all_deliveries = order.deliveries.all()
                if all_deliveries.exists() and all(
                    d.status == 'delivered' for d in all_deliveries
                ):
                    from orders.services.order_state_machine import OrderStateMachine
                    try:
                        OrderStateMachine.transition_to(
                            order=order,
                            new_status=OrderStateMachine.DELIVERED,
                            changed_by=user,
                            notes='Todas as entregas concluídas.',
                        )
                    except Exception:
                        pass  # Order pode já estar em estado terminal

            except OrderDelivery.DoesNotExist:
                pass

        return in_person_delivery

    @staticmethod
    @transaction.atomic
    def cancel_delivery(
        in_person_delivery: InPersonDelivery,
        user: CustomUser,
        cancellation_reason: str = ""
    ) -> InPersonDelivery:
        """
        Cancela a entrega presencial.

        Args:
            in_person_delivery: Entrega presencial
            user: Usuário cancelando
            cancellation_reason: Motivo do cancelamento

        Returns:
            InPersonDelivery atualizado
        """

        # Verificar permissão
        if user not in [in_person_delivery.seller, in_person_delivery.buyer]:
            raise ValueError('Usuário não tem permissão para cancelar esta entrega')

        # Não pode cancelar se já foi concluída
        if in_person_delivery.meeting_status == 'completed':
            raise ValueError('Não é possível cancelar uma entrega já concluída')

        # Atualizar status
        in_person_delivery.meeting_status = 'cancelled'
        in_person_delivery.completion_notes = f'Cancelado por {user.email}. Motivo: {cancellation_reason}'
        in_person_delivery.save()

        # Atualizar OrderDelivery
        try:
            order_delivery = in_person_delivery.order_delivery
            old_status = order_delivery.status
            order_delivery.status = 'cancelled'
            order_delivery.save()

            # Log
            DeliveryStatusLog.objects.create(
                order_delivery=order_delivery,
                from_status=old_status,
                to_status='cancelled',
                changed_by=user,
                notes=f'Entrega presencial cancelada. {cancellation_reason}'
            )
        except OrderDelivery.DoesNotExist:
            pass

        return in_person_delivery
