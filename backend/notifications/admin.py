from django.contrib import admin

from notifications.models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'recipient',
        'notification_type',
        'title',
        'is_read',
        'created_at',
    ]
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['recipient__email', 'title', 'body', 'idempotency_key']
    readonly_fields = ['id', 'created_at', 'read_at']
    ordering = ['-created_at']
    raw_id_fields = ['recipient']


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'order_created_ws', 'order_created_email', 'new_message_ws', 'new_message_email']
    search_fields = ['user__email']
    raw_id_fields = ['user']
