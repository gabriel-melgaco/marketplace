"""
Testes do ConversationService.

Valida:
- Criação de conversas (todos os tipos)
- Deduplicação de buyer_seller com mesmo listing/par
- is_participant com cache Redis (via LocMemCache no teste)
- list_conversations filtra por participação e status
- get_conversation garante autorização
- close_conversation garante regras de permissão
- invalidate_participant_cache limpa cache corretamente
"""

import uuid
import pytest
from django.test import override_settings

from chats.models import Conversation, ConversationParticipant
from chats.services import ConversationService
from chats.services.conversation_service import ConversationServiceError

CACHES_TEST = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "conv-service-tests",
    }
}

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def use_local_cache():
    with override_settings(CACHES=CACHES_TEST):
        yield


class TestCreateConversation:
    def test_creates_buyer_seller_conversation(self, buyer, seller):
        conv = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
        )
        assert conv.conversation_type == 'buyer_seller'
        assert conv.status == Conversation.STATUS_ACTIVE
        assert conv.created_by == buyer

    def test_participants_created_with_correct_roles(self, buyer, seller):
        conv = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
        )
        participants = {
            p.user_id: p.role
            for p in conv.participants.all()
        }
        assert participants[buyer.pk] == ConversationParticipant.ROLE_BUYER
        assert participants[seller.pk] == ConversationParticipant.ROLE_SELLER

    def test_creates_buyer_support_conversation(self, buyer, support_staff):
        conv = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_support',
            recipient_id=support_staff.pk,
        )
        assert conv.conversation_type == 'buyer_support'
        participants = {p.user_id: p.role for p in conv.participants.all()}
        assert participants[buyer.pk] == ConversationParticipant.ROLE_BUYER
        assert participants[support_staff.pk] == ConversationParticipant.ROLE_SUPPORT

    def test_creates_seller_support_conversation(self, seller, support_staff):
        conv = ConversationService.create_conversation(
            initiator=seller,
            conversation_type='seller_support',
            recipient_id=support_staff.pk,
        )
        assert conv.conversation_type == 'seller_support'
        participants = {p.user_id: p.role for p in conv.participants.all()}
        assert participants[seller.pk] == ConversationParticipant.ROLE_SELLER
        assert participants[support_staff.pk] == ConversationParticipant.ROLE_SUPPORT

    def test_raises_on_invalid_conversation_type(self, buyer, seller):
        with pytest.raises(ConversationServiceError, match="inválido"):
            ConversationService.create_conversation(
                initiator=buyer,
                conversation_type='invalid_type',
                recipient_id=seller.pk,
            )

    def test_raises_when_recipient_not_found(self, buyer):
        with pytest.raises(ConversationServiceError, match="não encontrado"):
            ConversationService.create_conversation(
                initiator=buyer,
                conversation_type='buyer_seller',
                recipient_id=999999,
            )

    def test_raises_when_user_tries_to_talk_to_self(self, buyer):
        with pytest.raises(ConversationServiceError, match="consigo mesmo"):
            ConversationService.create_conversation(
                initiator=buyer,
                conversation_type='buyer_seller',
                recipient_id=buyer.pk,
            )

    def test_deduplication_reuses_active_buyer_seller_for_same_listing(
        self, buyer, seller, listing
    ):
        """Segundo create_conversation com mesmo listing/par retorna o existente."""
        conv1 = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
            listing_id=listing.pk,
        )
        conv2 = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
            listing_id=listing.pk,
        )
        assert conv1.id == conv2.id
        # Confirma que apenas uma conversa foi criada
        total_convs = Conversation.objects.filter(
            conversation_type='buyer_seller',
            listing_id=listing.pk,
        ).count()
        assert total_convs == 1

    def test_no_deduplication_without_listing_id(self, buyer, seller):
        """Sem listing_id, cada create gera nova conversa."""
        conv1 = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
        )
        conv2 = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
        )
        assert conv1.id != conv2.id

    def test_no_deduplication_for_closed_conversation(self, buyer, seller, listing):
        """Conversa fechada não é reutilizada — nova conversa é criada."""
        conv1 = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
            listing_id=listing.pk,
        )
        conv1.status = Conversation.STATUS_CLOSED
        conv1.save()

        conv2 = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
            listing_id=listing.pk,
        )
        assert conv1.id != conv2.id

    def test_support_conversations_never_deduplicated(self, buyer, support_staff):
        """Conversas de suporte são sempre criadas frescas."""
        conv1 = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_support',
            recipient_id=support_staff.pk,
        )
        conv2 = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_support',
            recipient_id=support_staff.pk,
        )
        assert conv1.id != conv2.id


class TestIsParticipant:
    def test_returns_true_for_active_participant(self, buyer_seller_conversation, buyer):
        result = ConversationService.is_participant(buyer, str(buyer_seller_conversation.id))
        assert result is True

    def test_returns_true_for_recipient(self, buyer_seller_conversation, seller):
        result = ConversationService.is_participant(seller, str(buyer_seller_conversation.id))
        assert result is True

    def test_returns_false_for_non_participant(self, buyer_seller_conversation, outsider):
        result = ConversationService.is_participant(outsider, str(buyer_seller_conversation.id))
        assert result is False

    def test_caches_result_in_redis(self, buyer_seller_conversation, buyer):
        from django.core.cache import cache
        conv_id = str(buyer_seller_conversation.id)
        cache_key = f"chat:participants:{conv_id}:{buyer.pk}"

        # Limpa cache antes do teste
        cache.delete(cache_key)
        assert cache.get(cache_key) is None

        # Primeira chamada deve popular o cache
        ConversationService.is_participant(buyer, conv_id)
        cached_val = cache.get(cache_key)
        assert cached_val is True

    def test_cached_false_value_respected(self, buyer_seller_conversation, outsider):
        from django.core.cache import cache
        conv_id = str(buyer_seller_conversation.id)
        cache_key = f"chat:participants:{conv_id}:{outsider.pk}"
        cache.delete(cache_key)

        # Primeira chamada → False, deve ser cacheado
        result = ConversationService.is_participant(outsider, conv_id)
        assert result is False
        cached_val = cache.get(cache_key)
        assert cached_val is False

    def test_inactive_participant_returns_false(self, buyer_seller_conversation, buyer):
        # Desativa a participação
        ConversationParticipant.objects.filter(
            conversation=buyer_seller_conversation,
            user=buyer,
        ).update(is_active=False)

        # Invalida cache para forçar nova consulta ao banco
        ConversationService.invalidate_participant_cache(
            str(buyer_seller_conversation.id), buyer.pk
        )

        result = ConversationService.is_participant(buyer, str(buyer_seller_conversation.id))
        assert result is False

    def test_invalidate_cache_forces_db_recheck(self, buyer_seller_conversation, buyer):
        from django.core.cache import cache
        conv_id = str(buyer_seller_conversation.id)
        cache_key = f"chat:participants:{conv_id}:{buyer.pk}"

        # Popula cache
        ConversationService.is_participant(buyer, conv_id)
        assert cache.get(cache_key) is True

        # Invalida cache
        ConversationService.invalidate_participant_cache(conv_id, buyer.pk)
        assert cache.get(cache_key) is None


class TestListConversations:
    def test_returns_only_user_conversations(self, buyer, seller, outsider):
        conv = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
        )
        # outsider não deve ver a conversa
        buyer_convs = list(ConversationService.list_conversations(buyer))
        outsider_convs = list(ConversationService.list_conversations(outsider))

        assert conv in buyer_convs
        assert conv not in outsider_convs

    def test_filters_by_status(self, buyer, seller):
        active_conv = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
        )
        # Fecha a conversa
        active_conv.status = Conversation.STATUS_CLOSED
        active_conv.save()

        active_list = list(ConversationService.list_conversations(buyer, status='active'))
        closed_list = list(ConversationService.list_conversations(buyer, status='closed'))

        assert active_conv not in active_list
        assert active_conv in closed_list

    def test_excludes_inactive_participant_conversations(self, buyer, seller):
        conv = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
        )
        ConversationParticipant.objects.filter(
            conversation=conv, user=buyer
        ).update(is_active=False)

        buyer_convs = list(ConversationService.list_conversations(buyer))
        assert conv not in buyer_convs

    def test_ordered_by_updated_at_desc(self, buyer, seller, support_staff):
        from django.utils import timezone
        import time

        conv1 = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
        )
        # Pequena pausa para garantir diferença de timestamp
        time.sleep(0.01)
        conv2 = ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_support',
            recipient_id=support_staff.pk,
        )

        convs = list(ConversationService.list_conversations(buyer))
        ids = [c.id for c in convs]
        assert ids.index(conv2.id) < ids.index(conv1.id)


class TestGetConversation:
    def test_returns_conversation_for_participant(self, buyer_seller_conversation, buyer):
        conv = ConversationService.get_conversation(
            str(buyer_seller_conversation.id), buyer
        )
        assert conv.id == buyer_seller_conversation.id

    def test_raises_for_non_participant(self, buyer_seller_conversation, outsider):
        with pytest.raises(ConversationServiceError, match="permissão"):
            ConversationService.get_conversation(
                str(buyer_seller_conversation.id), outsider
            )

    def test_raises_for_nonexistent_conversation(self, buyer):
        fake_id = str(uuid.uuid4())
        with pytest.raises(ConversationServiceError, match="não encontrada"):
            ConversationService.get_conversation(fake_id, buyer)


class TestCloseConversation:
    def test_participant_can_close_conversation(self, buyer_seller_conversation, buyer):
        closed = ConversationService.close_conversation(
            str(buyer_seller_conversation.id), buyer
        )
        assert closed.status == Conversation.STATUS_CLOSED

    def test_staff_can_close_any_conversation(self, buyer_seller_conversation, support_staff):
        closed = ConversationService.close_conversation(
            str(buyer_seller_conversation.id), support_staff
        )
        assert closed.status == Conversation.STATUS_CLOSED

    def test_non_participant_cannot_close(self, buyer_seller_conversation, outsider):
        with pytest.raises(ConversationServiceError, match="permissão"):
            ConversationService.close_conversation(
                str(buyer_seller_conversation.id), outsider
            )

    def test_raises_when_already_closed(self, buyer_seller_conversation, buyer):
        ConversationService.close_conversation(
            str(buyer_seller_conversation.id), buyer
        )
        with pytest.raises(ConversationServiceError, match="já está fechada"):
            ConversationService.close_conversation(
                str(buyer_seller_conversation.id), buyer
            )

    def test_raises_for_nonexistent_conversation(self, buyer):
        fake_id = str(uuid.uuid4())
        with pytest.raises(ConversationServiceError, match="não encontrada"):
            ConversationService.close_conversation(fake_id, buyer)
