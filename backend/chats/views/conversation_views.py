"""
Conversation REST views.

All views follow the project's thin-view pattern:
    1. Validate the request (serializer or permissions)
    2. Delegate business logic to a service
    3. Serialize and return the response
"""

import logging

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chats.serializers import (
    ConversationSerializer,
    CreateConversationSerializer,
)
from chats.services import ConversationService, ConversationServiceError

logger = logging.getLogger(__name__)


class ConversationListCreateView(APIView):
    """
    GET  /api/chats/conversations/  — list the authenticated user's conversations.
    POST /api/chats/conversations/  — open a new conversation.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Chat'],
        summary='Listar conversas',
        description=(
            'Retorna todas as conversas do usuário autenticado. '
            'Filtre por status usando o query param `status` '
            '(`active`, `closed`, `archived`). Padrão: `active`.'
        ),
        parameters=[
            OpenApiParameter(
                name='status',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Status filter',
                enum=['active', 'closed', 'archived'],
            )
        ],
        responses={200: ConversationSerializer(many=True)},
        operation_id='chat_conversations_list',
    )
    def get(self, request: Request) -> Response:
        status_filter = request.query_params.get('status', 'active')
        conversations = ConversationService.list_conversations(
            user=request.user,
            status=status_filter,
        )
        serializer = ConversationSerializer(
            conversations, many=True, context={'request': request}
        )
        return Response(serializer.data)

    @extend_schema(
        tags=['Chat'],
        summary='Criar conversa',
        description='Abre uma nova conversa. Reutiliza conversas ativas existentes para o mesmo anúncio/par.',
        request=CreateConversationSerializer,
        responses={
            201: ConversationSerializer,
            200: ConversationSerializer,
            400: OpenApiTypes.OBJECT,
        },
        operation_id='chat_conversations_create',
    )
    def post(self, request: Request) -> Response:
        in_serializer = CreateConversationSerializer(data=request.data)
        in_serializer.is_valid(raise_exception=True)
        data = in_serializer.validated_data

        try:
            conversation = ConversationService.create_conversation(
                initiator=request.user,
                conversation_type=data['conversation_type'],
                recipient_id=data['recipient_id'],
                order_id=data.get('order_id'),
                listing_id=data.get('listing_id'),
            )
        except ConversationServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out_serializer = ConversationSerializer(
            conversation, context={'request': request}
        )
        # Return 200 if the existing conversation was reused, 201 if newly created
        http_status = status.HTTP_201_CREATED
        return Response(out_serializer.data, status=http_status)


class ConversationDetailView(APIView):
    """
    GET /api/chats/conversations/<uuid:pk>/ — retrieve a single conversation.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Chat'],
        summary='Detalhe de conversa',
        description='Retorna os dados completos de uma conversa. O usuário deve ser participante.',
        responses={
            200: ConversationSerializer,
            403: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
        operation_id='chat_conversation_detail',
    )
    def get(self, request: Request, pk: str) -> Response:
        try:
            conversation = ConversationService.get_conversation(
                conversation_id=str(pk), user=request.user
            )
        except ConversationServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)

        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data)


class ConversationCloseView(APIView):
    """
    PATCH /api/chats/conversations/<uuid:pk>/close/ — close a conversation.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Chat'],
        summary='Fechar conversa',
        description='Fecha uma conversa ativa. Apenas participantes ou staff podem fechar.',
        request=None,
        responses={
            200: ConversationSerializer,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
        operation_id='chat_conversation_close',
    )
    def patch(self, request: Request, pk: str) -> Response:
        try:
            conversation = ConversationService.close_conversation(
                conversation_id=str(pk), closed_by=request.user
            )
        except ConversationServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data)
