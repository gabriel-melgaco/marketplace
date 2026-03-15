"""
Webhook Service
Handles Stripe webhook events with idempotency and validation.

Supported events:
- payment_intent.succeeded        → confirm payment, dispatch transfers to sellers
- payment_intent.payment_failed   → mark payment/order as failed
- payment_intent.canceled         → mark payment/order as cancelled
- transfer.created                → confirm PaymentSplit dispatched status
- transfer.failed                 → mark PaymentSplit as failed
- charge.dispute.created          → create Dispute record, attempt transfer reversals
- charge.dispute.updated          → update Dispute status
- charge.dispute.closed           → final status update on Dispute

Design principles:
- All handlers are idempotent: re-processing the same event is safe
- PaymentIntent is retrieved with expand=['latest_charge'] to get charge_id
- Transfers are dispatched AFTER order status is updated to 'paid'
- Dispute handlers create Dispute records for audit/manual review
"""

import stripe
import logging
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from decimal import Decimal

from .models import Payment, PaymentWebhook, PaymentSplit, Dispute

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


class PaymentAmountMismatchError(Exception):
    """Raised when payment amount doesn't match expected amount"""
    pass


class WebhookService:
    """Service for processing Stripe webhooks with idempotency"""

    @staticmethod
    def verify_webhook_signature(payload, sig_header):
        """
        Verify Stripe webhook signature.

        Args:
            payload: Raw request body (bytes)
            sig_header: Stripe-Signature header value

        Returns:
            stripe.Event object

        Raises:
            ValueError: If secret not configured
            stripe.error.SignatureVerificationError: If verification fails
        """
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET

        if not webhook_secret:
            logger.error("STRIPE_WEBHOOK_SECRET not configured")
            raise ValueError("Webhook secret not configured")

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )

            logger.debug(
                "Webhook signature verified",
                extra={
                    'event_id': event.id,
                    'event_type': event.type,
                }
            )

            return event

        except stripe.error.SignatureVerificationError as e:
            logger.error(
                f"Webhook signature verification failed: {str(e)}",
                extra={'signature_header': sig_header[:50]},
                exc_info=True
            )
            raise

    @staticmethod
    def validate_payment_amount(payment_intent, payment):
        """
        Validate that payment intent amount matches payment record.

        Args:
            payment_intent: Stripe PaymentIntent object
            payment: Payment model instance

        Raises:
            PaymentAmountMismatchError: If amounts don't match
        """
        expected_amount_cents = int(float(payment.amount) * 100)
        actual_amount_cents = payment_intent.amount

        if expected_amount_cents != actual_amount_cents:
            error_msg = (
                f"Payment amount mismatch for payment {payment.id}. "
                f"Expected: {expected_amount_cents} cents, "
                f"Got: {actual_amount_cents} cents"
            )

            logger.error(
                error_msg,
                extra={
                    'payment_id': payment.id,
                    'order_id': str(payment.order.id),
                    'expected_amount': expected_amount_cents,
                    'actual_amount': actual_amount_cents,
                    'payment_intent_id': payment_intent.id,
                }
            )

            raise PaymentAmountMismatchError(error_msg)

        logger.debug(
            "Payment amount validated",
            extra={
                'payment_id': payment.id,
                'payment_intent_id': payment_intent.id,
                'amount_cents': expected_amount_cents,
            }
        )

    @staticmethod
    def handle_webhook(payload, sig_header):
        """
        Process Stripe webhook with idempotency.

        Args:
            payload: Raw request body (bytes)
            sig_header: Stripe-Signature header value

        Returns:
            bool: True if processed successfully

        Raises:
            Exception: If processing fails
        """
        # Verify webhook signature
        event = WebhookService.verify_webhook_signature(payload, sig_header)

        logger.info(
            f"Processing webhook event: {event.type}",
            extra={
                'event_id': event.id,
                'event_type': event.type,
            }
        )

        # Ignorar eventos V2 (ex: v2.core.event_destination.ping) que não têm data.object
        if event.type.startswith('v2.'):
            logger.info(f"Ignoring V2 event on V1 endpoint: {event.type}")
            return True

        # Check if event already processed (idempotency)
        webhook, created = PaymentWebhook.objects.get_or_create(
            stripe_event_id=event.id,
            defaults={
                'event_type': event.type,
                'payload': dict(event.data.object),
            }
        )

        if not created and webhook.processed:
            logger.info(
                "Webhook event already processed",
                extra={
                    'event_id': event.id,
                    'processed_at': webhook.processed_at.isoformat(),
                }
            )
            return True

        # Process event within atomic transaction
        try:
            with transaction.atomic():
                if event.type == 'payment_intent.succeeded':
                    WebhookService._handle_payment_succeeded(event, webhook)

                elif event.type == 'payment_intent.payment_failed':
                    WebhookService._handle_payment_failed(event, webhook)

                elif event.type == 'payment_intent.canceled':
                    WebhookService._handle_payment_canceled(event, webhook)

                elif event.type == 'transfer.created':
                    WebhookService._handle_transfer_created(event, webhook)

                elif event.type == 'transfer.failed':
                    WebhookService._handle_transfer_failed(event, webhook)

                elif event.type == 'charge.dispute.created':
                    WebhookService._handle_dispute_created(event, webhook)

                elif event.type == 'charge.dispute.updated':
                    WebhookService._handle_dispute_updated(event, webhook)

                elif event.type == 'charge.dispute.closed':
                    WebhookService._handle_dispute_closed(event, webhook)

                elif event.type == 'charge.refunded':
                    WebhookService._handle_charge_refunded(event, webhook)

                else:
                    logger.warning(
                        f"Unhandled webhook event type: {event.type}",
                        extra={'event_id': event.id}
                    )
                    # Mark as processed even if unhandled
                    webhook.processed = True
                    webhook.processed_at = timezone.now()
                    webhook.save(update_fields=['processed', 'processed_at'])
                    return True

                # Mark webhook as processed
                webhook.processed = True
                webhook.processed_at = timezone.now()
                webhook.save(update_fields=['processed', 'processed_at'])

            logger.info(
                "Webhook event processed successfully",
                extra={
                    'event_id': event.id,
                    'event_type': event.type,
                }
            )

            return True

        except Payment.DoesNotExist:
            error_msg = f"Payment not found for payment_intent_id in event {event.id}"
            logger.warning(error_msg, extra={'event_id': event.id})

            webhook.error_message = error_msg
            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.save(update_fields=['error_message', 'processed', 'processed_at'])
            return True

        except Exception as e:
            error_msg = f"Error processing webhook {event.id}: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    'event_id': event.id,
                    'event_type': event.type,
                },
                exc_info=True
            )

            webhook.error_message = str(e)
            webhook.save(update_fields=['error_message'])
            raise

    # =========================================================================
    # Private handlers
    # =========================================================================

    @staticmethod
    def _handle_payment_succeeded(event, webhook):
        """
        Handle payment_intent.succeeded event.

        Flow:
        1. Retrieve PaymentIntent with expand=['latest_charge'] to get charge_id
        2. Validate amount
        3. Update Payment record (status, charge_id, receipt_url)
        4. Update Order status via PaymentCallbackService
        5. Dispatch Transfers to all sellers via TransferDispatchService
        """
        payment_intent_data = event.data.object

        logger.info(
            "Handling payment_intent.succeeded",
            extra={
                'payment_intent_id': payment_intent_data.id,
                'amount': payment_intent_data.amount,
            }
        )

        # Re-retrieve PaymentIntent with latest_charge expanded
        # The event object does not automatically expand nested objects
        payment_intent = stripe.PaymentIntent.retrieve(
            payment_intent_data.id,
            expand=['latest_charge'],
        )

        # Get charge_id from latest_charge (required for Transfers)
        charge_id = None
        if payment_intent.latest_charge:
            if isinstance(payment_intent.latest_charge, str):
                charge_id = payment_intent.latest_charge
            else:
                charge_id = payment_intent.latest_charge.id

        logger.info(
            "Retrieved PaymentIntent with latest_charge",
            extra={
                'payment_intent_id': payment_intent.id,
                'charge_id': charge_id,
            }
        )

        # Get payment record
        payment = Payment.objects.select_for_update().get(
            stripe_payment_intent_id=payment_intent.id
        )

        # Validate amount
        WebhookService.validate_payment_amount(payment_intent, payment)

        # Update payment status and charge info
        payment.status = 'succeeded'
        payment.paid_at = timezone.now()

        if charge_id:
            payment.stripe_charge_id = charge_id

        # Extract receipt_url from charge if expanded
        if (
            payment_intent.latest_charge
            and not isinstance(payment_intent.latest_charge, str)
        ):
            receipt_url = getattr(payment_intent.latest_charge, 'receipt_url', '')
            if receipt_url:
                payment.receipt_url = receipt_url

        # Fallback: check charges list (older API format)
        if not payment.stripe_charge_id:
            charges = getattr(payment_intent, 'charges', None)
            if charges and charges.data:
                charge = charges.data[0]
                payment.stripe_charge_id = charge.id
                if not payment.receipt_url:
                    payment.receipt_url = getattr(charge, 'receipt_url', '')

        # Store metadata
        payment.metadata['webhook_processed_at'] = timezone.now().isoformat()
        payment.metadata['payment_intent_status'] = payment_intent.status
        if charge_id:
            payment.metadata['charge_id'] = charge_id

        payment.save()

        # Link webhook to payment
        webhook.payment = payment
        webhook.save(update_fields=['payment'])

        # Update order status using callback service (decoupled)
        order = payment.order
        try:
            from orders.services import PaymentCallbackService
            PaymentCallbackService.on_payment_succeeded(
                order=order,
                payment_intent_id=payment_intent.id,
                metadata={
                    'payment_id': payment.id,
                    'webhook_processed_at': timezone.now().isoformat(),
                }
            )
        except Exception as e:
            logger.error(
                f"Failed to update order status via callback: {str(e)}",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                },
                exc_info=True
            )
            raise

        # Dispatch Transfers to sellers
        # This must happen AFTER order is marked as PAID
        if charge_id:
            try:
                from .services.transfer_dispatch_service import TransferDispatchService
                splits = TransferDispatchService.dispatch_transfers_for_order(
                    order=order,
                    payment=payment,
                    charge_id=charge_id,
                )

                dispatched = sum(1 for s in splits if s.transfer_status == 'dispatched')
                failed = sum(1 for s in splits if s.transfer_status == 'failed')

                logger.info(
                    "Transfers dispatched after payment success",
                    extra={
                        'order_id': str(order.id),
                        'payment_id': payment.id,
                        'splits_total': len(splits),
                        'splits_dispatched': dispatched,
                        'splits_failed': failed,
                    }
                )
            except Exception as e:
                # Transfer dispatch failure MUST NOT roll back payment success
                # Log and continue — manual reconciliation will be needed for failed splits
                logger.error(
                    f"Transfer dispatch failed for payment {payment.id}: {str(e)}",
                    extra={
                        'payment_id': payment.id,
                        'order_id': str(order.id),
                        'charge_id': charge_id,
                    },
                    exc_info=True
                )
        else:
            logger.error(
                "No charge_id available — cannot dispatch transfers. "
                "Manual intervention required.",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                    'payment_intent_id': payment_intent.id,
                }
            )

        # Notify buyer and sellers that payment was confirmed.
        try:
            from notifications.services import NotificationService
            from notifications.models import NotificationType

            # Notify buyer
            NotificationService.notify(
                recipient=order.buyer,
                event_type=NotificationType.PAYMENT_CONFIRMED,
                title=f'Pagamento confirmado — Pedido #{order.order_number}',
                body=(
                    f'Seu pagamento de R$ {payment.amount:.2f} foi confirmado. '
                    f'Seu pedido #{order.order_number} está sendo preparado.'
                ),
                metadata={
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'payment_id': payment.id,
                    'amount': str(payment.amount),
                },
                idempotency_key=f'payment_confirmed_buyer_{payment.id}',
            )

            # Notify each seller that their sale payment was confirmed
            seen_sellers = set()
            for item in order.items.select_related('seller').all():
                seller = item.seller
                if seller.id in seen_sellers:
                    continue
                seen_sellers.add(seller.id)
                seller_subtotal = sum(
                    i.subtotal
                    for i in order.items.filter(seller=seller)
                )
                NotificationService.notify(
                    recipient=seller,
                    event_type=NotificationType.PAYMENT_CONFIRMED,
                    title=f'Pagamento recebido — Pedido #{order.order_number}',
                    body=(
                        f'O pagamento do pedido #{order.order_number} foi confirmado. '
                        f'Valor dos seus itens: R$ {seller_subtotal:.2f}. '
                        f'Prepare o pedido para envio.'
                    ),
                    metadata={
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'payment_id': payment.id,
                        'seller_subtotal': str(seller_subtotal),
                    },
                    idempotency_key=f'payment_confirmed_seller_{payment.id}_{seller.id}',
                )
        except Exception as _notify_exc:
            logger.warning(
                'Falha ao enfileirar notificação payment_confirmed para pedido %s: %s',
                order.order_number,
                _notify_exc,
            )

        logger.info(
            "Payment succeeded handler completed",
            extra={
                'payment_id': payment.id,
                'order_id': str(order.id),
                'order_number': order.order_number,
                'charge_id': charge_id,
            }
        )

    @staticmethod
    def _handle_payment_failed(event, webhook):
        """Handle payment_intent.payment_failed event"""
        payment_intent = event.data.object

        logger.info(
            "Handling payment_intent.payment_failed",
            extra={'payment_intent_id': payment_intent.id}
        )

        # Get payment record
        payment = Payment.objects.select_for_update().get(
            stripe_payment_intent_id=payment_intent.id
        )

        # Update payment status
        payment.status = 'failed'

        # Extract failure message
        failure_message = ''
        if payment_intent.last_payment_error:
            failure_message = payment_intent.last_payment_error.message
            payment.failure_message = failure_message

        # Store metadata
        payment.metadata['webhook_processed_at'] = timezone.now().isoformat()
        payment.metadata['payment_intent_status'] = payment_intent.status
        if payment_intent.last_payment_error:
            payment.metadata['error_code'] = payment_intent.last_payment_error.code

        payment.save()

        # Link webhook to payment
        webhook.payment = payment
        webhook.save(update_fields=['payment'])

        # Update order status via callback service
        order = payment.order
        try:
            from orders.services import PaymentCallbackService
            PaymentCallbackService.on_payment_failed(
                order=order,
                payment_intent_id=payment_intent.id,
                failure_message=failure_message
            )
        except Exception as e:
            logger.error(
                f"Failed to update order status via callback: {str(e)}",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                },
                exc_info=True
            )
            raise

        # Notify buyer that payment failed.
        try:
            from notifications.services import NotificationService
            from notifications.models import NotificationType
            NotificationService.notify(
                recipient=order.buyer,
                event_type=NotificationType.PAYMENT_FAILED,
                title=f'Falha no pagamento — Pedido #{order.order_number}',
                body=(
                    f'Infelizmente o pagamento do pedido #{order.order_number} não foi processado. '
                    f'Motivo: {failure_message or "Verifique os dados do cartão e tente novamente."}'
                ),
                metadata={
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'payment_id': payment.id,
                    'failure_message': failure_message,
                },
                idempotency_key=f'payment_failed_{payment.id}',
            )
        except Exception as _notify_exc:
            logger.warning(
                'Falha ao enfileirar notificação payment_failed para pedido %s: %s',
                order.order_number,
                _notify_exc,
            )

        logger.warning(
            "Payment failed handler completed",
            extra={
                'payment_id': payment.id,
                'order_id': str(payment.order.id),
                'failure_reason': payment.failure_message,
            }
        )

    @staticmethod
    def _handle_payment_canceled(event, webhook):
        """Handle payment_intent.canceled event"""
        payment_intent = event.data.object

        logger.info(
            "Handling payment_intent.canceled",
            extra={'payment_intent_id': payment_intent.id}
        )

        # Get payment record
        payment = Payment.objects.select_for_update().get(
            stripe_payment_intent_id=payment_intent.id
        )

        # Update payment status
        payment.status = 'cancelled'

        # Store metadata
        cancellation_reason = payment_intent.cancellation_reason or 'Payment canceled'
        payment.metadata['webhook_processed_at'] = timezone.now().isoformat()
        payment.metadata['payment_intent_status'] = payment_intent.status
        payment.metadata['cancellation_reason'] = cancellation_reason

        payment.save()

        # Link webhook to payment
        webhook.payment = payment
        webhook.save(update_fields=['payment'])

        # Update order status via callback service
        order = payment.order
        try:
            from orders.services import PaymentCallbackService
            PaymentCallbackService.on_payment_canceled(
                order=order,
                payment_intent_id=payment_intent.id,
                cancellation_reason=cancellation_reason
            )
        except Exception as e:
            logger.error(
                f"Failed to update order status via callback: {str(e)}",
                extra={
                    'payment_id': payment.id,
                    'order_id': str(order.id),
                },
                exc_info=True
            )
            raise

        logger.info(
            "Payment cancelled handler completed",
            extra={
                'payment_id': payment.id,
                'order_id': str(order.id),
                'order_number': order.order_number,
            }
        )

    @staticmethod
    def _handle_transfer_created(event, webhook):
        """
        Handle transfer.created event.
        Confirms that the Transfer was successfully created for a seller.
        Updates the PaymentSplit record to 'dispatched' if not already set.
        """
        transfer = event.data.object
        transfer_id = transfer.id

        logger.info(
            "Handling transfer.created",
            extra={'transfer_id': transfer_id}
        )

        # Find the PaymentSplit with this transfer_id
        try:
            split = PaymentSplit.objects.select_for_update().get(
                stripe_transfer_id=transfer_id
            )
            if split.transfer_status != 'dispatched':
                split.transfer_status = 'dispatched'
                split.save(update_fields=['transfer_status', 'updated_at'])

            webhook.payment = split.payment
            webhook.save(update_fields=['payment'])

            logger.info(
                "PaymentSplit confirmed dispatched via transfer.created",
                extra={
                    'split_id': split.id,
                    'transfer_id': transfer_id,
                    'seller_id': split.seller_id,
                }
            )
        except PaymentSplit.DoesNotExist:
            # Transfer might be from another context (e.g., manual) — log and ignore
            logger.warning(
                "transfer.created for unknown PaymentSplit",
                extra={'transfer_id': transfer_id}
            )

    @staticmethod
    def _handle_transfer_failed(event, webhook):
        """
        Handle transfer.failed event.
        Marks the PaymentSplit as failed for manual reconciliation.
        """
        transfer = event.data.object
        transfer_id = transfer.id

        logger.error(
            "Handling transfer.failed",
            extra={'transfer_id': transfer_id}
        )

        try:
            split = PaymentSplit.objects.select_for_update().get(
                stripe_transfer_id=transfer_id
            )
            split.transfer_status = 'failed'
            split.error_message = (
                f"Transfer failed. Stripe transfer_id={transfer_id}. "
                f"Manual reconciliation required."
            )
            split.save(update_fields=['transfer_status', 'error_message', 'updated_at'])

            webhook.payment = split.payment
            webhook.save(update_fields=['payment'])

            logger.error(
                "PaymentSplit marked as failed via transfer.failed",
                extra={
                    'split_id': split.id,
                    'transfer_id': transfer_id,
                    'seller_id': split.seller_id,
                    'net_amount': str(split.net_amount),
                }
            )
        except PaymentSplit.DoesNotExist:
            logger.warning(
                "transfer.failed for unknown PaymentSplit",
                extra={'transfer_id': transfer_id}
            )

    @staticmethod
    def _handle_dispute_created(event, webhook):
        """
        Handle charge.dispute.created event.

        Creates a Dispute record for audit/tracking.
        Attempts to create Transfer Reversals for the disputed amount
        to recover funds from sellers proportionally.
        """
        dispute_data = event.data.object
        dispute_id = dispute_data.id
        charge_id = dispute_data.charge

        logger.warning(
            "Handling charge.dispute.created (chargeback)",
            extra={
                'dispute_id': dispute_id,
                'charge_id': charge_id,
                'amount': dispute_data.amount,
                'reason': dispute_data.reason,
                'status': dispute_data.status,
            }
        )

        # Find Payment by charge_id
        try:
            payment = Payment.objects.select_for_update().get(
                stripe_charge_id=charge_id
            )
        except Payment.DoesNotExist:
            logger.error(
                "Dispute received for unknown charge_id",
                extra={'charge_id': charge_id, 'dispute_id': dispute_id}
            )
            return

        # Create Dispute record (idempotent)
        dispute, created = Dispute.objects.get_or_create(
            stripe_dispute_id=dispute_id,
            defaults={
                'payment': payment,
                'stripe_charge_id': charge_id,
                'amount': Decimal(dispute_data.amount) / 100,
                'currency': dispute_data.currency.upper(),
                'reason': dispute_data.reason,
                'status': dispute_data.status,
                'stripe_payload': dict(dispute_data),
            }
        )

        if not created:
            # Update status in case of duplicate event
            dispute.status = dispute_data.status
            dispute.save(update_fields=['status', 'updated_at'])

        webhook.payment = payment
        webhook.save(update_fields=['payment'])

        # Attempt Transfer Reversals to recover funds from sellers
        if not dispute.reversal_attempted:
            WebhookService._attempt_transfer_reversals_for_dispute(dispute, payment)

        # Notify buyer about dispute opening (only on creation).
        if created:
            try:
                from notifications.services import NotificationService
                from notifications.models import NotificationType
                order = payment.order
                NotificationService.notify(
                    recipient=order.buyer,
                    event_type=NotificationType.DISPUTE_OPENED,
                    title=f'Disputa aberta — Pedido #{order.order_number}',
                    body=(
                        f'Uma disputa foi aberta para o pedido #{order.order_number}. '
                        f'Nossa equipe entrará em contato em breve.'
                    ),
                    metadata={
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'dispute_id': dispute_id,
                        'charge_id': charge_id,
                        'reason': dispute_data.reason,
                    },
                    idempotency_key=f'dispute_opened_{dispute_id}',
                )
            except Exception as _notify_exc:
                logger.warning(
                    'Falha ao enfileirar notificação dispute_opened para disputa %s: %s',
                    dispute_id,
                    _notify_exc,
                )

        logger.warning(
            "Dispute record created/updated",
            extra={
                'dispute_id': dispute_id,
                'payment_id': payment.id,
                'dispute_status': dispute_data.status,
                'reversal_attempted': dispute.reversal_attempted,
            }
        )

    @staticmethod
    def _handle_dispute_updated(event, webhook):
        """
        Handle charge.dispute.updated event.
        Updates the Dispute status.
        """
        dispute_data = event.data.object
        dispute_id = dispute_data.id

        logger.info(
            "Handling charge.dispute.updated",
            extra={
                'dispute_id': dispute_id,
                'status': dispute_data.status,
            }
        )

        try:
            dispute = Dispute.objects.select_for_update().get(
                stripe_dispute_id=dispute_id
            )
            dispute.status = dispute_data.status
            dispute.stripe_payload = dict(dispute_data)
            dispute.save(update_fields=['status', 'stripe_payload', 'updated_at'])

            webhook.payment = dispute.payment
            webhook.save(update_fields=['payment'])

            logger.info(
                "Dispute status updated",
                extra={
                    'dispute_id': dispute_id,
                    'new_status': dispute_data.status,
                }
            )
        except Dispute.DoesNotExist:
            logger.warning(
                "dispute.updated for unknown dispute",
                extra={'dispute_id': dispute_id}
            )

    @staticmethod
    def _handle_dispute_closed(event, webhook):
        """
        Handle charge.dispute.closed event.
        Final status update. If 'lost', logs for financial reconciliation.
        """
        dispute_data = event.data.object
        dispute_id = dispute_data.id

        logger.info(
            "Handling charge.dispute.closed",
            extra={
                'dispute_id': dispute_id,
                'status': dispute_data.status,
            }
        )

        try:
            dispute = Dispute.objects.select_for_update().get(
                stripe_dispute_id=dispute_id
            )
            dispute.status = dispute_data.status
            dispute.stripe_payload = dict(dispute_data)
            dispute.save(update_fields=['status', 'stripe_payload', 'updated_at'])

            webhook.payment = dispute.payment
            webhook.save(update_fields=['payment'])

            if dispute_data.status == 'lost':
                logger.error(
                    "Dispute LOST — platform absorbed chargeback loss",
                    extra={
                        'dispute_id': dispute_id,
                        'payment_id': dispute.payment.id,
                        'amount': str(dispute.amount),
                        'reason': dispute.reason,
                    }
                )
            elif dispute_data.status == 'won':
                logger.info(
                    "Dispute WON — funds returned to platform",
                    extra={
                        'dispute_id': dispute_id,
                        'payment_id': dispute.payment.id,
                    }
                )

        except Dispute.DoesNotExist:
            logger.warning(
                "dispute.closed for unknown dispute",
                extra={'dispute_id': dispute_id}
            )

    @staticmethod
    def _handle_charge_refunded(event, webhook):
        """
        Handle charge.refunded event.
        Updates Payment status to 'refunded' and records refund metadata.
        """
        charge = event.data.object
        charge_id = charge.id

        logger.info(
            "Handling charge.refunded",
            extra={'charge_id': charge_id}
        )

        try:
            payment = Payment.objects.select_for_update().get(
                stripe_charge_id=charge_id
            )
        except Payment.DoesNotExist:
            logger.warning(
                "charge.refunded for unknown charge_id",
                extra={'charge_id': charge_id}
            )
            return

        payment.status = 'refunded'
        payment.refunded_at = timezone.now()

        # Extract refund amount from charge
        amount_refunded = getattr(charge, 'amount_refunded', None)
        if amount_refunded:
            payment.refund_amount = Decimal(amount_refunded) / 100

        payment.metadata['webhook_processed_at'] = timezone.now().isoformat()
        payment.metadata['charge_refunded_at'] = timezone.now().isoformat()
        payment.save()

        webhook.payment = payment
        webhook.save(update_fields=['payment'])

        logger.info(
            "Payment marked as refunded via charge.refunded",
            extra={
                'payment_id': payment.id,
                'charge_id': charge_id,
                'refund_amount': str(payment.refund_amount),
            }
        )

    @staticmethod
    def _attempt_transfer_reversals_for_dispute(dispute, payment):
        """
        Attempt to create Transfer Reversals for all dispatched splits
        proportional to the dispute amount.

        Called when a new dispute is created. The platform attempts to recover
        funds from sellers by reversing the transfers.

        Note: Transfer reversals reduce the seller's balance. The platform
        absorbs the dispute fee regardless.
        """
        dispatched_splits = PaymentSplit.objects.filter(
            payment=payment,
            transfer_status='dispatched',
        ).exclude(stripe_transfer_id='')

        if not dispatched_splits.exists():
            logger.warning(
                "No dispatched splits found to reverse for dispute",
                extra={
                    'dispute_id': dispute.stripe_dispute_id,
                    'payment_id': payment.id,
                }
            )
            dispute.reversal_attempted = True
            dispute.save(update_fields=['reversal_attempted', 'updated_at'])
            return

        dispute_amount_decimal = dispute.amount
        total_net = sum(s.net_amount for s in dispatched_splits)

        total_reversed = Decimal('0.00')

        for split in dispatched_splits:
            if total_net == 0:
                proportion = Decimal('0')
            else:
                proportion = split.net_amount / total_net

            reversal_amount_decimal = (dispute_amount_decimal * proportion).quantize(
                Decimal('0.01')
            )
            reversal_amount_cents = int(reversal_amount_decimal * 100)

            if reversal_amount_cents <= 0:
                continue

            idempotency_key = (
                f"rev_{split.stripe_transfer_id}_{dispute.stripe_dispute_id}"
            )

            logger.warning(
                "Creating Transfer Reversal for dispute",
                extra={
                    'dispute_id': dispute.stripe_dispute_id,
                    'transfer_id': split.stripe_transfer_id,
                    'reversal_amount_cents': reversal_amount_cents,
                    'seller_id': split.seller_id,
                    'idempotency_key': idempotency_key,
                }
            )

            try:
                stripe.Transfer.create_reversal(
                    split.stripe_transfer_id,
                    amount=reversal_amount_cents,
                    description=(
                        f"Reversal for dispute {dispute.stripe_dispute_id} "
                        f"on charge {dispute.stripe_charge_id}"
                    ),
                    metadata={
                        'dispute_id': dispute.stripe_dispute_id,
                        'payment_id': str(payment.id),
                        'split_id': str(split.id),
                        'seller_id': str(split.seller_id),
                    },
                    idempotency_key=idempotency_key,
                )

                total_reversed += reversal_amount_decimal

                logger.warning(
                    "Transfer Reversal created for dispute",
                    extra={
                        'dispute_id': dispute.stripe_dispute_id,
                        'transfer_id': split.stripe_transfer_id,
                        'reversed_cents': reversal_amount_cents,
                    }
                )

            except stripe.error.StripeError as e:
                logger.error(
                    f"Failed to create Transfer Reversal: {str(e)}",
                    extra={
                        'dispute_id': dispute.stripe_dispute_id,
                        'transfer_id': split.stripe_transfer_id,
                        'error_type': type(e).__name__,
                    },
                    exc_info=True
                )

        dispute.reversal_attempted = True
        dispute.reversal_amount = total_reversed
        dispute.save(update_fields=['reversal_attempted', 'reversal_amount', 'updated_at'])

        logger.warning(
            "Transfer Reversals attempt completed for dispute",
            extra={
                'dispute_id': dispute.stripe_dispute_id,
                'payment_id': payment.id,
                'total_reversed': str(total_reversed),
            }
        )
