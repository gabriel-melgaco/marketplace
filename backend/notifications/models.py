"""
Notifications App Models

Provides persistent storage for user notifications, per-user delivery
preferences, and idempotency enforcement via unique constraint on
idempotency_key.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationType(models.TextChoices):
    ORDER_CREATED = 'order_created', 'Pedido Criado'
    ORDER_STATUS_CHANGED = 'order_status_changed', 'Status do Pedido Alterado'
    PAYMENT_CONFIRMED = 'payment_confirmed', 'Pagamento Confirmado'
    PAYMENT_FAILED = 'payment_failed', 'Falha no Pagamento'
    DISPUTE_OPENED = 'dispute_opened', 'Disputa Aberta'
    SHIPMENT_CREATED = 'shipment_created', 'Envio Criado'
    SHIPMENT_STATUS_UPDATED = 'shipment_status_updated', 'Status do Envio Atualizado'
    DELIVERY_SCHEDULED = 'delivery_scheduled', 'Entrega Agendada'
    DELIVERY_CONFIRMED = 'delivery_confirmed', 'Entrega Confirmada'
    NEW_MESSAGE = 'new_message', 'Nova Mensagem'
    SELLER_VERIFIED = 'seller_verified', 'Vendedor Verificado'
    LISTING_BLOCKED = 'listing_blocked', 'Anúncio Bloqueado'
    LISTING_CREATED = 'listing_created', 'Anúncio Publicado'
    PAYOUT_SCHEDULED = 'payout_scheduled', 'Repasse Agendado'


class Notification(models.Model):
    """
    Persisted notification for a single user.

    idempotency_key prevents duplicate notifications when the same source
    event is processed more than once (e.g. Stripe webhook retry).  Callers
    should pass a stable key such as 'order_created_{order.id}'.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]
        verbose_name = 'Notificação'
        verbose_name_plural = 'Notificações'

    def __str__(self) -> str:
        return f'[{self.notification_type}] {self.title} → {self.recipient_id}'

    def mark_read(self) -> None:
        """Mark this notification as read in-place (does not save)."""
        self.is_read = True
        self.read_at = timezone.now()


class NotificationPreference(models.Model):
    """
    Per-user delivery channel toggles.

    Fields follow the pattern ``{event_type}_{channel}`` where channel is
    either ``ws`` (WebSocket / real-time) or ``email``.

    Defaults are set conservatively: almost everything is on for WS and on
    for email, except high-frequency events (new_message,
    shipment_status_updated) which default email to False to avoid inbox
    flooding.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences',
    )

    # --- order_created ---
    order_created_ws = models.BooleanField(default=True)
    order_created_email = models.BooleanField(default=True)

    # --- order_status_changed ---
    order_status_changed_ws = models.BooleanField(default=True)
    order_status_changed_email = models.BooleanField(default=True)

    # --- payment_confirmed ---
    payment_confirmed_ws = models.BooleanField(default=True)
    payment_confirmed_email = models.BooleanField(default=True)

    # --- payment_failed ---
    payment_failed_ws = models.BooleanField(default=True)
    payment_failed_email = models.BooleanField(default=True)

    # --- dispute_opened ---
    dispute_opened_ws = models.BooleanField(default=True)
    dispute_opened_email = models.BooleanField(default=True)

    # --- shipment_created ---
    shipment_created_ws = models.BooleanField(default=True)
    shipment_created_email = models.BooleanField(default=True)

    # --- shipment_status_updated (high-frequency — email off by default) ---
    shipment_status_updated_ws = models.BooleanField(default=True)
    shipment_status_updated_email = models.BooleanField(default=False)

    # --- delivery_scheduled ---
    delivery_scheduled_ws = models.BooleanField(default=True)
    delivery_scheduled_email = models.BooleanField(default=True)

    # --- delivery_confirmed ---
    delivery_confirmed_ws = models.BooleanField(default=True)
    delivery_confirmed_email = models.BooleanField(default=True)

    # --- new_message (high-frequency — email off by default) ---
    new_message_ws = models.BooleanField(default=True)
    new_message_email = models.BooleanField(default=False)

    # --- seller_verified ---
    seller_verified_ws = models.BooleanField(default=True)
    seller_verified_email = models.BooleanField(default=True)

    # --- listing_blocked ---
    listing_blocked_ws = models.BooleanField(default=True)
    listing_blocked_email = models.BooleanField(default=True)

    # --- listing_created ---
    listing_created_ws = models.BooleanField(default=True)
    listing_created_email = models.BooleanField(default=False)

    # --- payout_scheduled ---
    payout_scheduled_ws = models.BooleanField(default=True)
    payout_scheduled_email = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Preferência de Notificação'
        verbose_name_plural = 'Preferências de Notificação'

    def __str__(self) -> str:
        return f'Preferências de notificação — {self.user}'

    def ws_enabled_for(self, notification_type: str) -> bool:
        """Return whether WebSocket delivery is enabled for the given type."""
        field = f'{notification_type}_ws'
        return bool(getattr(self, field, True))

    def email_enabled_for(self, notification_type: str) -> bool:
        """Return whether email delivery is enabled for the given type."""
        field = f'{notification_type}_email'
        return bool(getattr(self, field, True))
