"""
Tests for seller ME wallet balance verification (Step 4.5).

Covers:
- _check_sellers_me_balance raises InsufficientMEBalanceError when balance < shipping_cost
- _check_sellers_me_balance passes silently when balance >= shipping_cost
- Skips sellers with zero shipping cost (in-person delivery)
- Skips sellers without SellerMelhorEnvioToken (fail-open)
- Raises InsufficientMEBalanceError for 401/token errors (ShippingValidationError)
- Fail-open on timeout / other API errors (logs warning, does not block)
- get_seller_balance returns correct Decimal from API response
- get_seller_balance raises ShippingValidationError on 401
- create_order_from_cart returns 422 via view when balance insufficient
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock, PropertyMock
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from authentication.models import CustomUser
from logistics.models import Address, ShippingQuote, SellerMelhorEnvioToken
from orders.models import Cart, CartItem
from orders.services.order_creation_service import (
    OrderCreationService,
    OrderCreationError,
    InsufficientMEBalanceError,
)
from products.models import (
    MarketplaceListing, Products, Brand, Condition, Category, Series
)


def _make_user(email, **kwargs):
    return CustomUser.objects.create_user(
        email=email, password='pass123', first_name='Test', last_name='User', **kwargs
    )


class CheckSellersMEBalanceUnitTest(TestCase):
    """
    Direct unit tests for _check_sellers_me_balance.
    Mocks MelhorEnvioService.get_seller_balance and SellerMelhorEnvioToken.
    """

    def setUp(self):
        self.seller = _make_user('seller@test.com')

    def _make_items_by_seller(self, seller, listing=None):
        """Build a minimal items_by_seller dict."""
        mock_listing = listing or MagicMock()
        return {
            seller.id: [{'seller': seller, 'listing': mock_listing, 'quantity': 1}]
        }

    @patch('logistics.models.SellerMelhorEnvioToken.objects')
    @patch('logistics.services.melhor_envio_service.MelhorEnvioService.get_seller_balance')
    def test_passes_when_balance_sufficient(self, mock_balance, mock_token_mgr):
        """No exception when balance >= shipping_cost."""
        mock_token_mgr.filter.return_value.exists.return_value = True
        mock_balance.return_value = Decimal('50.00')

        items = self._make_items_by_seller(self.seller)
        shipping = {self.seller.id: Decimal('17.90')}

        # Should not raise
        OrderCreationService._check_sellers_me_balance(items, shipping)

    @patch('logistics.models.SellerMelhorEnvioToken.objects')
    @patch('logistics.services.melhor_envio_service.MelhorEnvioService.get_seller_balance')
    def test_raises_when_balance_insufficient(self, mock_balance, mock_token_mgr):
        """InsufficientMEBalanceError raised when balance < shipping_cost."""
        mock_token_mgr.filter.return_value.exists.return_value = True
        mock_balance.return_value = Decimal('5.00')

        items = self._make_items_by_seller(self.seller)
        shipping = {self.seller.id: Decimal('17.90')}

        with self.assertRaises(InsufficientMEBalanceError) as ctx:
            OrderCreationService._check_sellers_me_balance(items, shipping)

        err = ctx.exception
        self.assertEqual(len(err.sellers_info), 1)
        info = err.sellers_info[0]
        self.assertEqual(info['seller_email'], self.seller.email)
        self.assertEqual(info['required'], Decimal('17.90'))
        self.assertEqual(info['available'], Decimal('5.00'))
        self.assertEqual(info['missing'], Decimal('12.90'))

    @patch('logistics.models.SellerMelhorEnvioToken.objects')
    @patch('logistics.services.melhor_envio_service.MelhorEnvioService.get_seller_balance')
    def test_skips_zero_shipping_cost(self, mock_balance, mock_token_mgr):
        """Sellers with zero shipping cost (in-person) are skipped entirely."""
        mock_token_mgr.filter.return_value.exists.return_value = True

        items = self._make_items_by_seller(self.seller)
        shipping = {self.seller.id: Decimal('0.00')}

        # Should not call get_seller_balance
        OrderCreationService._check_sellers_me_balance(items, shipping)
        mock_balance.assert_not_called()

    @patch('logistics.models.SellerMelhorEnvioToken.objects')
    @patch('logistics.services.melhor_envio_service.MelhorEnvioService.get_seller_balance')
    def test_skips_seller_without_token(self, mock_balance, mock_token_mgr):
        """If seller has no SellerMelhorEnvioToken, verification is skipped silently."""
        mock_token_mgr.filter.return_value.exists.return_value = False

        items = self._make_items_by_seller(self.seller)
        shipping = {self.seller.id: Decimal('17.90')}

        # Should not call get_seller_balance and should not raise
        OrderCreationService._check_sellers_me_balance(items, shipping)
        mock_balance.assert_not_called()

    @patch('logistics.models.SellerMelhorEnvioToken.objects')
    @patch('logistics.services.melhor_envio_service.MelhorEnvioService.get_seller_balance')
    def test_raises_on_shipping_validation_error_401(self, mock_balance, mock_token_mgr):
        """ShippingValidationError (401) is treated as zero balance — raises InsufficientMEBalanceError."""
        from logistics.services.melhor_envio_service import ShippingValidationError

        mock_token_mgr.filter.return_value.exists.return_value = True
        mock_balance.side_effect = ShippingValidationError(
            'Vendedor seller@test.com não possui conta do Melhor Envio conectada'
        )

        items = self._make_items_by_seller(self.seller)
        shipping = {self.seller.id: Decimal('17.90')}

        with self.assertRaises(InsufficientMEBalanceError) as ctx:
            OrderCreationService._check_sellers_me_balance(items, shipping)

        err = ctx.exception
        self.assertEqual(len(err.sellers_info), 1)
        info = err.sellers_info[0]
        self.assertEqual(info['seller_email'], self.seller.email)
        self.assertEqual(info['available'], Decimal('0.00'))
        self.assertEqual(info['missing'], Decimal('17.90'))
        self.assertIn('reason', info)

    @patch('logistics.models.SellerMelhorEnvioToken.objects')
    @patch('logistics.services.melhor_envio_service.MelhorEnvioService.get_seller_balance')
    def test_fail_open_on_generic_api_error(self, mock_balance, mock_token_mgr):
        """Timeout or 5xx errors cause verification to be skipped (fail-open), no exception."""
        mock_token_mgr.filter.return_value.exists.return_value = True
        mock_balance.side_effect = Exception('Connection timeout')

        items = self._make_items_by_seller(self.seller)
        shipping = {self.seller.id: Decimal('17.90')}

        # Should NOT raise — fail-open policy
        OrderCreationService._check_sellers_me_balance(items, shipping)

    @patch('logistics.models.SellerMelhorEnvioToken.objects')
    @patch('logistics.services.melhor_envio_service.MelhorEnvioService.get_seller_balance')
    def test_multiple_sellers_all_insufficient(self, mock_balance, mock_token_mgr):
        """All sellers with insufficient balance are reported together."""
        seller2 = _make_user('seller2@test.com')
        mock_token_mgr.filter.return_value.exists.return_value = True
        mock_balance.side_effect = [Decimal('2.00'), Decimal('1.00')]

        items = {
            self.seller.id: [{'seller': self.seller, 'listing': MagicMock(), 'quantity': 1}],
            seller2.id: [{'seller': seller2, 'listing': MagicMock(), 'quantity': 1}],
        }
        shipping = {
            self.seller.id: Decimal('10.00'),
            seller2.id: Decimal('20.00'),
        }

        with self.assertRaises(InsufficientMEBalanceError) as ctx:
            OrderCreationService._check_sellers_me_balance(items, shipping)

        self.assertEqual(len(ctx.exception.sellers_info), 2)

    @patch('logistics.models.SellerMelhorEnvioToken.objects')
    @patch('logistics.services.melhor_envio_service.MelhorEnvioService.get_seller_balance')
    def test_partial_sellers_some_pass_some_fail(self, mock_balance, mock_token_mgr):
        """Only insufficient sellers appear in sellers_info."""
        seller2 = _make_user('seller2partial@test.com')
        mock_token_mgr.filter.return_value.exists.return_value = True
        # seller1 balance = 50 (sufficient), seller2 balance = 1 (insufficient)
        mock_balance.side_effect = [Decimal('50.00'), Decimal('1.00')]

        items = {
            self.seller.id: [{'seller': self.seller, 'listing': MagicMock(), 'quantity': 1}],
            seller2.id: [{'seller': seller2, 'listing': MagicMock(), 'quantity': 1}],
        }
        shipping = {
            self.seller.id: Decimal('10.00'),
            seller2.id: Decimal('20.00'),
        }

        with self.assertRaises(InsufficientMEBalanceError) as ctx:
            OrderCreationService._check_sellers_me_balance(items, shipping)

        infos = ctx.exception.sellers_info
        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0]['seller_email'], seller2.email)

    @patch('logistics.models.SellerMelhorEnvioToken.objects')
    @patch('logistics.services.melhor_envio_service.MelhorEnvioService.get_seller_balance')
    def test_exact_balance_passes(self, mock_balance, mock_token_mgr):
        """Balance exactly equal to shipping cost should pass (not raise)."""
        mock_token_mgr.filter.return_value.exists.return_value = True
        mock_balance.return_value = Decimal('17.90')

        items = self._make_items_by_seller(self.seller)
        shipping = {self.seller.id: Decimal('17.90')}

        # Should not raise
        OrderCreationService._check_sellers_me_balance(items, shipping)


class GetSellerBalanceUnitTest(TestCase):
    """Unit tests for MelhorEnvioService.get_seller_balance."""

    def setUp(self):
        self.seller = _make_user('balanceseller@test.com')

    @patch('logistics.services.melhor_envio_service.MelhorEnvioService._get_headers')
    @patch('requests.get')
    def test_returns_decimal_from_string_balance(self, mock_get, mock_headers):
        """Response {"balance": "12.50"} returns Decimal('12.50')."""
        from logistics.services.melhor_envio_service import MelhorEnvioService

        mock_headers.return_value = {'Authorization': 'Bearer fake-token'}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'balance': '12.50'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        service = MelhorEnvioService()
        result = service.get_seller_balance(self.seller)

        self.assertEqual(result, Decimal('12.50'))
        self.assertIsInstance(result, Decimal)

    @patch('logistics.services.melhor_envio_service.MelhorEnvioService._get_headers')
    @patch('requests.get')
    def test_returns_decimal_from_numeric_balance(self, mock_get, mock_headers):
        """Response {"balance": 5} returns Decimal('5')."""
        from logistics.services.melhor_envio_service import MelhorEnvioService

        mock_headers.return_value = {'Authorization': 'Bearer fake-token'}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'balance': 5}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        service = MelhorEnvioService()
        result = service.get_seller_balance(self.seller)

        self.assertEqual(result, Decimal('5'))

    @patch('logistics.services.melhor_envio_service.MelhorEnvioService._get_headers')
    @patch('requests.get')
    def test_raises_shipping_validation_error_on_401(self, mock_get, mock_headers):
        """401 response raises ShippingValidationError."""
        from logistics.services.melhor_envio_service import MelhorEnvioService, ShippingValidationError

        mock_headers.return_value = {'Authorization': 'Bearer fake-token'}
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        service = MelhorEnvioService()
        with self.assertRaises(ShippingValidationError) as ctx:
            service.get_seller_balance(self.seller)

        self.assertIn('token OAuth expirou', str(ctx.exception))

    @patch('logistics.services.melhor_envio_service.MelhorEnvioService._get_headers')
    @patch('requests.get')
    def test_raises_exception_on_500(self, mock_get, mock_headers):
        """500 response raises generic Exception (caller handles as fail-open)."""
        import requests as req
        from logistics.services.melhor_envio_service import MelhorEnvioService

        mock_headers.return_value = {'Authorization': 'Bearer fake-token'}
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_response.json.side_effect = Exception('no json')
        http_err = req.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_err
        mock_get.return_value = mock_response

        service = MelhorEnvioService()
        with self.assertRaises(Exception) as ctx:
            service.get_seller_balance(self.seller)

        self.assertIn('500', str(ctx.exception))

    @patch('logistics.services.melhor_envio_service.MelhorEnvioService._get_headers')
    @patch('requests.get')
    def test_raises_exception_on_timeout(self, mock_get, mock_headers):
        """Timeout raises generic Exception."""
        import requests as req
        from logistics.services.melhor_envio_service import MelhorEnvioService

        mock_headers.return_value = {'Authorization': 'Bearer fake-token'}
        mock_get.side_effect = req.exceptions.Timeout()

        service = MelhorEnvioService()
        with self.assertRaises(Exception) as ctx:
            service.get_seller_balance(self.seller)

        self.assertIn('Timeout', str(ctx.exception))

    @patch('logistics.services.melhor_envio_service.MelhorEnvioService._get_headers')
    def test_raises_shipping_validation_error_when_headers_fail(self, mock_headers):
        """If _get_headers raises (no token), ShippingValidationError is raised."""
        from logistics.services.melhor_envio_service import MelhorEnvioService, ShippingValidationError

        mock_headers.side_effect = Exception('No token found for seller')

        service = MelhorEnvioService()
        with self.assertRaises(ShippingValidationError):
            service.get_seller_balance(self.seller)


class InsufficientMEBalanceErrorViewTest(TestCase):
    """
    Integration test: create_order view returns HTTP 422 with correct body
    when InsufficientMEBalanceError is raised by the service.

    We patch create_order_from_cart directly so no ShippingQuote DB record is needed.
    """

    def setUp(self):
        self.client = APIClient()

        self.buyer = _make_user('viewbuyer@test.com')
        self.seller = _make_user('viewseller@test.com')

        self.category = Category.objects.create(name='Equipment', slug='equipment')
        self.series = Series.objects.create(name='Series', slug='series')
        self.brand = Brand.objects.create(name='Brand', slug='brand')
        self.condition = Condition.objects.create(name='New', slug='new')

        self.product = Products.objects.create(
            name='Test Product',
            code='TP001',
            category=self.category,
            series=self.series,
        )

        from products.models import ShippingMethodChoices
        self.listing = MarketplaceListing.objects.create(
            seller=self.seller,
            product=self.product,
            brand=self.brand,
            condition=self.condition,
            title='Test Listing',
            description='A test listing',
            price=Decimal('100.00'),
            quantity=5,
            shipping_method=ShippingMethodChoices.MELHOR_ENVIO,
        )

        self.address = Address.objects.create(
            user=self.buyer,
            recipient_name='Buyer',
            recipient_phone='11999999999',
            zipcode='01310100',
            street='Av Paulista',
            number='1000',
            neighborhood='Bela Vista',
            city='São Paulo',
            state='SP',
            is_active=True,
        )

        self.cart, _ = Cart.objects.get_or_create(user=self.buyer)
        CartItem.objects.create(cart=self.cart, listing=self.listing, quantity=1)

        # Create ShippingQuote with all required fields so the serializer passes validation
        ShippingQuote.objects.create(
            user=self.buyer,
            seller=self.seller,
            origin_zipcode='12345000',
            origin_address={'zipcode': '12345000', 'city': 'Origem'},
            destination_zipcode='01310100',
            destination_address={'zipcode': '01310100', 'city': 'Destino'},
            weight=Decimal('5.00'),
            height=Decimal('20.00'),
            width=Decimal('30.00'),
            length=Decimal('40.00'),
            declared_value=Decimal('100.00'),
            expires_at=timezone.now() + timedelta(hours=2),
            quotes_data={
                'services': [
                    {
                        'id': 1,
                        'name': 'PAC',
                        'company': {'name': 'Correios'},
                        'price': '17.90',
                        'custom_price': '17.90',
                        'delivery_time': 5,
                    }
                ],
                'melhor_envio_listing_ids': [self.listing.id],
                'by_listing': {
                    str(self.listing.id): {
                        'services': [
                            {
                                'id': 1,
                                'name': 'PAC',
                                'company': {'name': 'Correios'},
                                'price': '17.90',
                                'custom_price': '17.90',
                                'delivery_time': 5,
                            }
                        ]
                    }
                },
            },
        )

    def test_create_order_returns_422_when_balance_insufficient(self):
        """POST /api/orders/create/ returns HTTP 422 when seller has insufficient ME balance."""
        self.client.force_authenticate(user=self.buyer)

        insufficient_error = InsufficientMEBalanceError(
            message='Saldo insuficiente',
            sellers_info=[{
                'seller_email': self.seller.email,
                'required': Decimal('17.90'),
                'available': Decimal('5.00'),
                'missing': Decimal('12.90'),
            }]
        )

        with patch.object(
            OrderCreationService,
            'create_order_from_cart',
            side_effect=insufficient_error
        ):
            response = self.client.post(
                '/api/orders/create/',
                data={
                    'shipping_address_id': self.address.id,
                    'items_delivery': [
                        {
                            'listing_id': self.listing.id,
                            'delivery_method': 'melhor_envio',
                            'service_id': 1,
                        }
                    ],
                    'payment_method': 'pix',
                    'buyer_notes': '',
                },
                format='json',
            )

        self.assertEqual(response.status_code, 422, f"Expected 422, got {response.status_code}. Body: {response.json()}")
        data = response.json()
        self.assertEqual(data['error'], 'insufficient_me_balance')
        self.assertIn('sellers', data)
        self.assertEqual(len(data['sellers']), 1)
        seller_info = data['sellers'][0]
        self.assertEqual(seller_info['seller_email'], self.seller.email)
        self.assertEqual(seller_info['required'], '17.90')
        self.assertEqual(seller_info['available'], '5.00')
        self.assertEqual(seller_info['missing'], '12.90')

    def test_create_order_422_does_not_contain_internal_reason_for_regular_insufficient(self):
        """The 422 response body has the documented structure even without 'reason' key."""
        self.client.force_authenticate(user=self.buyer)

        insufficient_error = InsufficientMEBalanceError(
            message='Saldo insuficiente',
            sellers_info=[{
                'seller_email': self.seller.email,
                'required': Decimal('10.00'),
                'available': Decimal('0.00'),
                'missing': Decimal('10.00'),
            }]
        )

        with patch.object(
            OrderCreationService,
            'create_order_from_cart',
            side_effect=insufficient_error
        ):
            response = self.client.post(
                '/api/orders/create/',
                data={
                    'shipping_address_id': self.address.id,
                    'items_delivery': [
                        {
                            'listing_id': self.listing.id,
                            'delivery_method': 'melhor_envio',
                            'service_id': 1,
                        }
                    ],
                    'payment_method': 'pix',
                },
                format='json',
            )

        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertIn('message', data)
        self.assertIn('sellers', data)
        # The 'reason' key from sellers_info should NOT leak into the API response
        self.assertNotIn('reason', data['sellers'][0])

    def test_insufficient_me_balance_error_is_subclass_of_order_creation_error(self):
        """InsufficientMEBalanceError must be a subclass of OrderCreationError."""
        err = InsufficientMEBalanceError('test', [])
        self.assertIsInstance(err, OrderCreationError)
        self.assertEqual(err.sellers_info, [])
        self.assertIn('test', str(err))
