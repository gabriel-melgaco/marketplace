from django.urls import path

from notifications.views import (
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    NotificationPreferenceView,
    NotificationUnreadCountView,
)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('read-all/', NotificationMarkAllReadView.as_view(), name='notification-read-all'),
    path('<str:notification_id>/read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('preferences/', NotificationPreferenceView.as_view(), name='notification-preferences'),
]
