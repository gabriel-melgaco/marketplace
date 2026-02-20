"""
Testes para o endpoint GET /api/logistics/carrier-services/

Cobre:
- Retorno bem-sucedido de servicos do Melhor Envio
- Autenticacao obrigatoria (retorna 401 sem token)
- Tratamento de falha na API do Melhor Envio (retorna 400)
- Estrutura da resposta (services + count)
- Metodo get_available_services do MelhorEnvioService
"""

from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from authentication.models import CustomUser
from logistics.services.melhor_envio_service import MelhorEnvioService


SAMPLE_SERVICES = [
    {
        'id': 1,
        'name': 'PAC',
        'type': 'normal',
        'range': {'min': 1, 'max': 30000},
        'restrictions': {
            'requirements': {},
            'optionals': {},
        },
        'company': {
            'id': 1,
            'name': 'Correios',
            'picture': 'https://sandbox.melhorenvio.com.br/images/shipping-companies/correios.png',
        },
    },
    {
        'id': 2,
        'name': 'SEDEX',
        'type': 'express',
        'range': {'min': 1, 'max': 30000},
        'restrictions': {
            'requirements': {},
            'optionals': {},
        },
        'company': {
            'id': 1,
            'name': 'Correios',
            'picture': 'https://sandbox.melhorenvio.com.br/images/shipping-companies/correios.png',
        },
    },
    {
        'id': 3,
        'name': 'Jadlog .Package',
        'type': 'normal',
        'range': {'min': 1, 'max': 100000},
        'restrictions': {
            'requirements': {},
            'optionals': {},
        },
        'company': {
            'id': 2,
            'name': 'Jadlog',
            'picture': 'https://sandbox.melhorenvio.com.br/images/shipping-companies/jadlog.png',
        },
    },
]


class GetCarrierServicesViewTestCase(TestCase):
    """Testes para GET /api/logistics/carrier-services/"""

    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email='buyer@test.com',
            password='pass123',
            full_name='Test Buyer',
        )
        self.url = reverse('logistics:carrier-services')

    def test_unauthenticated_request_returns_401(self):
        """Requisicao sem autenticacao deve retornar 401."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch.object(MelhorEnvioService, 'get_available_services')
    def test_successful_response_returns_services_and_count(self, mock_get_services):
        """Resposta bem-sucedida deve incluir services e count."""
        mock_get_services.return_value = SAMPLE_SERVICES

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('services', response.data)
        self.assertIn('count', response.data)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(len(response.data['services']), 3)

    @patch.object(MelhorEnvioService, 'get_available_services')
    def test_services_contain_expected_fields(self, mock_get_services):
        """Cada servico deve ter os campos retornados pelo ME."""
        mock_get_services.return_value = SAMPLE_SERVICES

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first_service = response.data['services'][0]

        self.assertIn('id', first_service)
        self.assertIn('name', first_service)
        self.assertIn('company', first_service)

    @patch.object(MelhorEnvioService, 'get_available_services')
    def test_empty_services_returns_count_zero(self, mock_get_services):
        """Quando API retorna lista vazia, count deve ser 0."""
        mock_get_services.return_value = []

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['services'], [])

    @patch.object(MelhorEnvioService, 'get_available_services')
    def test_api_failure_returns_400(self, mock_get_services):
        """Falha na API do Melhor Envio deve retornar 400 com mensagem de erro."""
        mock_get_services.side_effect = Exception('Erro de conexao com Melhor Envio')

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('detail', response.data)

    @patch.object(MelhorEnvioService, 'get_available_services')
    def test_service_is_called_once(self, mock_get_services):
        """O servico MelhorEnvio deve ser chamado exatamente uma vez por requisicao."""
        mock_get_services.return_value = SAMPLE_SERVICES

        self.client.force_authenticate(user=self.user)
        self.client.get(self.url)

        mock_get_services.assert_called_once()

    def test_only_get_method_allowed(self):
        """Apenas metodo GET deve ser aceito."""
        self.client.force_authenticate(user=self.user)

        response_post = self.client.post(self.url, data={})
        response_put = self.client.put(self.url, data={})
        response_delete = self.client.delete(self.url)

        self.assertEqual(response_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response_delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class MelhorEnvioGetAvailableServicesTestCase(TestCase):
    """Testes unitarios para MelhorEnvioService.get_available_services()"""

    def setUp(self):
        self.service = MelhorEnvioService()

    @patch('logistics.services.melhor_envio_service.requests.get')
    def test_successful_call_returns_service_list(self, mock_get):
        """Chamada bem-sucedida deve retornar lista de servicos."""
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_SERVICES
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with patch.object(self.service, '_get_headers', return_value={'Authorization': 'Bearer test'}):
            result = self.service.get_available_services()

        self.assertEqual(result, SAMPLE_SERVICES)
        mock_get.assert_called_once()

    @patch('logistics.services.melhor_envio_service.requests.get')
    def test_http_error_raises_exception(self, mock_get):
        """Erro HTTP deve levantar excecao com mensagem clara."""
        import requests as req
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {'message': 'Unauthenticated'}
        http_error = req.exceptions.HTTPError(response=mock_response)
        mock_get.return_value = MagicMock(raise_for_status=MagicMock(side_effect=http_error))

        with patch.object(self.service, '_get_headers', return_value={'Authorization': 'Bearer test'}):
            with self.assertRaises(Exception) as ctx:
                self.service.get_available_services()

        self.assertIn('Erro ao buscar servicos Melhor Envio', str(ctx.exception))

    @patch('logistics.services.melhor_envio_service.requests.get')
    def test_connection_error_raises_exception(self, mock_get):
        """Erro de conexao deve levantar excecao com mensagem clara."""
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError('Connection refused')

        with patch.object(self.service, '_get_headers', return_value={'Authorization': 'Bearer test'}):
            with self.assertRaises(Exception) as ctx:
                self.service.get_available_services()

        self.assertIn('Erro de conexao ao buscar servicos Melhor Envio', str(ctx.exception))

    @patch('logistics.services.melhor_envio_service.requests.get')
    def test_calls_correct_endpoint(self, mock_get):
        """Deve chamar o endpoint correto /api/v2/me/shipment/services."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with patch.object(self.service, '_get_headers', return_value={'Authorization': 'Bearer test'}):
            self.service.get_available_services()

        call_args = mock_get.call_args
        called_url = call_args[0][0] if call_args[0] else call_args[1].get('url', '')
        self.assertIn('/me/shipment/services', called_url)

    @patch('logistics.services.melhor_envio_service.requests.get')
    def test_uses_fallback_headers_no_oauth(self, mock_get):
        """get_available_services nao exige OAuth (nao usa require_oauth=True)."""
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_SERVICES
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # _get_headers() sem require_oauth deve ser chamado (fallback permitido)
        with patch.object(
            self.service, '_get_headers',
            return_value={'Authorization': 'Bearer legacy'}
        ) as mock_headers:
            self.service.get_available_services()

        # Deve ter sido chamado sem require_oauth=True
        mock_headers.assert_called_once_with()


class CarrierServicesUrlRemovedTestCase(TestCase):
    """Verifica que os endpoints de carrier rules nao existem mais."""

    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email='admin@test.com',
            password='pass123',
            full_name='Admin User',
            is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

    def test_old_carrier_rules_list_endpoint_not_found(self):
        """POST /api/logistics/carrier-rules/ nao deve existir."""
        response = self.client.post('/api/logistics/carrier-rules/', data={
            'carrier_name': 'Nova Transportadora',
            'modality': 'Nova Modalidade',
        }, content_type='application/json')
        # Deve retornar 404 (rota nao existe) ou 405 (metodo nao permitido)
        self.assertIn(response.status_code, [
            status.HTTP_404_NOT_FOUND,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        ])

    def test_validate_package_endpoint_not_found(self):
        """POST /api/logistics/carrier-rules/validate-package/ nao deve mais existir."""
        response = self.client.post('/api/logistics/carrier-rules/validate-package/', data={
            'height': 30,
            'width': 25,
            'length': 40,
            'weight': 5.5,
        }, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
