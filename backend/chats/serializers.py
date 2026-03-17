"""
Chat serializers.

All serializers are read-only for responses and have explicit write
counterparts where needed so drf-spectacular can generate clean schemas
without ambiguity.
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from chats.models import Conversation, ConversationParticipant, Message, MessageStatus


# ---------------------------------------------------------------------------
# Nested / simple serializers
# ---------------------------------------------------------------------------

class ParticipantUserSerializer(serializers.Serializer):
    """Minimal user representation embedded in participant data."""
    id = serializers.IntegerField()
    email = serializers.EmailField()
    full_name = serializers.CharField()


class ConversationParticipantSerializer(serializers.ModelSerializer):
    user = ParticipantUserSerializer(read_only=True)

    class Meta:
        model = ConversationParticipant
        fields = ['id', 'user', 'role', 'last_read_at', 'joined_at', 'is_active']


class MessageStatusSerializer(serializers.ModelSerializer):
    recipient_id = serializers.IntegerField(source='recipient.id', read_only=True)

    class Meta:
        model = MessageStatus
        fields = ['recipient_id', 'delivered_at', 'read_at']


# ---------------------------------------------------------------------------
# Message serializers
# ---------------------------------------------------------------------------

class MessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.IntegerField(source='sender.id', read_only=True)
    sender_name = serializers.SerializerMethodField()
    statuses = MessageStatusSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            'id',
            'conversation',
            'sender_id',
            'sender_name',
            'content',
            'message_type',
            'is_deleted',
            'created_at',
            'metadata',
            'statuses',
        ]

    @extend_schema_field(serializers.CharField())
    def get_sender_name(self, obj: Message) -> str:
        return obj.sender.full_name or obj.sender.email


# ---------------------------------------------------------------------------
# Conversation serializers
# ---------------------------------------------------------------------------

class ConversationSerializer(serializers.ModelSerializer):
    participants = ConversationParticipantSerializer(many=True, read_only=True)
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id',
            'conversation_type',
            'status',
            'order',
            'listing',
            'created_by',
            'created_at',
            'updated_at',
            'participants',
            'unread_count',
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_unread_count(self, obj: Conversation) -> int:
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        from chats.services import MessageService
        return MessageService.get_unread_count(request.user, str(obj.pk))


# ---------------------------------------------------------------------------
# Request serializers (write)
# ---------------------------------------------------------------------------

class CreateConversationSerializer(serializers.Serializer):
    """Request body for POST /api/chats/conversations/."""
    conversation_type = serializers.ChoiceField(
        choices=[c[0] for c in Conversation.CONVERSATION_TYPE_CHOICES]
    )
    recipient_id = serializers.IntegerField()
    order_id = serializers.UUIDField(required=False, allow_null=True)
    listing_id = serializers.IntegerField(required=False, allow_null=True)


