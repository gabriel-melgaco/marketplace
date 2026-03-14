"""
Message REST views.

GET  /api/chats/conversations/<uuid>/messages/       — cursor-paginated history
POST /api/chats/conversations/<uuid>/messages/read/  — mark messages as read
"""

import logging

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chats.serializers import MarkAsReadSerializer, MessageSerializer
from chats.services import MessageService, MessageServiceError

logger = logging.getLogger(__name__)


class MessageListView(APIView):
    """
    GET /api/chats/conversations/<uuid:pk>/messages/

    Returns up to `limit` messages in descending creation order
    (most recent first) optionally bounded by `before` cursor.

    The client should reverse the list to display oldest-first.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Chat'],
        summary='Histórico de mensagens',
        description=(
            'Retorna mensagens da conversa em ordem decrescente. '
            'Use `before=<message_id>` para paginar para mensagens mais antigas. '
            'Use `limit` para controlar o tamanho da página (máx. 100).'
        ),
        parameters=[
            OpenApiParameter(
                name='before',
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description='UUID da mensagem de referência (cursor de paginação).',
            ),
            OpenApiParameter(
                name='limit',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Número de mensagens a retornar (padrão 50, máx 100).',
            ),
        ],
        responses={
            200: MessageSerializer(many=True),
            403: OpenApiTypes.OBJECT,
        },
        operation_id='chat_messages_list',
    )
    def get(self, request: Request, pk: str) -> Response:
        before_id = request.query_params.get('before')
        try:
            limit = int(request.query_params.get('limit', 50))
        except (ValueError, TypeError):
            limit = 50

        try:
            messages = MessageService.get_history(
                user=request.user,
                conversation_id=str(pk),
                before_id=before_id,
                limit=limit,
            )
        except MessageServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data)


class MarkAsReadView(APIView):
    """
    POST /api/chats/conversations/<uuid:pk>/messages/read/

    Marks all messages up to `last_message_id` as read for the current user.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Chat'],
        summary='Marcar mensagens como lidas',
        description=(
            'Marca como lidas todas as mensagens desta conversa até '
            '`last_message_id` (inclusive) para o usuário autenticado.'
        ),
        request=MarkAsReadSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
        },
        operation_id='chat_messages_mark_read',
    )
    def post(self, request: Request, pk: str) -> Response:
        serializer = MarkAsReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        last_message_id = str(serializer.validated_data['last_message_id'])

        try:
            updated = MessageService.mark_as_read(
                user=request.user,
                conversation_id=str(pk),
                last_message_id=last_message_id,
            )
        except MessageServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'updated': updated})
