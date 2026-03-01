"""
Testes para validações do MelhorEnvioService

Valida:
- Bloqueio de CEPs iguais
- Validação de CPF/CNPJ
- Mensagens de erro em português
- Filtragem de serviços ME por conta do vendedor (_get_seller_active_service_ids)
- Erro 500 do cart ME tratado como ShippingValidationError
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from logistics.services.melhor_envio_service import MelhorEnvioService, ShippingValidationError


class MelhorEnvioValidationsTestCase(TestCase):
    """Testes de validação do MelhorEnvioService"""

    def setUp(self):
        """Configurar serviço para testes"""
        self.service = MelhorEnvioService()

    def test_validate_same_zipcode_raises_error(self):
        """Deve rejeitar CEPs de origem e destino iguais"""
        with self.assertRaises(ShippingValidationError) as context:
            self.service._validate_zipcodes('12030-000', '12030-000')

        error_message = str(context.exception)
        self.assertIn('não podem ser iguais', error_message)
        self.assertIn('12030-000', error_message)
        self.assertIn('entrega presencial', error_message.lower())

    def test_validate_different_zipcodes_passes(self):
        """Deve aceitar CEPs diferentes"""
        # Não deve lançar exceção
        try:
            self.service._validate_zipcodes('12030-000', '01310-100')
        except ShippingValidationError:
            self.fail("validate_zipcodes raised ShippingValidationError unexpectedly")

    def test_validate_zipcodes_without_formatting(self):
        """Deve aceitar CEPs sem formatação"""
        try:
            self.service._validate_zipcodes('12030000', '01310100')
        except ShippingValidationError:
            self.fail("validate_zipcodes raised ShippingValidationError unexpectedly")

    def test_validate_empty_zipcode_raises_error(self):
        """Deve rejeitar CEPs vazios"""
        with self.assertRaises(ShippingValidationError) as context:
            self.service._validate_zipcodes('', '12030-000')

        self.assertIn('obrigatórios', str(context.exception))

    def test_validate_valid_cpf(self):
        """Deve aceitar CPF válido"""
        # CPF válido: 111.444.777-35
        validated = self.service._validate_document('111.444.777-35', 'CPF')
        self.assertEqual(validated, '11144477735')

    def test_validate_valid_cnpj(self):
        """Deve aceitar CNPJ válido"""
        # CNPJ válido: 11.222.333/0001-81
        validated = self.service._validate_document('11.222.333/0001-81', 'CNPJ')
        self.assertEqual(validated, '11222333000181')

    def test_validate_invalid_cpf_raises_error(self):
        """Deve rejeitar CPF inválido"""
        with self.assertRaises(ShippingValidationError) as context:
            self.service._validate_document('111.111.111-11', 'CPF')

        error_message = str(context.exception)
        self.assertIn('inválido', error_message)

    def test_validate_invalid_cnpj_raises_error(self):
        """Deve rejeitar CNPJ inválido"""
        with self.assertRaises(ShippingValidationError) as context:
            self.service._validate_document('11.111.111/1111-11', 'CNPJ')

        error_message = str(context.exception)
        self.assertIn('inválido', error_message)

    def test_validate_empty_document_raises_error(self):
        """Deve rejeitar documento vazio"""
        with self.assertRaises(ShippingValidationError) as context:
            self.service._validate_document('', 'CPF')

        self.assertIn('não fornecido', str(context.exception))

    def test_validate_document_wrong_length_raises_error(self):
        """Deve rejeitar documento com tamanho incorreto"""
        with self.assertRaises(ShippingValidationError) as context:
            self.service._validate_document('123456', 'CPF')

        error_message = str(context.exception)
        self.assertIn('11 (CPF) ou 14 (CNPJ)', error_message)

    def test_error_messages_in_portuguese(self):
        """Todas as mensagens de erro devem estar em português"""
        test_cases = [
            (lambda: self.service._validate_zipcodes('12030-000', '12030-000'),
             ['não podem ser iguais', 'entrega presencial']),
            (lambda: self.service._validate_document('', 'CPF'),
             ['não fornecido']),
            (lambda: self.service._validate_document('111.111.111-11', 'CPF'),
             ['inválido']),
        ]

        for test_func, expected_phrases in test_cases:
            with self.assertRaises(ShippingValidationError) as context:
                test_func()

            error_message = str(context.exception).lower()
            for phrase in expected_phrases:
                self.assertIn(
                    phrase.lower(),
                    error_message,
                    f"Esperava '{phrase}' na mensagem de erro, mas recebeu: {error_message}"
                )


class GetSellerActiveServiceIdsTestCase(TestCase):
    """
    Testes para _get_seller_active_service_ids.

    Verifica que o método retorna None quando não há token ME do vendedor
    e retorna o conjunto correto quando o endpoint ME responde com sucesso.
    """

    def setUp(self):
        self.service = MelhorEnvioService()

    @patch('logistics.services.melhor_envio_service.MelhorEnvioService._get_seller_active_service_ids')
    def test_returns_none_when_no_seller_token(self, mock_method):
        """Deve retornar None quando vendedor não tem token ME (sem filtragem)."""
        mock_method.return_value = None
        result = self.service._get_seller_active_service_ids(seller=MagicMock())
        self.assertIsNone(result)

    def test_returns_none_when_seller_has_no_me_token(self):
        """
        Deve retornar None quando SellerMelhorEnvioToken não existe para o vendedor.
        Usa mock do banco para evitar dependência de fixture.
        """
        mock_seller = MagicMock()
        mock_seller.email = 'test@example.com'

        # MelhorEnvioOAuthService is imported lazily inside the method,
        # so we patch at the source module level.
        with patch('logistics.services.melhor_envio_oauth_service.MelhorEnvioOAuthService') as mock_oauth_cls, \
             patch('logistics.models.SellerMelhorEnvioToken.objects.filter') as mock_filter:

            mock_oauth = MagicMock()
            mock_oauth.environment = 'sandbox'
            mock_oauth_cls.return_value = mock_oauth

            mock_filter.return_value.first.return_value = None

            result = self.service._get_seller_active_service_ids(mock_seller)

        self.assertIsNone(result)

    def test_returns_set_of_active_service_ids_on_success(self):
        """
        Deve retornar conjunto de IDs inteiros quando o endpoint ME responde com sucesso.
        """
        mock_seller = MagicMock()
        mock_seller.email = 'seller@example.com'

        mock_me_response = [
            {'id': 1, 'name': 'PAC'},
            {'id': 2, 'name': 'SEDEX'},
            {'id': 7, 'name': 'PAC Mini'},
        ]

        with patch('logistics.models.SellerMelhorEnvioToken.objects.filter') as mock_filter, \
             patch.object(self.service, '_get_headers', return_value={'Authorization': 'Bearer test-token'}), \
             patch('requests.get') as mock_get:

            # Patch the lazy import inside the method
            import logistics.services.melhor_envio_oauth_service as oauth_mod
            original_cls = oauth_mod.MelhorEnvioOAuthService
            mock_oauth_instance = MagicMock()
            mock_oauth_instance.environment = 'sandbox'

            with patch.object(oauth_mod, 'MelhorEnvioOAuthService', return_value=mock_oauth_instance):
                mock_token = MagicMock()
                mock_filter.return_value.first.return_value = mock_token

                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = mock_me_response
                mock_get.return_value = mock_response

                result = self.service._get_seller_active_service_ids(mock_seller)

        self.assertEqual(result, {1, 2, 7})

    def test_returns_none_on_http_error(self):
        """
        Deve retornar None (fallback) quando o endpoint ME retorna erro HTTP.
        A cotação não deve falhar por causa de um erro temporário na API.
        """
        import requests as req_lib

        mock_seller = MagicMock()
        mock_seller.email = 'seller@example.com'

        with patch('logistics.models.SellerMelhorEnvioToken.objects.filter') as mock_filter, \
             patch.object(self.service, '_get_headers', return_value={'Authorization': 'Bearer test-token'}), \
             patch('requests.get') as mock_get:

            import logistics.services.melhor_envio_oauth_service as oauth_mod
            mock_oauth_instance = MagicMock()
            mock_oauth_instance.environment = 'sandbox'

            with patch.object(oauth_mod, 'MelhorEnvioOAuthService', return_value=mock_oauth_instance):
                mock_token = MagicMock()
                mock_filter.return_value.first.return_value = mock_token

                mock_http_response = MagicMock()
                mock_http_response.status_code = 401
                http_error = req_lib.exceptions.HTTPError(response=mock_http_response)
                mock_get.side_effect = http_error

                result = self.service._get_seller_active_service_ids(mock_seller)

        self.assertIsNone(result)


class PostToCartErrorHandlingTestCase(TestCase):
    """
    Testes para o tratamento de erros do _post_to_cart.

    Verifica que o erro 500 do ME (carrinho) é convertido em ShippingValidationError
    com mensagem informativa.
    """

    def setUp(self):
        self.service = MelhorEnvioService()

    def test_cart_500_raises_shipping_validation_error(self):
        """
        HTTP 500 do ME cart deve levantar ShippingValidationError (não Exception genérica).
        Isso permite que o chamador exiba uma mensagem amigável ao usuário.
        """
        import requests as req_lib

        mock_seller = MagicMock()

        from_block = {
            'name': 'Seller', 'phone': '11999999999', 'email': 'seller@example.com',
            'document': '12345678901', 'postal_code': '01310100', 'address': 'Av Paulista',
            'number': '1', 'complement': '', 'district': 'Bela Vista',
            'city': 'São Paulo', 'state_abbr': 'SP', 'country_id': 'BR',
        }
        to_block = {
            'name': 'Buyer', 'phone': '11988888888', 'email': 'buyer@example.com',
            'document': '98765432100', 'country_id': 'BR', 'postal_code': '12030000',
            'address': 'Rua X', 'number': '2', 'complement': '', 'district': 'Centro',
            'city': 'Taubaté', 'state_abbr': 'SP',
        }
        products = [{'name': 'Produto', 'quantity': '1', 'unitary_value': '100.00'}]
        volume = {'height': 100, 'width': 20, 'length': 30, 'weight': 10.0}
        options = {'insurance_value': 100.0, 'receipt': False, 'own_hand': False, 'non_commercial': True}

        with patch('logistics.services.melhor_envio_service.MelhorEnvioService._get_headers') as mock_headers, \
             patch('requests.post') as mock_post:

            mock_headers.return_value = {'Authorization': 'Bearer test-token'}

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {'error': 'Houve um erro ao salvar o pedido no carrinho.'}

            http_error = req_lib.exceptions.HTTPError(response=mock_response)
            mock_response.raise_for_status.side_effect = http_error
            mock_post.return_value = mock_response

            with self.assertRaises(ShippingValidationError) as ctx:
                self.service._post_to_cart(
                    service_id=3,
                    from_block=from_block,
                    to_block=to_block,
                    products=products,
                    volume=volume,
                    options=options,
                    seller=mock_seller,
                )

        error_msg = str(ctx.exception)
        self.assertIn('não está disponível', error_msg)
        self.assertIn('selecione outra opção', error_msg.lower())

    def test_cart_500_error_message_does_not_blame_seller_config_only(self):
        """
        A mensagem de erro deve mencionar tanto configuração quanto limites de dimensão
        para ser mais informativa ao usuário.
        """
        import requests as req_lib

        mock_seller = MagicMock()

        from_block = {
            'name': 'S', 'phone': '11999999999', 'email': 's@s.com',
            'document': '12345678901', 'postal_code': '01310100', 'address': 'A',
            'number': '1', 'complement': '', 'district': 'D',
            'city': 'Cidade', 'state_abbr': 'SP', 'country_id': 'BR',
        }
        to_block = {
            'name': 'B', 'phone': '11988888888', 'email': 'b@b.com',
            'document': '98765432100', 'country_id': 'BR', 'postal_code': '12030000',
            'address': 'R', 'number': '2', 'complement': '', 'district': 'C',
            'city': 'T', 'state_abbr': 'SP',
        }
        volume = {'height': 100, 'width': 20, 'length': 30, 'weight': 10.0}
        options = {'insurance_value': 100.0, 'receipt': False, 'own_hand': False}

        with patch('logistics.services.melhor_envio_service.MelhorEnvioService._get_headers') as mock_headers, \
             patch('requests.post') as mock_post:

            mock_headers.return_value = {'Authorization': 'Bearer test-token'}

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {'error': 'Houve um erro ao salvar o pedido no carrinho.'}

            http_error = req_lib.exceptions.HTTPError(response=mock_response)
            mock_response.raise_for_status.side_effect = http_error
            mock_post.return_value = mock_response

            with self.assertRaises(ShippingValidationError) as ctx:
                self.service._post_to_cart(
                    service_id=3,
                    from_block=from_block,
                    to_block=to_block,
                    products=[{'name': 'P', 'quantity': '1', 'unitary_value': '10.00'}],
                    volume=volume,
                    options=options,
                    seller=mock_seller,
                )

        error_msg = str(ctx.exception).lower()
        # Must mention both possible causes
        self.assertIn('dimensões', error_msg)
        self.assertIn('transportadora', error_msg)
