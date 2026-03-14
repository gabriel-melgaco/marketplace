"""
Notification Celery Tasks

Three tasks form a fan-out pipeline:

    dispatch_notification
        └── send_realtime_notification   (if ws enabled for user/type)
        └── send_email_notification      (if email enabled for user/type)

All tasks use bind=True so ``self`` is available for ``self.retry()``.
Retry back-off: 60 s → 120 s → 240 s (countdown doubles each attempt).
"""

import logging

from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fan-out dispatcher
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def dispatch_notification(self, notification_id: str) -> None:
    """
    Load a Notification and fan out delivery based on user preferences.

    This task is scheduled by ``NotificationService.notify()`` via
    ``transaction.on_commit`` to guarantee the DB row exists when the worker
    reads it.
    """
    from notifications.models import Notification, NotificationPreference

    try:
        notification = Notification.objects.select_related('recipient').get(
            id=notification_id
        )
    except Notification.DoesNotExist:
        logger.error(
            "dispatch_notification: Notification %s not found — skipping.",
            notification_id,
        )
        return

    prefs, _ = NotificationPreference.objects.get_or_create(
        user=notification.recipient
    )
    event_type = notification.notification_type

    if prefs.ws_enabled_for(event_type):
        send_realtime_notification.delay(notification_id)

    if prefs.email_enabled_for(event_type):
        send_email_notification.delay(notification_id)

    logger.info(
        "dispatch_notification: id=%s type=%s ws=%s email=%s",
        notification_id,
        event_type,
        prefs.ws_enabled_for(event_type),
        prefs.email_enabled_for(event_type),
    )


# ---------------------------------------------------------------------------
# Real-time (WebSocket) delivery
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_realtime_notification(self, notification_id: str) -> None:
    """
    Push a notification to the user's WebSocket group via the Channel Layer.

    Group name format: ``notifications_{user_id}``
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from notifications.models import Notification
    from notifications.serializers import NotificationSerializer

    try:
        notification = Notification.objects.select_related('recipient').get(
            id=notification_id
        )
    except Notification.DoesNotExist:
        logger.error(
            "send_realtime_notification: Notification %s not found.", notification_id
        )
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning(
            "send_realtime_notification: no channel layer configured — skipping ws."
        )
        return

    group_name = f"notifications_{notification.recipient_id}"
    data = NotificationSerializer(notification).data

    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "notification.send",
                "data": data,
            },
        )
        logger.info(
            "send_realtime_notification: sent id=%s to group=%s",
            notification_id,
            group_name,
        )
    except Exception as exc:
        logger.warning(
            "send_realtime_notification: failed id=%s: %s — retrying.",
            notification_id,
            exc,
        )
        countdown = 60 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_notification(self, notification_id: str) -> None:
    """
    Send a notification email via Django's email backend (Resend SMTP).

    Subject  : notification.title
    Body     : plain-text notification.body
    HTML body: simple HTML wrapping for better inbox rendering.
    """
    from notifications.models import Notification

    try:
        notification = Notification.objects.select_related('recipient').get(
            id=notification_id
        )
    except Notification.DoesNotExist:
        logger.error(
            "send_email_notification: Notification %s not found.", notification_id
        )
        return

    recipient_email = notification.recipient.email
    if not recipient_email:
        logger.warning(
            "send_email_notification: recipient %s has no email — skipping.",
            notification.recipient_id,
        )
        return

    html_body = _build_html_email(notification)

    try:
        send_mail(
            subject=notification.title,
            message=notification.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=html_body,
            fail_silently=False,
        )
        logger.info(
            "send_email_notification: sent id=%s to %s",
            notification_id,
            recipient_email,
        )
    except Exception as exc:
        logger.warning(
            "send_email_notification: failed id=%s to %s: %s — retrying.",
            notification_id,
            recipient_email,
            exc,
        )
        countdown = 60 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_html_email(notification) -> str:
    """Build a minimal but readable HTML email body."""
    from django.utils.html import escape

    title = escape(notification.title)
    body = escape(notification.body)
    frontend_url = getattr(settings, 'FRONTEND_BASE_URL', 'https://marketplace.megdev.com.br')

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:24px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:8px;padding:32px;max-width:600px;">
          <tr>
            <td>
              <h2 style="color:#1a1a1a;margin-top:0;">{title}</h2>
              <p style="color:#444;line-height:1.6;">{body}</p>
              <hr style="border:none;border-top:1px solid #eeeeee;margin:24px 0;">
              <p style="font-size:12px;color:#aaa;">
                Você recebeu esta mensagem porque tem uma conta no
                <a href="{frontend_url}" style="color:#555;">Marketplace Academia</a>.
                Gerencie suas preferências de notificação no seu painel.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
