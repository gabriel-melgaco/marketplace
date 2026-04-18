"""
Integration tests for per-seller Melhor Envio OAuth 2.0 endpoints.

Covers:
  - GET  /api/logistics/me/connect/    (seller_me_connect)
  - GET  /api/logistics/me/callback/   (seller_me_callback)
  - GET  /api/logistics/me/status/     (seller_me_status)
  - DELETE /api/logistics/me/disconnect/ (seller_me_disconnect)
  - POST /api/products/listings/create/ — requires active ME token

Run only this file:
    ./venv/bin/python -m pytest logistics/tests/test_seller_me_oauth.py -v
"""

from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import CustomUser
from logistics.models import SellerMelhorEnvioToken, Address
from logistics.services.melhor_envio_oauth_service import MelhorEnvioOAuthService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_seller(email='seller@test.com', password='pass1234', cpf='111.444.777-35'):
    """Create a seller user. Each test runs in its own transaction, so CPF reuse is safe."""
    return CustomUser.objects.create_user(
        email=email,
        password=password,
        full_name='Test Seller',
        cpf=cpf,
    )


def _make_me_address(seller):
    """Create an active shipping Address tied to the seller (simulates ME sync)."""
    return Address.objects.create(
        user=seller,
        recipient_name='Test Seller',
        recipient_phone='11999999999',
        zipcode='01310100',
        street='Avenida Paulista',
        number='1000',
        neighborhood='Bela Vista',
        city='São Paulo',
        state='SP',
        is_shipping_address=True,
        is_active=True,
    )


def _make_token(seller, environment='sandbox', is_active=True, me_email='seller@me.com',
                with_address=True):
    """
    Create a SellerMelhorEnvioToken for testing.

    If with_address=True (default), also creates and attaches a synced me_address
    so that the listing-creation serializer does not reject the token due to
    missing/inactive shipping address.
    """
    me_address = _make_me_address(seller) if with_address else None
    return SellerMelhorEnvioToken.objects.create(
        seller=seller,
        environment=environment,
        access_token='access_test_token',
        refresh_token='refresh_test_token',
        token_type='Bearer',
        expires_at=timezone.now() + timezone.timedelta(days=30),
        refresh_token_expires_at=timezone.now() + timezone.timedelta(days=45),
        is_active=is_active,
        me_email=me_email,
        me_address=me_address,
    )


# ---------------------------------------------------------------------------
# TestSellerMEConnect
# ---------------------------------------------------------------------------

class TestSellerMEConnect(TestCase):
    """Tests for GET /api/logistics/me/connect/"""

    def setUp(self):
        self.client = APIClient()
        self.seller = _make_seller()
        self.url = reverse('logistics:seller-me-connect')

    def test_connect_requires_auth(self):
        """Unauthenticated request must return 401."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch(
        'logistics.services.melhor_envio_oauth_service.MelhorEnvioOAuthService'
        '.get_seller_authorization_url'
    )
    def test_connect_returns_authorization_url(self, mock_get_url):
        """Authenticated GET returns 200 with authorization_url key."""
        mock_get_url.return_value = 'https://sandbox.melhorenvio.com.br/oauth/authorize?client_id=test'

        self.client.force_authenticate(user=self.seller)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('authorization_url', response.data)
        self.assertTrue(response.data['authorization_url'].startswith('https://'))

    @patch(
        'logistics.services.melhor_envio_oauth_service.MelhorEnvioOAuthService'
        '.get_seller_authorization_url'
    )
    def test_authorization_url_contains_seller_state(self, mock_get_url):
        """The authorization URL must contain state={seller.id}."""
        mock_get_url.return_value = (
            f'https://sandbox.melhorenvio.com.br/oauth/authorize?'
            f'client_id=test&state={self.seller.id}'
        )

        self.client.force_authenticate(user=self.seller)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        auth_url = response.data['authorization_url']
        self.assertIn(f'state={self.seller.id}', auth_url)
        mock_get_url.assert_called_once_with(seller=self.seller)

    @patch(
        'logistics.services.melhor_envio_oauth_service.MelhorEnvioOAuthService'
        '.get_seller_authorization_url'
    )
    def test_connect_returns_environment(self, mock_get_url):
        """Response must include an environment field."""
        mock_get_url.return_value = 'https://sandbox.melhorenvio.com.br/oauth/authorize'

        self.client.force_authenticate(user=self.seller)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('environment', response.data)


# ---------------------------------------------------------------------------
# TestSellerMECallback
# ---------------------------------------------------------------------------

class TestSellerMECallback(TestCase):
    """Tests for GET /api/logistics/me/callback/"""

    def setUp(self):
        self.client = APIClient()
        self.seller = _make_seller()
        self.url = reverse('logistics:seller-me-callback')

    def test_callback_without_code_returns_info(self):
        """GET without code returns 200 (ME connection test / info response)."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)

    def test_callback_missing_state_with_code_returns_400(self):
        """code present but state absent must return 400."""
        response = self.client.get(self.url, {'code': 'test_code'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_callback_with_invalid_state_returns_400(self):
        """code + non-existent state must return 400."""
        response = self.client.get(self.url, {'code': 'test_code', 'state': '999999'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    @patch(
        'logistics.services.melhor_envio_oauth_service.MelhorEnvioOAuthService'
        '.exchange_seller_code_for_token'
    )
    def test_callback_saves_token_for_seller(self, mock_exchange):
        """Valid code + HMAC-signed state should return 200 and call exchange service."""
        mock_token = MagicMock()
        mock_token.me_email = 'seller@me.com'
        mock_token.environment = 'sandbox'
        mock_exchange.return_value = mock_token

        # Generate a properly signed state so verify_seller_state passes
        signed_state = MelhorEnvioOAuthService.generate_seller_state(self.seller.id)

        response = self.client.get(
            self.url,
            {'code': 'test_code', 'state': signed_state}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_exchange.assert_called_once()

    @patch(
        'logistics.services.melhor_envio_oauth_service.MelhorEnvioOAuthService'
        '.exchange_seller_code_for_token'
    )
    def test_callback_response_includes_me_email_and_environment(self, mock_exchange):
        """Response must include me_email and environment when exchange succeeds."""
        mock_token = MagicMock()
        mock_token.me_email = 'seller@me.com'
        mock_token.environment = 'sandbox'
        mock_exchange.return_value = mock_token

        signed_state = MelhorEnvioOAuthService.generate_seller_state(self.seller.id)

        response = self.client.get(
            self.url,
            {'code': 'test_code', 'state': signed_state}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('environment', response.data)


# ---------------------------------------------------------------------------
# TestSellerMECallbackPost
# ---------------------------------------------------------------------------

class TestSellerMECallbackPost(TestCase):
    """
    Tests for POST /api/logistics/me/callback/post/

    This endpoint is the frontend-relay variant of the OAuth callback.
    The seller is identified via JWT (request.user); the state HMAC is still
    validated for CSRF protection, and state seller_id must match the
    authenticated seller.
    """

    def setUp(self):
        self.client = APIClient()
        self.seller = _make_seller()
        self.url = reverse('logistics:seller-me-callback-post')

    # ------------------------------------------------------------------
    # Authentication guard
    # ------------------------------------------------------------------

    def test_post_callback_requires_auth(self):
        """Unauthenticated POST must return 401."""
        signed_state = MelhorEnvioOAuthService.generate_seller_state(self.seller.id)
        response = self.client.post(
            self.url,
            {'code': 'test_code', 'state': signed_state},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ------------------------------------------------------------------
    # Payload validation
    # ------------------------------------------------------------------

    def test_post_callback_missing_code_returns_400(self):
        """POST without 'code' must return 400 (serializer validation)."""
        self.client.force_authenticate(user=self.seller)
        signed_state = MelhorEnvioOAuthService.generate_seller_state(self.seller.id)
        response = self.client.post(
            self.url,
            {'state': signed_state},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', response.data)

    def test_post_callback_missing_state_returns_400(self):
        """POST without 'state' must return 400 (serializer validation)."""
        self.client.force_authenticate(user=self.seller)
        response = self.client.post(
            self.url,
            {'code': 'test_code'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('state', response.data)

    def test_post_callback_empty_body_returns_400(self):
        """POST with empty body must return 400."""
        self.client.force_authenticate(user=self.seller)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # State HMAC validation
    # ------------------------------------------------------------------

    def test_post_callback_invalid_state_returns_400(self):
        """POST with a non-HMAC state must return 400."""
        self.client.force_authenticate(user=self.seller)
        response = self.client.post(
            self.url,
            {'code': 'test_code', 'state': 'not-a-valid-hmac-state'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_post_callback_state_for_different_seller_returns_400(self):
        """
        POST where state was signed for a different seller than the authenticated
        one must return 400 — prevents CSRF / token-swap attacks.
        """
        other_seller = _make_seller(email='other2@test.com', cpf='333.444.555-17')
        # State signed for 'other_seller' but request authenticated as 'self.seller'
        state_for_other = MelhorEnvioOAuthService.generate_seller_state(other_seller.id)

        self.client.force_authenticate(user=self.seller)
        response = self.client.post(
            self.url,
            {'code': 'test_code', 'state': state_for_other},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    # ------------------------------------------------------------------
    # Success path
    # ------------------------------------------------------------------

    @patch(
        'logistics.services.melhor_envio_oauth_service.MelhorEnvioOAuthService'
        '.exchange_seller_code_for_token'
    )
    def test_post_callback_success_returns_200_with_detail(self, mock_exchange):
        """Valid authenticated POST with matching state returns 200 and 'detail' key."""
        mock_token = MagicMock()
        mock_token.me_email = 'seller@me.com'
        mock_token.environment = 'sandbox'
        mock_exchange.return_value = mock_token

        signed_state = MelhorEnvioOAuthService.generate_seller_state(self.seller.id)
        self.client.force_authenticate(user=self.seller)

        response = self.client.post(
            self.url,
            {'code': 'test_code', 'state': signed_state},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('detail', response.data)

    @patch(
        'logistics.services.melhor_envio_oauth_service.MelhorEnvioOAuthService'
        '.exchange_seller_code_for_token'
    )
    def test_post_callback_success_calls_exchange_with_correct_seller(self, mock_exchange):
        """exchange_seller_code_for_token must be called with request.user as seller."""
        mock_token = MagicMock()
        mock_token.me_email = 'seller@me.com'
        mock_token.environment = 'sandbox'
        mock_exchange.return_value = mock_token

        signed_state = MelhorEnvioOAuthService.generate_seller_state(self.seller.id)
        self.client.force_authenticate(user=self.seller)

        self.client.post(
            self.url,
            {'code': 'test_code', 'state': signed_state},
            format='json',
        )

        mock_exchange.assert_called_once_with(code='test_code', seller=self.seller)

    @patch(
        'logistics.services.melhor_envio_oauth_service.MelhorEnvioOAuthService'
        '.exchange_seller_code_for_token'
    )
    def test_post_callback_response_includes_me_email_and_environment(self, mock_exchange):
        """Successful POST response must contain me_email and environment."""
        mock_token = MagicMock()
        mock_token.me_email = 'seller@me.com'
        mock_token.environment = 'sandbox'
        mock_exchange.return_value = mock_token

        signed_state = MelhorEnvioOAuthService.generate_seller_state(self.seller.id)
        self.client.force_authenticate(user=self.seller)

        response = self.client.post(
            self.url,
            {'code': 'test_code', 'state': signed_state},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('me_email'), 'seller@me.com')
        self.assertEqual(response.data.get('environment'), 'sandbox')

    # ------------------------------------------------------------------
    # Exchange failure
    # ------------------------------------------------------------------

    @patch(
        'logistics.services.melhor_envio_oauth_service.MelhorEnvioOAuthService'
        '.exchange_seller_code_for_token'
    )
    def test_post_callback_exchange_failure_returns_500(self, mock_exchange):
        """When exchange_seller_code_for_token raises, POST must return 500."""
        from logistics.services.melhor_envio_oauth_service import MelhorEnvioOAuthError
        mock_exchange.side_effect = MelhorEnvioOAuthError('ME API returned 400')

        signed_state = MelhorEnvioOAuthService.generate_seller_state(self.seller.id)
        self.client.force_authenticate(user=self.seller)

        response = self.client.post(
            self.url,
            {'code': 'test_code', 'state': signed_state},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn('error', response.data)


# ---------------------------------------------------------------------------
# TestSellerMEStatus
# ---------------------------------------------------------------------------

class TestSellerMEStatus(TestCase):
    """Tests for GET /api/logistics/me/status/"""

    def setUp(self):
        self.client = APIClient()
        self.seller = _make_seller()
        self.url = reverse('logistics:seller-me-status')

    def test_status_requires_auth(self):
        """Unauthenticated request must return 401."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_status_no_token(self):
        """Seller without ME token: connected=False."""
        self.client.force_authenticate(user=self.seller)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['connected'])

    def test_status_with_active_token(self):
        """Seller with active ME token: connected=True and me_email present."""
        _make_token(self.seller, me_email='active@me.com')

        self.client.force_authenticate(user=self.seller)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['connected'])
        self.assertEqual(response.data.get('me_email'), 'active@me.com')

    def test_status_returns_access_token_when_connected(self):
        """Seller with active ME token: response includes the access_token field."""
        _make_token(self.seller, me_email='active@me.com')

        self.client.force_authenticate(user=self.seller)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['connected'])
        self.assertEqual(response.data.get('access_token'), 'access_test_token')

    def test_status_does_not_return_access_token_when_not_connected(self):
        """Seller without ME token: response does not include access_token."""
        self.client.force_authenticate(user=self.seller)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['connected'])
        self.assertNotIn('access_token', response.data)

    def test_status_with_inactive_token_shows_not_connected(self):
        """Seller with is_active=False token: connected=False."""
        _make_token(self.seller, is_active=False)

        self.client.force_authenticate(user=self.seller)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['connected'])


# ---------------------------------------------------------------------------
# TestSellerMEDisconnect
# ---------------------------------------------------------------------------

class TestSellerMEDisconnect(TestCase):
    """Tests for DELETE /api/logistics/me/disconnect/"""

    def setUp(self):
        self.client = APIClient()
        self.seller = _make_seller()
        self.url = reverse('logistics:seller-me-disconnect')

    def test_disconnect_requires_auth(self):
        """Unauthenticated request must return 401."""
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_disconnect_no_token_returns_404(self):
        """Seller without active token: DELETE returns 404."""
        self.client.force_authenticate(user=self.seller)
        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_disconnect_deactivates_token(self):
        """Seller with active token: DELETE returns 200 and deactivates token."""
        token = _make_token(self.seller)
        self.assertTrue(token.is_active)

        self.client.force_authenticate(user=self.seller)
        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('disconnected'))

        token.refresh_from_db()
        self.assertFalse(token.is_active)

    def test_disconnect_does_not_affect_other_sellers_tokens(self):
        """Disconnecting one seller must not touch tokens of other sellers."""
        other_seller = _make_seller(email='other@test.com', cpf='222.333.444-09')
        other_token = _make_token(other_seller)
        token = _make_token(self.seller)

        self.client.force_authenticate(user=self.seller)
        self.client.delete(self.url)

        other_token.refresh_from_db()
        self.assertTrue(other_token.is_active)


# ---------------------------------------------------------------------------
# TestProductsListingMERequirement
# ---------------------------------------------------------------------------

class TestProductsListingMERequirement(TestCase):
    """
    Tests that MarketplaceListing creation requires an active SellerMelhorEnvioToken.
    """

    def setUp(self):
        self.client = APIClient()
        self.seller = _make_seller(email='prod_seller@test.com')
        self.url = reverse('products:listing-create')

        # Build required product fixtures
        from products.models import Category, Series, Products, Brand, Condition
        from logistics.models import Address

        self.category = Category.objects.create(name='Musculacao', slug='musculacao')
        self.series = Series.objects.create(name='Serie X', slug='serie-x')
        self.product = Products.objects.create(
            name='Haltere 10kg',
            slug='haltere-10kg',
            category=self.category,
            series=self.series,
            description='Haltere de ferro 10kg',
        )
        self.brand = Brand.objects.create(name='FitBrand', slug='fitbrand')
        self.condition = Condition.objects.create(name='Novo', slug='novo')

        # Seller shipping address (required by listing)
        self.address = Address.objects.create(
            user=self.seller,
            address_type='shipping',
            is_shipping_address=True,
            recipient_name='Test Seller',
            recipient_phone='11999999999',
            zipcode='01310-100',
            street='Avenida Paulista',
            number='1000',
            neighborhood='Bela Vista',
            city='Sao Paulo',
            state='SP',
        )

        self.valid_payload = {
            'product': self.product.id,
            'title': 'Haltere 10kg perfeito estado',
            'price': '50.00',
            'brand': self.brand.id,
            'quantity': 1,
            'description': 'Haltere de ferro 10kg em perfeito estado, pouco uso.',
            'condition': self.condition.id,
            'packages': [
                {
                    'weight_kg': '10.00',
                    'height_cm': '20.00',
                    'width_cm': '15.00',
                    'length_cm': '25.00',
                    'description': 'Caixa principal',
                }
            ],
        }

    def test_create_listing_without_me_connection_fails(self):
        """POST listing without active ME token returns 400."""
        self.client.force_authenticate(user=self.seller)
        response = self.client.post(self.url, data=self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_listing_requires_auth(self):
        """POST listing without authentication returns 401."""
        response = self.client.post(self.url, data=self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_listing_with_me_connection_succeeds(self):
        """POST listing with active ME token returns 201."""
        _make_token(self.seller)

        self.client.force_authenticate(user=self.seller)
        response = self.client.post(self.url, data=self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_listing_with_inactive_me_token_fails(self):
        """Inactive ME token (is_active=False) must also block listing creation."""
        _make_token(self.seller, is_active=False)

        self.client.force_authenticate(user=self.seller)
        response = self.client.post(self.url, data=self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_listing_without_me_connection_error_message(self):
        """The 400 error message must mention the ME connection requirement."""
        self.client.force_authenticate(user=self.seller)
        response = self.client.post(self.url, data=self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_text = str(response.data)
        self.assertIn('Melhor Envio', response_text)
