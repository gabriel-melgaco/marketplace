"""
Testes dos endpoints REST do sistema de chat.

Valida:
- GET /api/chats/conversations/  — lista apenas conversas do usuário
- POST /api/chats/conversations/ — cria conversa com participantes corretos
- GET /api/chats/conversations/<id>/ — detalhe com verificação de participação
- PATCH /api/chats/conversations/<id>/close/ — fecha conversa
- GET /api/chats/conversations/<id>/messages/ — histórico paginado
- POST /api/chats/conversations/<id>/messages/read/ — marca como lido
- Autenticação: 401 para requisições sem token
- Autorização: 403/404 para não-participantes
"""

import uuid
import json
import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from chats.models import Conversation, MessageStatus
from chats.services import ConversationService, MessageService

CACHES_TEST = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "rest-views-tests",
    }
}

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def use_local_cache():
    with override_settings(CACHES=CACHES_TEST):
        from django.core.cache import cache
        cache.clear()
        yield
        cache.clear()


@pytest.fixture
def buyer_client(buyer):
    client = APIClient()
    client.force_authenticate(user=buyer)
    return client


@pytest.fixture
def seller_client(seller):
    client = APIClient()
    client.force_authenticate(user=seller)
    return client


@pytest.fixture
def support_client(support_staff):
    client = APIClient()
    client.force_authenticate(user=support_staff)
    return client


@pytest.fixture
def outsider_client(outsider):
    client = APIClient()
    client.force_authenticate(user=outsider)
    return client


@pytest.fixture
def anon_client():
    return APIClient()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def conversations_url():
    return '/api/chats/conversations/'


def conversation_detail_url(pk):
    return f'/api/chats/conversations/{pk}/'


def conversation_close_url(pk):
    return f'/api/chats/conversations/{pk}/close/'


def messages_url(pk):
    return f'/api/chats/conversations/{pk}/messages/'


def mark_read_url(pk):
    return f'/api/chats/conversations/{pk}/messages/read/'


# ---------------------------------------------------------------------------
# GET /api/chats/conversations/
# ---------------------------------------------------------------------------

class TestConversationListView:
    def test_unauthenticated_request_returns_401(self, anon_client):
        response = anon_client.get(conversations_url())
        assert response.status_code == 401

    def test_returns_only_user_conversations(
        self, buyer_client, buyer_seller_conversation, buyer
    ):
        response = buyer_client.get(conversations_url())
        assert response.status_code == 200
        ids = [c['id'] for c in response.data]
        assert str(buyer_seller_conversation.id) in ids

    def test_outsider_cannot_see_conversation(
        self, outsider_client, buyer_seller_conversation
    ):
        response = outsider_client.get(conversations_url())
        assert response.status_code == 200
        ids = [c['id'] for c in response.data]
        assert str(buyer_seller_conversation.id) not in ids

    def test_filter_by_status_active(self, buyer_client, buyer_seller_conversation):
        # Fecha a conversa
        buyer_seller_conversation.status = Conversation.STATUS_CLOSED
        buyer_seller_conversation.save()

        response = buyer_client.get(conversations_url(), {'status': 'active'})
        assert response.status_code == 200
        ids = [c['id'] for c in response.data]
        assert str(buyer_seller_conversation.id) not in ids

    def test_filter_by_status_closed(self, buyer_client, buyer_seller_conversation):
        buyer_seller_conversation.status = Conversation.STATUS_CLOSED
        buyer_seller_conversation.save()

        response = buyer_client.get(conversations_url(), {'status': 'closed'})
        assert response.status_code == 200
        ids = [c['id'] for c in response.data]
        assert str(buyer_seller_conversation.id) in ids

    def test_response_contains_participants(
        self, buyer_client, buyer_seller_conversation
    ):
        response = buyer_client.get(conversations_url())
        assert response.status_code == 200
        conv_data = next(
            c for c in response.data
            if c['id'] == str(buyer_seller_conversation.id)
        )
        assert 'participants' in conv_data
        assert len(conv_data['participants']) == 2

    def test_response_contains_unread_count(
        self, buyer_client, buyer_seller_conversation
    ):
        response = buyer_client.get(conversations_url())
        assert response.status_code == 200
        conv_data = next(
            c for c in response.data
            if c['id'] == str(buyer_seller_conversation.id)
        )
        assert 'unread_count' in conv_data
        assert isinstance(conv_data['unread_count'], int)


# ---------------------------------------------------------------------------
# POST /api/chats/conversations/
# ---------------------------------------------------------------------------

class TestConversationCreateView:
    def test_unauthenticated_request_returns_401(self, anon_client, seller):
        response = anon_client.post(conversations_url(), {
            'conversation_type': 'buyer_seller',
            'recipient_id': seller.pk,
        }, format='json')
        assert response.status_code == 401

    def test_creates_buyer_seller_conversation(self, buyer_client, seller):
        response = buyer_client.post(conversations_url(), {
            'conversation_type': 'buyer_seller',
            'recipient_id': seller.pk,
        }, format='json')
        assert response.status_code == 201
        assert response.data['conversation_type'] == 'buyer_seller'

    def test_creates_buyer_support_conversation(self, buyer_client, support_staff):
        response = buyer_client.post(conversations_url(), {
            'conversation_type': 'buyer_support',
            'recipient_id': support_staff.pk,
        }, format='json')
        assert response.status_code == 201
        assert response.data['conversation_type'] == 'buyer_support'

    def test_returns_400_for_invalid_type(self, buyer_client, seller):
        response = buyer_client.post(conversations_url(), {
            'conversation_type': 'invalid',
            'recipient_id': seller.pk,
        }, format='json')
        assert response.status_code == 400

    def test_returns_400_for_missing_recipient(self, buyer_client):
        response = buyer_client.post(conversations_url(), {
            'conversation_type': 'buyer_seller',
        }, format='json')
        assert response.status_code == 400

    def test_returns_400_for_nonexistent_recipient(self, buyer_client):
        response = buyer_client.post(conversations_url(), {
            'conversation_type': 'buyer_seller',
            'recipient_id': 999999,
        }, format='json')
        assert response.status_code == 400

    def test_returns_400_when_talking_to_self(self, buyer_client, buyer):
        response = buyer_client.post(conversations_url(), {
            'conversation_type': 'buyer_seller',
            'recipient_id': buyer.pk,
        }, format='json')
        assert response.status_code == 400

    def test_response_has_correct_structure(self, buyer_client, seller):
        response = buyer_client.post(conversations_url(), {
            'conversation_type': 'buyer_seller',
            'recipient_id': seller.pk,
        }, format='json')
        assert response.status_code == 201
        data = response.data
        assert 'id' in data
        assert 'conversation_type' in data
        assert 'status' in data
        assert 'participants' in data
        assert 'created_at' in data

    def test_deduplication_returns_existing_for_same_listing(
        self, buyer_client, seller, listing
    ):
        payload = {
            'conversation_type': 'buyer_seller',
            'recipient_id': seller.pk,
            'listing_id': listing.pk,
        }
        r1 = buyer_client.post(conversations_url(), payload, format='json')
        r2 = buyer_client.post(conversations_url(), payload, format='json')
        assert r1.status_code == 201
        assert r2.status_code == 200
        assert r1.data['id'] == r2.data['id']


# ---------------------------------------------------------------------------
# GET /api/chats/conversations/<id>/
# ---------------------------------------------------------------------------

class TestConversationDetailView:
    def test_participant_can_access_detail(
        self, buyer_client, buyer_seller_conversation
    ):
        url = conversation_detail_url(buyer_seller_conversation.id)
        response = buyer_client.get(url)
        assert response.status_code == 200
        assert str(response.data['id']) == str(buyer_seller_conversation.id)

    def test_non_participant_gets_404(
        self, outsider_client, buyer_seller_conversation
    ):
        url = conversation_detail_url(buyer_seller_conversation.id)
        response = outsider_client.get(url)
        assert response.status_code == 404

    def test_unauthenticated_gets_401(self, anon_client, buyer_seller_conversation):
        url = conversation_detail_url(buyer_seller_conversation.id)
        response = anon_client.get(url)
        assert response.status_code == 401

    def test_nonexistent_conversation_returns_404(self, buyer_client):
        url = conversation_detail_url(uuid.uuid4())
        response = buyer_client.get(url)
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/chats/conversations/<id>/close/
# ---------------------------------------------------------------------------

class TestConversationCloseView:
    def test_participant_can_close(self, buyer_client, buyer_seller_conversation):
        url = conversation_close_url(buyer_seller_conversation.id)
        response = buyer_client.patch(url)
        assert response.status_code == 200
        assert response.data['status'] == 'closed'

    def test_staff_can_close_any_conversation(
        self, support_client, buyer_seller_conversation
    ):
        url = conversation_close_url(buyer_seller_conversation.id)
        response = support_client.patch(url)
        assert response.status_code == 200
        assert response.data['status'] == 'closed'

    def test_non_participant_cannot_close(
        self, outsider_client, buyer_seller_conversation
    ):
        url = conversation_close_url(buyer_seller_conversation.id)
        response = outsider_client.patch(url)
        assert response.status_code == 400

    def test_already_closed_returns_400(self, buyer_client, buyer_seller_conversation):
        url = conversation_close_url(buyer_seller_conversation.id)
        buyer_client.patch(url)  # primeiro close
        response = buyer_client.patch(url)  # segundo close
        assert response.status_code == 400

    def test_unauthenticated_gets_401(self, anon_client, buyer_seller_conversation):
        url = conversation_close_url(buyer_seller_conversation.id)
        response = anon_client.patch(url)
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/chats/conversations/<id>/messages/
# ---------------------------------------------------------------------------

class TestMessageListView:
    def test_unauthenticated_returns_401(self, anon_client, buyer_seller_conversation):
        url = messages_url(buyer_seller_conversation.id)
        response = anon_client.get(url)
        assert response.status_code == 401

    def test_participant_retrieves_messages(
        self, buyer_client, buyer_seller_conversation, buyer
    ):
        MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Olá",
        )
        url = messages_url(buyer_seller_conversation.id)
        response = buyer_client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_non_participant_gets_403(
        self, outsider_client, buyer_seller_conversation
    ):
        url = messages_url(buyer_seller_conversation.id)
        response = outsider_client.get(url)
        assert response.status_code == 403

    def test_cursor_pagination_with_before_param(
        self, buyer_client, buyer_seller_conversation, buyer, seller
    ):
        msg1 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Primeira",
        )
        msg2 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=seller,
            content="Segunda",
        )
        msg3 = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Terceira",
        )

        url = messages_url(buyer_seller_conversation.id)
        response = buyer_client.get(url, {'before': str(msg3.id)})
        assert response.status_code == 200
        ids = [m['id'] for m in response.data]
        assert str(msg3.id) not in ids

    def test_limit_param_respected(
        self, buyer_client, buyer_seller_conversation, buyer
    ):
        for i in range(5):
            MessageService.send_message(
                conversation=buyer_seller_conversation,
                sender=buyer,
                content=f"Msg {i}",
            )
        url = messages_url(buyer_seller_conversation.id)
        response = buyer_client.get(url, {'limit': 2})
        assert response.status_code == 200
        assert len(response.data) == 2

    def test_message_response_fields(
        self, buyer_client, buyer_seller_conversation, buyer
    ):
        MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Campos ok",
        )
        url = messages_url(buyer_seller_conversation.id)
        response = buyer_client.get(url)
        assert response.status_code == 200
        msg = response.data[0]
        expected_fields = ['id', 'content', 'sender_id', 'sender_name',
                           'message_type', 'created_at', 'is_deleted', 'metadata']
        for field in expected_fields:
            assert field in msg, f"Campo '{field}' ausente na resposta de mensagem"

    def test_invalid_limit_defaults_to_50(
        self, buyer_client, buyer_seller_conversation
    ):
        url = messages_url(buyer_seller_conversation.id)
        response = buyer_client.get(url, {'limit': 'abc'})
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/chats/conversations/<id>/messages/read/
# ---------------------------------------------------------------------------

class TestMarkAsReadView:
    def test_unauthenticated_returns_401(self, anon_client, buyer_seller_conversation):
        url = mark_read_url(buyer_seller_conversation.id)
        response = anon_client.post(url, {}, format='json')
        assert response.status_code == 401

    def test_marks_messages_as_read(
        self, seller_client, buyer_seller_conversation, buyer, seller
    ):
        MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Leia",
        )
        url = mark_read_url(buyer_seller_conversation.id)
        response = seller_client.post(url, format='json')
        assert response.status_code == 200
        assert 'updated' in response.data
        assert response.data['updated'] == 1

    def test_non_participant_gets_403(
        self, outsider_client, buyer_seller_conversation, buyer
    ):
        MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Não pode ler",
        )
        url = mark_read_url(buyer_seller_conversation.id)
        response = outsider_client.post(url, format='json')
        assert response.status_code == 403

    def test_read_status_persisted_in_database(
        self, seller_client, buyer_seller_conversation, buyer, seller
    ):
        msg = MessageService.send_message(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Leia e verifique no banco",
        )
        url = mark_read_url(buyer_seller_conversation.id)
        seller_client.post(url, format='json')

        status = MessageStatus.objects.get(message=msg, recipient=seller)
        assert status.read_at is not None
