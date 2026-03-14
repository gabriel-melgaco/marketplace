"""
Notification WebSocket Consumer

Connects an authenticated user to their personal notification group
``notifications_{user_id}``.  The Celery task ``send_realtime_notification``
pushes events to this group; the consumer forwards them to the browser.

Incoming client messages:
    {"type": "mark_read", "notification_id": "<uuid>"}

Outgoing server events:
    {"type": "notification", "data": {<NotificationSerializer fields>}}
    {"type": "unread_count", "count": <int>}
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)

# WebSocket close codes (matching chat app conventions)
WS_CLOSE_UNAUTHENTICATED = 4001


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    Personal notification channel for a single authenticated user.

    Group : notifications_{user.id}
    """

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        user = self.scope.get('user')

        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            logger.warning(
                "NotificationConsumer: unauthenticated connection rejected."
            )
            await self.close(code=WS_CLOSE_UNAUTHENTICATED)
            return

        self.user = user
        self.group_name = f"notifications_{user.pk}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send the current unread count on connect so the frontend badge is
        # immediately accurate without a separate REST call.
        unread = await self._get_unread_count()
        await self.send_json({"type": "unread_count", "count": unread})

        logger.info(
            "NotificationConsumer: user %s connected (group=%s)",
            user.pk,
            self.group_name,
        )

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name, self.channel_name
            )
        logger.info(
            "NotificationConsumer: user %s disconnected (code=%s)",
            getattr(self, 'user', '?'),
            close_code,
        )

    # ------------------------------------------------------------------
    # Incoming messages from the client
    # ------------------------------------------------------------------

    async def receive_json(self, content: dict, **kwargs) -> None:
        msg_type = content.get('type')

        if msg_type == 'mark_read':
            notification_id = content.get('notification_id')
            if notification_id:
                await self._mark_read(notification_id)
                unread = await self._get_unread_count()
                await self.send_json({"type": "unread_count", "count": unread})
        else:
            logger.debug(
                "NotificationConsumer: unknown message type '%s' from user %s.",
                msg_type,
                getattr(self, 'user', '?'),
            )

    # ------------------------------------------------------------------
    # Channel layer event handler
    # ------------------------------------------------------------------

    async def notification_send(self, event: dict) -> None:
        """
        Handler for ``notification.send`` events pushed by the Celery task.

        Django Channels converts ``"type": "notification.send"`` → method
        ``notification_send``.
        """
        await self.send_json({"type": "notification", "data": event.get("data", {})})

    # ------------------------------------------------------------------
    # DB helpers (run in thread pool via database_sync_to_async)
    # ------------------------------------------------------------------

    @database_sync_to_async
    def _get_unread_count(self) -> int:
        from notifications.models import Notification
        return Notification.objects.filter(
            recipient=self.user, is_read=False
        ).count()

    @database_sync_to_async
    def _mark_read(self, notification_id: str) -> None:
        from notifications.services import NotificationService
        try:
            NotificationService.mark_as_read(notification_id, self.user)
        except Exception as exc:
            logger.warning(
                "NotificationConsumer: could not mark %s as read for user %s: %s",
                notification_id,
                self.user.pk,
                exc,
            )
