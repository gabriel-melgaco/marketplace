import json
import requests
import logging
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from ..models import ShippingQuote, Shipment, ShipmentTracking, Address
from authentication.validators import is_valid_cpf, is_valid_cnpj, only_digits

logger = logging.getLogger(__name__)


class ShippingValidationError(Exception):
    """Erro de validação ao calcular ou criar frete"""
    pass


class MelhorEnvioService:
    """
    Serviço para integração com Melhor Envio API v2.

    IMPORTANTE - Autenticação OAuth 2.0:
    Este serviço usa preferencialmente tokens OAuth 2.0 (via MelhorEnvioOAuthService)
    para autenticar as chamadas à API. Isso é OBRIGATÓRIO para que o webhook do
    Melhor Envio seja acionado.

    O webhook só dispara para etiquetas criadas com um token OAuth 2.0 do aplicativo
    onde o webhook está configurado. Tokens pessoais/diretos (MELHOR_ENVIO_TOKEN)
    NÃO acionam o webhook.

    Fallback: Se não houver token OAuth ativo, usa MELHOR_ENVIO_TOKEN como fallback
    (útil para cálculo de frete, que não depende do webhook).
    """

    def __init__(self):
        """
        Inicializa o serviço Melhor Envio.

        Prioridade de autenticação:
        1. Token OAuth 2.0 (MelhorEnvioOAuthToken do banco de dados) - necessário para webhook
        2. MELHOR_ENVIO_TOKEN (fallback para operações que não dependem do webhook)
        """
        self.is_sandbox = getattr(settings, 'MELHOR_ENVIO_SANDBOX', True)

        # Define URL base conforme ambiente
        if self.is_sandbox:
            self.base_url = 'https://sandbox.melhorenvio.com.br/api/v2'
        else:
            self.base_url = 'https://melhorenvio.com.br/api/v2'

        # Token legado (fallback) - usado apenas se OAuth não estiver configurado
        self._legacy_token = getattr(settings, 'MELHOR_ENVIO_TOKEN', '')

        # Contact email para User-Agent
        self._contact_email = getattr(
            settings, 'MELHOR_ENVIO_USER_AGENT_EMAIL', 'contato@seuapp.com'
        )

    def _get_headers(self, require_oauth: bool = False) -> dict:
        """
        Retorna os headers HTTP para chamadas à API.

        Tenta usar o token OAuth 2.0. Se não disponível:
        - Se require_oauth=True: levanta exceção (operações que dependem do webhook)
        - Se require_oauth=False: usa MELHOR_ENVIO_TOKEN como fallback

        Args:
            require_oauth: Se True, falha se token OAuth não estiver disponível.
                           Deve ser True para operações de criação de etiqueta,
                           checkout e criação de shipment.

        Returns:
            dict: Headers com Authorization Bearer
        """
        from .melhor_envio_oauth_service import MelhorEnvioOAuthService, MelhorEnvioOAuthError

        oauth_service = MelhorEnvioOAuthService()

        try:
            return oauth_service.get_oauth_headers()
        except MelhorEnvioOAuthError as e:
            if require_oauth:
                raise

            # Fallback para token legado (somente para operações que não dependem do webhook)
            if self._legacy_token:
                logger.warning(
                    f'Token OAuth 2.0 não disponível ({e}). '
                    f'Usando MELHOR_ENVIO_TOKEN como fallback. '
                    f'ATENÇÃO: Etiquetas criadas com token legado NÃO acionam o webhook!'
                )
                return {
                    'Authorization': f'Bearer {self._legacy_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'User-Agent': f'Marketplace App ({self._contact_email})',
                }

            raise MelhorEnvioOAuthError(
                f'Nenhum método de autenticação disponível. '
                f'Configure MELHOR_ENVIO_TOKEN ou autorize o aplicativo via OAuth 2.0. '
                f'Detalhe: {e}'
            )

    def _sanitize_phone(self, phone: str) -> str:
        """
        Sanitiza número de telefone removendo todos os caracteres não-numéricos.

        A API do Melhor Envio aceita somente dígitos no campo phone.
        Formatos como '(24)9999-9999' ou '+55 11 99999-9999' causam erro 500
        no servidor do ME (validação interna não tratada como 422).

        Args:
            phone: Telefone em qualquer formato

        Returns:
            str: Apenas dígitos do telefone
        """
        if not phone:
            return ''
        return only_digits(phone)

    def _validate_document(self, document, document_type='CPF'):
        """
        Valida CPF ou CNPJ

        Args:
            document: CPF ou CNPJ (pode conter formatação)
            document_type: 'CPF' ou 'CNPJ' (usado apenas para mensagem de erro)

        Returns:
            str: Documento validado (apenas dígitos)

        Raises:
            ShippingValidationError: Se documento for inválido
        """
        if not document:
            raise ShippingValidationError(f'{document_type} não fornecido')

        # Remove formatação
        clean_doc = only_digits(document)

        # Valida CPF (11 dígitos)
        if len(clean_doc) == 11:
            if not is_valid_cpf(clean_doc):
                raise ShippingValidationError(f'{document_type} inválido: {document}')
            return clean_doc

        # Valida CNPJ (14 dígitos)
        if len(clean_doc) == 14:
            if not is_valid_cnpj(clean_doc):
                raise ShippingValidationError(f'{document_type} inválido: {document}')
            return clean_doc

        raise ShippingValidationError(
            f'{document_type} deve conter 11 (CPF) ou 14 (CNPJ) dígitos. Recebido: {document}'
        )

    def _validate_zipcodes(self, from_zipcode, to_zipcode):
        """
        Valida CEPs de origem e destino

        Args:
            from_zipcode: CEP de origem
            to_zipcode: CEP de destino

        Raises:
            ShippingValidationError: Se CEPs forem iguais ou inválidos
        """
        # Remove formatação
        clean_from = from_zipcode.replace('-', '').strip()
        clean_to = to_zipcode.replace('-', '').strip()

        if not clean_from or not clean_to:
            raise ShippingValidationError('CEP de origem e destino são obrigatórios')

        # Verifica se são iguais
        if clean_from == clean_to:
            raise ShippingValidationError(
                f'CEP de origem e destino não podem ser iguais ({from_zipcode}). '
                'Para entregas no mesmo CEP, utilize a opção de entrega presencial.'
            )
    
    def calculate_shipping(self, from_zipcode, to_zipcode, products=None, package=None, options=None):
        """
        Calcula frete usando API v2 do Melhor Envio

        Existem 2 formas de calcular:
        1. Enviando PRODUTOS (recomendado) - API calcula empacotamento automaticamente
        2. Enviando PACOTE pronto - quando você já tem as dimensões finais

        Args:
            from_zipcode: CEP de origem (apenas números)
            to_zipcode: CEP de destino (apenas números)
            products: Lista de produtos (OPÇÃO 1)
                [
                    {
                        "id": "x",
                        "width": 11,    # cm
                        "height": 17,   # cm
                        "length": 11,   # cm
                        "weight": 0.3,  # kg
                        "insurance_value": 10.1,  # valor unitário
                        "quantity": 1
                    }
                ]
            package: Pacote único (OPÇÃO 2)
                {
                    "width": 11,
                    "height": 17,
                    "length": 11,
                    "weight": 0.3
                }
            options: Opções adicionais
                {
                    "insurance_value": 100.0,
                    "receipt": false,      # Aviso de Recebimento (AR)
                    "own_hand": false,     # Mão própria
                    "collect": false       # Coleta
                }

        Returns:
            list: Lista de cotações das transportadoras

        Raises:
            ShippingValidationError: Se validação falhar
            Exception: Se chamada à API falhar
        """
        # VALIDAÇÃO 1: Verificar se CEPs de origem e destino são diferentes
        self._validate_zipcodes(from_zipcode, to_zipcode)

        url = f'{self.base_url}/me/shipment/calculate'

        # Monta payload base
        payload = {
            'from': {'postal_code': from_zipcode.replace('-', '')},
            'to': {'postal_code': to_zipcode.replace('-', '')}
        }

        # Adiciona produtos OU pacote (nunca os dois)
        if products:
            payload['products'] = products
        elif package:
            payload['package'] = package
        else:
            raise ValueError('Deve fornecer products ou package')

        # Adiciona opções se fornecidas
        if options:
            payload['options'] = options

        try:
            logger.info(f'Calculando frete: {from_zipcode} → {to_zipcode}')
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            logger.info(f'Frete calculado com sucesso: {from_zipcode} → {to_zipcode}')
            return response.json()
        except requests.exceptions.HTTPError as e:
            # MELHORIA: Capturar corpo completo da resposta para debug
            error_detail = 'Resposta não disponível'
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text

            logger.error(
                f'Erro HTTP ao calcular frete: {e.response.status_code if e.response else "N/A"}\n'
                f'URL: {url}\n'
                f'Payload: {payload}\n'
                f'Resposta: {error_detail}'
            )
            raise Exception(f'Erro HTTP ao calcular frete: {e.response.status_code} - {error_detail}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao calcular frete: {str(e)}')
            raise Exception(f'Erro de conexão ao calcular frete: {str(e)}')
    
    def create_shipping_quote_by_seller(self, user, cart, destination_zipcode):
        """
        Cria cotações de frete agrupadas por vendedor
        
        Args:
            user: Usuário comprador
            cart: Carrinho de compras
            destination_zipcode: CEP de destino
            
        Returns:
            dict: Cotações agrupadas por vendedor
        """
        from collections import defaultdict
        
        # Agrupar itens por vendedor
        items_by_seller = defaultdict(list)
        for item in cart.items.select_related('listing__seller', 'listing').all():
            items_by_seller[item.listing.seller].append(item)
        
        quotes_by_seller = {}
        
        # Calcular frete para cada vendedor
        for seller, items in items_by_seller.items():
            # VALIDAÇÃO: Verificar se comprador é o próprio vendedor
            if seller == user:
                quotes_by_seller[seller.id] = {
                    'error': 'Você não pode calcular frete para seus próprios produtos',
                    'seller_name': seller.get_full_name() or seller.email,
                    'seller_id': seller.id
                }
                continue

            # Buscar endereço de envio do listing (primeiro item do vendedor)
            # Todos os itens do mesmo vendedor devem ter o mesmo shipping_address
            first_listing = items[0].listing
            seller_address = first_listing.shipping_address

            if not seller_address:
                quotes_by_seller[seller.id] = {
                    'error': 'Produto não possui endereço de envio configurado',
                    'seller_name': seller.get_full_name() or seller.email,
                    'seller_id': seller.id
                }
                continue

            # VALIDAÇÃO: CEPs iguais
            origin_zip = seller_address.zipcode.replace('-', '').strip()
            destination_zip = destination_zipcode.replace('-', '').strip()
            if origin_zip == destination_zip:
                quotes_by_seller[seller.id] = {
                    'error': (
                        f'CEP de origem e destino são iguais ({origin_zip}). '
                        'Frete via transportadora não disponível. '
                        'Utilize a opção de entrega presencial.'
                    ),
                    'seller_name': seller.get_full_name() or seller.email,
                    'seller_id': seller.id,
                    'same_zipcode': True
                }
                continue

            # Preparar produtos para API (OPÇÃO 1 - Recomendada)
            products = []
            total_value = 0

            for item in items:
                listing = item.listing
                product_insurance = min(float(listing.price), settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE)
                product_data = {
                    'id': str(listing.id),
                    'width': float(listing.width_cm),
                    'height': float(listing.height_cm),
                    'length': float(listing.length_cm),
                    'weight': float(listing.weight_kg),
                    'insurance_value': product_insurance,
                    'quantity': item.quantity
                }
                products.append(product_data)
                total_value += float(listing.price) * item.quantity

            # Opções adicionais (cap no limite de envios não comerciais)
            capped_total = min(total_value, settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE)
            options = {
                'insurance_value': capped_total,
                'receipt': False,
                'own_hand': False,
                'collect': False
            }

            try:
                # Calcular frete usando API
                quotes_data = self.calculate_shipping(
                    from_zipcode=seller_address.zipcode,
                    to_zipcode=destination_zipcode,
                    products=products,
                    options=options
                )

                # Calcular dimensoes consolidadas do pacote
                package_weight = sum(p['weight'] * p['quantity'] for p in products)
                package_height = max(p['height'] for p in products)
                package_width = max(p['width'] for p in products)
                package_length = sum(p['length'] * p['quantity'] for p in products)

                # Salvar cotação no banco (com dados originais completos)
                quote = ShippingQuote.objects.create(
                    user=user,
                    seller=seller,
                    origin_zipcode=seller_address.zipcode,
                    origin_address=seller_address.to_dict(),
                    destination_zipcode=destination_zipcode,
                    destination_address={},
                    weight=package_weight,
                    height=package_height,
                    width=package_width,
                    length=package_length,
                    declared_value=total_value,
                    quotes_data=quotes_data,
                    expires_at=timezone.now() + timedelta(hours=24)
                )

                # Separar serviços disponíveis dos indisponíveis.
                # A API do ME retorna erros inline para transportadoras que não
                # aceitam o pacote (dimensões/peso excedidos, CEP não atendido).
                formatted_services = self._format_services(quotes_data)
                unavailable_services = self._format_unavailable_services(quotes_data)

                seller_result = {
                    'quote_id': quote.id,
                    'seller_name': seller.get_full_name() or seller.email,
                    'seller_id': seller.id,
                    'seller_city': seller_address.city,
                    'seller_state': seller_address.state,
                    'services': formatted_services,
                    'unavailable_services': unavailable_services,
                    'total_value': total_value,
                    'items_count': len(items),
                }

                # Se nenhum serviço disponível, informar
                if not formatted_services:
                    seller_result['error'] = (
                        'Nenhuma transportadora disponivel para este pacote.'
                    )
                    seller_result['no_eligible_carriers'] = True

                quotes_by_seller[seller.id] = seller_result

            except ShippingValidationError as e:
                quotes_by_seller[seller.id] = {
                    'error': str(e),
                    'seller_name': seller.get_full_name() or seller.email,
                    'seller_id': seller.id,
                    'validation_error': True
                }
            except Exception as e:
                logger.error(f'Erro ao calcular frete para vendedor {seller.id}: {str(e)}')
                quotes_by_seller[seller.id] = {
                    'error': str(e),
                    'seller_name': seller.get_full_name() or seller.email,
                    'seller_id': seller.id
                }
        
        return quotes_by_seller
    
    def _format_services(self, quotes_data):
        """
        Formata serviços de frete para resposta padronizada
        
        A API retorna uma lista de cotações. Cada cotação tem a estrutura:
        {
            "id": 1,
            "name": "PAC",
            "price": "17.90",
            "custom_price": "17.90",
            "discount": "5.03",
            "currency": "R$",
            "delivery_time": 4,
            "custom_delivery_time": 4,
            "company": {
                "id": 1,
                "name": "Correios",
                "picture": "https://..."
            },
            ...
        }
        """
        services = []

        if not isinstance(quotes_data, list):
            return services

        for quote in quotes_data:
            if isinstance(quote, dict) and 'error' not in quote:
                # Usar valores customizados se disponíveis (recomendação da doc)
                price = float(quote.get('custom_price', quote.get('price', 0)))
                delivery_time = quote.get('custom_delivery_time', quote.get('delivery_time', 0))

                service = {
                    'id': quote.get('id'),
                    'name': quote.get('name'),
                    'price': price,
                    'discount': float(quote.get('discount', 0)),
                    'delivery_time': delivery_time,
                    'currency': quote.get('currency', 'R$'),
                }

                # Informações da transportadora
                company = quote.get('company', {})
                if isinstance(company, dict):
                    service['company'] = company.get('name', '')
                    service['company_picture'] = company.get('picture', '')
                else:
                    service['company'] = ''
                    service['company_picture'] = ''

                services.append(service)

        return services

    def _format_unavailable_services(self, quotes_data):
        """
        Extrai serviços indisponíveis da resposta do Melhor Envio.

        A API retorna erros inline para transportadoras que não aceitam o pacote
        (dimensões excedidas, peso fora do range, CEP não atendido, etc.).
        Este método coleta essas entradas e as formata para exibição ao comprador.

        Returns:
            list: Serviços indisponíveis com id, name, company e reason.
        """
        unavailable = []

        if not isinstance(quotes_data, list):
            return unavailable

        for quote in quotes_data:
            if not isinstance(quote, dict):
                continue
            error = quote.get('error')
            if not error:
                continue

            company = quote.get('company', {})
            unavailable.append({
                'id': quote.get('id'),
                'name': quote.get('name', ''),
                'company': company.get('name', '') if isinstance(company, dict) else str(company),
                'company_picture': company.get('picture', '') if isinstance(company, dict) else '',
                'reason': error,
            })

        return unavailable
    
    def create_shipment_in_cart(self, order, seller, shipping_service_id):
        """
        PASSO 1: Adiciona envio ao carrinho do Melhor Envio

        Fluxo completo:
        1. Adicionar ao carrinho (este método)
        2. Fazer checkout/pagamento
        3. Gerar etiqueta

        Args:
            order: Pedido
            seller: Vendedor
            shipping_service_id: ID do serviço escolhido na cotação

        Returns:
            tuple: (response_data, payload_enviado)

        Raises:
            ShippingValidationError: Se validação falhar
            Exception: Se chamada à API falhar
        """
        url = f'{self.base_url}/me/cart'

        # Filtrar itens do vendedor
        seller_items = order.items.filter(seller=seller)
        if not seller_items.exists():
            raise Exception(f'Nenhum item do vendedor encontrado neste pedido')

        # Buscar endereço de envio do listing (primeiro item do vendedor)
        # Todos os itens do mesmo vendedor devem ter o mesmo shipping_address
        first_item = seller_items.first()
        from products.models import MarketplaceListing
        listing = MarketplaceListing.objects.select_related('shipping_address').get(id=first_item.listing_id)
        seller_address = listing.shipping_address

        if not seller_address:
            raise Exception(f'Produto não possui endereço de envio configurado')

        # VALIDAÇÃO 1: CEPs origem e destino
        origin_zipcode = seller_address.zipcode
        destination_zipcode = order.shipping_address['zipcode']
        self._validate_zipcodes(origin_zipcode, destination_zipcode)

        # VALIDAÇÃO 2: Documentos (CPF/CNPJ)
        # Validar documento do vendedor
        seller_document = getattr(seller, 'cpf', '') or getattr(seller, 'cnpj', '')
        if seller_document:
            validated_seller_doc = self._validate_document(seller_document, 'CPF/CNPJ do vendedor')
        else:
            raise ShippingValidationError('Vendedor não possui CPF ou CNPJ cadastrado')

        # Validar documento do comprador (buscar do modelo de usuário)
        buyer_document = getattr(order.buyer, 'cpf', '') or getattr(order.buyer, 'cnpj', '')
        if buyer_document:
            validated_buyer_doc = self._validate_document(buyer_document, 'CPF/CNPJ do comprador')
        else:
            raise ShippingValidationError('Comprador não possui CPF ou CNPJ cadastrado')

        # Preparar produtos
        # Documentação Melhor Envio: quantity e unitary_value devem ser strings.
        # unitary_value deve ter sempre 2 casas decimais (ex: "525.50", não "525.5").
        products = []
        for item in seller_items:
            products.append({
                'name': item.product_name,
                'quantity': str(item.quantity),
                'unitary_value': f"{float(item.unit_price):.2f}",
            })

        # Preparar volume único consolidado
        # Correios, J&T e Loggi não aceitam múltiplos volumes em uma única requisição
        total_weight = sum(float(item.weight_kg) * item.quantity for item in seller_items)
        max_height = max(float(item.height_cm) for item in seller_items)
        max_width = max(float(item.width_cm) for item in seller_items)
        total_length = sum(float(item.length_cm) * item.quantity for item in seller_items)

        # Convert dimensions to int as required by the Melhor Envio API documentation.
        # Float values can cause unexpected 500 errors on the ME side.
        vol_height = int(round(max_height))
        vol_width = int(round(max_width))
        vol_length = int(round(total_length))
        vol_weight = round(total_weight, 3)  # weight can have decimals (kg)

        # Warn if Correios girth formula is exceeded: major_side + 2*(side2 + side3) <= 200cm
        dims_sorted = sorted([vol_height, vol_width, vol_length], reverse=True)
        correios_girth = dims_sorted[0] + 2 * (dims_sorted[1] + dims_sorted[2])
        if correios_girth > 200:
            logger.warning(
                f'AVISO: Dimensoes do pacote excedem o limite do Correios '
                f'(maior lado + 2*(lado2 + lado3) = {correios_girth}cm > 200cm). '
                f'height={vol_height}cm, width={vol_width}cm, length={vol_length}cm. '
                f'O Correios (PAC/SEDEX) pode rejeitar este pacote. '
                f'Verifique as dimensoes do produto no banco de dados. '
                f'Pedido: {order.order_number}, vendedor: {seller.email}'
            )

        volumes = [{
            'height': vol_height,
            'width': vol_width,
            'length': vol_length,
            'weight': vol_weight
        }]

        # Montar bloco "from": credenciais da conta ME do marketplace + endereço físico do vendedor.
        # O ME valida from.document e from.email contra a conta OAuth autenticada (marketplace).
        # Em modelos onde vendedores não têm contas próprias no ME, usar os dados do marketplace.
        sender_document = getattr(settings, 'MELHOR_ENVIO_SENDER_DOCUMENT', '') or validated_seller_doc
        sender_email = getattr(settings, 'MELHOR_ENVIO_SENDER_EMAIL', '') or seller.email
        sender_name = getattr(settings, 'MELHOR_ENVIO_SENDER_NAME', '') or seller.get_full_name() or seller.email

        sender_is_pj = len(sender_document.replace('.', '').replace('/', '').replace('-', '')) == 14
        from_block = {
            'name': sender_name,
            'phone': self._sanitize_phone(seller_address.recipient_phone),
            'email': sender_email,
            'document': sender_document,
            'postal_code': origin_zipcode.replace('-', ''),
            'address': seller_address.street,
            'number': seller_address.number,
            'complement': seller_address.complement or '',
            'district': seller_address.neighborhood,
            'city': seller_address.city,
            'state_abbr': seller_address.state,
            'state_register': 'ISENTO',
        }
        if sender_is_pj:
            from_block['company_document'] = sender_document

        # Determine buyer document type to set state_register correctly.
        # Per ME docs: PF -> state_register="ISENTO"; also acceptable for PJ non-commercial.
        buyer_is_pj = len(validated_buyer_doc) == 14
        buyer_state_register = 'ISENTO'

        # Montar payload com documentos validados
        payload = {
            'service': shipping_service_id,
            'from': from_block,
            'to': {
                'name': order.shipping_address.get('recipient_name', ''),
                'phone': self._sanitize_phone(order.shipping_address.get('recipient_phone', '')),
                'email': order.buyer.email,
                'document': validated_buyer_doc,
                # country_id required by ME API (per official docs example)
                'country_id': 'BR',
                # state_register required per ME API docs: "ISENTO" for PF non-commercial
                'state_register': buyer_state_register,
                'postal_code': destination_zipcode.replace('-', ''),
                'address': order.shipping_address['street'],
                'number': order.shipping_address['number'],
                'complement': order.shipping_address.get('complement', ''),
                'district': order.shipping_address['neighborhood'],
                'city': order.shipping_address['city'],
                'state_abbr': order.shipping_address['state'],
            },
            'products': products,
            'volumes': volumes,
            'options': {
                'insurance_value': min(
                    float(sum(item.subtotal for item in seller_items)),
                    settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE
                ),
                'receipt': False,
                'own_hand': False,
                # platform identifies the originating application in ME dashboard
                'platform': getattr(settings, 'MELHOR_ENVIO_PLATFORM_NAME', 'Marketplace Academia'),
                # tag with order number for tracking in ME dashboard
                'tags': [{'tag': str(order.order_number), 'url': ''}],
            }
        }

        # Registrar warning se valor segurado foi limitado
        original_value = float(sum(item.subtotal for item in seller_items))
        insurance_capped = original_value > settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE
        if insurance_capped:
            logger.warning(
                f'Valor segurado limitado de R${original_value:.2f} para '
                f'R${settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE:.2f} (limite para envios não comerciais). '
                f'Pedido: {order.order_number}, vendedor: {seller.email}'
            )

        try:
            logger.info(
                f'Adicionando envio ao carrinho: pedido {order.order_number}, '
                f'vendedor {seller.email}, serviço {shipping_service_id}'
            )
            response = requests.post(url, json=payload, headers=self._get_headers(require_oauth=True), timeout=30)
            response.raise_for_status()
            logger.info(f'Envio adicionado ao carrinho com sucesso: pedido {order.order_number}')
            result = response.json()

            logger.info(
                f'Resposta do carrinho Melhor Envio: {json.dumps(result, default=str)[:2000]}'
            )

            if insurance_capped:
                result['_insurance_warning'] = {
                    'original_value': original_value,
                    'capped_value': settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE,
                    'message': (
                        f'O valor segurado foi limitado de R${original_value:.2f} para '
                        f'R${settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE:.2f}. Envios não comerciais possuem '
                        f'limite máximo de seguro de R$1.000,00.'
                    )
                }
            return result, payload
        except requests.exceptions.HTTPError as e:
            # MELHORIA: Capturar corpo completo da resposta para debug
            error_detail = 'Resposta não disponível'
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text

            logger.error(
                f'Erro HTTP ao adicionar envio ao carrinho: {e.response.status_code if e.response else "N/A"}\n'
                f'URL: {url}\n'
                f'Payload: {payload}\n'
                f'Resposta: {error_detail}'
            )
            raise Exception(f'Erro ao adicionar envio ao carrinho: {error_detail}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao adicionar envio ao carrinho: {str(e)}')
            raise Exception(f'Erro ao adicionar envio ao carrinho: {str(e)}')
    
    def checkout_cart(self, order_ids):
        """
        PASSO 2: Compra/Checkout dos envios do carrinho

        Args:
            order_ids: Lista de IDs dos pedidos no Melhor Envio (não confundir com Order do Django)

        Returns:
            dict: Resultado do checkout
        """
        url = f'{self.base_url}/me/shipment/checkout'

        payload = {
            'orders': order_ids  # IDs retornados ao adicionar no carrinho
        }

        try:
            logger.info(f'Fazendo checkout dos envios: {order_ids}')
            response = requests.post(url, json=payload, headers=self._get_headers(require_oauth=True), timeout=30)
            response.raise_for_status()
            logger.info(f'Checkout realizado com sucesso: {order_ids}')
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_detail = 'Resposta não disponível'
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text

            logger.error(
                f'Erro HTTP no checkout: {e.response.status_code if e.response else "N/A"}\n'
                f'URL: {url}\n'
                f'Payload: {payload}\n'
                f'Resposta: {error_detail}'
            )
            raise Exception(f'Erro no checkout: {error_detail}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão no checkout: {str(e)}')
            raise Exception(f'Erro no checkout: {str(e)}')
    
    def create_shipment_record(self, order, seller, cart_data, sent_payload):
        """
        Cria o registro de Shipment no banco de dados a partir da resposta do carrinho.

        Separa a lógica de criação de DB da chamada à API para permitir
        que o checkout seja feito em uma etapa posterior.

        Args:
            order: Pedido
            seller: Vendedor
            cart_data: Resposta da API do carrinho (POST /api/v2/me/cart)
            sent_payload: Payload enviado ao carrinho (para fallback de endereços)

        Returns:
            tuple: (Shipment, insurance_warning ou None)
        """
        melhorenvio_order_id = cart_data.get('id')
        if not melhorenvio_order_id:
            raise Exception('ID do pedido não retornado ao adicionar no carrinho')

        # Extrair warning de insurance (se houver)
        insurance_warning = cart_data.pop('_insurance_warning', None)

        # Calcular dimensões a partir dos itens do vendedor
        seller_items = order.items.filter(seller=seller)
        total_weight = sum(float(item.weight_kg) * item.quantity for item in seller_items)
        max_height = max(float(item.height_cm) for item in seller_items)
        max_width = max(float(item.width_cm) for item in seller_items)
        total_length = sum(float(item.length_cm) * item.quantity for item in seller_items)

        # Extrair carrier info da resposta da API
        service_data = cart_data.get('service') or {}
        company_data = service_data.get('company') or {}
        carrier_name = company_data.get('name', '')
        carrier_service = service_data.get('name', '')

        # Fallback: buscar carrier info do shipping_services da order (dados da cotação)
        if not carrier_name or not carrier_service:
            seller_shipping = (order.shipping_services or {}).get(str(seller.id), {})
            if isinstance(seller_shipping, dict):
                # 'company' pode ser string ou dict (objeto da API Melhor Envio)
                company = seller_shipping.get('company', '')
                if isinstance(company, dict):
                    carrier_name = carrier_name or company.get('name', '')
                else:
                    carrier_name = carrier_name or str(company)
                carrier_service = carrier_service or seller_shipping.get('service_name', '')

        # Extrair endereços da resposta (com fallback para o payload enviado)
        origin_address = cart_data.get('from') or sent_payload.get('from', {})
        destination_address = cart_data.get('to') or sent_payload.get('to', {})

        # Criar registro de Shipment com status 'pending' (ainda sem checkout)
        shipment = Shipment.objects.create(
            order=order,
            seller=seller,
            melhorenvio_order_id=melhorenvio_order_id,
            carrier_name=carrier_name,
            carrier_service=carrier_service,
            shipping_cost=cart_data.get('price', 0) or 0,
            insurance_value=cart_data.get('insurance_value', 0) or 0,
            weight=total_weight,
            height=max_height,
            width=max_width,
            length=total_length,
            origin_address=origin_address,
            destination_address=destination_address,
            status='pending'
        )

        return shipment, insurance_warning

    def add_to_cart_raw(self, buyer, seller, seller_validated_items, shipping_address_dict, service_id):
        """
        Adiciona ao carrinho do Melhor Envio usando dados brutos (sem order no banco).
        Usado ANTES da criação do pedido no banco para falhar rapidamente.

        Args:
            buyer: Usuário comprador
            seller: Usuário vendedor
            seller_validated_items: Lista de validated_items filtrados para este vendedor
            shipping_address_dict: Dict do endereço de entrega (resultado de Address.to_dict())
            service_id: ID do serviço ME

        Returns:
            tuple: (cart_response_dict, sent_payload_dict)
        """
        from decimal import Decimal
        url = f'{self.base_url}/me/cart'

        if not seller_validated_items:
            raise Exception(f'Nenhum item do vendedor {seller.email} fornecido')

        # Buscar endereço de envio do listing (primeiro item)
        first_item = seller_validated_items[0]
        listing = first_item['listing']
        from products.models import MarketplaceListing
        listing_with_addr = MarketplaceListing.objects.select_related('shipping_address').get(
            id=listing.id
        )
        seller_address = listing_with_addr.shipping_address
        if not seller_address:
            raise Exception('Produto não possui endereço de envio configurado')

        # Validar CEPs
        origin_zipcode = seller_address.zipcode
        destination_zipcode = shipping_address_dict['zipcode']
        self._validate_zipcodes(origin_zipcode, destination_zipcode)

        # Validar documentos
        seller_document = getattr(seller, 'cpf', '') or getattr(seller, 'cnpj', '')
        if not seller_document:
            raise ShippingValidationError('Vendedor não possui CPF ou CNPJ cadastrado')
        validated_seller_doc = self._validate_document(seller_document, 'CPF/CNPJ do vendedor')

        buyer_document = getattr(buyer, 'cpf', '') or getattr(buyer, 'cnpj', '')
        if not buyer_document:
            raise ShippingValidationError('Comprador não possui CPF ou CNPJ cadastrado')
        validated_buyer_doc = self._validate_document(buyer_document, 'CPF/CNPJ do comprador')

        # Preparar produtos e calcular seguro
        # A API do ME exige que quantity e unitary_value sejam strings.
        # unitary_value deve ter sempre 2 casas decimais (ex: "525.50", não "525.5").
        products = []
        total_insurance = Decimal('0')
        for item_data in seller_validated_items:
            products.append({
                'name': item_data['product_snapshot']['name'],
                'quantity': str(item_data['quantity']),
                'unitary_value': f"{float(item_data['unit_price']):.2f}",
            })
            total_insurance += item_data['unit_price'] * item_data['quantity']

        # Volumes consolidados
        total_weight = sum(
            float(i['dimensions']['weight_kg']) * i['quantity']
            for i in seller_validated_items
        )
        max_height = max(float(i['dimensions']['height_cm']) for i in seller_validated_items)
        max_width = max(float(i['dimensions']['width_cm']) for i in seller_validated_items)
        total_length = sum(
            float(i['dimensions']['length_cm']) * i['quantity']
            for i in seller_validated_items
        )
        # Convert dimensions to int as required by the Melhor Envio API documentation.
        # The API expects integer values for height, width, length (cm) and weight (kg).
        # Float values can cause unexpected 500 errors on the ME side.
        vol_height = int(round(max_height))
        vol_width = int(round(max_width))
        vol_length = int(round(total_length))
        vol_weight = round(total_weight, 3)  # weight can have decimals (kg)

        # Warn if Correios girth formula is exceeded: major_side + 2*(side2 + side3) <= 200cm
        # This is the most common cause of 500 errors for PAC/SEDEX with oversized packages.
        dims_sorted = sorted([vol_height, vol_width, vol_length], reverse=True)
        correios_girth = dims_sorted[0] + 2 * (dims_sorted[1] + dims_sorted[2])
        if correios_girth > 200:
            logger.warning(
                f'AVISO: Dimensoes do pacote excedem o limite do Correios '
                f'(maior lado + 2*(lado2 + lado3) = {correios_girth}cm > 200cm). '
                f'height={vol_height}cm, width={vol_width}cm, length={vol_length}cm. '
                f'O Correios (PAC/SEDEX) pode rejeitar este pacote. '
                f'Verifique as dimensoes do produto no banco de dados. '
                f'Vendedor: {seller.email}'
            )

        volumes = [{'height': vol_height, 'width': vol_width, 'length': vol_length, 'weight': vol_weight}]

        # Credenciais do remetente: usa a conta ME do marketplace (MELHOR_ENVIO_SENDER_*).
        # O ME valida que from.document e from.email correspondem à conta OAuth autenticada.
        # Em modelos onde os vendedores não têm contas individuais no ME, a conta do marketplace
        # é a autenticada e deve ser usada como identidade do remetente.
        # O endereço físico (postal_code, address, city...) ainda vem do vendedor para o label.
        sender_document = getattr(settings, 'MELHOR_ENVIO_SENDER_DOCUMENT', '') or validated_seller_doc
        sender_email = getattr(settings, 'MELHOR_ENVIO_SENDER_EMAIL', '') or seller.email
        sender_name = getattr(settings, 'MELHOR_ENVIO_SENDER_NAME', '') or seller.get_full_name() or seller.email

        sender_is_pj = len(sender_document.replace('.', '').replace('/', '').replace('-', '')) == 14
        from_block = {
            'name': sender_name,
            'phone': self._sanitize_phone(seller_address.recipient_phone),
            'email': sender_email,
            'document': sender_document,
            'postal_code': origin_zipcode.replace('-', ''),
            'address': seller_address.street,
            'number': seller_address.number,
            'complement': seller_address.complement or '',
            'district': seller_address.neighborhood,
            'city': seller_address.city,
            'state_abbr': seller_address.state,
            'state_register': 'ISENTO',
        }
        if sender_is_pj:
            from_block['company_document'] = sender_document

        # Determine buyer document type to set state_register correctly.
        # Per ME docs: PF -> state_register="ISENTO"; PJ -> state_register="" (empty or ISENTO).
        buyer_is_pj = len(validated_buyer_doc) == 14
        buyer_state_register = 'ISENTO'  # default for PF; also acceptable for PJ non-commercial

        capped_insurance = min(float(total_insurance), settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE)
        insurance_capped = float(total_insurance) > settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE

        payload = {
            'service': service_id,
            'from': from_block,
            'to': {
                'name': shipping_address_dict.get('recipient_name', ''),
                # Sanitizar telefone do comprador — pode vir formatado com (, ), -
                'phone': self._sanitize_phone(shipping_address_dict.get('recipient_phone', '')),
                'email': buyer.email,
                'document': validated_buyer_doc,
                # country_id required by ME API (per official docs example)
                'country_id': 'BR',
                # state_register required per ME API docs: "ISENTO" for PF non-commercial
                'state_register': buyer_state_register,
                'postal_code': destination_zipcode.replace('-', ''),
                'address': shipping_address_dict['street'],
                'number': shipping_address_dict['number'],
                'complement': shipping_address_dict.get('complement', ''),
                'district': shipping_address_dict['neighborhood'],
                'city': shipping_address_dict['city'],
                'state_abbr': shipping_address_dict['state'],
            },
            'products': products,
            'volumes': volumes,
            'options': {
                'insurance_value': capped_insurance,
                'receipt': False,
                'own_hand': False,
                # platform identifies the originating application in ME dashboard
                'platform': getattr(settings, 'MELHOR_ENVIO_PLATFORM_NAME', 'Marketplace Academia'),
            },
        }

        if insurance_capped:
            logger.warning(
                f'Valor segurado limitado de R${float(total_insurance):.2f} para '
                f'R${settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE:.2f}. '
                f'Vendedor: {seller.email}'
            )

        try:
            logger.info(
                f'Adicionando ao carrinho ME (pré-order): vendedor {seller.email}, '
                f'serviço {service_id}'
            )
            response = requests.post(
                url, json=payload, headers=self._get_headers(require_oauth=True), timeout=30
            )
            response.raise_for_status()
            result = response.json()
            logger.info(
                f'Adicionado ao carrinho ME: {json.dumps(result, default=str)[:500]}'
            )
            if insurance_capped:
                result['_insurance_warning'] = {
                    'original_value': float(total_insurance),
                    'capped_value': settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE,
                    'message': (
                        f'Valor segurado limitado de R${float(total_insurance):.2f} para '
                        f'R${settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE:.2f}.'
                    ),
                }
            return result, payload
        except requests.exceptions.HTTPError as e:
            error_detail = 'Resposta não disponível'
            resp = e.response
            status_code = resp.status_code if resp is not None else 'N/A'
            if resp is not None:
                try:
                    error_detail = resp.json()
                except Exception:
                    error_detail = resp.text
            logger.error(
                f'Erro HTTP ao adicionar ao carrinho ME: {status_code}\n'
                f'URL: {url}\nPayload: {payload}\nResposta: {error_detail}'
            )
            raise Exception(f'Erro ao adicionar ao carrinho ME: {error_detail}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao adicionar ao carrinho ME: {str(e)}')
            raise Exception(f'Erro ao adicionar ao carrinho ME: {str(e)}')

    def add_to_cart_and_create_shipment(self, order, seller, shipping_service_id):
        """
        ETAPA 1 do novo fluxo: Adiciona ao carrinho do Melhor Envio e cria
        o registro de Shipment no banco de dados com status 'pending'.

        O checkout deve ser realizado posteriormente via checkout_cart().

        Args:
            order: Pedido
            seller: Vendedor
            shipping_service_id: ID do serviço de frete escolhido

        Returns:
            tuple: (Shipment, insurance_warning ou None)

        Raises:
            ShippingValidationError: Se validação falhar
            Exception: Se chamada à API falhar
        """
        # Chamar API do Melhor Envio para adicionar ao carrinho
        cart_data, sent_payload = self.create_shipment_in_cart(order, seller, shipping_service_id)

        # Criar registro no banco de dados
        return self.create_shipment_record(order, seller, cart_data, sent_payload)

    def create_shipment(self, order, seller, shipping_service_id):
        """
        Cria envio completo (adiciona ao carrinho + faz checkout).

        ATENÇÃO: Este método combina as duas etapas em uma única chamada.
        No novo fluxo separado, use:
        - add_to_cart_and_create_shipment() na criação do pedido
        - checkout_cart() no endpoint de criação de shipments

        Args:
            order: Pedido
            seller: Vendedor
            shipping_service_id: ID do serviço de frete

        Returns:
            tuple: (Shipment, warning_dict ou None)
        """
        # ETAPA 1: Adicionar ao carrinho e criar registro de Shipment
        shipment, insurance_warning = self.add_to_cart_and_create_shipment(
            order, seller, shipping_service_id
        )

        melhorenvio_order_id = shipment.melhorenvio_order_id

        # ETAPA 2: Fazer checkout
        checkout_result = self.checkout_cart([melhorenvio_order_id])

        # Verificar se checkout foi bem-sucedido
        purchase = checkout_result.get('purchase', {})
        if purchase.get('status') != 'paid':
            # Em sandbox, pagamento é aprovado em até 5 minutos
            # Em produção, depende do método de pagamento
            pass

        # Atualizar status do Shipment para 'created' após o checkout
        shipment.status = 'created'
        shipment.save(update_fields=['status', 'updated_at'])

        return shipment, insurance_warning
    
    def generate_label(self, shipment):
        """
        PASSO 3: Gera etiqueta de envio (após pagamento confirmado)

        Args:
            shipment: Instância do Shipment

        Returns:
            str: URL da etiqueta
        """
        # Gerar etiqueta
        generate_url = f'{self.base_url}/me/shipment/generate'
        generate_payload = {'orders': [shipment.melhorenvio_order_id]}

        # Etiquetas DEVEM ser geradas com token OAuth para que o webhook seja acionado.
        # require_oauth=True garante que não haverá fallback silencioso aqui.
        oauth_headers = self._get_headers(require_oauth=True)

        try:
            logger.info(f'Gerando etiqueta para envio {shipment.melhorenvio_order_id}')
            response = requests.post(
                generate_url,
                json=generate_payload,
                headers=oauth_headers,
                timeout=30
            )
            response.raise_for_status()
            logger.info(f'Etiqueta gerada com sucesso: {shipment.melhorenvio_order_id}')
        except requests.exceptions.HTTPError as e:
            error_detail = 'Resposta não disponível'
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text

            logger.error(
                f'Erro HTTP ao gerar etiqueta: {e.response.status_code if e.response else "N/A"}\n'
                f'URL: {generate_url}\n'
                f'Payload: {generate_payload}\n'
                f'Resposta: {error_detail}'
            )
            raise Exception(f'Erro ao gerar etiqueta: {error_detail}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao gerar etiqueta: {str(e)}')
            raise Exception(f'Erro ao gerar etiqueta: {str(e)}')

        # Obter URL para impressão
        print_url = f'{self.base_url}/me/shipment/print'
        print_payload = {
            'mode': 'private',
            'orders': [shipment.melhorenvio_order_id]
        }

        try:
            logger.info(f'Obtendo URL de impressão da etiqueta: {shipment.melhorenvio_order_id}')
            print_response = requests.post(
                print_url,
                json=print_payload,
                headers=oauth_headers,
                timeout=30
            )
            print_response.raise_for_status()
            label_url = print_response.json().get('url')

            # Atualizar shipment
            shipment.label_url = label_url
            shipment.label_generated_at = timezone.now()
            shipment.status = 'label_generated'
            shipment.save()

            logger.info(f'URL da etiqueta obtida com sucesso: {shipment.melhorenvio_order_id}')
            return label_url

        except requests.exceptions.HTTPError as e:
            error_detail = 'Resposta não disponível'
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text

            logger.error(
                f'Erro HTTP ao obter URL da etiqueta: {e.response.status_code if e.response else "N/A"}\n'
                f'URL: {print_url}\n'
                f'Payload: {print_payload}\n'
                f'Resposta: {error_detail}'
            )
            raise Exception(f'Erro ao obter URL da etiqueta: {error_detail}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao obter URL da etiqueta: {str(e)}')
            raise Exception(f'Erro ao obter URL da etiqueta: {str(e)}')
    
    def track_shipment(self, shipment):
        """
        Rastreia envio e atualiza histórico

        Args:
            shipment: Instância do Shipment

        Returns:
            dict: Dados de rastreamento
        """
        url = f'{self.base_url}/me/shipment/tracking'
        payload = {'orders': [shipment.melhorenvio_order_id]}

        try:
            logger.info(f'Rastreando envio: {shipment.melhorenvio_order_id}')
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            data = response.json()

            # Processar dados de rastreamento
            if data and isinstance(data, dict):
                tracking_data = data.get(shipment.melhorenvio_order_id, {})

                # Atualizar código de rastreamento
                if tracking_data.get('tracking'):
                    shipment.melhorenvio_tracking_code = tracking_data['tracking']

                # Criar eventos de rastreamento
                events = tracking_data.get('events', [])
                for event in events:
                    ShipmentTracking.objects.get_or_create(
                        shipment=shipment,
                        occurred_at=event.get('datetime'),
                        defaults={
                            'status': event.get('status', ''),
                            'description': event.get('description', ''),
                            'location': event.get('location', '')
                        }
                    )

                # Atualizar status do envio
                last_status = tracking_data.get('status')
                if last_status:
                    shipment.status = self._map_status(last_status)

                    # Atualizar data de entrega se foi entregue
                    if last_status == 'delivered' and not shipment.delivered_at:
                        shipment.delivered_at = timezone.now()

                shipment.save()

            logger.info(f'Rastreamento atualizado com sucesso: {shipment.melhorenvio_order_id}')
            return data

        except requests.exceptions.HTTPError as e:
            error_detail = 'Resposta não disponível'
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text

            logger.error(
                f'Erro HTTP ao rastrear envio: {e.response.status_code if e.response else "N/A"}\n'
                f'URL: {url}\n'
                f'Payload: {payload}\n'
                f'Resposta: {error_detail}'
            )
            raise Exception(f'Erro ao rastrear envio: {error_detail}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao rastrear envio: {str(e)}')
            raise Exception(f'Erro ao rastrear envio: {str(e)}')
    
    def _map_status(self, melhorenvio_status):
        """Mapeia status do Melhor Envio para o sistema"""
        status_map = {
            'pending': 'pending',
            'paid': 'paid',
            'posted': 'posted',
            'in_transit': 'in_transit',
            'delivered': 'delivered',
            'cancelled': 'cancelled',
            'returned': 'returned',
            'undelivered': 'undelivered'
        }
        return status_map.get(melhorenvio_status, 'pending')
    
    def get_available_services(self) -> list:
        """
        Retorna todos os servicos de frete disponiveis no Melhor Envio.

        Chama GET /api/v2/me/shipment/services e retorna a lista de objetos
        com id, name, type, range, restrictions e company.

        Apenas requer User-Agent; usa fallback para token legado se OAuth
        nao estiver configurado (operacao de leitura, nao cria etiqueta).

        Returns:
            list: Lista de servicos disponiveis

        Raises:
            Exception: Se a chamada a API falhar
        """
        url = f'{self.base_url}/me/shipment/services'

        try:
            logger.info('Buscando servicos disponiveis no Melhor Envio')
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            data = response.json()
            logger.info(f'Servicos Melhor Envio obtidos com sucesso: {len(data)} servicos')
            return data
        except requests.exceptions.HTTPError as e:
            error_detail = 'Resposta nao disponivel'
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except Exception:
                    error_detail = e.response.text

            logger.error(
                f'Erro HTTP ao buscar servicos ME: '
                f'{e.response.status_code if e.response else "N/A"}\n'
                f'URL: {url}\nResposta: {error_detail}'
            )
            raise Exception(f'Erro ao buscar servicos Melhor Envio: {error_detail}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexao ao buscar servicos ME: {str(e)}')
            raise Exception(f'Erro de conexao ao buscar servicos Melhor Envio: {str(e)}')

    def lookup_zipcode(self, zipcode):
        """
        Busca informações de um CEP via ViaCEP
        
        A API do Melhor Envio não tem endpoint de CEP, então usamos ViaCEP
        
        Args:
            zipcode: CEP para buscar (apenas números)
            
        Returns:
            dict: Dados do endereço
        """
        url = f'https://viacep.com.br/ws/{zipcode}/json/'
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'erro' in data:
                raise Exception('CEP não encontrado')
            
            return {
                'zipcode': data['cep'],
                'street': data['logradouro'],
                'neighborhood': data['bairro'],
                'city': data['localidade'],
                'state': data['uf'],
                'complement': data.get('complemento', '')
            }
            
        except requests.exceptions.RequestException as e:
            raise Exception(f'Erro ao buscar CEP: {str(e)}')