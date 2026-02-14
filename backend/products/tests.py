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

        Address.objects.create(
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
        )

    def test_search_by_title(self):
        response = self.client.get('/api/products/search/', {'q': 'Supino Reto'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) > 0)
        self.assertEqual(response.data['results'][0]['title'], 'Supino Reto Profissional')
