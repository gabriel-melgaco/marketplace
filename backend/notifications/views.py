"""
Notification REST API Views

Endpoints:
    GET    /api/notifications/                 list (paginated, ?read=true/false)
    POST   /api/notifications/<id>/read/       mark single as read
    POST   /api/notifications/read-all/        mark all as read
    GET    /api/notifications/unread-count/    {"count": N}
    GET    /api/notifications/preferences/     get preferences
    PUT    /api/notifications/preferences/     full replace preferences
    PATCH  /api/notifications/preferences/     partial update preferences

Views are thin: validate → call service → serialize response.
"""

from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.serializers import NotificationPreferenceSerializer, NotificationSerializer
from notifications.services import NotificationService, PreferenceService


# ---------------------------------------------------------------------------
# Notification list
# ---------------------------------------------------------------------------

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='notifications_list',
        tags=['Notifications'],
        summary='List notifications',
        description='Return paginated notifications for the authenticated user.',
        parameters=[
            OpenApiParameter(
                name='read',
                description='Filter by read status. "true" = read only, "false" = unread only.',
                required=False,
                type=str,
                enum=['true', 'false'],
            ),
        ],
        responses={200: NotificationSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        read_param = request.query_params.get('read')

        if read_param is None:
            qs = NotificationService.get_user_notifications(request.user)
        elif read_param.lower() == 'false':
            qs = NotificationService.get_user_notifications(request.user, unread_only=True)
        else:
            qs = NotificationService.get_user_notifications(request.user).filter(is_read=True)

        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(qs, request)
        serializer = NotificationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ---------------------------------------------------------------------------
# Mark single notification as read
# ---------------------------------------------------------------------------

class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='notifications_mark_read',
        tags=['Notifications'],
        summary='Mark a notification as read',
        request=None,
        responses={
            200: NotificationSerializer,
            404: inline_serializer(
                name='NotificationNotFoundResponse',
                fields={'detail': drf_serializers.CharField()},
            ),
        },
    )
    def post(self, request: Request, notification_id: str) -> Response:
        from notifications.models import Notification

        try:
            notification = NotificationService.mark_as_read(
                notification_id, request.user
            )
        except Notification.DoesNotExist:
            return Response(
                {'detail': 'Notificação não encontrada.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(NotificationSerializer(notification).data)


# ---------------------------------------------------------------------------
# Mark all as read
# ---------------------------------------------------------------------------

class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='notifications_mark_all_read',
        tags=['Notifications'],
        summary='Mark all notifications as read',
        request=None,
        responses={
            200: inline_serializer(
                name='MarkAllReadResponse',
                fields={'marked': drf_serializers.IntegerField()},
            ),
        },
    )
    def post(self, request: Request) -> Response:
        count = NotificationService.mark_all_as_read(request.user)
        return Response({'marked': count})


# ---------------------------------------------------------------------------
# Unread count
# ---------------------------------------------------------------------------

class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='notifications_unread_count',
        tags=['Notifications'],
        summary='Get unread notification count',
        responses={
            200: inline_serializer(
                name='UnreadCountResponse',
                fields={'count': drf_serializers.IntegerField()},
            ),
        },
    )
    def get(self, request: Request) -> Response:
        count = NotificationService.get_unread_count(request.user)
        return Response({'count': count})


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

class NotificationPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='notifications_preferences_retrieve',
        tags=['Notifications'],
        summary='Get notification preferences',
        responses={200: NotificationPreferenceSerializer},
    )
    def get(self, request: Request) -> Response:
        prefs = PreferenceService.get_or_create_preferences(request.user)
        return Response(NotificationPreferenceSerializer(prefs).data)

    @extend_schema(
        operation_id='notifications_preferences_update',
        tags=['Notifications'],
        summary='Update notification preferences (full replace)',
        request=NotificationPreferenceSerializer,
        responses={200: NotificationPreferenceSerializer},
    )
    def put(self, request: Request) -> Response:
        return self._update(request, partial=False)

    @extend_schema(
        operation_id='notifications_preferences_partial_update',
        tags=['Notifications'],
        summary='Partially update notification preferences',
        request=NotificationPreferenceSerializer,
        responses={200: NotificationPreferenceSerializer},
    )
    def patch(self, request: Request) -> Response:
        return self._update(request, partial=True)

    def _update(self, request: Request, partial: bool) -> Response:
        prefs = PreferenceService.get_or_create_preferences(request.user)
        serializer = NotificationPreferenceSerializer(
            prefs, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        prefs = PreferenceService.update_preferences(
            request.user, serializer.validated_data
        )
        return Response(NotificationPreferenceSerializer(prefs).data)
