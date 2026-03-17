import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Conversation(models.Model):
    """
    Representa uma conversa entre dois participantes (comprador/vendedor
    ou usuário/suporte). Pode estar vinculada a um anúncio ou pedido.
    """

    TYPE_BUYER_SELLER = 'buyer_seller'
    TYPE_BUYER_SUPPORT = 'buyer_support'
    TYPE_SELLER_SUPPORT = 'seller_support'

    CONVERSATION_TYPE_CHOICES = [
        (TYPE_BUYER_SELLER, 'Comprador ↔ Vendedor'),
        (TYPE_BUYER_SUPPORT, 'Comprador ↔ Suporte'),
        (TYPE_SELLER_SUPPORT, 'Vendedor ↔ Suporte'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_CLOSED = 'closed'
    STATUS_ARCHIVED = 'archived'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Ativa'),
        (STATUS_CLOSED, 'Fechada'),
        (STATUS_ARCHIVED, 'Arquivada'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation_type = models.CharField(
        max_length=20,
        choices=CONVERSATION_TYPE_CHOICES,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversations',
    )
    listing = models.ForeignKey(
        'products.MarketplaceListing',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversations',
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_conversations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Conversa'
        verbose_name_plural = 'Conversas'
        indexes = [
            models.Index(fields=['status', '-updated_at']),
            models.Index(fields=['order']),
            models.Index(fields=['listing']),
        ]
        constraints = [
            # Garante que não existam duas conversas buyer_seller ativas
            # para o mesmo anúncio (listing).  Um anúncio possui exatamente
            # uma thread de conversa ativa entre comprador e vendedor.
            # A constraint é PARCIAL (condition=Q(status='active')) para que
            # conversas fechadas/arquivadas não interfiram com novas aberturas.
            models.UniqueConstraint(
                fields=['conversation_type', 'listing'],
                condition=models.Q(
                    conversation_type='buyer_seller',
                    status='active',
                ),
                name='unique_active_buyer_seller_per_listing',
            ),
        ]

    def __str__(self) -> str:
        return f"Conversation({self.id}, type={self.conversation_type}, status={self.status})"


class ConversationParticipant(models.Model):
    """
    Representa a participação de um usuário em uma conversa,
    incluindo seu papel e informações de leitura.
    """

    ROLE_BUYER = 'buyer'
    ROLE_SELLER = 'seller'
    ROLE_SUPPORT = 'support'

    ROLE_CHOICES = [
        (ROLE_BUYER, 'Comprador'),
        (ROLE_SELLER, 'Vendedor'),
        (ROLE_SUPPORT, 'Suporte'),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='participants',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chat_participations',
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    last_read_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Participante'
        verbose_name_plural = 'Participantes'
        unique_together = ('conversation', 'user')

    def __str__(self) -> str:
        return f"Participant({self.user_id}, role={self.role}, conv={self.conversation_id})"


class Message(models.Model):
    """
    Mensagem enviada em uma conversa. Suporta soft-delete e metadados extras.
    """

    TYPE_TEXT = 'text'
    TYPE_SYSTEM = 'system'

    MESSAGE_TYPE_CHOICES = [
        (TYPE_TEXT, 'Texto'),
        (TYPE_SYSTEM, 'Sistema'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='sent_messages',
    )
    content = models.TextField()
    message_type = models.CharField(
        max_length=10,
        choices=MESSAGE_TYPE_CHOICES,
        default=TYPE_TEXT,
    )
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Mensagem'
        verbose_name_plural = 'Mensagens'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', '-created_at']),
            models.Index(fields=['sender', '-created_at']),
        ]

    def __str__(self) -> str:
        return f"Message({self.id}, sender={self.sender_id}, conv={self.conversation_id})"


class MessageStatus(models.Model):
    """
    Rastreia o estado de entrega e leitura de uma mensagem por cada destinatário.
    """

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='statuses',
    )
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='message_statuses',
    )
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Status de Mensagem'
        verbose_name_plural = 'Status de Mensagens'
        unique_together = ('message', 'recipient')

    def __str__(self) -> str:
        return f"MessageStatus(msg={self.message_id}, recipient={self.recipient_id})"
