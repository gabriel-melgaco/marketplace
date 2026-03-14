"""
Notification Serializers
"""

from rest_framework import serializers

from notifications.models import Notification, NotificationPreference, NotificationType


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'title',
            'body',
            'metadata',
            'is_read',
            'created_at',
            'read_at',
        ]
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        # Exclude 'user' — the user is inferred from the request.
        exclude = ['id', 'user']
