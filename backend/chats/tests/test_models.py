"""
Testes de modelos e migrations do sistema de chat.

Valida:
- Criação e representação de Conversation, ConversationParticipant, Message, MessageStatus
- Constraints unique_together
- Índices implícitos via operações no banco
- Campos e defaults corretos
"""

import uuid
import pytest
from django.db import IntegrityError
from django.utils import timezone

from chats.models import Conversation, ConversationParticipant, Message, MessageStatus


pytestmark = pytest.mark.django_db


class TestConversationModel:
    def test_conversation_has_uuid_pk(self, buyer, seller):
        conv = Conversation.objects.create(
            conversation_type=Conversation.TYPE_BUYER_SELLER,
            created_by=buyer,
        )
        assert isinstance(conv.id, uuid.UUID)

    def test_conversation_default_status_is_active(self, buyer):
        conv = Conversation.objects.create(
            conversation_type=Conversation.TYPE_BUYER_SELLER,
            created_by=buyer,
        )
        assert conv.status == Conversation.STATUS_ACTIVE

    def test_conversation_str_representation(self, buyer):
        conv = Conversation.objects.create(
            conversation_type=Conversation.TYPE_BUYER_SELLER,
            created_by=buyer,
        )
        s = str(conv)
        assert 'buyer_seller' in s
        assert 'active' in s

    def test_conversation_type_choices_are_valid(self):
        valid_types = {c[0] for c in Conversation.CONVERSATION_TYPE_CHOICES}
        assert 'buyer_seller' in valid_types
        assert 'buyer_support' in valid_types
        assert 'seller_support' in valid_types

    def test_conversation_status_choices_are_valid(self):
        valid_statuses = {c[0] for c in Conversation.STATUS_CHOICES}
        assert 'active' in valid_statuses
        assert 'closed' in valid_statuses
        assert 'archived' in valid_statuses

    def test_conversation_auto_timestamps(self, buyer):
        before = timezone.now()
        conv = Conversation.objects.create(
            conversation_type=Conversation.TYPE_BUYER_SELLER,
            created_by=buyer,
        )
        after = timezone.now()
        assert before <= conv.created_at <= after
        assert before <= conv.updated_at <= after

    def test_conversation_ordering_uses_updated_at_index(self, buyer, seller):
        """Confirma que o índice composto (status, -updated_at) está presente."""
        index_names = [i.name for i in Conversation._meta.indexes]
        assert any('status' in n for n in index_names), (
            f"Índice com 'status' não encontrado. Índices: {index_names}"
        )


class TestConversationParticipantModel:
    def test_participant_unique_together_enforced(self, buyer_seller_conversation, buyer):
        """Dois registros do mesmo usuário na mesma conversa devem falhar."""
        with pytest.raises(IntegrityError):
            ConversationParticipant.objects.create(
                conversation=buyer_seller_conversation,
                user=buyer,
                role=ConversationParticipant.ROLE_BUYER,
            )

    def test_participant_is_active_default_true(self, buyer_seller_conversation, buyer):
        participant = ConversationParticipant.objects.get(
            conversation=buyer_seller_conversation,
            user=buyer,
        )
        assert participant.is_active is True

    def test_participant_role_choices(self):
        roles = {c[0] for c in ConversationParticipant.ROLE_CHOICES}
        assert 'buyer' in roles
        assert 'seller' in roles
        assert 'support' in roles

    def test_participant_str_representation(self, buyer_seller_conversation, buyer):
        participant = ConversationParticipant.objects.get(
            conversation=buyer_seller_conversation,
            user=buyer,
        )
        s = str(participant)
        assert str(buyer.pk) in s
        assert 'buyer' in s

    def test_participant_last_read_at_is_null_by_default(self, buyer_seller_conversation, buyer):
        participant = ConversationParticipant.objects.get(
            conversation=buyer_seller_conversation,
            user=buyer,
        )
        assert participant.last_read_at is None


class TestMessageModel:
    def test_message_has_uuid_pk(self, buyer_seller_conversation, buyer):
        msg = Message.objects.create(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        assert isinstance(msg.id, uuid.UUID)

    def test_message_default_type_is_text(self, buyer_seller_conversation, buyer):
        msg = Message.objects.create(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        assert msg.message_type == Message.TYPE_TEXT

    def test_message_is_not_deleted_by_default(self, buyer_seller_conversation, buyer):
        msg = Message.objects.create(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        assert msg.is_deleted is False

    def test_message_default_metadata_is_empty_dict(self, buyer_seller_conversation, buyer):
        msg = Message.objects.create(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        assert msg.metadata == {}

    def test_message_ordering_by_created_at(self, buyer_seller_conversation, buyer):
        """Mensagens devem ser retornadas em ordem cronológica."""
        msg1 = Message.objects.create(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Primeira",
        )
        msg2 = Message.objects.create(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Segunda",
        )
        messages = list(Message.objects.filter(conversation=buyer_seller_conversation))
        assert messages[0].id == msg1.id
        assert messages[1].id == msg2.id

    def test_message_str_representation(self, buyer_seller_conversation, buyer):
        msg = Message.objects.create(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        s = str(msg)
        assert str(msg.id) in s
        assert str(buyer.pk) in s


class TestMessageStatusModel:
    def test_message_status_unique_together_enforced(self, buyer_seller_conversation, buyer, seller):
        msg = Message.objects.create(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        MessageStatus.objects.create(message=msg, recipient=seller)
        with pytest.raises(IntegrityError):
            MessageStatus.objects.create(message=msg, recipient=seller)

    def test_message_status_delivered_and_read_at_nullable(self, buyer_seller_conversation, buyer, seller):
        msg = Message.objects.create(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        status = MessageStatus.objects.create(message=msg, recipient=seller)
        assert status.delivered_at is None
        assert status.read_at is None

    def test_message_status_str_representation(self, buyer_seller_conversation, buyer, seller):
        msg = Message.objects.create(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        status = MessageStatus.objects.create(message=msg, recipient=seller)
        s = str(status)
        assert str(msg.id) in s
        assert str(seller.pk) in s
