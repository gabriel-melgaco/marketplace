"""
Message Service

Handles sending, retrieving, and read-tracking of chat messages.
"""

import logging
import uuid
from typing import Optional
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from chats.models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageStatus,
)
from .conversation_service import ConversationService, ConversationServiceError

logger = logging.getLogger(__name__)
User = get_user_model()


class MessageServiceError(Exception):
    """Raised when a message operation cannot be completed."""
    pass


class MessageService:
    """
    Service layer for Message operations.

    Key design decisions:
    - send_message creates MessageStatus rows for every *other* participant in
      one bulk_create call to avoid N+1 inserts.
    - get_history uses cursor-based pagination (before_id) rather than offset
      pagination to ensure stable results under concurrent writes.
    - mark_as_read issues a single bulk_update instead of per-row saves.
    """

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def send_message(
        conversation: Conversation,
        sender: User,
        content: str,
        message_type: str = Message.TYPE_TEXT,
        metadata: Optional[dict] = None,
    ) -> Message:
        """
        Persist a new message and create MessageStatus entries for all recipients.

        Also bumps Conversation.updated_at so list_conversations ordering stays
        correct.

        Args:
            conversation: Target Conversation instance.
            sender: The sending user (must be an active participant).
            content: Text body of the message.
            message_type: 'text' or 'system'.
            metadata: Optional arbitrary metadata dict.

        Returns:
            The created Message.

        Raises:
            MessageServiceError: If sender is not a participant or conversation
                is not active.
        """
        if conversation.status != Conversation.STATUS_ACTIVE:
            raise MessageServiceError(
                "Não é possível enviar mensagens em uma conversa fechada ou arquivada."
            )

        if not ConversationService.is_participant(sender, str(conversation.pk)):
            raise MessageServiceError(
                "Você não é participante desta conversa."
            )

        message = Message.objects.create(
            conversation=conversation,
            sender=sender,
            content=content,
            message_type=message_type,
            metadata=metadata or {},
        )

        # Create delivery receipts for all OTHER active participants
        other_participants = (
            ConversationParticipant.objects
            .filter(conversation=conversation, is_active=True)
            .exclude(user=sender)
            .values_list('user_id', flat=True)
        )

        now = timezone.now()
        statuses = [
            MessageStatus(
                message=message,
                recipient_id=recipient_id,
                delivered_at=now,
            )
            for recipient_id in other_participants
        ]
        if statuses:
            MessageStatus.objects.bulk_create(statuses, ignore_conflicts=True)

        # Touch conversation so ordering by -updated_at reflects this message
        Conversation.objects.filter(pk=conversation.pk).update(updated_at=now)

        logger.info(
            "Message %s sent by user %s in conversation %s",
            message.id, sender.pk, conversation.pk,
        )
        return message

    # ------------------------------------------------------------------
    # History retrieval
    # ------------------------------------------------------------------

    @staticmethod
    def get_history(
        user: User,
        conversation_id: str,
        before_id: Optional[str] = None,
        limit: int = 50,
    ) -> QuerySet:
        """
        Return messages for a conversation using cursor-based pagination.

        Messages are returned in ascending created_at order (oldest first)
        so the frontend can append them naturally. The cursor `before_id` is
        the UUID of the oldest message the client already has; the service
        returns the page of messages that precede it.

        Args:
            user: The requesting user (must be a participant).
            conversation_id: UUID string of the target conversation.
            before_id: UUID of the reference message (exclusive upper bound).
            limit: Maximum number of messages to return (capped at 100).

        Returns:
            QuerySet of Message ordered by created_at.

        Raises:
            MessageServiceError: If the user is not a participant.
        """
        if not ConversationService.is_participant(user, conversation_id):
            raise MessageServiceError(
                "Você não tem permissão para ver as mensagens desta conversa."
            )

        limit = min(limit, 100)

        qs = (
            Message.objects
            .filter(conversation_id=conversation_id, is_deleted=False)
            .select_related('sender')
            .order_by('created_at')
        )

        if before_id:
            try:
                pivot = Message.objects.only('created_at').get(
                    pk=before_id, conversation_id=conversation_id
                )
                qs = qs.filter(created_at__lt=pivot.created_at)
            except Message.DoesNotExist:
                raise MessageServiceError(
                    f"Mensagem de referência {before_id} não encontrada."
                )

        # Return the last `limit` messages before the cursor
        return qs.order_by('-created_at')[:limit]

    # ------------------------------------------------------------------
    # Read receipts
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def mark_as_read(
        user: User,
        conversation_id: str,
        last_message_id: str,
    ) -> int:
        """
        Mark all messages up to and including `last_message_id` as read
        for the given user.

        Updates both:
        - MessageStatus.read_at for each affected row
        - ConversationParticipant.last_read_at

        Args:
            user: The user marking messages as read.
            conversation_id: UUID string of the conversation.
            last_message_id: UUID of the last message the user has seen.

        Returns:
            Number of MessageStatus rows updated.

        Raises:
            MessageServiceError: If the user is not a participant or the
                reference message does not exist.
        """
        if not ConversationService.is_participant(user, conversation_id):
            raise MessageServiceError(
                "Você não é participante desta conversa."
            )

        try:
            pivot = Message.objects.only('created_at').get(
                pk=last_message_id, conversation_id=conversation_id
            )
        except Message.DoesNotExist:
            raise MessageServiceError(
                f"Mensagem {last_message_id} não encontrada nesta conversa."
            )

        now = timezone.now()

        # Bulk-update all unread statuses up to the pivot message
        updated = MessageStatus.objects.filter(
            recipient=user,
            read_at__isnull=True,
            message__conversation_id=conversation_id,
            message__created_at__lte=pivot.created_at,
        ).update(read_at=now)

        # Also update the participant's last_read_at watermark
        ConversationParticipant.objects.filter(
            conversation_id=conversation_id,
            user=user,
        ).update(last_read_at=now)

        logger.info(
            "User %s marked %d messages as read in conversation %s (up to %s)",
            user.pk, updated, conversation_id, last_message_id,
        )
        return updated

    # ------------------------------------------------------------------
    # Unread count
    # ------------------------------------------------------------------

    @staticmethod
    def get_unread_count(user: User, conversation_id: str) -> int:
        """
        Count messages in the conversation that the user has not yet read.

        Uses ConversationParticipant.last_read_at as the watermark.

        Args:
            user: The requesting user.
            conversation_id: UUID string of the conversation.

        Returns:
            Integer count of unread messages.
        """
        try:
            participant = ConversationParticipant.objects.get(
                conversation_id=conversation_id, user=user
            )
        except ConversationParticipant.DoesNotExist:
            return 0

        qs = Message.objects.filter(
            conversation_id=conversation_id,
            is_deleted=False,
        ).exclude(sender=user)

        if participant.last_read_at:
            qs = qs.filter(created_at__gt=participant.last_read_at)

        return qs.count()
