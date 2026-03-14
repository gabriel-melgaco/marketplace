"""
Notification Signals

Auto-create a NotificationPreference row whenever a new user is created,
so the first ``get_or_create_preferences()`` call is always a get.
"""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_notification_preferences(sender, instance, created: bool, **kwargs) -> None:
    if created:
        from notifications.models import NotificationPreference
        NotificationPreference.objects.get_or_create(user=instance)
