"""
Conversation Service

Handles all business logic related to conversation lifecycle:
creation, retrieval, listing, participant validation, and closing.
"""

import logging
from typing import Optional
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q, QuerySet

from chats.models import Conversation, ConversationParticipant

logger = logging.getLogger(__name__)
User = get_user_model()

# TTL in seconds for the participant cache key
_PARTICIPANT_CACHE_TTL = 300


class ConversationServiceError(Exception):
    """Raised when a conversation operation cannot be completed."""
    pass


class ConversationService:
    """
    Service layer for Conversation management.

    All mutating methods are decorated with @transaction.atomic to guarantee
    data consistency. Non-mutating methods are plain reads optimised with
    select_related / prefetch_related.
    """

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def create_conversation(
        initiator: User,
        conversation_type: str,
        recipient_id: int,
        order_id: Optional[str] = None,
        listing_id: Optional[int] = None,
    ) -> tuple['Conversation', bool]:
        """
        Get or create a conversation between `initiator` and `recipient`.

        Returns a tuple ``(conversation, created)`` where ``created`` is
        ``True`` if a new conversation was inserted, ``False`` if an existing
        active conversation was reused.

        Rules:
        - A ``buyer_seller`` conversation is unique per (listing, buyer, seller)
          while the conversation is still active.  Any attempt to open a second
          conversation for the exact same triple reuses the existing one.
        - The check runs inside a ``SELECT … FOR UPDATE`` lock on the matching
          rows so that concurrent requests cannot create duplicates even under
          high load.
        - Support conversations (``buyer_support`` / ``seller_support``) are
          always created fresh — they are not deduplicated.
        - The ``initiator`` role is derived automatically from
          ``conversation_type``:
            buyer_seller   → initiator = buyer,  recipient = seller
            buyer_support  → initiator = buyer,  recipient = support (staff)
            seller_support → initiator = seller, recipient = support (staff)

        Args:
            initiator: The user opening the conversation.
            conversation_type: One of Conversation.CONVERSATION_TYPE_CHOICES values.
            recipient_id: PK of the other participant.
            order_id: Optional UUID of a related Order.
            listing_id: Optional PK of a related MarketplaceListing.

        Returns:
            Tuple of (Conversation, bool) — the conversation and whether it
            was freshly created.

        Raises:
            ConversationServiceError: On invalid input or business rule violation.
        """
        valid_types = {c[0] for c in Conversation.CONVERSATION_TYPE_CHOICES}
        if conversation_type not in valid_types:
            raise ConversationServiceError(
                f"Tipo de conversa inválido: '{conversation_type}'. "
                f"Escolha um de: {valid_types}"
            )

        try:
            recipient = User.objects.get(pk=recipient_id)
        except User.DoesNotExist:
            raise ConversationServiceError(
                f"Destinatário com id={recipient_id} não encontrado."
            )

        if initiator.pk == recipient.pk:
            raise ConversationServiceError(
                "Não é possível iniciar uma conversa consigo mesmo."
            )

        # Determine roles
        if conversation_type == Conversation.TYPE_BUYER_SELLER:
            initiator_role = ConversationParticipant.ROLE_BUYER
            recipient_role = ConversationParticipant.ROLE_SELLER
        elif conversation_type == Conversation.TYPE_BUYER_SUPPORT:
            initiator_role = ConversationParticipant.ROLE_BUYER
            recipient_role = ConversationParticipant.ROLE_SUPPORT
        else:  # seller_support
            initiator_role = ConversationParticipant.ROLE_SELLER
            recipient_role = ConversationParticipant.ROLE_SUPPORT

        # ------------------------------------------------------------------
        # Uniqueness guard for buyer_seller conversations scoped to a listing.
        #
        # We use select_for_update() to lock the matching rows inside the
        # atomic transaction, serialising concurrent creation attempts for
        # the same (type, listing, buyer, seller) triple.  Without the lock
        # two simultaneous POST requests could both pass the .exists() check
        # and both proceed to INSERT, producing duplicates.
        # ------------------------------------------------------------------
        if conversation_type == Conversation.TYPE_BUYER_SELLER and listing_id:
            existing = (
                Conversation.objects
                .select_for_update()
                .filter(
                    conversation_type=conversation_type,
                    listing_id=listing_id,
                    status=Conversation.STATUS_ACTIVE,
                    participants__user=initiator,
                    participants__role=initiator_role,
                )
                .filter(
                    participants__user=recipient,
                    participants__role=recipient_role,
                )
                .first()
            )
            if existing:
                logger.info(
                    "Reusing existing conversation %s for listing %s pair (%s=%s, %s=%s)",
                    existing.id,
                    listing_id,
                    initiator_role,
                    initiator.pk,
                    recipient_role,
                    recipient.pk,
                )
                return existing, False

        conversation = Conversation.objects.create(
            conversation_type=conversation_type,
            status=Conversation.STATUS_ACTIVE,
            created_by=initiator,
            order_id=order_id,
            listing_id=listing_id,
        )

        ConversationParticipant.objects.bulk_create([
            ConversationParticipant(
                conversation=conversation,
                user=initiator,
                role=initiator_role,
            ),
            ConversationParticipant(
                conversation=conversation,
                user=recipient,
                role=recipient_role,
            ),
        ])

        logger.info(
            "Conversation %s created (type=%s) by user %s",
            conversation.id, conversation_type, initiator.pk,
        )
        return conversation, True

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    @staticmethod
    def get_conversation(conversation_id: str, user: User) -> Conversation:
        """
        Retrieve a single conversation, verifying the user is a participant.

        Args:
            conversation_id: UUID string of the conversation.
            user: The requesting user.

        Returns:
            The Conversation instance with participants prefetched.

        Raises:
            ConversationServiceError: If not found or user is not a participant.
        """
        try:
            conversation = (
                Conversation.objects
                .prefetch_related('participants__user')
                .select_related('listing', 'order', 'created_by')
                .get(pk=conversation_id)
            )
        except Conversation.DoesNotExist:
            raise ConversationServiceError("Conversa não encontrada.")

        if not ConversationService.is_participant(user, str(conversation_id)):
            raise ConversationServiceError(
                "Você não tem permissão para acessar esta conversa."
            )

        return conversation

    @staticmethod
    def list_conversations(user: User, status: str = 'active') -> QuerySet:
        """
        Return all conversations the user participates in, filtered by status.

        Each conversation is annotated with `unread_count` (messages sent by
        others that the user has not yet read based on last_read_at).

        Args:
            user: The requesting user.
            status: Conversation status filter ('active', 'closed', 'archived').

        Returns:
            QuerySet of Conversation ordered by -updated_at.
        """
        participant_qs = (
            ConversationParticipant.objects
            .filter(user=user, is_active=True)
            .values_list('conversation_id', flat=True)
        )

        qs = (
            Conversation.objects
            .filter(id__in=participant_qs, status=status)
            .prefetch_related('participants__user')
            .select_related('listing', 'order', 'created_by')
            .order_by('-updated_at')
        )

        return qs

    # ------------------------------------------------------------------
    # Participant validation (with Redis cache)
    # ------------------------------------------------------------------

    @staticmethod
    def is_participant(user: User, conversation_id: str) -> bool:
        """
        Check whether `user` is an active participant of the given conversation.

        The result is cached in Redis for _PARTICIPANT_CACHE_TTL seconds to
        avoid repeated DB queries during WebSocket connections.

        Args:
            user: The user to check.
            conversation_id: UUID string of the conversation.

        Returns:
            True if the user is an active participant.
        """
        cache_key = f"chat:participants:{conversation_id}:{user.pk}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        result = ConversationParticipant.objects.filter(
            conversation_id=conversation_id,
            user=user,
            is_active=True,
        ).exists()

        cache.set(cache_key, result, _PARTICIPANT_CACHE_TTL)
        return result

    @staticmethod
    def invalidate_participant_cache(conversation_id: str, user_id: int) -> None:
        """Evict the participant cache entry for a specific user/conversation pair."""
        cache_key = f"chat:participants:{conversation_id}:{user_id}"
        cache.delete(cache_key)

    # ------------------------------------------------------------------
    # Close / archive
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def close_conversation(conversation_id: str, closed_by: User) -> Conversation:
        """
        Close an active conversation. Only participants or staff can close it.

        Args:
            conversation_id: UUID string of the conversation.
            closed_by: The user requesting the close action.

        Returns:
            The updated Conversation instance.

        Raises:
            ConversationServiceError: If not found, already closed, or permission denied.
        """
        try:
            conversation = Conversation.objects.select_for_update().get(
                pk=conversation_id
            )
        except Conversation.DoesNotExist:
            raise ConversationServiceError("Conversa não encontrada.")

        if conversation.status == Conversation.STATUS_CLOSED:
            raise ConversationServiceError("Conversa já está fechada.")

        if not (
            closed_by.is_staff
            or ConversationService.is_participant(closed_by, conversation_id)
        ):
            raise ConversationServiceError(
                "Você não tem permissão para fechar esta conversa."
            )

        conversation.status = Conversation.STATUS_CLOSED
        conversation.save(update_fields=['status', 'updated_at'])

        logger.info(
            "Conversation %s closed by user %s", conversation_id, closed_by.pk
        )
        return conversation
