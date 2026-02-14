from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from authentication.models import CustomUser
from logistics.models import Address
from products.models import (
    Category, Series, Products, Brand, Condition, MarketplaceListing
)


class ListingTitleTestBase(TestCase):
    """Base com fixtures comuns para testes de title em Listing."""

    def setUp(self):
        self.client = APIClient()

        self.user = CustomUser.objects.create_user(
            email='seller@test.com',
            password='Test1234!',
            full_name='Vendedor Teste',
            cpf='123.456.789-00',
        )

        self.shipping_address = Address.objects.create(
            user=self.user,
            address_type='shipping',
            nickname='Depósito',
            recipient_name='Vendedor Teste',
            recipient_phone='11999999999',
            street='Rua A',
            number='100',
            neighborhood='Centro',
            city='São Paulo',
            state='SP',
            zipcode='01001000',
            is_shipping_address=True,
            is_active=True,
        )

        self.category = Category.objects.create(name='Musculação', slug='musculacao')
        self.series = Series.objects.create(name='Série A', slug='serie-a')
        self.product = Products.objects.create(
            name='Barra Olímpica',
            slug='barra-olimpica',
            category=self.category,
            series=self.series,
        )
        self.brand = Brand.objects.create(name='Marca X', slug='marca-x')
        self.condition = Condition.objects.create(name='Novo', slug='novo')

        self.listing_data = {
            'product': self.product.pk,
            'title': 'Barra Olímpica 20kg - Seminova',
            'price': '150.00',
            'brand': self.brand.pk,
            'quantity': 2,
            'description': 'Barra olímpica em ótimo estado, pouco uso, com presilhas inclusas.',
            'condition': self.condition.pk,
            'weight_kg': '20.00',
            'height_cm': '10.00',
            'width_cm': '10.00',
            'length_cm': '220.00',
            'shipping_address': self.shipping_address.pk,
        }


class ListingCreateTitleTest(ListingTitleTestBase):

    def test_create_listing_with_title(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/products/listings/create/', self.listing_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], self.listing_data['title'])

        listing = MarketplaceListing.objects.latest('pk')
        self.assertEqual(listing.title, self.listing_data['title'])

    def test_create_listing_without_title_fails(self):
        self.client.force_authenticate(user=self.user)
        data = self.listing_data.copy()
        del data['title']
        response = self.client.post('/api/products/listings/create/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('title', response.data)

    def test_create_listing_title_too_short(self):
        self.client.force_authenticate(user=self.user)
        data = self.listing_data.copy()
        data['title'] = 'ab'
        response = self.client.post('/api/products/listings/create/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('title', response.data)

    def test_create_listing_title_max_length(self):
        self.client.force_authenticate(user=self.user)
        data = self.listing_data.copy()
        data['title'] = 'A' * 151
        response = self.client.post('/api/products/listings/create/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('title', response.data)


class ListingUpdateTitleTest(ListingTitleTestBase):

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user)
        self.client.post('/api/products/listings/create/', self.listing_data, format='json')
        self.listing_id = MarketplaceListing.objects.latest('pk').pk

    def test_update_title(self):
        new_title = 'Barra Olímpica 20kg - Nova'
        response = self.client.patch(
            f'/api/products/listings/{self.listing_id}/update/',
            {'title': new_title},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], new_title)

    def test_update_title_too_short(self):
        response = self.client.patch(
            f'/api/products/listings/{self.listing_id}/update/',
            {'title': 'ab'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('title', response.data)


class ListingReadTitleTest(ListingTitleTestBase):

    def setUp(self):
        super().setUp()
        self.listing = MarketplaceListing.objects.create(
            product=self.product,
            seller=self.user,
            title='Anúncio Teste Leitura',
            price=Decimal('200.00'),
            brand=self.brand,
            quantity=1,
            description='Descrição do anúncio com mais de trinta caracteres obrigatórios.',
            condition=self.condition,
            weight_kg=Decimal('15.00'),
            height_cm=Decimal('20.00'),
            width_cm=Decimal('30.00'),
            length_cm=Decimal('100.00'),
            shipping_address=self.shipping_address,
        )

    def test_listing_list_contains_title(self):
        response = self.client.get('/api/products/listings/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data if isinstance(response.data, list) else response.data.get('results', [])
        listing_data = next(
            (item for item in results if item['id'] == self.listing.pk), None
        )
        self.assertIsNotNone(listing_data)
        self.assertEqual(listing_data['title'], 'Anúncio Teste Leitura')

    def test_listing_detail_contains_title(self):
        response = self.client.get(f'/api/products/listings/{self.listing.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Anúncio Teste Leitura')

    def test_my_listings_contains_title(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/products/my-listings/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data if isinstance(response.data, list) else response.data.get('results', [])
        listing_data = next(
            (item for item in results if item['id'] == self.listing.pk), None
        )
        self.assertIsNotNone(listing_data)
        self.assertEqual(listing_data['title'], 'Anúncio Teste Leitura')


class ListingSearchTitleTest(ListingTitleTestBase):

    def setUp(self):
        super().setUp()
        MarketplaceListing.objects.create(
            product=self.product,
            seller=self.user,
            title='Supino Reto Profissional',
            price=Decimal('500.00'),
            brand=self.brand,
            quantity=1,
            description='Banco supino reto profissional para academia completa.',
            condition=self.condition,
            weight_kg=Decimal('25.00'),
            height_cm=Decimal('50.00'),
            width_cm=Decimal('60.00'),
            length_cm=Decimal('150.00'),
            shipping_address=self.shipping_address,
        )

    def test_search_by_title(self):
        response = self.client.get('/api/products/search/', {'q': 'Supino Reto'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) > 0)
        self.assertEqual(response.data['results'][0]['title'], 'Supino Reto Profissional')


# =================== Shipping Address Tests ===================
class ListingShippingAddressTestBase(TestCase):
    """Base class for shipping_address tests"""

    def setUp(self):
        self.client = APIClient()

        # Create seller with shipping address
        self.seller = CustomUser.objects.create_user(
            email='seller@test.com',
            password='Test1234!',
            full_name='Vendedor Teste',
            cpf='123.456.789-00',
        )

        self.shipping_address = Address.objects.create(
            user=self.seller,
            address_type='shipping',
            nickname='Depósito Principal',
            recipient_name='Vendedor Teste',
            recipient_phone='11999999999',
            street='Rua A',
            number='100',
            neighborhood='Centro',
            city='São Paulo',
            state='SP',
            zipcode='01001000',
            is_shipping_address=True,
            is_active=True,
        )

        # Create another address that is NOT a shipping address
        self.home_address = Address.objects.create(
            user=self.seller,
            address_type='home',
            nickname='Casa',
            recipient_name='Vendedor Teste',
            recipient_phone='11888888888',
            street='Rua B',
            number='200',
            neighborhood='Jardim',
            city='São Paulo',
            state='SP',
            zipcode='02002000',
            is_shipping_address=False,
            is_active=True,
        )

        # Create another user to test ownership validation
        self.other_user = CustomUser.objects.create_user(
            email='other@test.com',
            password='Test1234!',
            full_name='Outro Usuario',
            cpf='987.654.321-00',
        )

        self.other_user_address = Address.objects.create(
            user=self.other_user,
            address_type='shipping',
            nickname='Depósito Outro',
            recipient_name='Outro Usuario',
            recipient_phone='11777777777',
            street='Rua C',
            number='300',
            neighborhood='Vila',
            city='Rio de Janeiro',
            state='RJ',
            zipcode='03003000',
            is_shipping_address=True,
            is_active=True,
        )

        # Create product fixtures
        self.category = Category.objects.create(name='Musculação', slug='musculacao')
        self.series = Series.objects.create(name='Série A', slug='serie-a')
        self.product = Products.objects.create(
            name='Barra Olímpica',
            slug='barra-olimpica',
            category=self.category,
            series=self.series,
        )
        self.brand = Brand.objects.create(name='Marca X', slug='marca-x')
        self.condition = Condition.objects.create(name='Novo', slug='novo')

        self.base_listing_data = {
            'product': self.product.pk,
            'title': 'Barra Olímpica 20kg - Nova',
            'price': '150.00',
            'brand': self.brand.pk,
            'quantity': 2,
            'description': 'Barra olímpica em ótimo estado, pouco uso, com presilhas inclusas.',
            'condition': self.condition.pk,
            'weight_kg': '20.00',
            'height_cm': '10.00',
            'width_cm': '10.00',
            'length_cm': '220.00',
        }


class ListingShippingAddressCreateTest(ListingShippingAddressTestBase):
    """Tests for creating listings with shipping_address"""

    def test_create_listing_with_shipping_address(self):
        """Test creating a listing with a valid shipping address"""
        self.client.force_authenticate(user=self.seller)
        data = self.base_listing_data.copy()
        data['shipping_address'] = self.shipping_address.pk

        response = self.client.post('/api/products/listings/create/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, f"Response: {response.data}")
        self.assertIn('shipping_address', response.data, f"Keys: {list(response.data.keys())}")
        self.assertEqual(response.data['shipping_address'], self.shipping_address.id)

        # Verify the listing was created with the correct address
        listing = MarketplaceListing.objects.latest('created_at')
        self.assertEqual(listing.shipping_address, self.shipping_address)

    def test_create_listing_without_shipping_address_fails(self):
        """Test creating a listing without shipping_address fails"""
        self.client.force_authenticate(user=self.seller)
        data = self.base_listing_data.copy()
        # Don't include shipping_address

        response = self.client.post('/api/products/listings/create/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('shipping_address', response.data)

    def test_create_listing_with_other_user_address_fails(self):
        """Test creating a listing with an address that doesn't belong to the user fails"""
        self.client.force_authenticate(user=self.seller)
        data = self.base_listing_data.copy()
        data['shipping_address'] = self.other_user_address.pk

        response = self.client.post('/api/products/listings/create/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('shipping_address', response.data)
        self.assertIn('não pertence a você', str(response.data['shipping_address']))

    def test_create_listing_with_non_shipping_address_fails(self):
        """Test creating a listing with a non-shipping address fails"""
        self.client.force_authenticate(user=self.seller)
        data = self.base_listing_data.copy()
        data['shipping_address'] = self.home_address.pk

        response = self.client.post('/api/products/listings/create/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('shipping_address', response.data)
        self.assertIn('não é um endereço de envio', str(response.data['shipping_address']))

    def test_create_listing_with_inactive_address_fails(self):
        """Test creating a listing with an inactive address fails"""
        self.client.force_authenticate(user=self.seller)

        # Deactivate the shipping address
        self.shipping_address.is_active = False
        self.shipping_address.save()

        data = self.base_listing_data.copy()
        data['shipping_address'] = self.shipping_address.pk

        response = self.client.post('/api/products/listings/create/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('shipping_address', response.data)
        self.assertIn('inativo', str(response.data['shipping_address']))


class ListingShippingAddressUpdateTest(ListingShippingAddressTestBase):
    """Tests for updating listings with shipping_address"""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.seller)

        # Create a second shipping address for the seller first (before creating listing)
        self.second_shipping_address = Address.objects.create(
            user=self.seller,
            address_type='shipping',
            nickname='Depósito Secundário',
            recipient_name='Vendedor Teste',
            recipient_phone='11999999999',
            street='Rua D',
            number='400',
            neighborhood='Centro',
            city='São Paulo',
            state='SP',
            zipcode='04004000',
            is_shipping_address=True,
            is_active=True,
        )

        # Create a listing
        data = self.base_listing_data.copy()
        data['shipping_address'] = self.shipping_address.pk
        response = self.client.post('/api/products/listings/create/', data, format='json')

        # Get the created listing ID from database
        self.listing = MarketplaceListing.objects.latest('created_at')
        self.listing_id = self.listing.pk

    def test_update_listing_shipping_address(self):
        """Test updating a listing's shipping_address to another valid address"""
        response = self.client.patch(
            f'/api/products/listings/{self.listing_id}/update/',
            {'shipping_address': self.second_shipping_address.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['shipping_address'], self.second_shipping_address.id)

        listing = MarketplaceListing.objects.get(id=self.listing_id)
        self.assertEqual(listing.shipping_address, self.second_shipping_address)

    def test_update_listing_with_other_user_address_fails(self):
        """Test updating a listing with another user's address fails"""
        response = self.client.patch(
            f'/api/products/listings/{self.listing_id}/update/',
            {'shipping_address': self.other_user_address.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('shipping_address', response.data)

    def test_update_listing_with_non_shipping_address_fails(self):
        """Test updating a listing with a non-shipping address fails"""
        response = self.client.patch(
            f'/api/products/listings/{self.listing_id}/update/',
            {'shipping_address': self.home_address.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('shipping_address', response.data)


class ListingShippingAddressReadTest(ListingShippingAddressTestBase):
    """Tests for reading listings with shipping_address"""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.seller)

        # Create a listing
        self.listing = MarketplaceListing.objects.create(
            product=self.product,
            seller=self.seller,
            title='Anúncio com Endereço',
            price=Decimal('200.00'),
            brand=self.brand,
            quantity=1,
            description='Descrição do anúncio com mais de trinta caracteres obrigatórios.',
            condition=self.condition,
            weight_kg=Decimal('15.00'),
            height_cm=Decimal('20.00'),
            width_cm=Decimal('30.00'),
            length_cm=Decimal('100.00'),
            shipping_address=self.shipping_address,
        )

    def test_listing_detail_includes_shipping_address(self):
        """Test that listing detail includes shipping_address data"""
        response = self.client.get(f'/api/products/listings/{self.listing.pk}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('shipping_address', response.data)
        self.assertEqual(response.data['shipping_address']['id'], self.shipping_address.id)
        self.assertEqual(response.data['shipping_address']['zipcode'], self.shipping_address.zipcode)
        self.assertEqual(response.data['shipping_address']['city'], self.shipping_address.city)

    def test_listing_list_includes_shipping_address(self):
        """Test that listing list includes shipping_address data"""
        response = self.client.get('/api/products/listings/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data if isinstance(response.data, list) else response.data.get('results', [])

        listing_data = next((item for item in results if item['id'] == self.listing.pk), None)
        self.assertIsNotNone(listing_data)
        self.assertIn('shipping_address', listing_data)
        self.assertEqual(listing_data['shipping_address']['id'], self.shipping_address.id)


class ListingShippingAddressFreightCalculationTest(ListingShippingAddressTestBase):
    """Tests for freight calculation using listing's shipping_address"""

    def setUp(self):
        super().setUp()

        # Create buyer
        self.buyer = CustomUser.objects.create_user(
            email='buyer@test.com',
            password='Test1234!',
            full_name='Comprador Teste',
            cpf='111.222.333-44',
        )

        # Create buyer's shipping address
        self.buyer_address = Address.objects.create(
            user=self.buyer,
            address_type='home',
            nickname='Casa',
            recipient_name='Comprador Teste',
            recipient_phone='11888888888',
            street='Rua Destino',
            number='500',
            neighborhood='Bairro',
            city='Rio de Janeiro',
            state='RJ',
            zipcode='20000000',
            is_active=True,
        )

        # Create listing with shipping address
        self.listing = MarketplaceListing.objects.create(
            product=self.product,
            seller=self.seller,
            title='Produto para Teste de Frete',
            price=Decimal('100.00'),
            brand=self.brand,
            quantity=1,
            description='Produto para testar cálculo de frete usando shipping_address.',
            condition=self.condition,
            weight_kg=Decimal('5.00'),
            height_cm=Decimal('15.00'),
            width_cm=Decimal('20.00'),
            length_cm=Decimal('30.00'),
            shipping_address=self.shipping_address,
        )

        # Create cart and add item
        from orders.models import Cart, CartItem
        self.cart = Cart.objects.create(user=self.buyer)
        self.cart_item = CartItem.objects.create(
            cart=self.cart,
            listing=self.listing,
            quantity=1,
        )

    def test_freight_calculation_uses_listing_shipping_address(self):
        """
        Test that freight calculation uses the listing's shipping_address
        instead of dynamically looking up the seller's shipping address
        """
        self.client.force_authenticate(user=self.buyer)

        # This test validates that the freight calculation endpoint works
        # with the listing's shipping_address. We're not testing the Melhor Envio API
        # response here, just that the address is correctly passed.

        # The test will call the calculate shipping endpoint
        # We expect it to use self.shipping_address (from the listing)
        # instead of dynamically querying for the seller's shipping address

        # Note: This test may fail if Melhor Envio API is not available in sandbox
        # but it validates that the correct address is being used
        from unittest.mock import patch, MagicMock

        with patch('logistics.services.melhor_envio_service.MelhorEnvioService.calculate_shipping') as mock_calc:
            # Mock the API response
            mock_calc.return_value = []

            response = self.client.post(
                '/api/logistics/shipping/calculate/',
                {'shipping_address_id': self.buyer_address.id},
                format='json'
            )

            # Verify the call was made
            self.assertEqual(mock_calc.call_count, 1)

            # Verify the from_zipcode matches the listing's shipping_address
            call_args = mock_calc.call_args
            from_zipcode_used = call_args[1]['from_zipcode']

            # The zipcode should be from the listing's shipping_address
            self.assertEqual(
                from_zipcode_used.replace('-', ''),
                self.shipping_address.zipcode.replace('-', '')
            )
