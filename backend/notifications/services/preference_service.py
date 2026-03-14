"""
Preference Service

Handles reading and updating per-user notification delivery preferences.
"""

from django.db import transaction

from notifications.models import NotificationPreference


class PreferenceService:

    @staticmethod
    def get_or_create_preferences(user) -> NotificationPreference:
        """Get or create a NotificationPreference for *user*."""
        prefs, _ = NotificationPreference.objects.get_or_create(user=user)
        return prefs

    @staticmethod
    @transaction.atomic
    def update_preferences(user, data: dict) -> NotificationPreference:
        """
        Partially update a user's notification preferences.

        Args:
            user: The user whose preferences to update.
            data: Dict of field_name → value.  Only recognised preference
                fields are applied; unknown keys are silently ignored.

        Returns:
            Updated NotificationPreference instance.
        """
        prefs = PreferenceService.get_or_create_preferences(user)

        allowed_fields = {
            f.name for f in NotificationPreference._meta.get_fields()
            if f.name not in ('id', 'user')
        }

        update_fields = []
        for field, value in data.items():
            if field in allowed_fields:
                setattr(prefs, field, value)
                update_fields.append(field)

        if update_fields:
            prefs.save(update_fields=update_fields)

        return prefs
