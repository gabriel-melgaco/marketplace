"""
Notification Service

Entry point for all notification creation.  Other apps call
``NotificationService.notify()`` and this service handles:

1. Persisting the Notification record (with idempotency guard).
2. Scheduling the Celery dispatch task via ``transaction.on_commit`` so the DB
   row is committed and visible to workers before they try to read it.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from notifications.models import Notification, NotificationPreference, NotificationType

logger = logging.getLogger(__name__)


class NotificationService:

    @staticmethod
    def notify(
        recipient,
        event_type: str,
        title: str,
        body: str,
        metadata: dict | None = None,
        idempotency_key: str | None = None,
    ) -> Notification | None:
        """
        Create a Notification record and schedule async delivery.

        This is the single public interface for all source apps.  It MUST be
        called from within an existing database transaction so that
        ``transaction.on_commit`` fires at the right boundary.

        Args:
            recipient: User instance (the notification target).
            event_type: One of ``NotificationType`` values.
            title: Short summary shown in UI / email subject.
            body: Full notification text.
            metadata: Arbitrary dict stored as JSON for the front-end.
            idempotency_key: Stable key preventing duplicate delivery on retry.
                Recommended format: ``'{event_type}_{object_id}'``.

        Returns:
            The created Notification, or None if the idempotency_key was
            already used (duplicate silently skipped).
        """
        try:
            # Use a nested atomic block (savepoint) so that an IntegrityError on the
            # unique idempotency_key constraint does NOT abort the outer PostgreSQL
            # transaction.  Without this, any duplicate-key hit inside an outer
            # @transaction.atomic block would leave the connection in an error state,
            # making every subsequent query in that request fail with
            # "current transaction is aborted".
            with transaction.atomic():
                notification = Notification.objects.create(
                    recipient=recipient,
                    notification_type=event_type,
                    title=title,
                    body=body,
                    metadata=metadata or {},
                    idempotency_key=idempotency_key,
                )
        except IntegrityError:
            # Duplicate idempotency_key — already processed, skip silently.
            logger.info(
                "Notification skipped (duplicate idempotency_key=%s)", idempotency_key
            )
            return None

        notification_id = str(notification.id)

        # Enqueue delivery AFTER the current transaction commits so the worker
        # can read the row.  If no transaction is active, on_commit fires
        # immediately (Django behaviour).
        def _enqueue() -> None:
            from notifications.tasks import dispatch_notification
            dispatch_notification.delay(notification_id)

        transaction.on_commit(_enqueue)

        logger.info(
            "Notification created: id=%s type=%s recipient=%s",
            notification_id,
            event_type,
            recipient.pk,
        )
        return notification

    @staticmethod
    def get_user_notifications(user, unread_only: bool = False):
        """Return the queryset of notifications for *user*."""
        qs = Notification.objects.filter(recipient=user)
        if unread_only:
            qs = qs.filter(is_read=False)
        return qs

    @staticmethod
    @transaction.atomic
    def mark_as_read(notification_id: str, user) -> Notification:
        """
        Mark a single notification as read.

        Args:
            notification_id: UUID string.
            user: Must be the recipient.

        Returns:
            Updated Notification.

        Raises:
            Notification.DoesNotExist: If not found or owned by another user.
        """
        notification = Notification.objects.select_for_update().get(
            id=notification_id,
            recipient=user,
        )
        if not notification.is_read:
            notification.mark_read()
            notification.save(update_fields=['is_read', 'read_at'])
        return notification

    @staticmethod
    @transaction.atomic
    def mark_all_as_read(user) -> int:
        """
        Mark all unread notifications for *user* as read.

        Returns:
            Number of rows updated.
        """
        now = timezone.now()
        updated = Notification.objects.filter(
            recipient=user,
            is_read=False,
        ).update(is_read=True, read_at=now)
        return updated

    @staticmethod
    def get_unread_count(user) -> int:
        """Return the count of unread notifications for *user*."""
        return Notification.objects.filter(recipient=user, is_read=False).count()

    @staticmethod
    def get_or_create_preferences(user) -> NotificationPreference:
        """Get or create the NotificationPreference for *user*."""
        prefs, _ = NotificationPreference.objects.get_or_create(user=user)
        return prefs
