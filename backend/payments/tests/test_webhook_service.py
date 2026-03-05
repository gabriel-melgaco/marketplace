"""
Tests for WebhookService - New handlers

Validates:
- payment_intent.succeeded dispatches transfers after confirming payment
- charge.dispute.created creates Dispute record and attempts transfer reversals
- transfer.created confirms PaymentSplit as dispatched
- transfer.failed marks PaymentSplit as failed
- charge.dispute.updated / closed update Dispute status
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from products.models import (
    Products, Brand, Condition, MarketplaceListing, Category, Series
)
from orders.models import Order, OrderItem
from payments.models import Payment, PaymentSplit, Dispute, PaymentWebhook
from payments.webhook_service import WebhookService

User = get_user_model()


def _make_mock_event(event_type, data_object):
    """Helper to create a mock Stripe event"""
    event = MagicMock()
    event.id = f'evt_test_{event_type.replace(".", "_")}'
    event.type = event_type
    event.data = MagicMock()
    event.data.object = data_object
    return event


class TestWebhookServiceTransferHandlers(TestCase):
    """Tests for transfer.created and transfer.failed handlers"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            email='buyer_wh@test.com', password='pass'
        )
        self.seller = User.objects.create_user(
            email='seller_wh@test.com', password='pass',
            stripe_account_id='acct_seller_wh',
        )
        self.category = Category.objects.create(name='CatWH', slug='catwh')
        self.series = Series.objects.create(name='SeriesWH', slug='serieswh')
        self.product = Products.objects.create(
            name='ProdWH', slug='prodwh', category=self.category, series=self.series
        )
        self.brand = Brand.objects.create(name='BrandWH', slug='brandwh')
        self.condition = Condition.objects.create(name='NewWH', slug='newwh')
        self.listing = MarketplaceListing.objects.create(
            product=self.product, seller=self.seller,
            brand=self.brand, condition=self.condition,
            price=Decimal('100.00'), quantity=5, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('10.00'),
            total=Decimal('110.00'),
            shipping_address={'street': 'Test'},
            status='paid'
        )
        OrderItem.objects.create(
            order=self.order, listing=self.listing, seller=self.seller,
            quantity=1, unit_price=Decimal('100.00'), subtotal=Decimal('100.00'),
            shipping_cost=Decimal('10.00'),
            product_name='ProdWH', product_code='', brand_name='BrandWH',
            condition_name='NewWH', weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'), width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )
        self.payment = Payment.objects.create(
            order=self.order, user=self.buyer,
            stripe_payment_intent_id='pi_wh_001',
            stripe_charge_id='ch_wh_001',
            transfer_group='group_' + str(self.order.id),
            amount=Decimal('110.00'),
            currency='brl',
            payment_method='credit_card',
            status='succeeded',
            idempotency_key='pi_wh_001_key',
        )
        self.split = PaymentSplit.objects.create(
            payment=self.payment,
            seller=self.seller,
            gross_amount=Decimal('110.00'),
            platform_fee_amount=Decimal('11.00'),
            net_amount=Decimal('99.00'),
            stripe_transfer_id='tr_wh_001',
            transfer_status='dispatched',
        )

    def test_handle_transfer_created_updates_split(self):
        """transfer.created confirms PaymentSplit as dispatched"""
        # Set split to pending to test update
        self.split.transfer_status = 'pending'
        self.split.save()

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_tr_created_001',
            event_type='transfer.created',
            payload={'id': 'tr_wh_001'},
        )

        transfer_data = MagicMock()
        transfer_data.id = 'tr_wh_001'

        WebhookService._handle_transfer_created(
            _make_mock_event('transfer.created', transfer_data),
            webhook
        )

        self.split.refresh_from_db()
        self.assertEqual(self.split.transfer_status, 'dispatched')

    def test_handle_transfer_failed_marks_split_failed(self):
        """transfer.failed marks PaymentSplit as failed"""
        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_tr_failed_001',
            event_type='transfer.failed',
            payload={'id': 'tr_wh_001'},
        )

        transfer_data = MagicMock()
        transfer_data.id = 'tr_wh_001'

        WebhookService._handle_transfer_failed(
            _make_mock_event('transfer.failed', transfer_data),
            webhook
        )

        self.split.refresh_from_db()
        self.assertEqual(self.split.transfer_status, 'failed')
        self.assertIn('tr_wh_001', self.split.error_message)

    def test_handle_transfer_created_for_unknown_transfer_does_not_raise(self):
        """transfer.created for unknown transfer_id logs and continues"""
        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_tr_unknown_001',
            event_type='transfer.created',
            payload={'id': 'tr_unknown_xyz'},
        )

        transfer_data = MagicMock()
        transfer_data.id = 'tr_unknown_xyz'

        # Should not raise
        WebhookService._handle_transfer_created(
            _make_mock_event('transfer.created', transfer_data),
            webhook
        )


class TestWebhookServiceDisputeHandlers(TestCase):
    """Tests for charge.dispute.created/updated/closed handlers"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            email='buyer_disp@test.com', password='pass'
        )
        self.seller = User.objects.create_user(
            email='seller_disp@test.com', password='pass',
            stripe_account_id='acct_seller_disp',
        )
        self.category = Category.objects.create(name='CatD', slug='catd')
        self.series = Series.objects.create(name='SeriesD', slug='seriesd')
        self.product = Products.objects.create(
            name='ProdD', slug='prodd', category=self.category, series=self.series
        )
        self.brand = Brand.objects.create(name='BrandD', slug='brandd')
        self.condition = Condition.objects.create(name='NewD', slug='newd')
        self.listing = MarketplaceListing.objects.create(
            product=self.product, seller=self.seller,
            brand=self.brand, condition=self.condition,
            price=Decimal('200.00'), quantity=5, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('200.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('200.00'),
            shipping_address={'street': 'Test'},
            status='paid'
        )
        OrderItem.objects.create(
            order=self.order, listing=self.listing, seller=self.seller,
            quantity=1, unit_price=Decimal('200.00'), subtotal=Decimal('200.00'),
            shipping_cost=Decimal('0.00'),
            product_name='ProdD', product_code='', brand_name='BrandD',
            condition_name='NewD', weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'), width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )
        self.payment = Payment.objects.create(
            order=self.order, user=self.buyer,
            stripe_payment_intent_id='pi_disp_001',
            stripe_charge_id='ch_disp_001',
            transfer_group='group_' + str(self.order.id),
            amount=Decimal('200.00'),
            currency='brl',
            payment_method='credit_card',
            status='succeeded',
            idempotency_key='pi_disp_001_key',
        )
        self.split = PaymentSplit.objects.create(
            payment=self.payment,
            seller=self.seller,
            gross_amount=Decimal('200.00'),
            platform_fee_amount=Decimal('20.00'),
            net_amount=Decimal('180.00'),
            stripe_transfer_id='tr_disp_001',
            transfer_status='dispatched',
        )

    @patch('payments.webhook_service.stripe.Transfer.create_reversal')
    def test_dispute_created_creates_dispute_record(self, mock_reversal):
        """charge.dispute.created creates a Dispute record"""
        mock_reversal.return_value = MagicMock(id='rev_001')

        dispute_data = MagicMock()
        dispute_data.id = 'dp_test_001'
        dispute_data.charge = 'ch_disp_001'
        dispute_data.amount = 20000  # 200.00 BRL in cents
        dispute_data.currency = 'brl'
        dispute_data.reason = 'fraudulent'
        dispute_data.status = 'needs_response'
        # Make dict() work on the mock
        dispute_data.__iter__ = MagicMock(return_value=iter([]))
        # Use a real dict for stripe_payload
        dispute_data_dict = {
            'id': 'dp_test_001', 'charge': 'ch_disp_001',
            'amount': 20000, 'currency': 'brl',
            'reason': 'fraudulent', 'status': 'needs_response',
        }

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_dp_created_001',
            event_type='charge.dispute.created',
            payload=dispute_data_dict,
        )

        with patch('payments.webhook_service.Dispute.objects.get_or_create') as mock_goc:
            dispute_instance = Dispute(
                payment=self.payment,
                stripe_dispute_id='dp_test_001',
                stripe_charge_id='ch_disp_001',
                amount=Decimal('200.00'),
                currency='BRL',
                reason='fraudulent',
                status='needs_response',
                reversal_attempted=False,
                stripe_payload=dispute_data_dict,
            )
            dispute_instance.save = MagicMock()
            mock_goc.return_value = (dispute_instance, True)

            with patch.object(
                WebhookService, '_attempt_transfer_reversals_for_dispute'
            ) as mock_reversal_attempt:
                event = _make_mock_event('charge.dispute.created', dispute_data)
                # Fix dict() call on data_object
                event.data.object = dispute_data

                WebhookService._handle_dispute_created(event, webhook)

                # Dispute.get_or_create was called
                mock_goc.assert_called_once()
                # Reversal attempted
                mock_reversal_attempt.assert_called_once()

    @patch('payments.webhook_service.stripe.Transfer.create_reversal')
    def test_dispute_created_attempts_transfer_reversal(self, mock_reversal):
        """charge.dispute.created calls _attempt_transfer_reversals_for_dispute"""
        mock_reversal.return_value = MagicMock(id='rev_001')

        # Create Dispute in DB directly
        dispute = Dispute.objects.create(
            payment=self.payment,
            stripe_dispute_id='dp_direct_001',
            stripe_charge_id='ch_disp_001',
            amount=Decimal('200.00'),
            currency='BRL',
            reason='fraudulent',
            status='needs_response',
            reversal_attempted=False,
        )

        WebhookService._attempt_transfer_reversals_for_dispute(
            dispute=dispute,
            payment=self.payment,
        )

        # Transfer Reversal was attempted
        mock_reversal.assert_called_once()
        call_kwargs = mock_reversal.call_args[1]
        self.assertIn('amount', call_kwargs)
        # Amount should be > 0
        self.assertGreater(call_kwargs['amount'], 0)

        dispute.refresh_from_db()
        self.assertTrue(dispute.reversal_attempted)

    @patch('payments.webhook_service.stripe.Transfer.create_reversal')
    def test_dispute_updated_changes_status(self, mock_reversal):
        """charge.dispute.updated updates Dispute status"""
        dispute = Dispute.objects.create(
            payment=self.payment,
            stripe_dispute_id='dp_update_001',
            stripe_charge_id='ch_disp_001',
            amount=Decimal('200.00'),
            currency='BRL',
            reason='fraudulent',
            status='needs_response',
            reversal_attempted=True,
        )

        dispute_data = MagicMock()
        dispute_data.id = 'dp_update_001'
        dispute_data.status = 'under_review'

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_dp_updated_001',
            event_type='charge.dispute.updated',
            payload={'id': 'dp_update_001', 'status': 'under_review'},
        )

        with patch('payments.webhook_service.dict', return_value={'status': 'under_review'}):
            WebhookService._handle_dispute_updated(
                _make_mock_event('charge.dispute.updated', dispute_data),
                webhook
            )

        dispute.refresh_from_db()
        self.assertEqual(dispute.status, 'under_review')

    @patch('payments.webhook_service.stripe.Transfer.create_reversal')
    def test_dispute_closed_updates_status_to_lost(self, mock_reversal):
        """charge.dispute.closed updates Dispute status to 'lost'"""
        dispute = Dispute.objects.create(
            payment=self.payment,
            stripe_dispute_id='dp_closed_001',
            stripe_charge_id='ch_disp_001',
            amount=Decimal('200.00'),
            currency='BRL',
            reason='fraudulent',
            status='under_review',
            reversal_attempted=True,
        )

        dispute_data = MagicMock()
        dispute_data.id = 'dp_closed_001'
        dispute_data.status = 'lost'

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_dp_closed_001',
            event_type='charge.dispute.closed',
            payload={'id': 'dp_closed_001', 'status': 'lost'},
        )

        with patch('payments.webhook_service.dict', return_value={'status': 'lost'}):
            WebhookService._handle_dispute_closed(
                _make_mock_event('charge.dispute.closed', dispute_data),
                webhook
            )

        dispute.refresh_from_db()
        self.assertEqual(dispute.status, 'lost')


class TestWebhookServiceChargeRefunded(TestCase):
    """Tests for charge.refunded handler"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            email='buyer_ref@test.com', password='pass'
        )
        self.seller = User.objects.create_user(
            email='seller_ref@test.com', password='pass',
            stripe_account_id='acct_seller_ref',
        )
        self.category = Category.objects.create(name='CatR', slug='catr')
        self.series = Series.objects.create(name='SeriesR', slug='seriesr')
        self.product = Products.objects.create(
            name='ProdR', slug='prodr', category=self.category, series=self.series
        )
        self.brand = Brand.objects.create(name='BrandR', slug='brandr')
        self.condition = Condition.objects.create(name='NewR', slug='newr')
        self.listing = MarketplaceListing.objects.create(
            product=self.product, seller=self.seller,
            brand=self.brand, condition=self.condition,
            price=Decimal('100.00'), quantity=5, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'),
            total=Decimal('100.00'),
            shipping_address={'street': 'Test'},
            status='paid'
        )
        OrderItem.objects.create(
            order=self.order, listing=self.listing, seller=self.seller,
            quantity=1, unit_price=Decimal('100.00'), subtotal=Decimal('100.00'),
            shipping_cost=Decimal('0.00'),
            product_name='ProdR', product_code='', brand_name='BrandR',
            condition_name='NewR', weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'), width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )
        self.payment = Payment.objects.create(
            order=self.order, user=self.buyer,
            stripe_payment_intent_id='pi_ref_001',
            stripe_charge_id='ch_ref_001',
            transfer_group='group_ref',
            amount=Decimal('100.00'),
            currency='brl',
            payment_method='credit_card',
            status='succeeded',
            idempotency_key='pi_ref_001_key',
        )

    def test_charge_refunded_updates_payment_status(self):
        """charge.refunded marks Payment as refunded"""
        charge_data = MagicMock()
        charge_data.id = 'ch_ref_001'
        charge_data.amount_refunded = 10000  # R$100.00 in cents

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_ref_001',
            event_type='charge.refunded',
            payload={'id': 'ch_ref_001'},
        )

        WebhookService._handle_charge_refunded(
            _make_mock_event('charge.refunded', charge_data),
            webhook
        )

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded')
        self.assertIsNotNone(self.payment.refunded_at)
        self.assertEqual(self.payment.refund_amount, Decimal('100.00'))

    def test_charge_refunded_unknown_charge_does_not_raise(self):
        """charge.refunded for unknown charge_id logs warning and continues"""
        charge_data = MagicMock()
        charge_data.id = 'ch_unknown_xyz'
        charge_data.amount_refunded = 5000

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_ref_unknown_001',
            event_type='charge.refunded',
            payload={'id': 'ch_unknown_xyz'},
        )

        # Should not raise
        WebhookService._handle_charge_refunded(
            _make_mock_event('charge.refunded', charge_data),
            webhook
        )


class TestWebhookServicePaymentSucceededWithTransfers(TestCase):
    """Tests for payment_intent.succeeded dispatching transfers"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            email='buyer_succ@test.com', password='pass'
        )
        self.seller = User.objects.create_user(
            email='seller_succ@test.com', password='pass',
            stripe_account_id='acct_seller_succ',
        )
        self.category = Category.objects.create(name='CatS', slug='cats')
        self.series = Series.objects.create(name='SeriesS', slug='seriess')
        self.product = Products.objects.create(
            name='ProdS', slug='prods', category=self.category, series=self.series
        )
        self.brand = Brand.objects.create(name='BrandS', slug='brands')
        self.condition = Condition.objects.create(name='NewS', slug='news')
        self.listing = MarketplaceListing.objects.create(
            product=self.product, seller=self.seller,
            brand=self.brand, condition=self.condition,
            price=Decimal('100.00'), quantity=5, is_active=True,
            weight_kg=Decimal('1.00'), height_cm=Decimal('5.00'),
            width_cm=Decimal('5.00'), length_cm=Decimal('5.00'),
        )
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            shipping_cost=Decimal('10.00'),
            total=Decimal('110.00'),
            shipping_address={'street': 'Test'},
            status='pending_payment'
        )
        OrderItem.objects.create(
            order=self.order, listing=self.listing, seller=self.seller,
            quantity=1, unit_price=Decimal('100.00'), subtotal=Decimal('100.00'),
            shipping_cost=Decimal('10.00'),
            product_name='ProdS', product_code='', brand_name='BrandS',
            condition_name='NewS', weight_kg=Decimal('1.00'),
            height_cm=Decimal('5.00'), width_cm=Decimal('5.00'),
            length_cm=Decimal('5.00'),
        )
        self.payment = Payment.objects.create(
            order=self.order, user=self.buyer,
            stripe_payment_intent_id='pi_succ_001',
            transfer_group='group_' + str(self.order.id),
            amount=Decimal('110.00'),
            currency='brl',
            payment_method='credit_card',
            status='pending',
            idempotency_key='pi_succ_001_key',
        )

    @patch('payments.webhook_service.stripe.Transfer.create')
    @patch('payments.webhook_service.stripe.PaymentIntent.retrieve')
    @patch('logistics.services.shipment_creation_service.ShipmentCreationService.checkout_shipments_for_order')
    def test_payment_succeeded_dispatches_transfers(
        self, mock_me_checkout, mock_pi_retrieve, mock_transfer_create
    ):
        """payment_intent.succeeded calls TransferDispatchService after confirming payment"""
        charge_id = 'ch_succ_001'

        # Mock expanded PaymentIntent
        mock_pi = MagicMock()
        mock_pi.id = 'pi_succ_001'
        mock_pi.amount = 11000  # 110.00 in cents
        mock_pi.status = 'succeeded'
        mock_pi.latest_charge = charge_id  # As string (not expanded object)
        mock_pi.charges = None
        mock_pi_retrieve.return_value = mock_pi

        # Mock Transfer creation
        mock_tr = MagicMock()
        mock_tr.id = 'tr_succ_001'
        mock_transfer_create.return_value = mock_tr

        # Mock ME checkout (not critical for this test)
        mock_me_checkout.return_value = None

        webhook = PaymentWebhook.objects.create(
            stripe_event_id='evt_pi_succ_001',
            event_type='payment_intent.succeeded',
            payload={'id': 'pi_succ_001', 'amount': 11000},
        )

        event_data = MagicMock()
        event_data.id = 'pi_succ_001'
        event_data.amount = 11000
        event_data.status = 'succeeded'
        event_data.latest_charge = charge_id
        event_data.charges = None

        WebhookService._handle_payment_succeeded(
            _make_mock_event('payment_intent.succeeded', event_data),
            webhook
        )

        # Payment status updated
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'succeeded')
        self.assertEqual(self.payment.stripe_charge_id, charge_id)

        # Transfer was dispatched
        mock_transfer_create.assert_called_once()
        call_kwargs = mock_transfer_create.call_args[1]
        self.assertEqual(call_kwargs.get('source_transaction'), charge_id)

        # PaymentSplit created
        split = PaymentSplit.objects.filter(
            payment=self.payment, seller=self.seller
        ).first()
        self.assertIsNotNone(split)
        self.assertEqual(split.transfer_status, 'dispatched')
