"""
Testes do ChatConsumer WebSocket.

Usa channels.testing.WebsocketCommunicator com InMemoryChannelLayer.
Todos os testes de consumer rodam com override de CHANNEL_LAYERS e CACHES.

Valida:
- Conexão autenticada aceita (código 101 / connect aceita)
- Conexão sem token/token inválido fecha com 4001
- Não-participante fecha com 4003
- Conversa inexistente fecha com 4004
- Envio de mensagem é entregue para ambos os participantes
- Mensagem persiste no banco de dados
- mark as read via WebSocket atualiza banco
- Mensagem vazia retorna erro sem persistir
- JSON malformado retorna erro
- Typing indicator é enviado e recebido por outros
- Typing indicator não é recebido pelo próprio usuário
- disconnect limpa grupos Redis
"""

import json
import uuid
import pytest
from unittest.mock import patch
from django.test import override_settings
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer

from chats.consumers.chat_consumer import ChatConsumer
from chats.models import Conversation, Message, MessageStatus, ConversationParticipant
from chats.services.presence_service import PresenceService

CHANNEL_LAYERS_TEST = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

CACHES_TEST = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "consumer-tests",
    }
}


def make_communicator(conversation_id, user=None, token=None):
    """
    Cria um WebsocketCommunicator para o ChatConsumer.
    Injeta `user` diretamente no scope (bypass do JWTAuthMiddleware).
    """
    from django.contrib.auth.models import AnonymousUser
    scope_user = user or AnonymousUser()
    app = ChatConsumer.as_asgi()

    communicator = WebsocketCommunicator(
        app,
        f"/ws/chats/{conversation_id}/",
        headers=[],
    )
    communicator.scope['url_route'] = {
        'kwargs': {'conversation_id': str(conversation_id)}
    }
    communicator.scope['user'] = scope_user
    return communicator


@pytest.fixture(autouse=True)
def override_settings_for_consumer():
    with override_settings(
        CHANNEL_LAYERS=CHANNEL_LAYERS_TEST,
        CACHES=CACHES_TEST,
    ):
        from django.core.cache import cache
        cache.clear()
        yield
        cache.clear()


pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]


class TestWebSocketConnection:
    async def test_authenticated_participant_connects_successfully(
        self, buyer, buyer_seller_conversation
    ):
        communicator = make_communicator(buyer_seller_conversation.id, user=buyer)
        connected, _ = await communicator.connect()
        assert connected is True
        await communicator.disconnect()

    async def test_unauthenticated_user_is_rejected_with_4001(
        self, buyer_seller_conversation
    ):
        from django.contrib.auth.models import AnonymousUser
        communicator = make_communicator(
            buyer_seller_conversation.id, user=AnonymousUser()
        )
        connected, code = await communicator.connect()
        assert connected is False
        assert code == 4001

    async def test_non_participant_is_rejected_with_4003(
        self, outsider, buyer_seller_conversation
    ):
        communicator = make_communicator(buyer_seller_conversation.id, user=outsider)
        connected, code = await communicator.connect()
        assert connected is False
        assert code == 4003

    async def test_nonexistent_conversation_is_rejected_with_4004(self, buyer):
        fake_id = uuid.uuid4()
        communicator = make_communicator(fake_id, user=buyer)
        connected, code = await communicator.connect()
        assert connected is False
        assert code == 4004

    async def test_disconnect_is_graceful(self, buyer, buyer_seller_conversation):
        communicator = make_communicator(buyer_seller_conversation.id, user=buyer)
        await communicator.connect()
        await communicator.disconnect()
        # Sem exceção = desconexão ok


class TestMessageSending:
    async def test_sent_message_is_received_by_sender(
        self, buyer, buyer_seller_conversation
    ):
        comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        await comm.connect()
        await comm.send_json_to({
            'type': 'message.send',
            'content': 'Olá, tudo bem?',
        })
        response = await comm.receive_json_from(timeout=3)
        assert response['type'] == 'new_message'
        assert response['message']['content'] == 'Olá, tudo bem?'
        await comm.disconnect()

    async def test_sent_message_is_received_by_recipient(
        self, buyer, seller, buyer_seller_conversation
    ):
        """Ambos os comunicadores devem receber a mensagem."""
        buyer_comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        seller_comm = make_communicator(buyer_seller_conversation.id, user=seller)

        await buyer_comm.connect()
        await seller_comm.connect()

        await buyer_comm.send_json_to({
            'type': 'message.send',
            'content': 'Broadcast test',
        })

        # Comprador recebe própria mensagem via broadcast
        buyer_response = await buyer_comm.receive_json_from(timeout=3)
        assert buyer_response['type'] == 'new_message'

        # Vendedor recebe a mensagem do comprador
        seller_response = await seller_comm.receive_json_from(timeout=3)
        assert seller_response['type'] == 'new_message'
        assert seller_response['message']['content'] == 'Broadcast test'

        await buyer_comm.disconnect()
        await seller_comm.disconnect()

    async def test_sent_message_is_persisted_in_database(
        self, buyer, buyer_seller_conversation
    ):
        from asgiref.sync import sync_to_async

        comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        await comm.connect()
        await comm.send_json_to({
            'type': 'message.send',
            'content': 'Persista no banco',
        })
        await comm.receive_json_from(timeout=3)
        await comm.disconnect()

        count = await sync_to_async(
            Message.objects.filter(
                conversation=buyer_seller_conversation,
                content='Persista no banco',
            ).count
        )()
        assert count == 1

    async def test_message_payload_contains_expected_fields(
        self, buyer, buyer_seller_conversation
    ):
        comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        await comm.connect()
        await comm.send_json_to({'type': 'message.send', 'content': 'Campos ok'})
        response = await comm.receive_json_from(timeout=3)
        msg = response['message']
        for field in ['id', 'content', 'sender_id', 'sender_name',
                      'created_at', 'message_type', 'conversation_id']:
            assert field in msg, f"Campo '{field}' ausente no payload de mensagem"
        await comm.disconnect()

    async def test_empty_content_returns_error(self, buyer, buyer_seller_conversation):
        comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        await comm.connect()
        await comm.send_json_to({'type': 'message.send', 'content': '   '})
        response = await comm.receive_json_from(timeout=3)
        assert response['type'] == 'error'
        assert response['code'] == 'empty_content'
        await comm.disconnect()

    async def test_empty_content_is_not_persisted(
        self, buyer, buyer_seller_conversation
    ):
        from asgiref.sync import sync_to_async

        comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        await comm.connect()
        await comm.send_json_to({'type': 'message.send', 'content': ''})
        await comm.receive_json_from(timeout=3)
        await comm.disconnect()

        count = await sync_to_async(
            Message.objects.filter(conversation=buyer_seller_conversation).count
        )()
        assert count == 0

    async def test_malformed_json_returns_error(
        self, buyer, buyer_seller_conversation
    ):
        comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        await comm.connect()
        await comm.send_to(text_data='{not valid json}')
        response = await comm.receive_json_from(timeout=3)
        assert response['type'] == 'error'
        assert response['code'] == 'invalid_json'
        await comm.disconnect()

    async def test_unknown_message_type_returns_error(
        self, buyer, buyer_seller_conversation
    ):
        comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        await comm.connect()
        await comm.send_json_to({'type': 'unknown.event', 'data': 'x'})
        response = await comm.receive_json_from(timeout=3)
        assert response['type'] == 'error'
        assert response['code'] == 'unknown_type'
        await comm.disconnect()

    async def test_message_with_special_characters(
        self, buyer, buyer_seller_conversation
    ):
        content = 'Olá! 🎉 <b>negrito</b> & "aspas" \'apostrophe\''
        comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        await comm.connect()
        await comm.send_json_to({'type': 'message.send', 'content': content})
        response = await comm.receive_json_from(timeout=3)
        assert response['message']['content'] == content
        await comm.disconnect()


class TestMarkAsRead:
    async def test_mark_as_read_broadcasts_receipt(
        self, buyer, seller, buyer_seller_conversation
    ):
        from asgiref.sync import sync_to_async

        # Cria mensagem pelo comprador
        msg = await sync_to_async(Message.objects.create)(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Leia",
        )
        await sync_to_async(MessageStatus.objects.create)(
            message=msg,
            recipient=seller,
        )

        buyer_comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        seller_comm = make_communicator(buyer_seller_conversation.id, user=seller)

        await buyer_comm.connect()
        await seller_comm.connect()

        # Vendedor marca como lido
        await seller_comm.send_json_to({
            'type': 'message.read',
            'last_message_id': str(msg.id),
        })

        # Ambos devem receber o read receipt
        seller_receipt = await seller_comm.receive_json_from(timeout=3)
        assert seller_receipt['type'] == 'message_read'
        assert seller_receipt['receipt']['last_message_id'] == str(msg.id)

        await buyer_comm.disconnect()
        await seller_comm.disconnect()

    async def test_mark_as_read_updates_database(
        self, buyer, seller, buyer_seller_conversation
    ):
        from asgiref.sync import sync_to_async

        msg = await sync_to_async(Message.objects.create)(
            conversation=buyer_seller_conversation,
            sender=buyer,
            content="Atualizar banco",
        )
        await sync_to_async(MessageStatus.objects.create)(
            message=msg,
            recipient=seller,
        )

        seller_comm = make_communicator(buyer_seller_conversation.id, user=seller)
        await seller_comm.connect()
        await seller_comm.send_json_to({
            'type': 'message.read',
            'last_message_id': str(msg.id),
        })
        await seller_comm.receive_json_from(timeout=3)
        await seller_comm.disconnect()

        status = await sync_to_async(MessageStatus.objects.get)(
            message=msg, recipient=seller
        )
        assert status.read_at is not None

    async def test_mark_as_read_missing_last_message_id_returns_error(
        self, seller, buyer_seller_conversation
    ):
        comm = make_communicator(buyer_seller_conversation.id, user=seller)
        await comm.connect()
        await comm.send_json_to({'type': 'message.read'})
        response = await comm.receive_json_from(timeout=3)
        assert response['type'] == 'error'
        assert response['code'] == 'missing_field'
        await comm.disconnect()


class TestTypingIndicator:
    async def test_typing_indicator_received_by_other_participant(
        self, buyer, seller, buyer_seller_conversation
    ):
        buyer_comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        seller_comm = make_communicator(buyer_seller_conversation.id, user=seller)

        await buyer_comm.connect()
        await seller_comm.connect()

        await buyer_comm.send_json_to({'type': 'typing.start'})

        # Vendedor deve receber o indicador
        response = await seller_comm.receive_json_from(timeout=3)
        assert response['type'] == 'typing'
        assert response['typing']['user_id'] == str(buyer.pk)

        await buyer_comm.disconnect()
        await seller_comm.disconnect()

    async def test_typing_indicator_not_received_by_sender(
        self, buyer, seller, buyer_seller_conversation
    ):
        """O próprio remetente não deve receber seu próprio typing indicator."""
        buyer_comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        seller_comm = make_communicator(buyer_seller_conversation.id, user=seller)

        await buyer_comm.connect()
        await seller_comm.connect()

        await buyer_comm.send_json_to({'type': 'typing.start'})

        # Vendedor recebe
        await seller_comm.receive_json_from(timeout=3)

        # Comprador não deve ter recebido nada (timeout esperado)
        response = await buyer_comm.receive_nothing(timeout=0.2)
        assert response is True  # True significa que não recebeu nada

        await buyer_comm.disconnect()
        await seller_comm.disconnect()


class TestPresenceInConsumer:
    async def test_set_online_called_on_connect(
        self, buyer, buyer_seller_conversation
    ):
        """Após connect, presença deve estar marcada como online."""
        from django.core.cache import cache

        comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        await comm.connect()

        # Verifica presença via cache
        key = f"chat:presence:{buyer.pk}:{buyer_seller_conversation.id}"
        from asgiref.sync import sync_to_async
        val = await sync_to_async(cache.get)(key)
        assert val == '1'

        await comm.disconnect()

    async def test_set_offline_called_on_disconnect(
        self, buyer, buyer_seller_conversation
    ):
        """Após disconnect, presença deve ser removida."""
        from django.core.cache import cache
        from asgiref.sync import sync_to_async

        comm = make_communicator(buyer_seller_conversation.id, user=buyer)
        await comm.connect()
        await comm.disconnect()

        key = f"chat:presence:{buyer.pk}:{buyer_seller_conversation.id}"
        val = await sync_to_async(cache.get)(key)
        assert val is None
