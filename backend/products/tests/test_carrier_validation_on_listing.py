"""
Tests for carrier dimension validation on listing creation/update.

Covers:
- MelhorEnvioService.validate_package_fits_any_carrier:
    - Package accepted by at least one service → returns True
    - Package rejected by all services → raises ValidationError with restriction details
    - Service without box restrictions → treated as accepting any package
    - API failure (HTTP error) → raises ValidationError with friendly message
    - API failure (network error) → raises ValidationError with friendly message
    - sum constraint (width+height+length) respected

- MarketplaceListingCreateSerializer.validate:
    - shipping_method=melhor_envio + incompatible package → 400 with carrier error
    - shipping_method=melhor_envio + compatible package → passes
    - shipping_method=in_person → validation NOT called (skipped)
    - shipping_method=both → validation NOT called (skipped)

- MarketplaceListingUpdateSerializer.validate:
    - Changing to shipping_method=melhor_envio with incompatible existing packages → error
    - Changing to shipping_method=melhor_envio with new incompatible packages → error
    - Changing to shipping_method=melhor_envio with compatible packages → passes
    - Changing to in_person → validation NOT called
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests as req_lib
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from authentication.models import CustomUser
from logistics.models import Address
from logistics.services.melhor_envio_service import MelhorEnvioService
from products.models import (
    Brand, Category, Condition, ListingPackage,
    MarketplaceListing, Products, Series, ShippingMethodChoices,
)


# ---------------------------------------------------------------------------
# Sample ME /me/shipment/services responses
# ---------------------------------------------------------------------------

# One service with tight box restrictions (PAC-like)
SERVICES_WITH_BOX = [
    {
        'id': 1,
        'name': 'PAC',
        'restrictions': {
            'formats': {
                'box': {
                    'weight': {'min': 0.001, 'max': 30},
                    'width':  {'min': 11,    'max': 105},
                    'height': {'min': 2,     'max': 105},
                    'length': {'min': 16,    'max': 105},
                    'sum': 200,
                }
            }
        },
    },
    {
        'id': 2,
        'name': 'SEDEX',
        'restrictions': {
            'formats': {
                'box': {
                    'weight': {'min': 0.001, 'max': 30},
                    'width':  {'min': 11,    'max': 105},
                    'height': {'min': 2,     'max': 105},
                    'length': {'min': 16,    'max': 105},
                    'sum': 200,
                }
            }
        },
    },
]

# Service with NO box restrictions at all
SERVICES_NO_BOX = [
    {
        'id': 3,
        'name': 'Jadlog .Package',
        'restrictions': {
            'formats': {}   # no 'box' key
        },
    }
]

# Service where box key exists but is null/falsy
SERVICES_BOX_NULL = [
    {
        'id': 4,
        'name': 'Carrier X',
        'restrictions': {
            'formats': {
                'box': None,
            }
        },
    }
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_me_response(services):
    """Return a mock requests.Response for GET /me/shipment/services."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = services
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# Unit tests: MelhorEnvioService.validate_package_fits_any_carrier
# ---------------------------------------------------------------------------

class ValidatePackageFitsAnyCarrierTest(TestCase):
    """Unit tests for MelhorEnvioService.validate_package_fits_any_carrier."""

    def setUp(self):
        self.service = MelhorEnvioService()
        self.seller = MagicMock()
        self.seller.email = 'seller@test.com'

    def _call(self, weight, width, height, length, services):
        """Helper: patches _get_headers + requests.get, then calls the method."""
        with patch.object(
            self.service, '_get_headers', return_value={'Authorization': 'Bearer test'}
        ), patch(
            'logistics.services.melhor_envio_service.requests.get',
            return_value=_make_me_response(services),
        ):
            return self.service.validate_package_fits_any_carrier(
                seller=self.seller,
                weight=weight,
                width=width,
                height=height,
                length=length,
            )

    # --- Package accepted ---

    def test_valid_package_within_all_limits_returns_true(self):
        """Package within all limits of at least one service must return True."""
        result = self._call(
            weight=5, width=20, height=15, length=30,
            services=SERVICES_WITH_BOX,
        )
        self.assertTrue(result)

    def test_package_fits_second_service_returns_true(self):
        """Package accepted by the second service (not first) must return True."""
        services = [
            {
                'id': 1,
                'name': 'Strict Carrier',
                'restrictions': {
                    'formats': {
                        'box': {
                            'weight': {'min': 0.001, 'max': 1},  # only up to 1 kg
                            'width':  {'min': 11, 'max': 20},
                            'height': {'min': 2,  'max': 20},
                            'length': {'min': 16, 'max': 20},
                        }
                    }
                },
            },
            {
                'id': 2,
                'name': 'Lenient Carrier',
                'restrictions': {
                    'formats': {
                        'box': {
                            'weight': {'min': 0.001, 'max': 30},
                            'width':  {'min': 11, 'max': 105},
                            'height': {'min': 2,  'max': 105},
                            'length': {'min': 16, 'max': 105},
                            'sum': 200,
                        }
                    }
                },
            },
        ]
        result = self._call(
            weight=5, width=20, height=15, length=30,
            services=services,
        )
        self.assertTrue(result)

    def test_service_without_box_restrictions_accepts_any_package(self):
        """A service with no 'box' key in formats is treated as accepting all packages."""
        result = self._call(
            weight=999, width=999, height=999, length=999,
            services=SERVICES_NO_BOX,
        )
        self.assertTrue(result)

    def test_service_with_null_box_accepts_any_package(self):
        """A service whose box value is null/falsy is treated as no restriction."""
        result = self._call(
            weight=999, width=999, height=999, length=999,
            services=SERVICES_BOX_NULL,
        )
        self.assertTrue(result)

    # --- Package rejected ---

    def test_weight_exceeds_max_raises_validation_error(self):
        """Package with weight > max must raise ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            self._call(
                weight=31, width=20, height=15, length=30,
                services=SERVICES_WITH_BOX,
            )
        self.assertIn('31', str(ctx.exception.detail))

    def test_width_exceeds_max_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._call(
                weight=5, width=110, height=15, length=30,
                services=SERVICES_WITH_BOX,
            )

    def test_height_below_min_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._call(
                weight=5, width=20, height=1, length=30,  # height min is 2
                services=SERVICES_WITH_BOX,
            )

    def test_length_below_min_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._call(
                weight=5, width=20, height=15, length=10,  # length min is 16
                services=SERVICES_WITH_BOX,
            )

    def test_sum_exceeds_limit_raises_validation_error(self):
        """width+height+length > sum must cause rejection."""
        # sum limit is 200; 70+70+70=210 > 200
        with self.assertRaises(ValidationError):
            self._call(
                weight=5, width=70, height=70, length=70,
                services=SERVICES_WITH_BOX,
            )

    def test_sum_exactly_at_limit_passes(self):
        """width+height+length == sum must be accepted."""
        # sum=200: e.g. 60+70+70=200
        result = self._call(
            weight=5, width=60, height=70, length=70,
            services=SERVICES_WITH_BOX,
        )
        self.assertTrue(result)

    def test_error_message_contains_dimensions(self):
        """ValidationError message must mention the package dimensions."""
        with self.assertRaises(ValidationError) as ctx:
            self._call(
                weight=31, width=20, height=15, length=30,
                services=SERVICES_WITH_BOX,
            )
        msg = str(ctx.exception.detail)
        self.assertIn('31', msg)   # weight

    def test_error_message_contains_carrier_restrictions(self):
        """ValidationError message must mention at least one carrier name."""
        with self.assertRaises(ValidationError) as ctx:
            self._call(
                weight=31, width=20, height=15, length=30,
                services=SERVICES_WITH_BOX,
            )
        msg = str(ctx.exception.detail)
        self.assertTrue('PAC' in msg or 'SEDEX' in msg or 'transportadora' in msg.lower())

    # --- API failures ---

    def test_http_error_raises_validation_error_with_friendly_message(self):
        """HTTP error from ME API must raise ValidationError with user-friendly message."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        http_error = req_lib.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error

        with patch.object(
            self.service, '_get_headers', return_value={'Authorization': 'Bearer test'}
        ), patch(
            'logistics.services.melhor_envio_service.requests.get',
            return_value=mock_response,
        ):
            with self.assertRaises(ValidationError) as ctx:
                self.service.validate_package_fits_any_carrier(
                    seller=self.seller, weight=5, width=20, height=15, length=30,
                )

        msg = str(ctx.exception.detail).lower()
        self.assertIn('não foi possível', msg)

    def test_network_error_raises_validation_error_with_friendly_message(self):
        """Network error from ME API must raise ValidationError with user-friendly message."""
        with patch.object(
            self.service, '_get_headers', return_value={'Authorization': 'Bearer test'}
        ), patch(
            'logistics.services.melhor_envio_service.requests.get',
            side_effect=req_lib.exceptions.ConnectionError('Connection refused'),
        ):
            with self.assertRaises(ValidationError) as ctx:
                self.service.validate_package_fits_any_carrier(
                    seller=self.seller, weight=5, width=20, height=15, length=30,
                )

        msg = str(ctx.exception.detail).lower()
        self.assertIn('não foi possível', msg)

    def test_error_message_is_in_portuguese(self):
        """Error message when no carrier accepts must be in pt-BR."""
        with self.assertRaises(ValidationError) as ctx:
            self._call(
                weight=31, width=20, height=15, length=30,
                services=SERVICES_WITH_BOX,
            )
        # DRF ValidationError.detail is a string or list; join into plain text
        detail = ctx.exception.detail
        if isinstance(detail, list):
            msg = ' '.join(str(d) for d in detail).lower()
        else:
            msg = str(detail).lower()
        # Must contain Portuguese words, not English error terms
        self.assertFalse('exceeds' in msg or 'invalid' in msg)
        self.assertTrue('transportadora' in msg or 'dimensões' in msg or 'aceitas' in msg)


# ---------------------------------------------------------------------------
# Integration: MarketplaceListingCreateSerializer
# ---------------------------------------------------------------------------

def _make_seller(email='seller@listing.com', cpf='11144477735'):
    user, _ = CustomUser.objects.get_or_create(
        email=email,
        defaults={'full_name': 'Seller', 'cpf': cpf},
    )
    user.set_password('pass')
    user.save()
    return user


def _make_address(user):
    return Address.objects.create(
        user=user,
        recipient_name='Seller',
        recipient_phone='11999999999',
        zipcode='01310100',
        street='Av Paulista',
        number='1578',
        neighborhood='Bela Vista',
        city='São Paulo',
        state='SP',
        is_shipping_address=True,
        is_active=True,
    )


def _get_or_create_catalog():
    cat = Category.objects.get_or_create(
        slug='cat-carrier-test', defaults={'name': 'Cat Carrier', 'is_active': True}
    )[0]
    ser = Series.objects.get_or_create(
        slug='ser-carrier-test', defaults={'name': 'Ser Carrier'}
    )[0]
    prod = Products.objects.get_or_create(
        slug='prod-carrier-test',
        defaults={'name': 'Prod Carrier', 'category': cat, 'series': ser},
    )[0]
    brand = Brand.objects.get_or_create(
        slug='brand-carrier-test', defaults={'name': 'Brand Carrier', 'is_active': True}
    )[0]
    cond = Condition.objects.get_or_create(
        slug='cond-carrier-test', defaults={'name': 'Cond Carrier'}
    )[0]
    return prod, brand, cond


def _valid_payload(product, brand, condition, shipping_method='melhor_envio', packages=None):
    return {
        'product': product.id,
        'title': 'Supino Reto Profissional Carrier',
        'price': '850.00',
        'brand': brand.id,
        'quantity': 1,
        'description': 'Supino reto com regulagem de encosto e suporte para barras. Aço reforçado.',
        'condition': condition.id,
        'shipping_method': shipping_method,
        'packages': packages or [
            {
                'weight_kg': '5.00',
                'height_cm': '20.00',
                'width_cm': '15.00',
                'length_cm': '30.00',
                'description': 'Caixa',
            }
        ],
    }


class CreateSerializerCarrierValidationTest(TestCase):
    """
    Tests for carrier validation inside MarketplaceListingCreateSerializer.validate().

    We mock: SellerMelhorEnvioToken.objects.get (always returns a connected token)
    and MelhorEnvioService.validate_package_fits_any_carrier (controls pass/fail).
    """

    def setUp(self):
        from products.serializers import MarketplaceListingCreateSerializer
        self.serializer_class = MarketplaceListingCreateSerializer

        self.seller = _make_seller(email='carrier_create@test.com', cpf='52998224725')
        self.address = _make_address(self.seller)
        self.product, self.brand, self.condition = _get_or_create_catalog()

    def _mock_request(self):
        req = MagicMock()
        req.user = self.seller
        return req

    def _build_serializer(self, payload, request=None):
        return self.serializer_class(
            data=payload,
            context={'request': request or self._mock_request()},
        )

    def _with_me_token(self, address):
        """Context manager: patches SellerMelhorEnvioToken lookup to return connected token."""
        mock_token = MagicMock()
        mock_token.me_address = address
        mock_token.me_address.is_active = True
        # The serializer does a lazy import then calls SellerMelhorEnvioToken.objects.get(...)
        # Patch at the model class level so the lazy import picks it up.
        return patch(
            'logistics.models.SellerMelhorEnvioToken.objects.get',
            return_value=mock_token,
        )

    def _with_me_service_pass(self):
        """Patch MelhorEnvioService so validate_package_fits_any_carrier always passes."""
        mock_instance = MagicMock()
        mock_instance.validate_package_fits_any_carrier.return_value = True
        return patch(
            'logistics.services.melhor_envio_service.MelhorEnvioService',
            return_value=mock_instance,
        ), mock_instance

    def _with_me_service_fail(self, message='Dimensões incompatíveis.'):
        """Patch MelhorEnvioService so validate_package_fits_any_carrier always raises."""
        mock_instance = MagicMock()
        mock_instance.validate_package_fits_any_carrier.side_effect = ValidationError(message)
        return patch(
            'logistics.services.melhor_envio_service.MelhorEnvioService',
            return_value=mock_instance,
        ), mock_instance

    def test_melhor_envio_compatible_package_passes(self):
        """shipping_method=melhor_envio + compatible package → serializer is valid."""
        payload = _valid_payload(self.product, self.brand, self.condition,
                                 shipping_method='melhor_envio')

        svc_patch, _ = self._with_me_service_pass()
        with self._with_me_token(self.address), svc_patch:
            s = self._build_serializer(payload)
            self.assertTrue(s.is_valid(), s.errors)

    def test_melhor_envio_incompatible_package_raises_error(self):
        """shipping_method=melhor_envio + incompatible package → serializer is invalid."""
        payload = _valid_payload(self.product, self.brand, self.condition,
                                 shipping_method='melhor_envio')

        svc_patch, _ = self._with_me_service_fail(
            'As dimensões do pacote não são aceitas por nenhuma transportadora.'
        )
        with self._with_me_token(self.address), svc_patch:
            s = self._build_serializer(payload)
            self.assertFalse(s.is_valid())

    def test_in_person_skips_carrier_validation(self):
        """shipping_method=in_person must NOT call validate_package_fits_any_carrier."""
        payload = _valid_payload(self.product, self.brand, self.condition,
                                 shipping_method='in_person')

        svc_patch, mock_instance = self._with_me_service_pass()
        with self._with_me_token(self.address), svc_patch:
            s = self._build_serializer(payload)
            s.is_valid()  # may fail for other reasons, that's fine
        mock_instance.validate_package_fits_any_carrier.assert_not_called()

    def test_both_skips_carrier_validation(self):
        """shipping_method=both must NOT call validate_package_fits_any_carrier."""
        payload = _valid_payload(self.product, self.brand, self.condition,
                                 shipping_method='both')

        svc_patch, mock_instance = self._with_me_service_pass()
        with self._with_me_token(self.address), svc_patch:
            s = self._build_serializer(payload)
            s.is_valid()
        mock_instance.validate_package_fits_any_carrier.assert_not_called()

    def test_validate_called_once_per_package(self):
        """validate_package_fits_any_carrier is called once for each package."""
        packages = [
            {'weight_kg': '5.00', 'height_cm': '20.00', 'width_cm': '15.00', 'length_cm': '30.00'},
            {'weight_kg': '3.00', 'height_cm': '15.00', 'width_cm': '10.00', 'length_cm': '25.00'},
        ]
        payload = _valid_payload(
            self.product, self.brand, self.condition,
            shipping_method='melhor_envio',
            packages=packages,
        )

        svc_patch, mock_instance = self._with_me_service_pass()
        with self._with_me_token(self.address), svc_patch:
            s = self._build_serializer(payload)
            s.is_valid()
        self.assertEqual(mock_instance.validate_package_fits_any_carrier.call_count, 2)

    def test_validate_called_with_correct_dimensions(self):
        """validate_package_fits_any_carrier receives the exact dimensions from the payload."""
        packages = [
            {'weight_kg': '7.50', 'height_cm': '25.00', 'width_cm': '18.00', 'length_cm': '35.00'},
        ]
        payload = _valid_payload(
            self.product, self.brand, self.condition,
            shipping_method='melhor_envio',
            packages=packages,
        )

        svc_patch, mock_instance = self._with_me_service_pass()
        with self._with_me_token(self.address), svc_patch:
            s = self._build_serializer(payload)
            s.is_valid()

        mock_instance.validate_package_fits_any_carrier.assert_called_once()
        call_kwargs = mock_instance.validate_package_fits_any_carrier.call_args[1]
        self.assertAlmostEqual(call_kwargs['weight'], 7.5)
        self.assertAlmostEqual(call_kwargs['width'], 18.0)
        self.assertAlmostEqual(call_kwargs['height'], 25.0)
        self.assertAlmostEqual(call_kwargs['length'], 35.0)


# ---------------------------------------------------------------------------
# Integration: MarketplaceListingUpdateSerializer
# ---------------------------------------------------------------------------

def _make_listing(seller, address):
    product, brand, condition = _get_or_create_catalog()
    listing = MarketplaceListing.objects.create(
        product=product,
        seller=seller,
        title='Banco de Musculação Update Test',
        price=Decimal('350.00'),
        brand=brand,
        quantity=1,
        description='Banco ajustável de musculação para treinos em casa com suporte de peso.',
        condition=condition,
        shipping_address=address,
        shipping_method=ShippingMethodChoices.BOTH,
        is_active=True,
    )
    ListingPackage.objects.create(
        listing=listing,
        weight_kg=Decimal('15.00'),
        height_cm=Decimal('60.00'),
        width_cm=Decimal('50.00'),
        length_cm=Decimal('100.00'),
    )
    return listing


class UpdateSerializerCarrierValidationTest(TestCase):
    """
    Tests for carrier validation inside MarketplaceListingUpdateSerializer.validate().
    """

    def setUp(self):
        from products.serializers import MarketplaceListingUpdateSerializer
        self.serializer_class = MarketplaceListingUpdateSerializer

        self.seller = _make_seller(email='carrier_update@test.com', cpf='98765432100')
        self.address = _make_address(self.seller)
        self.listing = _make_listing(self.seller, self.address)

    def _mock_request(self):
        req = MagicMock()
        req.user = self.seller
        return req

    def _build_serializer(self, data, partial=True):
        return self.serializer_class(
            instance=self.listing,
            data=data,
            partial=partial,
            context={'request': self._mock_request()},
        )

    def _svc_pass(self):
        mock_instance = MagicMock()
        mock_instance.validate_package_fits_any_carrier.return_value = True
        return patch(
            'logistics.services.melhor_envio_service.MelhorEnvioService',
            return_value=mock_instance,
        ), mock_instance

    def _svc_fail(self, msg='Dimensões incompatíveis.'):
        mock_instance = MagicMock()
        mock_instance.validate_package_fits_any_carrier.side_effect = ValidationError(msg)
        return patch(
            'logistics.services.melhor_envio_service.MelhorEnvioService',
            return_value=mock_instance,
        ), mock_instance

    def test_changing_to_melhor_envio_with_compatible_existing_packages_passes(self):
        """Switching to melhor_envio with existing compatible packages must pass."""
        svc_patch, mock_instance = self._svc_pass()
        with svc_patch:
            s = self._build_serializer({'shipping_method': 'melhor_envio'})
            self.assertTrue(s.is_valid(), s.errors)
        mock_instance.validate_package_fits_any_carrier.assert_called_once()

    def test_changing_to_melhor_envio_with_incompatible_existing_packages_fails(self):
        """Switching to melhor_envio with incompatible existing packages must fail."""
        svc_patch, _ = self._svc_fail()
        with svc_patch:
            s = self._build_serializer({'shipping_method': 'melhor_envio'})
            self.assertFalse(s.is_valid())

    def test_changing_to_melhor_envio_with_new_compatible_packages_passes(self):
        """Switching to melhor_envio + providing new compatible packages must pass."""
        new_packages = [
            {'weight_kg': '5.00', 'height_cm': '20.00', 'width_cm': '15.00', 'length_cm': '30.00'},
        ]
        svc_patch, mock_instance = self._svc_pass()
        with svc_patch:
            s = self._build_serializer({'shipping_method': 'melhor_envio', 'packages': new_packages})
            self.assertTrue(s.is_valid(), s.errors)
        mock_instance.validate_package_fits_any_carrier.assert_called_once()

    def test_changing_to_melhor_envio_with_new_incompatible_packages_fails(self):
        """Switching to melhor_envio + providing new incompatible packages must fail."""
        new_packages = [
            {'weight_kg': '50.00', 'height_cm': '200.00', 'width_cm': '150.00', 'length_cm': '300.00'},
        ]
        svc_patch, _ = self._svc_fail('Dimensões incompatíveis com transportadoras.')
        with svc_patch:
            s = self._build_serializer({'shipping_method': 'melhor_envio', 'packages': new_packages})
            self.assertFalse(s.is_valid())

    def test_changing_to_in_person_skips_carrier_validation(self):
        """Switching to in_person must NOT call validate_package_fits_any_carrier."""
        svc_patch, mock_instance = self._svc_pass()
        with svc_patch:
            s = self._build_serializer({'shipping_method': 'in_person'})
            s.is_valid()
        mock_instance.validate_package_fits_any_carrier.assert_not_called()

    def test_no_shipping_method_change_skips_carrier_validation(self):
        """Updating only title (not shipping_method) must NOT call carrier validation."""
        svc_patch, mock_instance = self._svc_pass()
        with svc_patch:
            s = self._build_serializer({'title': 'Novo Título do Banco de Musculação'})
            s.is_valid()
        mock_instance.validate_package_fits_any_carrier.assert_not_called()
