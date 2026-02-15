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
    """Serviço para integração com Melhor Envio API v2"""
    
    def __init__(self):
        """
        Inicializa o serviço Melhor Envio
        
        Configuração necessária no settings.py:
        MELHOR_ENVIO_TOKEN = 'seu_token_aqui'
        MELHOR_ENVIO_SANDBOX = True  # ou False para produção
        """
        self.token = settings.MELHOR_ENVIO_TOKEN
        self.is_sandbox = getattr(settings, 'MELHOR_ENVIO_SANDBOX', True)
        
        # Define URL base conforme ambiente
        if self.is_sandbox:
            self.base_url = 'https://sandbox.melhorenvio.com.br/api/v2'
        else:
            self.base_url = 'https://melhorenvio.com.br/api/v2'
        
        # Headers obrigatórios conforme documentação
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Marketplace App (contato@seuapp.com)'  # OBRIGATÓRIO
        }

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
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
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

                # Calcular dimensoes consolidadas do pacote para validacao
                package_weight = sum(p['weight'] * p['quantity'] for p in products)
                package_height = max(p['height'] for p in products)
                package_width = max(p['width'] for p in products)
                package_length = sum(p['length'] * p['quantity'] for p in products)

                # Filtrar cotacoes usando regras de transportadoras
                from .carrier_rule_service import CarrierRuleService
                filter_result = CarrierRuleService.filter_melhor_envio_quotes(
                    quotes_data=quotes_data,
                    height=package_height,
                    width=package_width,
                    length=package_length,
                    weight=package_weight,
                )

                filtered_quotes = filter_result['filtered_quotes']
                removed_quotes = filter_result['removed_quotes']
                carrier_warnings = filter_result['warnings']

                if removed_quotes:
                    logger.info(
                        f'Vendedor {seller.id}: {len(removed_quotes)} servico(s) removido(s) '
                        f'por regras de transportadora: '
                        f'{[q["company_name"] + " " + q["service_name"] for q in removed_quotes]}'
                    )

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

                # Formatar servicos a partir das cotacoes FILTRADAS
                formatted_services = self._format_services(filtered_quotes)

                seller_result = {
                    'quote_id': quote.id,
                    'seller_name': seller.get_full_name() or seller.email,
                    'seller_id': seller.id,
                    'seller_city': seller_address.city,
                    'seller_state': seller_address.state,
                    'services': formatted_services,
                    'total_value': total_value,
                    'items_count': len(items),
                }

                # Incluir informacoes de transportadoras removidas
                if removed_quotes:
                    seller_result['removed_carriers'] = removed_quotes

                # Incluir avisos (ex: taxa de nao mecanizavel)
                if carrier_warnings:
                    seller_result['carrier_warnings'] = carrier_warnings

                # Se nenhum servico restou apos filtragem, informar o motivo
                if not formatted_services:
                    seller_result['error'] = (
                        'Nenhuma transportadora disponivel para as dimensoes/peso '
                        'deste pacote. Verifique as restricoes de cada transportadora.'
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
        products = []
        for item in seller_items:
            products.append({
                'name': item.product_name,
                'quantity': item.quantity,
                'unitary_value': float(item.unit_price)
            })

        # Preparar volume único consolidado (transportadoras não aceitam múltiplos volumes)
        total_weight = sum(float(item.weight_kg) * item.quantity for item in seller_items)
        max_height = max(float(item.height_cm) for item in seller_items)
        max_width = max(float(item.width_cm) for item in seller_items)
        total_length = sum(float(item.length_cm) * item.quantity for item in seller_items)

        volumes = [{
            'height': max_height,
            'width': max_width,
            'length': total_length,
            'weight': total_weight
        }]

        # Montar payload com documentos validados
        payload = {
            'service': shipping_service_id,
            'from': {
                'name': seller.get_full_name() or seller.email,
                'phone': seller_address.recipient_phone,
                'email': seller.email,
                'document': validated_seller_doc,
                'company_document': '',  # Deixar vazio, usar apenas 'document'
                'postal_code': origin_zipcode.replace('-', ''),
                'address': seller_address.street,
                'number': seller_address.number,
                'complement': seller_address.complement or '',
                'district': seller_address.neighborhood,
                'city': seller_address.city,
                'state_abbr': seller_address.state,
            },
            'to': {
                'name': order.shipping_address.get('recipient_name', ''),
                'phone': order.shipping_address.get('recipient_phone', ''),
                'email': order.buyer.email,
                'document': validated_buyer_doc,
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
                'collect': False
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
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
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
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
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
    
    def create_shipment(self, order, seller, shipping_service_id):
        """
        Cria envio completo (adiciona ao carrinho + faz checkout)

        Args:
            order: Pedido
            seller: Vendedor
            shipping_service_id: ID do serviço de frete

        Returns:
            tuple: (Shipment, warning_dict ou None)
        """
        # PASSO 1: Adicionar ao carrinho
        cart_data, sent_payload = self.create_shipment_in_cart(order, seller, shipping_service_id)
        melhorenvio_order_id = cart_data.get('id')

        if not melhorenvio_order_id:
            raise Exception('ID do pedido não retornado ao adicionar no carrinho')

        # Extrair warning de insurance (se houver)
        insurance_warning = cart_data.pop('_insurance_warning', None)

        # PASSO 2: Fazer checkout
        checkout_result = self.checkout_cart([melhorenvio_order_id])

        # Verificar se checkout foi bem-sucedido
        purchase = checkout_result.get('purchase', {})
        if purchase.get('status') != 'paid':
            # Em sandbox, pagamento é aprovado em até 5 minutos
            # Em produção, depende do método de pagamento
            pass

        # Calcular dimensões a partir dos itens do vendedor
        seller_items = order.items.filter(seller=seller)
        total_weight = sum(float(item.weight_kg) for item in seller_items)
        max_height = max(float(item.height_cm) for item in seller_items)
        max_width = max(float(item.width_cm) for item in seller_items)
        total_length = sum(float(item.length_cm) for item in seller_items)

        # Extrair carrier info da resposta (com fallback para dados conhecidos)
        service_data = cart_data.get('service') or {}
        company_data = service_data.get('company') or {}
        carrier_name = company_data.get('name', '')
        carrier_service = service_data.get('name', '')

        # Extrair endereços da resposta (com fallback para o payload enviado)
        origin_address = cart_data.get('from') or sent_payload.get('from', {})
        destination_address = cart_data.get('to') or sent_payload.get('to', {})

        # Criar registro de Shipment
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
            status='created'
        )

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

        try:
            logger.info(f'Gerando etiqueta para envio {shipment.melhorenvio_order_id}')
            response = requests.post(
                generate_url,
                json=generate_payload,
                headers=self.headers,
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
                headers=self.headers,
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
        params = {'orders': shipment.melhorenvio_order_id}

        try:
            logger.info(f'Rastreando envio: {shipment.melhorenvio_order_id}')
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
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
                f'Params: {params}\n'
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