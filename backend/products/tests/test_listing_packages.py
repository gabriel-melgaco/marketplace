"""
Tests for multi-package support on MarketplaceListing.

Covers:
- ListingPackage model creation and __str__
- MarketplaceListingCreateSerializer: packages field required, bulk_create
- MarketplaceListingUpdateSerializer: optional package replacement
- MarketplaceListingSerializer (read): packages included
- ListingPackageSerializer: validation (weight, height, width, length > 0)
- GET /api/products/listings/<id>/packages/ (public)
- POST /api/products/listings/<id>/packages/ (seller only)
- PUT/PATCH /api/products/listings/<id>/packages/<pk>/ (seller only)
- DELETE /api/products/listings/<id>/packages/<pk>/ (seller only, not last)
- MelhorEnvioService._build_volumes_for_items: packages path + legacy fallback
- MelhorEnvioService._build_volumes_for_raw_items: packages path + legacy fallback
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from authentication.models import CustomUser
from products.models import (
    Category, Series, Products, Brand, Condition,
    MarketplaceListing, ListingPackage,
)
from logistics.models import Address
from logistics.services.melhor_envio_service import MelhorEnvioService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(email='seller@test.com', cpf='11144477735'):
    """Create and return a test CustomUser."""
    user, _ = CustomUser.objects.get_or_create(
        email=email,
        defaults={
            'full_name': 'Test Seller',
            'cpf': cpf,
        }
    )
    user.set_password('testpass123')
    user.save()
    return user


def make_address(user, zipcode='01310100'):
    """Create and return a test Address."""
    return Address.objects.create(
        user=user,
        recipient_name='Test Seller',
        recipient_phone='11999999999',
        zipcode=zipcode,
        street='Avenida Paulista',
        number='1578',
        neighborhood='Bela Vista',
        city='São Paulo',
        state='SP',
        is_shipping_address=True,
        is_active=True,
    )


def make_listing(seller, address, title='Banco de Musculação Premium'):
    """Create and return a test MarketplaceListing (no legacy dimension fields)."""
    category = Category.objects.get_or_create(
        slug='musculacao', defaults={'name': 'Musculação', 'is_active': True}
    )[0]
    series = Series.objects.get_or_create(
        slug='fitness', defaults={'name': 'Fitness'}
    )[0]
    product = Products.objects.get_or_create(
        slug='banco-musculacao',
        defaults={
            'name': 'Banco de Musculação',
            'category': category,
            'series': series,
        }
    )[0]
    brand = Brand.objects.get_or_create(
        slug='iron-force',
        defaults={'name': 'Iron Force', 'is_active': True}
    )[0]
    condition = Condition.objects.get_or_create(
        slug='novo', defaults={'name': 'Novo'}
    )[0]

    return MarketplaceListing.objects.create(
        product=product,
        seller=seller,
        title=title,
        price=Decimal('350.00'),
        brand=brand,
        quantity=2,
        description='Banco de musculação ajustável com suporte para pesos. Ideal para treinos em casa.',
        condition=condition,
        shipping_address=address,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class ListingPackageModelTest(TestCase):
    """Tests for the ListingPackage model."""

    def setUp(self):
        self.seller = make_user()
        self.address = make_address(self.seller)
        self.listing = make_listing(self.seller, self.address)

    def test_create_single_package(self):
        pkg = ListingPackage.objects.create(
            listing=self.listing,
            weight_kg=Decimal('15.00'),
            height_cm=Decimal('60.00'),
            width_cm=Decimal('50.00'),
            length_cm=Decimal('120.00'),
            description='Caixa principal',
        )
        self.assertEqual(pkg.listing, self.listing)
        self.assertEqual(pkg.weight_kg, Decimal('15.00'))
        self.assertIn(str(self.listing.id), str(pkg))

    def test_str_includes_listing_title_and_weight(self):
        pkg = ListingPackage.objects.create(
            listing=self.listing,
            weight_kg=Decimal('8.50'),
            height_cm=Decimal('40.00'),
            width_cm=Decimal('30.00'),
            length_cm=Decimal('60.00'),
        )
        expected = f'Pacote {pkg.id} - {self.listing.title} (8.50kg)'
        self.assertEqual(str(pkg), expected)

    def test_multiple_packages_per_listing(self):
        for i in range(3):
            ListingPackage.objects.create(
                listing=self.listing,
                weight_kg=Decimal('5.00'),
                height_cm=Decimal('30.00'),
                width_cm=Decimal('20.00'),
                length_cm=Decimal('40.00'),
                description=f'Caixa {i + 1}',
            )
        self.assertEqual(self.listing.packages.count(), 3)

    def test_packages_ordered_by_id(self):
        pkg1 = ListingPackage.objects.create(
            listing=self.listing,
            weight_kg=Decimal('10.00'),
            height_cm=Decimal('30.00'),
            width_cm=Decimal('20.00'),
            length_cm=Decimal('40.00'),
        )
        pkg2 = ListingPackage.objects.create(
            listing=self.listing,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('20.00'),
            width_cm=Decimal('15.00'),
            length_cm=Decimal('30.00'),
        )
        qs = list(self.listing.packages.all())
        self.assertEqual(qs[0].id, pkg1.id)
        self.assertEqual(qs[1].id, pkg2.id)

    def test_package_cascade_deletes_with_listing(self):
        ListingPackage.objects.create(
            listing=self.listing,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('30.00'),
            width_cm=Decimal('20.00'),
            length_cm=Decimal('40.00'),
        )
        listing_id = self.listing.id
        self.listing.delete()
        self.assertFalse(ListingPackage.objects.filter(listing_id=listing_id).exists())


# ---------------------------------------------------------------------------
# Serializer Tests
# ---------------------------------------------------------------------------

class ListingPackageSerializerTest(TestCase):
    """Tests for ListingPackageSerializer validation."""

    def setUp(self):
        from products.serializers import ListingPackageSerializer
        self.serializer_class = ListingPackageSerializer

    def _valid_data(self, **overrides):
        data = {
            'weight_kg': '5.00',
            'height_cm': '30.00',
            'width_cm': '20.00',
            'length_cm': '40.00',
            'description': 'Caixa A',
        }
        data.update(overrides)
        return data

    def test_valid_package_passes(self):
        s = self.serializer_class(data=self._valid_data())
        self.assertTrue(s.is_valid(), s.errors)

    def test_zero_weight_fails(self):
        s = self.serializer_class(data=self._valid_data(weight_kg='0'))
        self.assertFalse(s.is_valid())
        self.assertIn('weight_kg', s.errors)

    def test_negative_height_fails(self):
        s = self.serializer_class(data=self._valid_data(height_cm='-1'))
        self.assertFalse(s.is_valid())
        self.assertIn('height_cm', s.errors)

    def test_zero_width_fails(self):
        s = self.serializer_class(data=self._valid_data(width_cm='0'))
        self.assertFalse(s.is_valid())
        self.assertIn('width_cm', s.errors)

    def test_negative_length_fails(self):
        s = self.serializer_class(data=self._valid_data(length_cm='-0.1'))
        self.assertFalse(s.is_valid())
        self.assertIn('length_cm', s.errors)

    def test_description_is_optional(self):
        data = self._valid_data()
        data.pop('description')
        s = self.serializer_class(data=data)
        self.assertTrue(s.is_valid(), s.errors)


# ---------------------------------------------------------------------------
# Build Volumes — Service Unit Tests
# ---------------------------------------------------------------------------

class BuildVolumesForItemsTest(TestCase):
    """
    Unit tests for MelhorEnvioService._build_volumes_for_items.

    Uses mock OrderItems (not real DB objects) to test the volume-building logic
    in isolation.
    """

    def setUp(self):
        self.service = MelhorEnvioService.__new__(MelhorEnvioService)

    def _make_item(self, packages, quantity=1, legacy_dims=None):
        """
        Build a mock OrderItem with a mock listing.

        Args:
            packages: list of (weight_kg, height_cm, width_cm, length_cm) tuples
                      representing ListingPackage-like objects. Empty list = use legacy.
            quantity: OrderItem.quantity
            legacy_dims: dict with weight_kg, height_cm, width_cm, length_cm for fallback
        """
        item = MagicMock()
        item.quantity = quantity

        listing = MagicMock()

        # Build mock packages
        mock_pkgs = []
        for w, h, wi, le in packages:
            pkg = MagicMock()
            pkg.weight_kg = Decimal(str(w))
            pkg.height_cm = Decimal(str(h))
            pkg.width_cm = Decimal(str(wi))
            pkg.length_cm = Decimal(str(le))
            mock_pkgs.append(pkg)

        listing.packages.all.return_value = mock_pkgs
        item.listing = listing

        # Legacy fallback dimensions
        if legacy_dims:
            item.weight_kg = Decimal(str(legacy_dims.get('weight_kg', 0)))
            item.height_cm = Decimal(str(legacy_dims.get('height_cm', 0)))
            item.width_cm = Decimal(str(legacy_dims.get('width_cm', 0)))
            item.length_cm = Decimal(str(legacy_dims.get('length_cm', 0)))
            listing.weight_kg = item.weight_kg
            listing.height_cm = item.height_cm
            listing.width_cm = item.width_cm
            listing.length_cm = item.length_cm
        else:
            item.weight_kg = None
            item.height_cm = None
            item.width_cm = None
            item.length_cm = None
            listing.weight_kg = None
            listing.height_cm = None
            listing.width_cm = None
            listing.length_cm = None

        return item

    def test_single_item_single_package_quantity_one(self):
        """One item, one package, quantity=1 → one volume."""
        item = self._make_item(packages=[(10, 50, 40, 80)], quantity=1)
        volumes = self.service._build_volumes_for_items([item])
        self.assertEqual(len(volumes), 1)
        self.assertEqual(volumes[0], {'height': 50, 'width': 40, 'length': 80, 'weight': 10.0})

    def test_single_item_single_package_quantity_three(self):
        """One item, one package, quantity=3 → three volumes."""
        item = self._make_item(packages=[(5, 30, 20, 40)], quantity=3)
        volumes = self.service._build_volumes_for_items([item])
        self.assertEqual(len(volumes), 3)
        for vol in volumes:
            self.assertEqual(vol, {'height': 30, 'width': 20, 'length': 40, 'weight': 5.0})

    def test_single_item_two_packages_quantity_two(self):
        """One item with 2 packages, quantity=2 → 2 packages × 2 qty = 4 volumes."""
        item = self._make_item(
            packages=[(10, 50, 40, 80), (5, 30, 25, 45)],
            quantity=2,
        )
        volumes = self.service._build_volumes_for_items([item])
        self.assertEqual(len(volumes), 4)

    def test_two_items_with_packages(self):
        """Two different items each with packages."""
        item1 = self._make_item(packages=[(8, 40, 30, 60)], quantity=1)
        item2 = self._make_item(packages=[(3, 20, 15, 25)], quantity=2)
        volumes = self.service._build_volumes_for_items([item1, item2])
        # 1 (item1: 1pkg × 1qty) + 2 (item2: 1pkg × 2qty) = 3
        self.assertEqual(len(volumes), 3)

    def test_legacy_fallback_no_packages(self):
        """Item with no packages → legacy dims used, one volume per quantity unit."""
        item = self._make_item(
            packages=[],
            quantity=2,
            legacy_dims={'weight_kg': 7, 'height_cm': 45, 'width_cm': 35, 'length_cm': 70},
        )
        volumes = self.service._build_volumes_for_items([item])
        self.assertEqual(len(volumes), 2)
        for vol in volumes:
            self.assertEqual(vol, {'height': 45, 'width': 35, 'length': 70, 'weight': 7.0})

    def test_dimensions_converted_to_int(self):
        """Fractional cm values must be rounded to int."""
        item = self._make_item(packages=[(5.5, 29.7, 19.3, 39.6)], quantity=1)
        vol = self.service._build_volumes_for_items([item])[0]
        self.assertIsInstance(vol['height'], int)
        self.assertIsInstance(vol['width'], int)
        self.assertIsInstance(vol['length'], int)
        self.assertEqual(vol['height'], 30)
        self.assertEqual(vol['width'], 19)
        self.assertEqual(vol['length'], 40)

    def test_weight_is_float_rounded_to_3dp(self):
        """Weight must remain float rounded to 3 decimal places."""
        item = self._make_item(packages=[(5.5555, 30, 20, 40)], quantity=1)
        vol = self.service._build_volumes_for_items([item])[0]
        self.assertIsInstance(vol['weight'], float)
        self.assertEqual(vol['weight'], 5.556)

    def test_empty_items_raises(self):
        """No items should raise an Exception."""
        with self.assertRaises(Exception):
            self.service._build_volumes_for_items([])

    def test_girth_warning_logged(self):
        """Package exceeding 200cm girth logs a warning."""
        # h=100, w=60, l=60 → girth = 100 + 2*(60+60) = 340
        item = self._make_item(packages=[(10, 100, 60, 60)], quantity=1)
        import logging
        with self.assertLogs('logistics.services.melhor_envio_service', level='WARNING') as cm:
            self.service._build_volumes_for_items([item])
        self.assertTrue(any('girth' in msg.lower() or '200' in msg for msg in cm.output))


class BuildVolumesForRawItemsTest(TestCase):
    """
    Unit tests for MelhorEnvioService._build_volumes_for_raw_items.

    Uses dicts with 'listing', 'quantity', 'dimensions' keys (pre-order flow).
    """

    def setUp(self):
        self.service = MelhorEnvioService.__new__(MelhorEnvioService)

    def _make_raw_item(self, packages, quantity=1, dimensions=None):
        listing = MagicMock()

        mock_pkgs = []
        for w, h, wi, le in packages:
            pkg = MagicMock()
            pkg.weight_kg = Decimal(str(w))
            pkg.height_cm = Decimal(str(h))
            pkg.width_cm = Decimal(str(wi))
            pkg.length_cm = Decimal(str(le))
            mock_pkgs.append(pkg)

        listing.packages.all.return_value = mock_pkgs
        listing.id = 999
        listing.seller_id = 1

        return {
            'listing': listing,
            'quantity': quantity,
            'dimensions': dimensions or {},
        }

    def test_packages_path_single(self):
        item = self._make_raw_item(packages=[(10, 50, 40, 80)], quantity=1)
        volumes = self.service._build_volumes_for_raw_items([item])
        self.assertEqual(len(volumes), 1)
        self.assertEqual(volumes[0]['height'], 50)

    def test_packages_multiplied_by_quantity(self):
        item = self._make_raw_item(packages=[(5, 30, 20, 40)], quantity=3)
        volumes = self.service._build_volumes_for_raw_items([item])
        self.assertEqual(len(volumes), 3)

    def test_legacy_fallback_via_dimensions_dict(self):
        dims = {'weight_kg': 6, 'height_cm': 35, 'width_cm': 25, 'length_cm': 55}
        item = self._make_raw_item(packages=[], quantity=2, dimensions=dims)
        volumes = self.service._build_volumes_for_raw_items([item])
        self.assertEqual(len(volumes), 2)
        self.assertEqual(volumes[0]['height'], 35)
        self.assertEqual(volumes[0]['weight'], 6.0)

    def test_empty_raises(self):
        with self.assertRaises(Exception):
            self.service._build_volumes_for_raw_items([])


# ---------------------------------------------------------------------------
# API Tests — Listing Package Endpoints
# ---------------------------------------------------------------------------

class ListingPackageAPITest(APITestCase):
    """Integration tests for ListingPackage REST endpoints."""

    def setUp(self):
        self.seller = make_user(email='api_seller@test.com', cpf='98765432100')
        self.other_user = make_user(email='other@test.com', cpf='12345678909')
        self.address = make_address(self.seller)
        self.listing = make_listing(self.seller, self.address, title='Equipamento de Crossfit Completo')

        # Add a base package
        self.pkg1 = ListingPackage.objects.create(
            listing=self.listing,
            weight_kg=Decimal('15.00'),
            height_cm=Decimal('60.00'),
            width_cm=Decimal('50.00'),
            length_cm=Decimal('100.00'),
            description='Caixa 1',
        )

    def _seller_client(self):
        client = APIClient()
        client.force_authenticate(user=self.seller)
        return client

    def _other_client(self):
        client = APIClient()
        client.force_authenticate(user=self.other_user)
        return client

    # --- GET list ---

    def _extract_results(self, response_data):
        """Handle both paginated (dict with 'results') and plain list responses."""
        if isinstance(response_data, dict) and 'results' in response_data:
            return response_data['results']
        return response_data

    def test_list_packages_public(self):
        """Anyone can list packages of a listing."""
        url = f'/api/products/listings/{self.listing.id}/packages/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        # The listing was created fresh in setUp — pkg1 must be in the results
        pkg_ids = [p['id'] for p in results]
        self.assertIn(self.pkg1.id, pkg_ids)
        # All returned packages belong to this listing
        db_pkg_ids = list(ListingPackage.objects.filter(listing=self.listing).values_list('id', flat=True))
        self.assertEqual(sorted(pkg_ids), sorted(db_pkg_ids))

    def test_list_packages_returns_all_packages(self):
        pkg2 = ListingPackage.objects.create(
            listing=self.listing,
            weight_kg=Decimal('8.00'),
            height_cm=Decimal('40.00'),
            width_cm=Decimal('30.00'),
            length_cm=Decimal('60.00'),
            description='Caixa 2',
        )
        url = f'/api/products/listings/{self.listing.id}/packages/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        pkg_ids = [p['id'] for p in results]
        self.assertIn(self.pkg1.id, pkg_ids)
        self.assertIn(pkg2.id, pkg_ids)

    def test_list_packages_404_for_nonexistent_listing(self):
        url = '/api/products/listings/99999/packages/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- POST (add package) ---

    def test_seller_can_add_package(self):
        client = self._seller_client()
        url = f'/api/products/listings/{self.listing.id}/packages/'
        payload = {
            'weight_kg': '8.00',
            'height_cm': '40.00',
            'width_cm': '30.00',
            'length_cm': '60.00',
            'description': 'Caixa 2',
        }
        response = client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self.listing.packages.count(), 2)

    def test_unauthenticated_cannot_add_package(self):
        url = f'/api/products/listings/{self.listing.id}/packages/'
        response = self.client.post(url, {'weight_kg': '5', 'height_cm': '20', 'width_cm': '15', 'length_cm': '30'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_other_user_cannot_add_package(self):
        client = self._other_client()
        url = f'/api/products/listings/{self.listing.id}/packages/'
        payload = {
            'weight_kg': '5.00',
            'height_cm': '20.00',
            'width_cm': '15.00',
            'length_cm': '30.00',
        }
        response = client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_package_validation_zero_weight(self):
        client = self._seller_client()
        url = f'/api/products/listings/{self.listing.id}/packages/'
        response = client.post(url, {
            'weight_kg': '0',
            'height_cm': '30',
            'width_cm': '20',
            'length_cm': '40',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('weight_kg', response.data)

    # --- GET detail ---

    def test_retrieve_package_public(self):
        url = f'/api/products/listings/{self.listing.id}/packages/{self.pkg1.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.pkg1.id)

    def test_retrieve_package_404_wrong_listing(self):
        other_listing = make_listing(self.seller, self.address, title='Outro Produto de Academia')
        url = f'/api/products/listings/{other_listing.id}/packages/{self.pkg1.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- PATCH (partial update) ---

    def test_seller_can_patch_package(self):
        client = self._seller_client()
        url = f'/api/products/listings/{self.listing.id}/packages/{self.pkg1.id}/'
        response = client.patch(url, {'weight_kg': '20.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.pkg1.refresh_from_db()
        self.assertEqual(self.pkg1.weight_kg, Decimal('20.00'))

    def test_other_user_cannot_patch_package(self):
        client = self._other_client()
        url = f'/api/products/listings/{self.listing.id}/packages/{self.pkg1.id}/'
        response = client.patch(url, {'weight_kg': '20.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- DELETE ---

    def test_seller_can_delete_non_last_package(self):
        """Should succeed when the listing still has another package."""
        pkg2 = ListingPackage.objects.create(
            listing=self.listing,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('25.00'),
            width_cm=Decimal('20.00'),
            length_cm=Decimal('35.00'),
        )
        client = self._seller_client()
        url = f'/api/products/listings/{self.listing.id}/packages/{pkg2.id}/'
        response = client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.listing.packages.count(), 1)

    def test_seller_cannot_delete_last_package(self):
        """Deleting the only package must be rejected."""
        client = self._seller_client()
        url = f'/api/products/listings/{self.listing.id}/packages/{self.pkg1.id}/'
        response = client.delete(url)
        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY
        ])
        self.assertEqual(self.listing.packages.count(), 1)

    def test_unauthenticated_cannot_delete_package(self):
        url = f'/api/products/listings/{self.listing.id}/packages/{self.pkg1.id}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# MarketplaceListingCreateSerializer Tests (packages field)
# ---------------------------------------------------------------------------

class ListingCreateWithPackagesTest(TestCase):
    """Tests for MarketplaceListingCreateSerializer package handling."""

    def setUp(self):
        from products.serializers import MarketplaceListingCreateSerializer
        self.serializer_class = MarketplaceListingCreateSerializer

        self.seller = make_user(email='create_seller@test.com', cpf='52998224725')
        self.address = make_address(self.seller)

        category = Category.objects.get_or_create(
            slug='cat-test', defaults={'name': 'Cat Test', 'is_active': True}
        )[0]
        series = Series.objects.get_or_create(
            slug='ser-test', defaults={'name': 'Ser Test'}
        )[0]
        self.product = Products.objects.get_or_create(
            slug='prod-test',
            defaults={'name': 'Prod Test', 'category': category, 'series': series}
        )[0]
        self.brand = Brand.objects.get_or_create(
            slug='brand-test', defaults={'name': 'Brand Test', 'is_active': True}
        )[0]
        self.condition = Condition.objects.get_or_create(
            slug='cond-test', defaults={'name': 'Cond Test'}
        )[0]

    def _mock_request(self, user):
        """Build a mock request object with a real authenticated user."""
        request = MagicMock()
        request.user = user
        return request

    def _valid_payload(self, packages=None):
        return {
            'product': self.product.id,
            'title': 'Supino Reto Profissional',
            'price': '850.00',
            'brand': self.brand.id,
            'quantity': 1,
            'description': 'Supino reto com regulagem de encosto e suporte para barras. Fabricado em aço.',
            'condition': self.condition.id,
            'packages': packages or [
                {
                    'weight_kg': '20.00',
                    'height_cm': '80.00',
                    'width_cm': '60.00',
                    'length_cm': '150.00',
                    'description': 'Estrutura principal',
                }
            ],
        }

    def test_missing_packages_field_fails(self):
        """
        Creating a listing without packages must fail.

        Tests validate_packages() directly — the field is required so omitting
        it results in a 'required' error on the packages field.
        """
        s = self.serializer_class(data={'packages': None})
        # We don't need a full valid payload — the 'packages' field being missing/None
        # should produce an error on 'packages'. DRF marks write_only ListSerializer
        # fields as required by default.
        # Directly call run_validators on an empty payload to check packages is required.
        minimal = {}
        s2 = self.serializer_class(data=minimal)
        s2.is_valid()
        self.assertIn('packages', s2.errors)

    def test_empty_packages_list_fails_via_validate_method(self):
        """
        validate_packages([]) must raise ValidationError.

        Tested by calling the method directly on the serializer instance.
        """
        s = self.serializer_class()
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            s.validate_packages([])


# ---------------------------------------------------------------------------
# MarketplaceListingUpdateSerializer Tests (packages replacement)
# ---------------------------------------------------------------------------

class ListingUpdateWithPackagesTest(TestCase):
    """Tests for MarketplaceListingUpdateSerializer package replacement."""

    def setUp(self):
        from products.serializers import MarketplaceListingUpdateSerializer
        self.serializer_class = MarketplaceListingUpdateSerializer

        self.seller = make_user(email='update_seller@test.com', cpf='11122233396')
        self.address = make_address(self.seller)
        self.listing = make_listing(self.seller, self.address, title='Estação de Musculação Completa')

        # Create initial packages
        self.pkg1 = ListingPackage.objects.create(
            listing=self.listing,
            weight_kg=Decimal('30.00'),
            height_cm=Decimal('120.00'),
            width_cm=Decimal('80.00'),
            length_cm=Decimal('60.00'),
            description='Caixa estrutura',
        )
        self.pkg2 = ListingPackage.objects.create(
            listing=self.listing,
            weight_kg=Decimal('15.00'),
            height_cm=Decimal('50.00'),
            width_cm=Decimal('40.00'),
            length_cm=Decimal('30.00'),
            description='Caixa acessórios',
        )

    def _mock_request(self, user):
        """Build a mock request object with a real authenticated user."""
        request = MagicMock()
        request.user = user
        return request

    def test_update_without_packages_keeps_existing(self):
        """Omitting packages in update should leave packages unchanged."""
        request = self._mock_request(self.seller)
        s = self.serializer_class(
            instance=self.listing,
            data={'title': 'Estação Atualizada - Alta Performance'},
            partial=True,
            context={'request': request},
        )
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.assertEqual(self.listing.packages.count(), 2)

    def test_update_with_packages_replaces_all(self):
        """Providing packages in update should replace all existing packages."""
        request = self._mock_request(self.seller)
        new_packages = [
            {
                'weight_kg': '10.00',
                'height_cm': '40.00',
                'width_cm': '30.00',
                'length_cm': '50.00',
                'description': 'Novo pacote único',
            }
        ]
        s = self.serializer_class(
            instance=self.listing,
            data={'packages': new_packages},
            partial=True,
            context={'request': request},
        )
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.assertEqual(self.listing.packages.count(), 1)
        pkg = self.listing.packages.first()
        self.assertEqual(pkg.weight_kg, Decimal('10.00'))
        self.assertEqual(pkg.description, 'Novo pacote único')

    def test_update_with_empty_packages_fails(self):
        """Providing an empty packages list must fail validation."""
        request = self._mock_request(self.seller)
        s = self.serializer_class(
            instance=self.listing,
            data={'packages': []},
            partial=True,
            context={'request': request},
        )
        self.assertFalse(s.is_valid())
        self.assertIn('packages', s.errors)

    def test_update_with_multiple_new_packages(self):
        """Providing 3 new packages replaces the existing 2."""
        request = self._mock_request(self.seller)
        new_packages = [
            {'weight_kg': '5', 'height_cm': '20', 'width_cm': '15', 'length_cm': '25'},
            {'weight_kg': '8', 'height_cm': '30', 'width_cm': '20', 'length_cm': '35'},
            {'weight_kg': '3', 'height_cm': '15', 'width_cm': '10', 'length_cm': '20'},
        ]
        s = self.serializer_class(
            instance=self.listing,
            data={'packages': new_packages},
            partial=True,
            context={'request': request},
        )
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.assertEqual(self.listing.packages.count(), 3)


# ---------------------------------------------------------------------------
# MarketplaceListingSerializer (read) includes packages
# ---------------------------------------------------------------------------

class ListingReadSerializerPackagesTest(TestCase):
    """Test that MarketplaceListingSerializer (read) includes packages."""

    def test_packages_included_in_read_serializer(self):
        from products.serializers import MarketplaceListingSerializer

        seller = make_user(email='read_seller@test.com', cpf='98765432100')
        address = make_address(seller, zipcode='04538133')
        listing = make_listing(seller, address, title='Hack Squat Profissional')

        ListingPackage.objects.create(
            listing=listing,
            weight_kg=Decimal('40.00'),
            height_cm=Decimal('90.00'),
            width_cm=Decimal('70.00'),
            length_cm=Decimal('120.00'),
        )
        ListingPackage.objects.create(
            listing=listing,
            weight_kg=Decimal('20.00'),
            height_cm=Decimal('50.00'),
            width_cm=Decimal('40.00'),
            length_cm=Decimal('60.00'),
        )

        data = MarketplaceListingSerializer(listing).data
        self.assertIn('packages', data)
        self.assertEqual(len(data['packages']), 2)
        for pkg_data in data['packages']:
            self.assertIn('id', pkg_data)
            self.assertIn('weight_kg', pkg_data)
            self.assertIn('height_cm', pkg_data)
