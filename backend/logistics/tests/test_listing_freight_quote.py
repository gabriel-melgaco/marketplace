"""
Tests for POST /api/logistics/listings/<listing_id>/freight-quote/

Covers:
- Service layer: MelhorEnvioService.calculate_listing_freight
    - in_person only listing → available=False
    - no shipping_address → available=False
    - same origin/destination ZIP → available=False (ShippingValidationError)
    - no packages and no legacy dimensions → available=False
    - single package, happy path → available=True with options
    - multi-package: sums prices and takes max delivery_days
    - ME API returns no valid carriers → available=False
    - ME API request failure → available=False (no exception propagated)
    - Packages preferred over legacy fields when both exist
    - Options sorted by price ascending

- Serializer: ListingFreightQuoteRequestSerializer
    - valid CEP with dash
    - valid CEP without dash
    - invalid CEP (letters, wrong length)

- View: POST /api/logistics/listings/<listing_id>/freight-quote/
    - 401 when unauthenticated
    - 404 when listing not found or inactive
    - 400 on invalid destination_cep
    - 200 with available=True on success
    - 200 with available=False when in_person only
    - 200 with available=False when same ZIP
    - 200 with available=False when ME API fails
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock, call

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from authentication.models import CustomUser
from logistics.models import Address
from logistics.serializers import ListingFreightQuoteRequestSerializer
from logistics.services.melhor_envio_service import MelhorEnvioService, ShippingValidationError
from products.models import (
    Category, Series, Products, Brand, Condition,
    MarketplaceListing, ListingPackage, ShippingMethodChoices,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(email='seller@test.com', cpf='11144477735'):
    user, _ = CustomUser.objects.get_or_create(
        email=email,
        defaults={'full_name': 'Test Seller', 'cpf': cpf},
    )
    user.set_password('testpass123')
    user.save()
    return user


def make_address(user, zipcode='01310100'):
    return Address.objects.create(
        user=user,
        recipient_name='Test Seller',
        recipient_phone='11999999999',
        zipcode=zipcode,
        street='Avenida Paulista',
        number='1578',
        neighborhood='Bela Vista',
        city='Sao Paulo',
        state='SP',
        is_shipping_address=True,
        is_active=True,
    )


def make_listing(seller, address, shipping_method=ShippingMethodChoices.MELHOR_ENVIO):
    category = Category.objects.get_or_create(
        slug='musculacao-fq', defaults={'name': 'Musculacao FQ', 'is_active': True}
    )[0]
    series = Series.objects.get_or_create(
        slug='fitness-fq', defaults={'name': 'Fitness FQ'}
    )[0]
    product = Products.objects.get_or_create(
        slug='banco-musculacao-fq',
        defaults={'name': 'Banco FQ', 'category': category, 'series': series},
    )[0]
    brand = Brand.objects.get_or_create(
        slug='iron-force-fq', defaults={'name': 'Iron Force FQ', 'is_active': True}
    )[0]
    condition = Condition.objects.get_or_create(
        slug='novo-fq', defaults={'name': 'Novo FQ'}
    )[0]
    return MarketplaceListing.objects.create(
        product=product,
        seller=seller,
        title='Banco de Musculacao Premium FQ',
        price=Decimal('350.00'),
        brand=brand,
        quantity=2,
        description='Banco de musculacao para testes do freight quote.',
        condition=condition,
        shipping_address=address,
        shipping_method=shipping_method,
        is_active=True,
    )


def make_package(listing, weight=15.0, height=60.0, width=50.0, length=120.0, description='Caixa'):
    return ListingPackage.objects.create(
        listing=listing,
        weight_kg=Decimal(str(weight)),
        height_cm=Decimal(str(height)),
        width_cm=Decimal(str(width)),
        length_cm=Decimal(str(length)),
        description=description,
    )


# ---------------------------------------------------------------------------
# Fake ME API responses
# ---------------------------------------------------------------------------

FAKE_ME_RESPONSE = [
    {
        'id': 1,
        'name': 'PAC',
        'price': '25.00',
        'custom_price': '25.00',
        'discount': '5.00',
        'currency': 'R$',
        'delivery_time': 5,
        'custom_delivery_time': 5,
        'company': {'id': 1, 'name': 'Correios', 'picture': 'https://img.me.com/correios.png'},
    },
    {
        'id': 2,
        'name': 'SEDEX',
        'price': '45.00',
        'custom_price': '45.00',
        'discount': '0.00',
        'currency': 'R$',
        'delivery_time': 2,
        'custom_delivery_time': 2,
        'company': {'id': 1, 'name': 'Correios', 'picture': 'https://img.me.com/correios.png'},
    },
    {
        'id': 3,
        'name': 'Jadlog .Package',
        'error': 'CEP nao atendido pela transportadora.',
        'company': {'id': 2, 'name': 'Jadlog', 'picture': 'https://img.me.com/jadlog.png'},
    },
]


# ---------------------------------------------------------------------------
# Service-layer unit tests
# ---------------------------------------------------------------------------

class CalculateListingFreightServiceTest(TestCase):
    """Unit tests for MelhorEnvioService.calculate_listing_freight."""

    def setUp(self):
        self.service = MelhorEnvioService()
        self.seller = make_user('seller_service@test.com', '11144477735')
        self.seller_address = make_address(self.seller, zipcode='01310100')
        self.listing = make_listing(self.seller, self.seller_address)
        self.pkg = make_package(self.listing)

    # ------------------------------------------------------------------
    # Available=False cases
    # ------------------------------------------------------------------

    def test_in_person_listing_returns_unavailable(self):
        """Listing with shipping_method=in_person must return available=False."""
        self.listing.shipping_method = ShippingMethodChoices.IN_PERSON
        self.listing.save()

        result = self.service.calculate_listing_freight(self.listing, '04094050')

        self.assertFalse(result['available'])
        self.assertIn('Contate o vendedor', result['message'])
        self.assertNotIn('options', result)

    def test_no_shipping_address_returns_unavailable(self):
        """Listing without shipping_address must return available=False."""
        self.listing.shipping_address = None
        self.listing.save()

        result = self.service.calculate_listing_freight(self.listing, '04094050')

        self.assertFalse(result['available'])
        self.assertNotIn('options', result)

    def test_same_zipcode_returns_unavailable(self):
        """
        Same origin and destination ZIP must raise ShippingValidationError
        and the view converts it to available=False.
        Testing at service layer: exception is propagated.
        """
        same_zip = self.seller_address.zipcode  # '01310100'
        with self.assertRaises(ShippingValidationError):
            self.service.calculate_listing_freight(self.listing, same_zip)

    def test_no_volumes_returns_unavailable(self):
        """Listing with no packages and no legacy dimensions returns available=False."""
        # Remove the package created in setUp
        self.pkg.delete()
        # Ensure legacy fields are also empty
        self.listing.weight_kg = None
        self.listing.height_cm = None
        self.listing.width_cm = None
        self.listing.length_cm = None
        self.listing.save()

        result = self.service.calculate_listing_freight(self.listing, '04094050')

        self.assertFalse(result['available'])

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', return_value=[
        {
            'id': 1,
            'name': 'PAC',
            'error': 'CEP invalido',
            'company': {'id': 1, 'name': 'Correios', 'picture': ''},
        }
    ])
    def test_all_carriers_have_errors_returns_unavailable(self, mock_calc, mock_ids):
        """When all ME quotes have errors, result must be available=False."""
        result = self.service.calculate_listing_freight(self.listing, '04094050')

        self.assertFalse(result['available'])

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', side_effect=Exception('timeout'))
    def test_me_api_failure_returns_unavailable(self, mock_calc, mock_ids):
        """ME API failures must be caught and return available=False (no exception propagated)."""
        result = self.service.calculate_listing_freight(self.listing, '04094050')

        self.assertFalse(result['available'])

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', return_value=FAKE_ME_RESPONSE)
    def test_single_package_returns_available_with_options(self, mock_calc, mock_ids):
        """Single package listing returns available=True with formatted options."""
        result = self.service.calculate_listing_freight(self.listing, '04094050')

        self.assertTrue(result['available'])
        self.assertIn('options', result)
        # Jadlog has error → filtered out
        self.assertEqual(len(result['options']), 2)

        option_names = {opt['name'] for opt in result['options']}
        self.assertIn('PAC', option_names)
        self.assertIn('SEDEX', option_names)

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', return_value=FAKE_ME_RESPONSE)
    def test_options_sorted_by_price_ascending(self, mock_calc, mock_ids):
        """Options must be sorted cheapest-first."""
        result = self.service.calculate_listing_freight(self.listing, '04094050')

        prices = [opt['price'] for opt in result['options']]
        self.assertEqual(prices, sorted(prices))

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', return_value=FAKE_ME_RESPONSE)
    def test_option_fields_present(self, mock_calc, mock_ids):
        """Each option must include required fields."""
        result = self.service.calculate_listing_freight(self.listing, '04094050')
        required_fields = {'service_id', 'name', 'company', 'company_picture', 'price', 'delivery_days'}

        for opt in result['options']:
            self.assertTrue(required_fields.issubset(opt.keys()), f'Missing fields in {opt}')

    # ------------------------------------------------------------------
    # Multi-package: sum prices, max delivery_days
    # ------------------------------------------------------------------

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping')
    def test_multi_package_sums_prices_and_takes_max_delivery(self, mock_calc, mock_ids):
        """
        For 2 packages, prices for each service must be the SUM of both volumes,
        and delivery_days must be the MAX across both volumes.
        """
        # Add a second package
        make_package(self.listing, weight=5.0, height=30.0, width=20.0, length=40.0,
                     description='Caixa 2')

        # Package 1: PAC=25, SEDEX=45, delivery 5/2
        vol1_response = [
            {'id': 1, 'name': 'PAC', 'custom_price': '25.00', 'custom_delivery_time': 5,
             'company': {'id': 1, 'name': 'Correios', 'picture': ''}},
            {'id': 2, 'name': 'SEDEX', 'custom_price': '45.00', 'custom_delivery_time': 2,
             'company': {'id': 1, 'name': 'Correios', 'picture': ''}},
        ]
        # Package 2: PAC=12, SEDEX=18, delivery 3/1
        vol2_response = [
            {'id': 1, 'name': 'PAC', 'custom_price': '12.00', 'custom_delivery_time': 3,
             'company': {'id': 1, 'name': 'Correios', 'picture': ''}},
            {'id': 2, 'name': 'SEDEX', 'custom_price': '18.00', 'custom_delivery_time': 1,
             'company': {'id': 1, 'name': 'Correios', 'picture': ''}},
        ]
        mock_calc.side_effect = [vol1_response, vol2_response]

        result = self.service.calculate_listing_freight(self.listing, '04094050')

        self.assertTrue(result['available'])
        options_by_id = {opt['service_id']: opt for opt in result['options']}

        # PAC: 25 + 12 = 37, max_delivery = max(5, 3) = 5
        self.assertAlmostEqual(float(options_by_id[1]['price']), 37.0, places=2)
        self.assertEqual(options_by_id[1]['delivery_days'], 5)

        # SEDEX: 45 + 18 = 63, max_delivery = max(2, 1) = 2
        self.assertAlmostEqual(float(options_by_id[2]['price']), 63.0, places=2)
        self.assertEqual(options_by_id[2]['delivery_days'], 2)

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping')
    def test_multi_package_calls_calculate_once_per_volume(self, mock_calc, mock_ids):
        """calculate_shipping must be called once per ListingPackage."""
        make_package(self.listing, weight=3.0, height=20.0, width=15.0, length=30.0)

        mock_calc.return_value = FAKE_ME_RESPONSE

        self.service.calculate_listing_freight(self.listing, '04094050')

        # listing now has 2 packages
        self.assertEqual(mock_calc.call_count, 2)

    # ------------------------------------------------------------------
    # Legacy dimension fallback
    # ------------------------------------------------------------------

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', return_value=FAKE_ME_RESPONSE)
    def test_legacy_fields_used_when_no_packages(self, mock_calc, mock_ids):
        """When no ListingPackages exist, legacy dimension fields are used as a single volume."""
        self.pkg.delete()
        self.listing.weight_kg = Decimal('10.00')
        self.listing.height_cm = Decimal('50.00')
        self.listing.width_cm = Decimal('40.00')
        self.listing.length_cm = Decimal('80.00')
        self.listing.save()

        result = self.service.calculate_listing_freight(self.listing, '04094050')

        self.assertTrue(result['available'])
        # calculate_shipping called once with the legacy single volume
        self.assertEqual(mock_calc.call_count, 1)
        called_package = mock_calc.call_args[1]['package']
        self.assertEqual(called_package['weight'], 10.0)

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', return_value=FAKE_ME_RESPONSE)
    def test_packages_preferred_over_legacy_fields(self, mock_calc, mock_ids):
        """ListingPackages must be used even when legacy dimension fields are set."""
        # Set legacy fields on the listing too
        self.listing.weight_kg = Decimal('99.00')
        self.listing.height_cm = Decimal('99.00')
        self.listing.width_cm = Decimal('99.00')
        self.listing.length_cm = Decimal('99.00')
        self.listing.save()

        # pkg still exists from setUp
        result = self.service.calculate_listing_freight(self.listing, '04094050')

        self.assertTrue(result['available'])
        # The package weight (15 kg) must be used, not the legacy 99 kg
        called_package = mock_calc.call_args[1]['package']
        self.assertNotEqual(called_package['weight'], 99.0)


# ---------------------------------------------------------------------------
# Serializer unit tests
# ---------------------------------------------------------------------------

class ListingFreightQuoteRequestSerializerTest(TestCase):
    """Unit tests for ListingFreightQuoteRequestSerializer."""

    def _validate(self, data):
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.post('/')
        user = make_user('ser_user@test.com', '11144477735')
        request.user = user
        s = ListingFreightQuoteRequestSerializer(data=data, context={'request': request})
        return s

    def test_valid_cep_with_dash(self):
        s = self._validate({'destination_cep': '01310-100'})
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data['destination_cep'], '01310100')

    def test_valid_cep_without_dash(self):
        s = self._validate({'destination_cep': '01310100'})
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data['destination_cep'], '01310100')

    def test_invalid_cep_too_short(self):
        s = self._validate({'destination_cep': '0131010'})
        self.assertFalse(s.is_valid())
        self.assertIn('destination_cep', s.errors)

    def test_invalid_cep_with_letters(self):
        s = self._validate({'destination_cep': '01310-ABC'})
        self.assertFalse(s.is_valid())

    def test_missing_destination_cep(self):
        s = self._validate({})
        self.assertFalse(s.is_valid())
        self.assertIn('destination_cep', s.errors)


# ---------------------------------------------------------------------------
# View integration tests
# ---------------------------------------------------------------------------

class ListingFreightQuoteViewTest(TestCase):
    """Integration tests for POST /api/logistics/listings/<id>/freight-quote/."""

    def setUp(self):
        self.client = APIClient()
        self.buyer = make_user('buyer_view@test.com', '98765432100')
        self.seller = make_user('seller_view@test.com', '12345678909')
        self.seller_address = make_address(self.seller, zipcode='01310100')
        self.listing = make_listing(self.seller, self.seller_address)
        self.pkg = make_package(self.listing)
        self.url = reverse('logistics:listing-freight-quote', kwargs={'listing_id': self.listing.pk})

    def _auth(self):
        self.client.force_authenticate(user=self.buyer)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self.url, {'destination_cep': '04094050'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ------------------------------------------------------------------
    # 404
    # ------------------------------------------------------------------

    def test_nonexistent_listing_returns_404(self):
        self._auth()
        url = reverse('logistics:listing-freight-quote', kwargs={'listing_id': 99999})
        response = self.client.post(url, {'destination_cep': '04094050'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_inactive_listing_returns_404(self):
        self._auth()
        self.listing.is_active = False
        self.listing.save()
        response = self.client.post(self.url, {'destination_cep': '04094050'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # 400
    # ------------------------------------------------------------------

    def test_missing_destination_cep_returns_400(self):
        self._auth()
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_cep_format_returns_400(self):
        self._auth()
        response = self.client.post(self.url, {'destination_cep': 'ABCDEFGH'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # 200 — available=True
    # ------------------------------------------------------------------

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', return_value=FAKE_ME_RESPONSE)
    def test_success_returns_200_with_options(self, mock_calc, mock_ids):
        self._auth()
        response = self.client.post(self.url, {'destination_cep': '04094050'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['available'])
        self.assertIn('options', data)
        self.assertGreater(len(data['options']), 0)

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', return_value=FAKE_ME_RESPONSE)
    def test_success_response_has_correct_fields(self, mock_calc, mock_ids):
        self._auth()
        response = self.client.post(self.url, {'destination_cep': '04094050'})
        data = response.json()

        option = data['options'][0]
        for field in ('service_id', 'name', 'company', 'company_picture', 'price', 'delivery_days'):
            self.assertIn(field, option, f'Missing field: {field}')

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', return_value=FAKE_ME_RESPONSE)
    def test_success_options_sorted_by_price(self, mock_calc, mock_ids):
        self._auth()
        response = self.client.post(self.url, {'destination_cep': '04094050'})
        data = response.json()

        prices = [float(opt['price']) for opt in data['options']]
        self.assertEqual(prices, sorted(prices))

    # ------------------------------------------------------------------
    # 200 — available=False
    # ------------------------------------------------------------------

    def test_in_person_listing_returns_200_unavailable(self):
        self._auth()
        self.listing.shipping_method = ShippingMethodChoices.IN_PERSON
        self.listing.save()

        response = self.client.post(self.url, {'destination_cep': '04094050'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data['available'])
        self.assertIn('message', data)

    def test_same_zipcode_returns_200_unavailable(self):
        """Same origin/destination ZIP → available=False (ShippingValidationError caught by view)."""
        self._auth()
        # Destination == seller origin
        response = self.client.post(self.url, {'destination_cep': '01310100'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data['available'])
        self.assertIn('message', data)

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', side_effect=Exception('ME down'))
    def test_me_api_failure_returns_200_unavailable(self, mock_calc, mock_ids):
        self._auth()
        response = self.client.post(self.url, {'destination_cep': '04094050'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data['available'])
        self.assertIn('message', data)

    @patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None)
    @patch.object(MelhorEnvioService, 'calculate_shipping', return_value=[
        {'id': 3, 'name': 'Jadlog', 'error': 'nao atende', 'company': {'id': 2, 'name': 'Jadlog', 'picture': ''}}
    ])
    def test_no_valid_carriers_returns_200_unavailable(self, mock_calc, mock_ids):
        self._auth()
        response = self.client.post(self.url, {'destination_cep': '04094050'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data['available'])

    def test_cep_with_dash_accepted(self):
        """CEP with dash must be accepted and normalized."""
        self._auth()
        with patch.object(MelhorEnvioService, '_get_seller_active_service_ids', return_value=None), \
             patch.object(MelhorEnvioService, 'calculate_shipping', return_value=FAKE_ME_RESPONSE):
            response = self.client.post(self.url, {'destination_cep': '04094-050'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
