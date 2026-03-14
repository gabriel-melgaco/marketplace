"""
ChatConsumer — synchronous WebSocket consumer for the chat system.

Architecture decisions:
- WebsocketConsumer (sync) is used to keep Django ORM calls straightforward
  without async wrappers on every DB access.
- async_to_sync bridges the channel layer's async group_send/group_add to the
  sync consumer context.
- Rate limiting uses Redis (via Django cache) with a simple counter per user
  per minute window (sliding window approximated by key TTL).
- group_send for new messages is called inside transaction.on_commit so the DB
  row is visible to all readers before the broadcast goes out.

Group names:
- Conversation group : chat_conv_{conversation.id.hex}  (no hyphens)
- User personal group: chat_user_{user.id}
"""

import json
import logging
from typing import Optional

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from chats.models import Conversation, Message
from chats.services import ConversationService, MessageService, PresenceService

logger = logging.getLogger(__name__)

# WebSocket close codes
WS_CLOSE_UNAUTHENTICATED = 4001
WS_CLOSE_FORBIDDEN = 4003
WS_CLOSE_NOT_FOUND = 4004

# Rate limit: max messages per user per minute
RATE_LIMIT_MAX = 60
RATE_LIMIT_WINDOW = 60  # seconds


class ChatConsumer(WebsocketConsumer):
    """
    Synchronous WebSocket consumer handling real-time chat for a single conversation.

    Lifecycle:
        connect()    → authenticate → verify participant → join groups → accept
        disconnect() → leave groups → set_offline
        receive()    → dispatch to handle_message_send / handle_message_read / handle_typing

    Channel layer events (group → consumer):
        chat_message       → forwards new message payload to the connected client
        chat_read_receipt  → forwards read receipt payload
        chat_typing        → forwards typing indicator
        chat_new_conversation → forwards new conversation notification
    """

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        try:
            self._do_connect()
        except Exception as exc:
            logger.exception("Unexpected error in connect(): %s", exc)
            raise

    def _do_connect(self) -> None:
        user = self.scope.get('user')
        logger.debug("WS connect: user=%s authenticated=%s", user, getattr(user, 'is_authenticated', False))

        if not user or not user.is_authenticated:
            logger.warning("Unauthenticated WebSocket connection attempt rejected.")
            self.close(code=WS_CLOSE_UNAUTHENTICATED)
            return

        conversation_id: str = self.scope['url_route']['kwargs']['conversation_id']
        logger.debug("WS connect: conversation_id=%s", conversation_id)

        # Verify conversation exists
        try:
            self.conversation = Conversation.objects.get(pk=conversation_id)
        except Conversation.DoesNotExist:
            logger.warning(
                "User %s tried to connect to non-existent conversation %s",
                user.pk, conversation_id,
            )
            self.close(code=WS_CLOSE_NOT_FOUND)
            return

        # Verify the user is an active participant
        is_part = ConversationService.is_participant(user, conversation_id)
        logger.debug("WS connect: is_participant=%s for user=%s", is_part, user.pk)
        if not is_part:
            logger.warning(
                "User %s is not a participant of conversation %s",
                user.pk, conversation_id,
            )
            self.close(code=WS_CLOSE_FORBIDDEN)
            return

        self.user = user
        self.conversation_id = conversation_id
        self.conv_group = f"chat_conv_{self.conversation.id.hex}"
        self.user_group = f"chat_user_{user.pk}"

        # Join channel groups
        logger.debug("WS connect: joining groups %s %s", self.conv_group, self.user_group)
        async_to_sync(self.channel_layer.group_add)(self.conv_group, self.channel_name)
        async_to_sync(self.channel_layer.group_add)(self.user_group, self.channel_name)

        PresenceService.set_online(user.pk, conversation_id)

        self.accept()
        logger.info(
            "User %s connected to conversation %s", user.pk, conversation_id
        )

    def disconnect(self, code: int) -> None:
        if not hasattr(self, 'user'):
            return

        async_to_sync(self.channel_layer.group_discard)(
            self.conv_group, self.channel_name
        )
        async_to_sync(self.channel_layer.group_discard)(
            self.user_group, self.channel_name
        )

        PresenceService.set_offline(self.user.pk, self.conversation_id)
        logger.info(
            "User %s disconnected from conversation %s (code=%s)",
            self.user.pk, self.conversation_id, code,
        )

    # ------------------------------------------------------------------
    # Incoming messages
    # ------------------------------------------------------------------

    def receive(self, text_data: str = None, bytes_data: bytes = None) -> None:
        try:
            data = json.loads(text_data or '{}')
        except json.JSONDecodeError:
            self._send_error('invalid_json', 'Payload JSON inválido.')
            return

        msg_type = data.get('type', '')

        dispatch = {
            'message.send': self.handle_message_send,
            'message.read': self.handle_message_read,
            'typing.start': self.handle_typing,
        }

        handler = dispatch.get(msg_type)
        if handler is None:
            self._send_error('unknown_type', f"Tipo desconhecido: '{msg_type}'.")
            return

        handler(data)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def handle_message_send(self, data: dict) -> None:
        """Validate, persist, and broadcast a new chat message."""
        content: str = (data.get('content') or '').strip()
        if not content:
            self._send_error('empty_content', 'O conteúdo da mensagem não pode estar vazio.')
            return

        # Rate limiting
        if not self._check_rate_limit():
            self._send_error(
                'rate_limited',
                'Você está enviando mensagens rápido demais. Aguarde um momento.',
            )
            return

        try:
            with transaction.atomic():
                message = MessageService.send_message(
                    conversation=self.conversation,
                    sender=self.user,
                    content=content,
                    message_type=Message.TYPE_TEXT,
                )

                payload = {
                    'type': 'chat_message',
                    'message': self._serialize_message(message),
                }

                # Broadcast only after the transaction commits so all readers
                # see the persisted row.
                transaction.on_commit(
                    lambda: async_to_sync(self.channel_layer.group_send)(
                        self.conv_group, payload
                    )
                )

        except Exception as exc:
            logger.exception(
                "Error sending message in conversation %s: %s",
                self.conversation_id, exc,
            )
            self._send_error('send_failed', 'Falha ao enviar mensagem.')

    def handle_message_read(self, data: dict) -> None:
        """Mark messages up to `last_message_id` as read and broadcast a receipt."""
        last_message_id: Optional[str] = data.get('last_message_id')
        if not last_message_id:
            self._send_error('missing_field', "'last_message_id' é obrigatório.")
            return

        try:
            MessageService.mark_as_read(
                user=self.user,
                conversation_id=self.conversation_id,
                last_message_id=last_message_id,
            )
        except Exception as exc:
            logger.warning(
                "mark_as_read failed for user %s: %s", self.user.pk, exc
            )
            self._send_error('read_failed', str(exc))
            return

        now = timezone.now().isoformat()
        receipt_payload = {
            'type': 'chat_read_receipt',
            'receipt': {
                'conversation_id': self.conversation_id,
                'last_message_id': last_message_id,
                'user_id': str(self.user.pk),
                'read_at': now,
            },
        }
        async_to_sync(self.channel_layer.group_send)(self.conv_group, receipt_payload)

    def handle_typing(self, data: dict) -> None:
        """Broadcast a typing indicator to other participants."""
        typing_payload = {
            'type': 'chat_typing',
            'typing': {
                'conversation_id': self.conversation_id,
                'user_id': str(self.user.pk),
                'user_name': self.user.full_name or self.user.email,
            },
        }
        async_to_sync(self.channel_layer.group_send)(self.conv_group, typing_payload)

    # ------------------------------------------------------------------
    # Channel layer event handlers (group → this consumer)
    # ------------------------------------------------------------------

    def chat_message(self, event: dict) -> None:
        """Forward a new_message event to the WebSocket client."""
        self.send(text_data=json.dumps({
            'type': 'new_message',
            'message': event['message'],
        }))

    def chat_read_receipt(self, event: dict) -> None:
        """Forward a read receipt to the WebSocket client."""
        self.send(text_data=json.dumps({
            'type': 'message_read',
            'receipt': event['receipt'],
        }))

    def chat_typing(self, event: dict) -> None:
        """Forward a typing indicator to the WebSocket client (skip own events)."""
        if str(event['typing'].get('user_id')) == str(self.user.pk):
            return
        self.send(text_data=json.dumps({
            'type': 'typing',
            'typing': event['typing'],
        }))

    def chat_new_conversation(self, event: dict) -> None:
        """Notify the client about a new conversation they were added to."""
        self.send(text_data=json.dumps({
            'type': 'new_conversation',
            'conversation': event['conversation'],
        }))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _send_error(self, code: str, message: str) -> None:
        """Send a structured error frame to the connected client."""
        self.send(text_data=json.dumps({
            'type': 'error',
            'code': code,
            'message': message,
        }))

    def _check_rate_limit(self) -> bool:
        """
        Sliding-window rate limiter using Redis.

        Returns True if the user is within the allowed rate, False if exceeded.
        """
        rate_key = f"chat:rate:{self.user.pk}"
        count = cache.get(rate_key, 0)
        if count >= RATE_LIMIT_MAX:
            return False
        # Increment; if this is the first hit, set the TTL window
        pipe_result = cache.get_or_set(rate_key, 0, RATE_LIMIT_WINDOW)
        cache.set(rate_key, (cache.get(rate_key) or 0) + 1, RATE_LIMIT_WINDOW)
        return True

    @staticmethod
    def _serialize_message(message: Message) -> dict:
        """Produce a JSON-serializable dict from a Message instance."""
        sender = message.sender
        return {
            'id': str(message.id),
            'conversation_id': str(message.conversation_id),
            'sender_id': str(sender.pk),
            'sender_name': sender.full_name or sender.email,
            'content': message.content,
            'message_type': message.message_type,
            'created_at': message.created_at.isoformat(),
            'metadata': message.metadata,
        }
