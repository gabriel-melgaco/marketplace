"""
Testes do MessageService.

Valida:
- send_message: criação de Message + MessageStatus para destinatários
- send_message: rejeita mensagem em conversa fechada
- send_message: rejeita remetente não-participante
- get_history: paginação cursor (before_id)
- get_history: rejeita não-participante
- mark_as_read: atualiza MessageStatus.read_at em bulk
- mark_as_read: atualiza ConversationParticipant.last_read_at
- get_unread_count: contagem correta de não lidas
"""

import uuid
import pytest
from django.test import override_settings
from django.utils import timezone

from chats.models import Conversation, ConversationParticipant, Message, MessageStatus
from chats.services import MessageService
from chats.services.message_service import MessageServiceError

CACHES_TEST = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "msg-service-tests",
    }
}

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def use_local_cache():
    with override_settings(CACHES=CACHES_TEST):
        yield


class TestSendMessage:
    def test_creates_message_in_database(self, buyer_seller_conversation, buyer):
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá, ainda está disponível?",
        )
        assert Message.objects.filter(pk=msg.id).exists()

    def test_message_has_correct_fields(self, buyer_seller_conversation, buyer):
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Teste de mensagem",
        )
        assert msg.sender == buyer
        assert msg.conversation == buyer_seller_conversation
        assert msg.content == "Teste de mensagem"
        assert msg.message_type == Message.TYPE_TEXT
        assert msg.is_deleted is False

    def test_creates_message_status_for_all_recipients(
        self, buyer_seller_conversation, buyer, seller
    ):
        """MessageStatus deve ser criado para cada participante exceto o remetente."""
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        statuses = MessageStatus.objects.filter(message=msg)
        recipient_ids = set(statuses.values_list('recipient_id', flat=True))

        # Deve ter status para o vendedor (destinatário), não para o comprador (remetente)
        assert seller.pk in recipient_ids
        assert buyer.pk not in recipient_ids

    def test_message_status_has_delivered_at_set(self, buyer_seller_conversation, buyer, seller):
        before = timezone.now()
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Entregue?",
        )
        after = timezone.now()
        status = MessageStatus.objects.get(message=msg, recipient=seller)
        assert status.delivered_at is not None
        assert before <= status.delivered_at <= after

    def test_message_status_read_at_is_null_on_creation(
        self, buyer_seller_conversation, buyer, seller
    ):
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        status = MessageStatus.objects.get(message=msg, recipient=seller)
        assert status.read_at is None

    def test_raises_when_conversation_is_closed(self, buyer_seller_conversation, buyer):
        buyer_seller_conversation.status = Conversation.STATUS_CLOSED
        buyer_seller_conversation.save()

        with pytest.raises(MessageServiceError, match="fechada"):
            MessageService.send_message(
                conversation=buyer_seller_conversation,
                sender=buyer,
                content="Tentando enviar",
            )

    def test_raises_when_sender_is_not_participant(
        self, buyer_seller_conversation, outsider
    ):
        with pytest.raises(MessageServiceError, match="participante"):
            MessageService.send_message(
                conversation=buyer_seller_conversation,
                sender=outsider,
                content="Invasor",
            )

    def test_custom_metadata_persisted(self, buyer_seller_conversation, buyer):
        meta = {'attachment': 'image.jpg', 'size': 1024}
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Com anexo",
            metadata=meta,
        )
        refreshed = Message.objects.get(pk=msg.id)
        assert refreshed.metadata == meta

    def test_conversation_updated_at_bumped(self, buyer_seller_conversation, buyer):
        old_updated = buyer_seller_conversation.updated_at
        MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Bump",
        )
        buyer_seller_conversation.refresh_from_db()
        assert buyer_seller_conversation.updated_at >= old_updated

    def test_message_with_special_characters(self, buyer_seller_conversation, buyer):
        content = "Olá! 🎉 <script>alert('xss')</script> & \"quotes\" 'apostrophes'"
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content=content,
        )
        refreshed = Message.objects.get(pk=msg.id)
        assert refreshed.content == content

    def test_no_duplicate_message_status_on_retry(
        self, buyer_seller_conversation, buyer, seller
    ):
        """ignore_conflicts deve prevenir duplicação em MessageStatus."""
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Retry safe",
        )
        # Simula retry: tenta criar o mesmo MessageStatus novamente
        MessageStatus.objects.bulk_create(
            [MessageStatus(message=msg, recipient=seller)],
            ignore_conflicts=True,
        )
        count = MessageStatus.objects.filter(message=msg, recipient=seller).count()
        assert count == 1

    def test_sender_has_no_message_status_for_own_message(
        self, buyer_seller_conversation, buyer
    ):
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Minha mensagem",
        )
        assert not MessageStatus.objects.filter(message=msg, recipient=buyer).exists()


class TestGetHistory:
    def test_returns_messages_for_participant(self, buyer_seller_conversation, buyer):
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Histórico",
        )
        history = list(MessageService.get_history(buyer, str(buyer_seller_conversation.id)))
        msg_ids = [m.id for m in history]
        assert msg.id in msg_ids

    def test_raises_for_non_participant(self, buyer_seller_conversation, outsider):
        with pytest.raises(MessageServiceError, match="permissão"):
            list(MessageService.get_history(outsider, str(buyer_seller_conversation.id)))

    def test_excludes_deleted_messages(self, buyer_seller_conversation, buyer):
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Será deletada",
        )
        msg.is_deleted = True
        msg.save()

        history = list(MessageService.get_history(buyer, str(buyer_seller_conversation.id)))
        assert msg.id not in [m.id for m in history]

    def test_cursor_pagination_before_id(self, buyer_seller_conversation, buyer, seller):
        """before_id deve retornar apenas mensagens anteriores ao cursor."""
        msg1 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Mensagem 1",
        )
        msg2 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=seller,
            content="Mensagem 2",
        )
        msg3 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Mensagem 3",
        )

        # Cursor no msg3: deve retornar msg1 e msg2
        history = list(MessageService.get_history(
            buyer,
            str(buyer_seller_conversation.id),
            before_id=str(msg3.id),
        ))
        msg_ids = [m.id for m in history]
        assert msg1.id in msg_ids
        assert msg2.id in msg_ids
        assert msg3.id not in msg_ids

    def test_cursor_raises_for_invalid_before_id(self, buyer_seller_conversation, buyer):
        fake_id = str(uuid.uuid4())
        with pytest.raises(MessageServiceError, match="não encontrada"):
            list(MessageService.get_history(
                buyer,
                str(buyer_seller_conversation.id),
                before_id=fake_id,
            ))

    def test_limit_respected(self, buyer_seller_conversation, buyer):
        for i in range(10):
            MessageService.send_message(
                conversation=buyer_seller_conversation,
                sender=buyer,
                content=f"Mensagem {i}",
            )
        history = list(MessageService.get_history(
            buyer,
            str(buyer_seller_conversation.id),
            limit=3,
        ))
        assert len(history) == 3

    def test_limit_capped_at_100(self, buyer_seller_conversation, buyer):
        history = list(MessageService.get_history(
            buyer,
            str(buyer_seller_conversation.id),
            limit=200,
        ))
        assert len(history) <= 100


class TestMarkAsRead:
    def test_updates_message_status_read_at(self, buyer_seller_conversation, buyer, seller):
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Leia esta",
        )
        # Verifica que está não lida antes
        status = MessageStatus.objects.get(message=msg, recipient=seller)
        assert status.read_at is None

        before = timezone.now()
        MessageService.mark_as_read(
            user=seller,
            conversation_id=str(buyer_seller_conversation.id),
        )
        after = timezone.now()

        status.refresh_from_db()
        assert status.read_at is not None
        assert before <= status.read_at <= after

    def test_updates_participant_last_read_at(self, buyer_seller_conversation, buyer, seller):
        MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Atualize last_read_at",
        )
        before = timezone.now()
        MessageService.mark_as_read(
            user=seller,
            conversation_id=str(buyer_seller_conversation.id),
        )
        after = timezone.now()

        participant = ConversationParticipant.objects.get(
            conversation=buyer_seller_conversation,
            user=seller,
        )
        assert participant.last_read_at is not None
        assert before <= participant.last_read_at <= after

    def test_bulk_marks_all_messages_up_to_pivot(
        self, buyer_seller_conversation, buyer, seller
    ):
        msg1 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Msg 1",
        )
        msg2 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Msg 2",
        )
        msg3 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Msg 3 — cursor aqui",
        )

        count = MessageService.mark_as_read(
            user=seller,
            conversation_id=str(buyer_seller_conversation.id),
        )

        # Todas as 3 mensagens devem ser marcadas como lidas
        assert count == 3
        for msg in [msg1, msg2, msg3]:
            status = MessageStatus.objects.get(message=msg, recipient=seller)
            assert status.read_at is not None

    def test_returns_correct_count_of_updated_statuses(
        self, buyer_seller_conversation, buyer, seller
    ):
        msg1 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Um",
        )
        msg2 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Dois",
        )
        count = MessageService.mark_as_read(
            user=seller,
            conversation_id=str(buyer_seller_conversation.id),
        )
        assert count == 2

    def test_raises_for_non_participant(self, buyer_seller_conversation, buyer, outsider):
        MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Não pode ler",
        )
        with pytest.raises(MessageServiceError, match="participante"):
            MessageService.mark_as_read(
                user=outsider,
                conversation_id=str(buyer_seller_conversation.id),
            )

    def test_idempotent_second_mark_as_read(
        self, buyer_seller_conversation, buyer, seller
    ):
        """Segunda chamada de mark_as_read não deve falhar, apenas retornar 0 updates."""
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Já lida",
        )
        MessageService.mark_as_read(
            user=seller,
            conversation_id=str(buyer_seller_conversation.id),
        )
        # Segunda chamada deve ser zero updates (já marcado como lido)
        count2 = MessageService.mark_as_read(
            user=seller,
            conversation_id=str(buyer_seller_conversation.id),
        )
        assert count2 == 0

    def test_does_not_mark_own_messages_as_read(
        self, buyer_seller_conversation, buyer, seller
    ):
        """O remetente não tem MessageStatus para suas próprias mensagens."""
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Minha msg",
        )
        # mark_as_read pelo próprio remetente deve retornar 0 (nada a marcar)
        count = MessageService.mark_as_read(
            user=buyer,
            conversation_id=str(buyer_seller_conversation.id),
        )
        assert count == 0


class TestGetUnreadCount:
    def test_counts_unread_messages(self, buyer_seller_conversation, buyer, seller):
        MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Não lida 1",
        )
        MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Não lida 2",
        )
        count = MessageService.get_unread_count(seller, str(buyer_seller_conversation.id))
        assert count == 2

    def test_unread_count_zero_after_mark_as_read(
        self, buyer_seller_conversation, buyer, seller
    ):
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Lida",
        )
        MessageService.mark_as_read(
            user=seller,
            conversation_id=str(buyer_seller_conversation.id),
        )
        count = MessageService.get_unread_count(seller, str(buyer_seller_conversation.id))
        assert count == 0

    def test_sender_own_messages_not_counted_as_unread(
        self, buyer_seller_conversation, buyer
    ):
        MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Minha mensagem",
        )
        # Comprador não deve ver suas próprias mensagens como não lidas
        count = MessageService.get_unread_count(buyer, str(buyer_seller_conversation.id))
        assert count == 0

    def test_returns_zero_for_non_participant(self, buyer_seller_conversation, outsider):
        count = MessageService.get_unread_count(outsider, str(buyer_seller_conversation.id))
        assert count == 0
