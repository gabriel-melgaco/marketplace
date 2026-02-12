"""
Testes para validações do MelhorEnvioService

Valida:
- Bloqueio de CEPs iguais
- Validação de CPF/CNPJ
- Mensagens de erro em português
"""
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
