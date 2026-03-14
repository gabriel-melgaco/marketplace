"""
Presence Service

Tracks online/offline state of users per conversation using Django's cache
(backed by Redis). Keys expire automatically so no explicit cleanup is needed
on disconnect — the TTL acts as a heartbeat mechanism.
"""

import logging
from typing import List
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Seconds until a presence key expires if not renewed (heartbeat interval
# should be shorter than this, e.g. every 60s).
_PRESENCE_TTL = 90


def _key(user_id: int, conversation_id: str) -> str:
    return f"chat:presence:{user_id}:{conversation_id}"


class PresenceService:
    """
    Thin wrapper around the Django cache layer for user presence tracking.

    The stored value is always the string '1'. Existence of the key means
    the user is considered online in that conversation.
    """

    @staticmethod
    def set_online(user_id: int, conversation_id: str) -> None:
        """
        Mark a user as online in the given conversation.

        Args:
            user_id: PK of the user.
            conversation_id: UUID string of the conversation.
        """
        cache.set(_key(user_id, conversation_id), '1', _PRESENCE_TTL)
        logger.debug("User %s online in conversation %s", user_id, conversation_id)

    @staticmethod
    def set_offline(user_id: int, conversation_id: str) -> None:
        """
        Mark a user as offline in the given conversation.

        Args:
            user_id: PK of the user.
            conversation_id: UUID string of the conversation.
        """
        cache.delete(_key(user_id, conversation_id))
        logger.debug("User %s offline in conversation %s", user_id, conversation_id)

    @staticmethod
    def is_online(user_id: int, conversation_id: str) -> bool:
        """
        Check whether a user is currently online in the given conversation.

        Args:
            user_id: PK of the user.
            conversation_id: UUID string of the conversation.

        Returns:
            True if the user has an active presence key.
        """
        return cache.get(_key(user_id, conversation_id)) is not None

    @staticmethod
    def get_online_participants(
        conversation_id: str, participant_ids: List[int]
    ) -> List[int]:
        """
        Return the subset of `participant_ids` that are currently online.

        Uses cache.get_many for a single round-trip to Redis.

        Args:
            conversation_id: UUID string of the conversation.
            participant_ids: List of user PKs to check.

        Returns:
            List of user PKs that are currently online.
        """
        keys = {_key(uid, conversation_id): uid for uid in participant_ids}
        found = cache.get_many(list(keys.keys()))
        return [keys[k] for k in found]
