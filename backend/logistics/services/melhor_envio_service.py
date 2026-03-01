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
            settings, 'MELHOR_ENVIO_USER_AGENT_EMAIL', 'gabrielmelgacom@gmail.com'
        )

    def _get_headers(self, seller=None, require_oauth: bool = False) -> dict:
        """
        Retorna os headers HTTP para chamadas à API.

        Se seller for fornecido, usa o token OAuth do vendedor (per-seller).
        Caso contrário, usa o token da plataforma (comportamento legado).

        Se seller=None e token OAuth da plataforma não disponível:
        - Se require_oauth=True: levanta exceção
        - Se require_oauth=False: usa MELHOR_ENVIO_TOKEN como fallback

        Args:
            seller: Instância de CustomUser (vendedor). Se fornecido, usa token do vendedor.
            require_oauth: Se True, falha se token OAuth não estiver disponível.

        Returns:
            dict: Headers com Authorization Bearer
        """
        from .melhor_envio_oauth_service import MelhorEnvioOAuthService, MelhorEnvioOAuthError

        oauth_service = MelhorEnvioOAuthService()

        # Per-seller: usa token OAuth do vendedor
        if seller is not None:
            return oauth_service.get_seller_oauth_headers(seller)

        # Plataforma: usa token OAuth da conta compartilhada
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

    def get_account_info(self) -> dict:
        """
        Retorna as informações da conta ME autenticada via OAuth.
        Útil para diagnóstico: verifica document, email, store name e estado da conta.
        """
        url = f'{self.base_url}/me'
        try:
            response = requests.get(url, headers=self._get_headers(require_oauth=True), timeout=15)
            logger.info(f'ME /me status={response.status_code} body={response.text[:500]}')
            response.raise_for_status()
            try:
                return response.json()
            except Exception:
                return {'raw': response.text, 'status_code': response.status_code}
        except requests.exceptions.HTTPError as e:
            resp = e.response
            status_code = resp.status_code if resp is not None else 'N/A'
            try:
                detail = resp.json() if resp is not None else str(e)
            except Exception:
                detail = resp.text if resp is not None else str(e)
            raise Exception(f'Erro ao buscar dados da conta ME — GET /me ({status_code}): {detail}')

    def get_cart_items(self) -> dict:
        """
        Lista todas as etiquetas inseridas no carrinho do Melhor Envio.
        GET /api/v2/me/cart
        """
        url = f'{self.base_url}/me/cart'
        try:
            response = requests.get(url, headers=self._get_headers(require_oauth=True), timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            resp = e.response
            status_code = resp.status_code if resp is not None else 'N/A'
            detail = 'Resposta não disponível'
            if resp is not None:
                try:
                    detail = resp.json()
                except Exception:
                    detail = resp.text
            raise Exception(f'Erro ao listar carrinho ME ({status_code}): {detail}')

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
    
    def calculate_shipping(self, from_zipcode, to_zipcode, products=None, package=None, options=None, seller=None, services=None):
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
            seller: Instância de CustomUser do vendedor (opcional). Quando fornecido,
                usa o token OAuth do vendedor para a cotação, garantindo que apenas
                serviços disponíveis para a conta do vendedor sejam retornados.
                Se None, usa token da plataforma (fallback para retro-compatibilidade).

        Returns:
            list: Lista de cotações das transportadoras

        Raises:
            ShippingValidationError: Se validação falhar ou vendedor não tiver ME conectado
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

        # Adiciona filtro de serviços se fornecido
        if services:
            payload['services'] = services

        try:
            logger.info(f'Calculando frete: {from_zipcode} → {to_zipcode}' +
                        (f' (vendedor: {seller.email})' if seller else ''))
            response = requests.post(url, json=payload, headers=self._get_headers(seller=seller), timeout=30)
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
        for item in cart.items.select_related('listing__seller', 'listing').prefetch_related('listing__packages').all():
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

            # VALIDAÇÃO: shipping_method — filtrar apenas itens elegíveis para ME.
            # Itens com in_person são excluídos da cotação; só entram itens com
            # shipping_method = 'melhor_envio' ou 'both'.
            from products.models import ShippingMethodChoices
            me_items = [
                item for item in items
                if item.listing.shipping_method != ShippingMethodChoices.IN_PERSON
            ]
            in_person_items = [
                item for item in items
                if item.listing.shipping_method == ShippingMethodChoices.IN_PERSON
            ]

            if not me_items:
                # Todos os itens deste vendedor são somente in_person
                quotes_by_seller[seller.id] = {
                    'error': (
                        'Este produto aceita somente entrega por conta do vendedor. '
                        'O envio via transportadora (Melhor Envio) não está disponível.'
                    ),
                    'seller_name': seller.get_full_name() or seller.email,
                    'seller_id': seller.id,
                    'in_person_only': True,
                    'melhor_envio_items': [],
                }
                continue

            # Usar apenas itens elegíveis para o cálculo de frete
            items = me_items

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

            # ----------------------------------------------------------------
            # Calcular cotações POR LISTING para que o comprador possa
            # escolher serviços distintos por anúncio.
            # O agregado global (soma de preços) é mantido para compatibilidade.
            # ----------------------------------------------------------------

            total_value = 0
            all_volumes = []          # agregado global (para dimensões do ShippingQuote)
            by_listing: dict = {}     # {str(listing_id): {services, unavailable_services, ...}}
            global_agg: dict = {}     # {service_id: agg} — agregado de TODOS os listings

            capped_total_global = min(
                sum(float(it.listing.price) * it.quantity for it in items),
                settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE
            )
            options_base = {
                'insurance_value': capped_total_global,
                'receipt': False,
                'own_hand': False,
                'collect': False,
            }

            for item in items:
                listing = item.listing
                packages = list(listing.packages.all())
                item_value = float(listing.price) * item.quantity
                total_value += item_value

                # Montar volumes deste listing
                listing_volumes = []
                if packages:
                    for pkg in packages:
                        for _ in range(item.quantity):
                            vol_height = int(round(float(pkg.height_cm)))
                            vol_width = int(round(float(pkg.width_cm)))
                            vol_length = int(round(float(pkg.length_cm)))
                            vol_weight = round(float(pkg.weight_kg), 3)

                            dims_sorted = sorted(
                                [vol_height, vol_width, vol_length], reverse=True
                            )
                            girth = dims_sorted[0] + 2 * (dims_sorted[1] + dims_sorted[2])
                            if girth > 200:
                                logger.warning(
                                    f'[create_shipping_quote_by_seller] Volume do pacote '
                                    f'{pkg.id} (listing {listing.id}) excede o limite de '
                                    f'girth dos Correios: {girth}cm > 200cm. '
                                    f'h={vol_height}, w={vol_width}, l={vol_length}. '
                                    f'Verifique os dados no DB.'
                                )
                            listing_volumes.append({
                                'height': vol_height,
                                'width': vol_width,
                                'length': vol_length,
                                'weight': vol_weight,
                            })
                else:
                    # Fallback: campos legados do listing
                    for _ in range(item.quantity):
                        vol_height = int(round(float(listing.height_cm or 0)))
                        vol_width = int(round(float(listing.width_cm or 0)))
                        vol_length = int(round(float(listing.length_cm or 0)))
                        vol_weight = round(float(listing.weight_kg or 0), 3)
                        listing_volumes.append({
                            'height': vol_height,
                            'width': vol_width,
                            'length': vol_length,
                            'weight': vol_weight,
                        })

                all_volumes.extend(listing_volumes)

                if not listing_volumes:
                    logger.warning(
                        f'[create_shipping_quote_by_seller] Listing {listing.id} sem '
                        f'volumes — ignorado na cotação.'
                    )
                    continue

                # Cotação por volume para este listing
                listing_agg: dict = {}
                logger.info(
                    f'[create_shipping_quote_by_seller] Listing {listing.id} '
                    f'({listing.title[:40]}): {len(listing_volumes)} volume(s)'
                )
                for vol_idx, vol in enumerate(listing_volumes):
                    vol_quotes = self.calculate_shipping(
                        from_zipcode=seller_address.zipcode,
                        to_zipcode=destination_zipcode,
                        package=vol,
                        options=options_base,
                        seller=seller,
                        services=settings.MELHOR_ENVIO_DEFAULT_SERVICES,
                    )
                    if not isinstance(vol_quotes, list):
                        logger.warning(
                            f'[create_shipping_quote_by_seller] Resposta inesperada do ME '
                            f'para listing {listing.id} vol {vol_idx}: {vol_quotes!r}'
                        )
                        continue
                    for quote_entry in vol_quotes:
                        if not isinstance(quote_entry, dict):
                            continue
                        svc_id = quote_entry.get('id')
                        if svc_id is None:
                            continue
                        has_error = bool(quote_entry.get('error'))
                        if svc_id not in listing_agg:
                            listing_agg[svc_id] = {
                                'base': quote_entry,
                                'total_price': 0.0,
                                'max_delivery_time': 0,
                                'has_error': has_error,
                            }
                        la = listing_agg[svc_id]
                        if has_error:
                            la['has_error'] = True
                        else:
                            vol_price = float(
                                quote_entry.get('custom_price', quote_entry.get('price', 0)) or 0
                            )
                            vol_delivery = int(
                                quote_entry.get('custom_delivery_time',
                                                quote_entry.get('delivery_time', 0)) or 0
                            )
                            la['total_price'] += vol_price
                            la['max_delivery_time'] = max(la['max_delivery_time'], vol_delivery)

                # Montar quotes_data deste listing
                listing_quotes_data = []
                for svc_id, la in listing_agg.items():
                    entry = dict(la['base'])
                    if la['has_error']:
                        if not entry.get('error'):
                            entry['error'] = (
                                'Serviço indisponível para um ou mais volumes deste item.'
                            )
                    else:
                        price_str = f'{la["total_price"]:.2f}'
                        entry['price'] = price_str
                        entry['custom_price'] = price_str
                        entry['delivery_time'] = la['max_delivery_time']
                        entry['custom_delivery_time'] = la['max_delivery_time']
                        entry.pop('error', None)
                    listing_quotes_data.append(entry)

                by_listing[str(listing.id)] = {
                    'listing_id': listing.id,
                    'title': listing.title,
                    'shipping_method': listing.shipping_method,
                    'packages_count': len(listing_volumes),
                    'services': self._format_services(listing_quotes_data),
                    'unavailable_services': self._format_unavailable_services(listing_quotes_data),
                }

                # Acumular no agregado global
                for svc_id, la in listing_agg.items():
                    if svc_id not in global_agg:
                        global_agg[svc_id] = {
                            'base': la['base'],
                            'total_price': 0.0,
                            'max_delivery_time': 0,
                            'has_error': la['has_error'],
                        }
                    ga = global_agg[svc_id]
                    if la['has_error']:
                        ga['has_error'] = True
                    else:
                        if not ga['has_error']:
                            ga['total_price'] += la['total_price']
                            ga['max_delivery_time'] = max(
                                ga['max_delivery_time'], la['max_delivery_time']
                            )

            if not all_volumes:
                raise ShippingValidationError(
                    'Nenhum volume encontrado para o pedido. '
                    'Verifique se os produtos possuem dimensões configuradas.'
                )

            # Calcular dimensões consolidadas (para armazenamento no ShippingQuote)
            package_weight = sum(v['weight'] for v in all_volumes)
            package_height = max(v['height'] for v in all_volumes)
            package_width = max(v['width'] for v in all_volumes)
            package_length = sum(v['length'] for v in all_volumes)

            try:
                # Montar quotes_data global agregado
                quotes_data = []
                for svc_id, ga in global_agg.items():
                    entry = dict(ga['base'])
                    if ga['has_error']:
                        if not entry.get('error'):
                            entry['error'] = (
                                'Serviço indisponível para um ou mais volumes do pedido.'
                            )
                    else:
                        price_str = f'{ga["total_price"]:.2f}'
                        entry['price'] = price_str
                        entry['custom_price'] = price_str
                        entry['delivery_time'] = ga['max_delivery_time']
                        entry['custom_delivery_time'] = ga['max_delivery_time']
                        entry.pop('error', None)
                    quotes_data.append(entry)

                logger.info(
                    f'[create_shipping_quote_by_seller] Cotação por listing concluída — '
                    f'{len(by_listing)} listing(s), {len(quotes_data)} serviço(s) no agregado. '
                    f'Total de volumes: {len(all_volumes)}'
                )

                # Salvar cotação no banco (com dados agregados + by_listing)
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
                    quotes_data={
                        'services': quotes_data,
                        'by_listing': by_listing,
                        'melhor_envio_listing_ids': [it.listing.id for it in me_items],
                    },
                    expires_at=timezone.now() + timedelta(hours=2)
                )

                # Separar serviços disponíveis dos indisponíveis (agregado global).
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
                    'by_listing': by_listing,
                    'total_value': total_value,
                    'items_count': len(items),
                    # Itens incluídos no cálculo de frete via Melhor Envio
                    'melhor_envio_items': [
                        {
                            'listing_id': it.listing.id,
                            'title': it.listing.title,
                            'shipping_method': it.listing.shipping_method,
                        }
                        for it in me_items
                    ],
                    # Itens excluídos do cálculo (somente in_person)
                    'in_person_items': [
                        {
                            'listing_id': it.listing.id,
                            'title': it.listing.title,
                            'shipping_method': it.listing.shipping_method,
                        }
                        for it in in_person_items
                    ] if in_person_items else [],
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
    
    def _build_volumes_for_items(self, seller_items) -> list:
        """
        Constrói a lista de volumes para o payload ME a partir dos OrderItems do vendedor.

        Estratégia:
        - Se o listing do item tiver ListingPackages, cada pacote multiplicado pela
          quantidade do OrderItem vira um volume separado no payload.
        - Caso contrário, faz fallback para os campos legados do listing/item,
          criando um volume por unidade do OrderItem.

        Validação de girth dos Correios (PAC/SEDEX):
        Cada volume é validado individualmente contra o limite de perímetro
        dos Correios: maior_lado + 2 * (lado2 + lado3) <= 200 cm.
        Volumes que excedem o limite recebem um aviso no log, mas não bloqueiam
        o envio (para não impedir o uso de outras transportadoras como JADLOG,
        J&T, Loggi).

        Args:
            seller_items: QuerySet ou lista de OrderItem do vendedor.

        Returns:
            list: Lista de dicts com height, width, length (int, cm) e weight (float, kg).

        Raises:
            ShipmentCreationError: Se nenhum volume puder ser calculado.
        """
        from orders.models import OrderItem  # evitar import circular no top

        volumes = []

        for item in seller_items:
            listing = item.listing
            packages = list(listing.packages.all())

            if packages:
                # Novo caminho: cada pacote × quantidade vira um volume separado
                for pkg in packages:
                    for _ in range(item.quantity):
                        vol_height = int(round(float(pkg.height_cm)))
                        vol_width = int(round(float(pkg.width_cm)))
                        vol_length = int(round(float(pkg.length_cm)))
                        vol_weight = round(float(pkg.weight_kg), 3)

                        # Warn on Correios girth violation per individual volume
                        dims_sorted = sorted([vol_height, vol_width, vol_length], reverse=True)
                        girth = dims_sorted[0] + 2 * (dims_sorted[1] + dims_sorted[2])
                        if girth > 200:
                            logger.warning(
                                f'Volume do pacote {pkg.id} (listing {listing.id}) excede o '
                                f'limite de girth dos Correios: {girth}cm > 200cm. '
                                f'h={vol_height}, w={vol_width}, l={vol_length}. '
                                f'Correios (PAC/SEDEX) pode rejeitar. Verifique os dados no DB.'
                            )

                        volumes.append({
                            'height': vol_height,
                            'width': vol_width,
                            'length': vol_length,
                            'weight': vol_weight,
                        })
            else:
                # Fallback: campos legados do item (snapshot) ou do listing
                weight = float(item.weight_kg) if item.weight_kg else float(listing.weight_kg or 0)
                height = float(item.height_cm) if item.height_cm else float(listing.height_cm or 0)
                width = float(item.width_cm) if item.width_cm else float(listing.width_cm or 0)
                length = float(item.length_cm) if item.length_cm else float(listing.length_cm or 0)

                for _ in range(item.quantity):
                    vol_height = int(round(height))
                    vol_width = int(round(width))
                    vol_length = int(round(length))
                    vol_weight = round(weight, 3)

                    dims_sorted = sorted([vol_height, vol_width, vol_length], reverse=True)
                    girth = dims_sorted[0] + 2 * (dims_sorted[1] + dims_sorted[2])
                    if girth > 200:
                        logger.warning(
                            f'Volume legado do item (listing {listing.id}) excede o '
                            f'limite de girth dos Correios: {girth}cm > 200cm. '
                            f'h={vol_height}, w={vol_width}, l={vol_length}. '
                            f'Correios (PAC/SEDEX) pode rejeitar. Verifique os dados no DB.'
                        )

                    volumes.append({
                        'height': vol_height,
                        'width': vol_width,
                        'length': vol_length,
                        'weight': vol_weight,
                    })

        if not volumes:
            raise Exception('Nenhum volume encontrado para criar o envio. '
                            'Verifique se os itens possuem dimensões configuradas.')

        return volumes

    def _build_volumes_for_raw_items(self, seller_validated_items) -> list:
        """
        Versão de _build_volumes_for_items para o fluxo `add_to_cart_raw`,
        onde os items ainda não existem no banco como OrderItem — são dicts
        com chaves: listing, quantity, dimensions (weight_kg, height_cm, etc.).

        Estratégia igual à de _build_volumes_for_items: prefere ListingPackages
        e faz fallback para o dict de dimensions.

        Args:
            seller_validated_items: Lista de dicts com:
                - listing: instância de MarketplaceListing
                - quantity: int
                - dimensions: dict com weight_kg, height_cm, width_cm, length_cm

        Returns:
            list: Lista de dicts com height, width, length (int, cm) e weight (float, kg).

        Raises:
            Exception: Se nenhum volume puder ser calculado.
        """
        volumes = []

        for item_data in seller_validated_items:
            listing = item_data['listing']
            quantity = item_data['quantity']
            dimensions = item_data.get('dimensions', {})

            packages = list(listing.packages.all())

            if packages:
                for pkg in packages:
                    for _ in range(quantity):
                        vol_height = int(round(float(pkg.height_cm)))
                        vol_width = int(round(float(pkg.width_cm)))
                        vol_length = int(round(float(pkg.length_cm)))
                        vol_weight = round(float(pkg.weight_kg), 3)

                        dims_sorted = sorted([vol_height, vol_width, vol_length], reverse=True)
                        girth = dims_sorted[0] + 2 * (dims_sorted[1] + dims_sorted[2])
                        if girth > 200:
                            logger.warning(
                                f'Volume do pacote {pkg.id} (listing {listing.id}) excede o '
                                f'limite de girth dos Correios: {girth}cm > 200cm. '
                                f'h={vol_height}, w={vol_width}, l={vol_length}. '
                                f'Vendedor: {listing.seller_id}'
                            )

                        volumes.append({
                            'height': vol_height,
                            'width': vol_width,
                            'length': vol_length,
                            'weight': vol_weight,
                        })
            else:
                # Fallback para dimensions dict
                weight = float(dimensions.get('weight_kg', 0))
                height = float(dimensions.get('height_cm', 0))
                width = float(dimensions.get('width_cm', 0))
                length = float(dimensions.get('length_cm', 0))

                for _ in range(quantity):
                    vol_height = int(round(height))
                    vol_width = int(round(width))
                    vol_length = int(round(length))
                    vol_weight = round(weight, 3)

                    dims_sorted = sorted([vol_height, vol_width, vol_length], reverse=True)
                    girth = dims_sorted[0] + 2 * (dims_sorted[1] + dims_sorted[2])
                    if girth > 200:
                        logger.warning(
                            f'Volume legado (listing {listing.id}) excede o '
                            f'limite de girth dos Correios: {girth}cm > 200cm. '
                            f'h={vol_height}, w={vol_width}, l={vol_length}.'
                        )

                    volumes.append({
                        'height': vol_height,
                        'width': vol_width,
                        'length': vol_length,
                        'weight': vol_weight,
                    })

        if not volumes:
            raise Exception('Nenhum volume encontrado para criar o envio. '
                            'Verifique se os itens possuem dimensões configuradas.')

        return volumes

    def _post_to_cart(self, service_id, from_block, to_block, products, volume, options, seller):
        """
        Faz UMA chamada POST /api/v2/me/cart com um único volume.

        Cada ListingPackage gera uma chamada separada para que cada pacote
        seja tratado como um envio independente no Melhor Envio.

        Args:
            service_id: ID do serviço ME (ex: '1' para Correios PAC)
            from_block: Dict com dados do remetente
            to_block: Dict com dados do destinatário
            products: Lista de produtos (mesma para todos os volumes)
            volume: Dict com height, width, length (int) e weight (float)
            options: Dict com insurance_value, receipt, own_hand, platform, tags
            seller: Instância de CustomUser do vendedor (para token OAuth)

        Returns:
            tuple: (response_dict, payload_dict)

        Raises:
            Exception: Se a chamada HTTP falhar
        """
        url = f'{self.base_url}/me/cart'

        # Garantir que service_id seja inteiro (ME rejeita strings)
        try:
            service_id_int = int(service_id)
        except (TypeError, ValueError):
            logger.error(f'[_post_to_cart] service_id inválido: {service_id!r} (tipo {type(service_id)})')
            raise Exception(f'service_id inválido para o carrinho ME: {service_id!r}')

        # Validar campos críticos do bloco from antes de enviar
        from_phone = from_block.get('phone', '')
        if not from_phone:
            logger.warning(
                '[_post_to_cart] from.phone está VAZIO — ME pode retornar 500. '
                'Verifique se o endereço do vendedor possui telefone cadastrado.'
            )
        elif len(from_phone) < 10:
            logger.warning(
                f'[_post_to_cart] from.phone={from_phone!r} tem menos de 10 dígitos — '
                'ME pode rejeitar o payload. Formato esperado: DDD + número (10 ou 11 dígitos).'
            )

        from_state = from_block.get('state_abbr', '')
        if not from_state:
            logger.warning(
                '[_post_to_cart] from.state_abbr está VAZIO — ME pode retornar 500. '
                'Verifique o campo state no endereço do vendedor.'
            )

        payload = {
            'service': service_id_int,
            'from': from_block,
            'to': to_block,
            'products': products,
            'volumes': [volume],
            'options': options,
        }

        logger.info(
            f'[_post_to_cart] Payload COMPLETO enviado ao ME cart:\n'
            f'{json.dumps(payload, default=str, indent=2)}'
        )

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(seller=seller, require_oauth=True),
                timeout=30,
            )
            response.raise_for_status()
            return response.json(), payload
        except requests.exceptions.HTTPError as e:
            error_detail = 'Resposta não disponível'
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except Exception:
                    error_detail = e.response.text
            status_code = e.response.status_code if e.response is not None else 'N/A'
            logger.error(
                f'Erro HTTP ao adicionar volume ao carrinho ME: '
                f'{status_code} — service={service_id_int} — volume={volume} — {error_detail}\n'
                f'Payload enviado: {json.dumps(payload, default=str, indent=2)}'
            )
            # Mensagem amigável para o erro genérico do ME (500)
            if status_code == 500 or (isinstance(error_detail, dict) and 'Houve um erro' in str(error_detail)):
                raise Exception(
                    f'O Melhor Envio rejeitou o serviço {service_id_int} para este vendedor. '
                    f'Verifique se o vendedor tem o serviço/transportadora configurado e ativo '
                    f'em sua conta Melhor Envio. Detalhe: {error_detail}'
                )
            raise Exception(f'Erro ao adicionar envio ao carrinho: {error_detail}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao adicionar volume ao carrinho ME: {e}')
            raise Exception(f'Erro ao adicionar envio ao carrinho: {e}')

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

        # VALIDAÇÃO 2: CPF do vendedor e do comprador (apenas PF suportado)
        seller_document = getattr(seller, 'cpf', '')
        if seller_document:
            validated_seller_doc = self._validate_document(seller_document, 'CPF do vendedor')
        else:
            raise ShippingValidationError('Vendedor não possui CPF cadastrado')

        # Validar CPF do comprador (buscar do modelo de usuário)
        buyer_document = getattr(order.buyer, 'cpf', '')
        if buyer_document:
            validated_buyer_doc = self._validate_document(buyer_document, 'CPF do comprador')
        else:
            raise ShippingValidationError('Comprador não possui CPF cadastrado')

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

        # Construir volumes a partir dos ListingPackages (ou fallback legado)
        # Cada pacote × quantidade vira um volume separado no payload ME.
        # Validação de girth dos Correios é feita por volume em _build_volumes_for_items.
        seller_items_list = list(seller_items.select_related('listing').prefetch_related('listing__packages'))
        volumes = self._build_volumes_for_items(seller_items_list)

        # Resolver identidade do remetente: usar dados da conta ME do vendedor se disponível
        from ..models import SellerMelhorEnvioToken
        from .melhor_envio_oauth_service import MelhorEnvioOAuthService

        oauth_service = MelhorEnvioOAuthService()
        environment = oauth_service.environment

        seller_me_token = SellerMelhorEnvioToken.objects.filter(
            seller=seller,
            environment=environment,
            is_active=True
        ).first()

        if seller_me_token and seller_me_token.me_document:
            sender_document = seller_me_token.me_document
            sender_email = seller_me_token.me_email or seller.email
            sender_name = seller_me_token.me_firstname or seller.get_full_name() or seller.email
        else:
            # Fallback para CPF do vendedor no marketplace
            sender_document = validated_seller_doc
            sender_email = seller.email
            sender_name = seller.get_full_name() or seller.email

        sender_digits = sender_document.replace('.', '').replace('/', '').replace('-', '')
        if len(sender_digits) == 14:
            raise ShippingValidationError(
                'Envio via Melhor Envio para vendedores PJ (CNPJ) não é suportado. '
                'Configure o remetente como CPF (Pessoa Física).'
            )

        from_block = {
            'name': sender_name,
            'phone': self._sanitize_phone(seller_address.recipient_phone),
            'email': sender_email,
            'document': sender_digits,
            'postal_code': origin_zipcode.replace('-', ''),
            'address': seller_address.street,
            'number': seller_address.number,
            'complement': seller_address.complement or '',
            'district': seller_address.neighborhood,
            'city': seller_address.city,
            # Normalizar state para maiúsculas — ME exige 'SP', 'PR', etc. (não 'Pr' ou 'sp')
            'state_abbr': (seller_address.state or '').upper().strip(),
            'country_id': 'BR',
        }

        buyer_digits = validated_buyer_doc.replace('.', '').replace('/', '').replace('-', '')

        to_block = {
            'name': order.shipping_address.get('recipient_name', ''),
            'phone': self._sanitize_phone(order.shipping_address.get('recipient_phone', '')),
            'email': order.buyer.email,
            'document': buyer_digits,
            'country_id': 'BR',
            'postal_code': destination_zipcode.replace('-', ''),
            'address': order.shipping_address['street'],
            'number': order.shipping_address['number'],
            'complement': order.shipping_address.get('complement', ''),
            'district': order.shipping_address['neighborhood'],
            'city': order.shipping_address['city'],
            # Normalizar state para maiúsculas
            'state_abbr': (order.shipping_address.get('state', '') or '').upper().strip(),
        }

        original_value = float(sum(item.subtotal for item in seller_items))
        insurance_capped = original_value > settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE
        if insurance_capped:
            logger.warning(
                f'Valor segurado limitado de R${original_value:.2f} para '
                f'R${settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE:.2f} (limite para envios não comerciais). '
                f'Pedido: {order.order_number}, vendedor: {seller.email}'
            )

        options = {
            'insurance_value': min(original_value, settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE),
            'receipt': False,
            'own_hand': False,
            'non_commercial': getattr(settings, 'MELHOR_ENVIO_NON_COMMERCIAL', True),
            'platform': getattr(settings, 'MELHOR_ENVIO_PLATFORM_NAME', 'Marketplace Academia'),
            'tags': [{'tag': str(order.order_number), 'url': ''}],
        }

        # Uma chamada ao carrinho por volume (= por ListingPackage).
        # Isso cria N envios independentes no ME — um por caixa física.
        logger.info(
            f'Adicionando {len(volumes)} volume(s) ao carrinho ME: pedido {order.order_number}, '
            f'vendedor {seller.email}, serviço {shipping_service_id}'
        )
        cart_results = []
        base_payload = None
        for idx, volume in enumerate(volumes):
            result, sent = self._post_to_cart(
                shipping_service_id, from_block, to_block, products, volume, options, seller
            )
            if base_payload is None:
                base_payload = sent
            logger.info(
                f'Volume {idx + 1}/{len(volumes)} adicionado ao carrinho: '
                f'me_id={result.get("id")}, pedido {order.order_number}'
            )
            cart_results.append(result)

        if insurance_capped:
            cart_results[0]['_insurance_warning'] = {
                'original_value': original_value,
                'capped_value': settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE,
                'message': (
                    f'O valor segurado foi limitado de R${original_value:.2f} para '
                    f'R${settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE:.2f}. '
                    'Envios não comerciais possuem limite máximo de seguro de R$1.000,00.'
                ),
            }

        return cart_results, base_payload

    def checkout_cart(self, order_ids, seller=None):
        """
        PASSO 2: Compra/Checkout dos envios do carrinho

        Args:
            order_ids: Lista de IDs dos pedidos no Melhor Envio (não confundir com Order do Django)
            seller: Vendedor cujo token OAuth deve ser utilizado (opcional)

        Returns:
            dict: Resultado do checkout
        """
        url = f'{self.base_url}/me/shipment/checkout'

        payload = {
            'orders': order_ids  # IDs retornados ao adicionar no carrinho
        }

        try:
            logger.info(f'Fazendo checkout dos envios: {order_ids}')
            response = requests.post(url, json=payload, headers=self._get_headers(seller=seller, require_oauth=True), timeout=30)
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
        Cria o registro de Shipment no banco de dados a partir da(s) resposta(s) do carrinho.

        Quando o listing possui múltiplos pacotes, `cart_data` é uma lista de respostas
        (uma por volume/pacote). Também aceita um único dict para retrocompatibilidade.

        Args:
            order: Pedido
            seller: Vendedor
            cart_data: Lista de respostas do carrinho ME ou único dict (retrocompat)
            sent_payload: Payload base enviado ao carrinho (para fallback de endereços)

        Returns:
            tuple: (Shipment, insurance_warning ou None)
        """
        # Normalizar: aceitar tanto lista quanto dict único
        if isinstance(cart_data, dict):
            cart_data_list = [cart_data]
        else:
            cart_data_list = list(cart_data)

        if not cart_data_list:
            raise Exception('Nenhuma resposta do carrinho recebida')

        first = cart_data_list[0]
        melhorenvio_order_id = first.get('id')
        if not melhorenvio_order_id:
            raise Exception('ID do pedido não retornado ao adicionar no carrinho')

        all_me_ids = [r['id'] for r in cart_data_list if r.get('id')]

        # Extrair warning de insurance (presente apenas no primeiro item quando limitado)
        insurance_warning = None
        for r in cart_data_list:
            w = r.pop('_insurance_warning', None)
            if w:
                insurance_warning = w
                break

        # Calcular dimensões consolidadas para armazenamento no Shipment
        # (usamos agregação para os campos legados do Shipment — não afeta o payload ME)
        seller_items = order.items.filter(seller=seller).select_related('listing').prefetch_related('listing__packages')
        total_weight = 0.0
        max_height = 0.0
        max_width = 0.0
        total_length = 0.0
        for item in seller_items:
            listing = item.listing
            packages = list(listing.packages.all())
            if packages:
                for pkg in packages:
                    total_weight += float(pkg.weight_kg) * item.quantity
                    max_height = max(max_height, float(pkg.height_cm))
                    max_width = max(max_width, float(pkg.width_cm))
                    total_length += float(pkg.length_cm) * item.quantity
            else:
                w = float(item.weight_kg) if item.weight_kg else float(listing.weight_kg or 0)
                h = float(item.height_cm) if item.height_cm else float(listing.height_cm or 0)
                wi = float(item.width_cm) if item.width_cm else float(listing.width_cm or 0)
                le = float(item.length_cm) if item.length_cm else float(listing.length_cm or 0)
                total_weight += w * item.quantity
                max_height = max(max_height, h)
                max_width = max(max_width, wi)
                total_length += le * item.quantity

        # Extrair carrier info da primeira resposta
        service_data = first.get('service') or {}
        company_data = service_data.get('company') or {}
        carrier_name = company_data.get('name', '')
        carrier_service = service_data.get('name', '')

        # Fallback: buscar carrier info do shipping_services da order (dados da cotação)
        if not carrier_name or not carrier_service:
            seller_shipping = (order.shipping_services or {}).get(str(seller.id), {})
            if isinstance(seller_shipping, dict):
                # Para split delivery, os dados de transportadora estão em 'shipping'
                if seller_shipping.get('delivery_method') == 'split':
                    seller_shipping = seller_shipping.get('shipping', {})
                company = seller_shipping.get('company', '')
                if isinstance(company, dict):
                    carrier_name = carrier_name or company.get('name', '')
                else:
                    carrier_name = carrier_name or str(company)
                carrier_service = carrier_service or seller_shipping.get('service_name', '')

        # Somar custos e seguros de todos os volumes (cada chamada retorna price individual)
        total_shipping_cost = sum(float(r.get('price', 0) or 0) for r in cart_data_list)
        total_insurance_value = sum(float(r.get('insurance_value', 0) or 0) for r in cart_data_list)

        # Extrair endereços da primeira resposta (com fallback para o payload enviado)
        origin_address = first.get('from') or sent_payload.get('from', {})
        destination_address = first.get('to') or sent_payload.get('to', {})

        # Criar registro de Shipment com status 'pending' (ainda sem checkout)
        shipment = Shipment.objects.create(
            order=order,
            seller=seller,
            melhorenvio_order_id=melhorenvio_order_id,
            melhorenvio_order_ids=all_me_ids,
            carrier_name=carrier_name,
            carrier_service=carrier_service,
            shipping_cost=total_shipping_cost,
            insurance_value=total_insurance_value,
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

        # Validar CPFs do vendedor e do comprador (apenas PF suportado)
        seller_document = getattr(seller, 'cpf', '')
        if not seller_document:
            raise ShippingValidationError('Vendedor não possui CPF cadastrado')
        validated_seller_doc = self._validate_document(seller_document, 'CPF do vendedor')

        buyer_document = getattr(buyer, 'cpf', '')
        if not buyer_document:
            raise ShippingValidationError('Comprador não possui CPF cadastrado')
        validated_buyer_doc = self._validate_document(buyer_document, 'CPF do comprador')

        # Preparar produtos e calcular seguro
        # A API do ME exige que quantity e unitary_value sejam strings.
        # unitary_value deve ter sempre 2 casas decimais (ex: "525.50", não "525.5").
        products = []
        total_insurance = Decimal('0')
        raw_unit_prices = []
        for item_data in seller_validated_items:
            raw_price = float(item_data['unit_price'])
            raw_unit_prices.append(raw_price)
            products.append({
                'name': item_data['product_snapshot']['name'],
                'quantity': str(item_data['quantity']),
            })
            total_insurance += item_data['unit_price'] * item_data['quantity']

        # O unitary_value precisa ser proporcional ao insurance_value capeado.
        # ME valida que insurance_value >= sum(unitary_value * quantity) e rejeita com 500
        # se o produto declara valor maior do que o seguro cobre.
        max_insurance = float(settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE)
        total_float = float(total_insurance)
        insurance_ratio = min(1.0, max_insurance / total_float) if total_float > 0 else 1.0
        for p, raw_price in zip(products, raw_unit_prices):
            p['unitary_value'] = f"{raw_price * insurance_ratio:.2f}"

        # Construir volumes a partir dos ListingPackages (ou fallback para dimensions dict)
        # Enriquece cada item com a instância do listing para consulta aos packages
        for item_data in seller_validated_items:
            if 'listing' not in item_data or not hasattr(item_data['listing'], 'packages'):
                from products.models import MarketplaceListing as _ML
                item_data['listing'] = _ML.objects.prefetch_related('packages').get(
                    id=item_data['listing'].id
                )
        volumes = self._build_volumes_for_raw_items(seller_validated_items)

        # Resolver identidade do remetente: usar dados da conta ME do vendedor se disponível
        from ..models import SellerMelhorEnvioToken
        from .melhor_envio_oauth_service import MelhorEnvioOAuthService

        oauth_service = MelhorEnvioOAuthService()
        environment = oauth_service.environment

        seller_me_token = SellerMelhorEnvioToken.objects.filter(
            seller=seller,
            environment=environment,
            is_active=True
        ).first()

        if seller_me_token and seller_me_token.me_document:
            sender_document = seller_me_token.me_document
            sender_email = seller_me_token.me_email or seller.email
            sender_name = seller_me_token.me_firstname or seller.get_full_name() or seller.email
            logger.info(
                f'[add_to_cart_raw] Usando credenciais da conta ME cacheada: '
                f'me_email={seller_me_token.me_email!r}, me_document={seller_me_token.me_document[:4]}*** '
                f'(vendedor marketplace: {seller.email})'
            )
        else:
            # Fallback para CPF do vendedor no marketplace
            sender_document = validated_seller_doc
            sender_email = seller.email
            sender_name = seller.get_full_name() or seller.email
            logger.warning(
                f'[add_to_cart_raw] ATENÇÃO: me_document vazio no SellerMelhorEnvioToken de {seller.email}. '
                f'Usando dados do marketplace como fallback. '
                f'O token ME pode ter sido salvo sem cachear os dados da conta. '
                f'Reconecte a conta ME em /api/logistics/me/connect/'
            )

        sender_digits = sender_document.replace('.', '').replace('/', '').replace('-', '')

        logger.info(
            f'[add_to_cart_raw] Remetente: document={sender_digits}, email={sender_email}, '
            f'postal_code={origin_zipcode.replace("-", "")}, district={seller_address.neighborhood}, '
            f'phone={self._sanitize_phone(seller_address.recipient_phone) or "(vazio)"}'
        )

        if len(sender_digits) == 14:
            raise ShippingValidationError(
                'Envio via Melhor Envio para vendedores PJ (CNPJ) não é suportado. '
                'Configure o remetente como CPF (Pessoa Física).'
            )

        if not sender_digits:
            raise ShippingValidationError(
                'Documento do remetente não configurado. '
                'Garanta que o vendedor possui CPF cadastrado ou conecte sua conta Melhor Envio.'
            )

        from_block = {
            'name': sender_name,
            'phone': self._sanitize_phone(seller_address.recipient_phone),
            'email': sender_email,
            'document': sender_digits,
            'postal_code': origin_zipcode.replace('-', ''),
            'address': seller_address.street,
            'number': seller_address.number,
            'complement': seller_address.complement or '',
            'district': seller_address.neighborhood,
            'city': seller_address.city,
            # Normalizar state para maiúsculas — ME exige 'SP', 'PR', etc. (não 'Pr' ou 'sp')
            'state_abbr': (seller_address.state or '').upper().strip(),
            'country_id': 'BR',
        }

        buyer_digits = validated_buyer_doc.replace('.', '').replace('/', '').replace('-', '')

        capped_insurance = min(float(total_insurance), settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE)
        insurance_capped = float(total_insurance) > settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE

        to_block = {
            'name': shipping_address_dict.get('recipient_name', ''),
            'phone': self._sanitize_phone(shipping_address_dict.get('recipient_phone', '')) or '11999999999',
            'email': buyer.email,
            'document': buyer_digits,
            'country_id': 'BR',
            'postal_code': destination_zipcode.replace('-', ''),
            'address': shipping_address_dict['street'],
            'number': shipping_address_dict['number'],
            'complement': shipping_address_dict.get('complement', ''),
            'district': shipping_address_dict['neighborhood'],
            'city': shipping_address_dict['city'],
            # Normalizar state para maiúsculas
            'state_abbr': (shipping_address_dict.get('state', '') or '').upper().strip(),
        }

        if insurance_capped:
            logger.warning(
                f'Valor segurado limitado de R${float(total_insurance):.2f} para '
                f'R${settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE:.2f}. '
                f'Vendedor: {seller.email}'
            )

        options = {
            'insurance_value': capped_insurance,
            'receipt': False,
            'own_hand': False,
            'non_commercial': getattr(settings, 'MELHOR_ENVIO_NON_COMMERCIAL', True),
            'platform': getattr(settings, 'MELHOR_ENVIO_PLATFORM_NAME', 'Marketplace Academia'),
        }

        # Uma chamada ao carrinho por volume (= por ListingPackage).
        logger.info(
            f'Adicionando {len(volumes)} volume(s) ao carrinho ME (pré-order): '
            f'vendedor {seller.email}, serviço {service_id}'
        )
        cart_results = []
        base_payload = None
        for idx, volume in enumerate(volumes):
            result, sent = self._post_to_cart(
                service_id, from_block, to_block, products, volume, options, seller
            )
            if base_payload is None:
                base_payload = sent
            logger.info(
                f'Volume {idx + 1}/{len(volumes)} adicionado ao carrinho ME (pré-order): '
                f'me_id={result.get("id")}'
            )
            cart_results.append(result)

        if insurance_capped:
            cart_results[0]['_insurance_warning'] = {
                'original_value': float(total_insurance),
                'capped_value': settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE,
                'message': (
                    f'Valor segurado limitado de R${float(total_insurance):.2f} para '
                    f'R${settings.MELHOR_ENVIO_MAX_INSURANCE_VALUE:.2f}.'
                ),
            }

        return cart_results, base_payload

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

        # ETAPA 2: Fazer checkout com TODOS os cart IDs do shipment.
        # Quando o listing tem múltiplos pacotes físicos, o ME gera um cart ID
        # por volume. Usar melhorenvio_order_ids (lista completa) garante que
        # todos os volumes sejam enviados ao checkout, não apenas o primeiro.
        all_me_ids = shipment.melhorenvio_order_ids or [shipment.melhorenvio_order_id]
        checkout_result = self.checkout_cart(all_me_ids)

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
    
    def generate_label(self, shipment, seller=None):
        """
        PASSO 3: Gera etiqueta de envio (após pagamento confirmado)

        Args:
            shipment: Instância do Shipment
            seller: Instância de CustomUser (vendedor). Se fornecido, usa token do vendedor.
                    Se None, tenta inferir o seller a partir do shipment.

        Returns:
            str: URL da etiqueta
        """
        # Resolver o seller a partir do shipment se não fornecido
        if seller is None:
            seller = getattr(shipment, 'seller', None)

        # Todos os IDs ME do shipment (um por pacote quando listing tem múltiplos pacotes)
        all_me_ids = shipment.melhorenvio_order_ids or [shipment.melhorenvio_order_id]

        # Gerar etiqueta
        generate_url = f'{self.base_url}/me/shipment/generate'
        generate_payload = {'orders': all_me_ids}

        # Etiquetas DEVEM ser geradas com token OAuth para que o webhook seja acionado.
        # Usa o token do vendedor se disponível; caso contrário usa token da plataforma.
        oauth_headers = self._get_headers(seller=seller, require_oauth=True)

        try:
            logger.info(f'Gerando etiqueta para envio(s) {all_me_ids}')
            response = requests.post(
                generate_url,
                json=generate_payload,
                headers=oauth_headers,
                timeout=30
            )
            response.raise_for_status()
            logger.info(f'Etiqueta(s) gerada(s) com sucesso: {all_me_ids}')
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
            'orders': all_me_ids,
        }

        try:
            logger.info(f'Obtendo URL de impressão da etiqueta: {all_me_ids}')
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
            shipment.status = 'generated'
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
        all_ids = shipment.melhorenvio_order_ids or [shipment.melhorenvio_order_id]
        payload = {'orders': all_ids}

        try:
            logger.info(f'Rastreando envio: {all_ids}')
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            data = response.json()

            # Processar dados de rastreamento de TODOS os pacotes
            if data and isinstance(data, dict):
                # Ordem dos status do menos para o mais avançado.
                # Usamos o status do pacote menos avançado como status geral
                # (o pedido só está "entregue" quando TODOS os pacotes estiverem entregues).
                STATUS_ORDER = [
                    'pending', 'created', 'released', 'generated',
                    'posted', 'in_transit', 'out_for_delivery', 'delivered',
                ]

                def _status_rank(s):
                    mapped = self._map_status(s)
                    try:
                        return STATUS_ORDER.index(mapped)
                    except ValueError:
                        return -1

                tracking_codes = []
                pkg_statuses = []

                for me_id in all_ids:
                    pkg_data = data.get(me_id, {})
                    if not pkg_data:
                        logger.warning(f'Nenhum dado retornado pelo ME para o pacote {me_id}')
                        continue

                    # Coletar tracking code deste pacote
                    if pkg_data.get('tracking'):
                        tracking_codes.append(pkg_data['tracking'])

                    # Coletar status deste pacote
                    if pkg_data.get('status'):
                        pkg_statuses.append(pkg_data['status'])

                    # Criar/atualizar eventos deste pacote.
                    # A unicidade é (shipment, occurred_at, package_me_id), portanto
                    # dois pacotes do mesmo shipment com evento no mesmo instante
                    # geram registros separados e identificáveis.
                    for event in pkg_data.get('events', []):
                        ShipmentTracking.objects.get_or_create(
                            shipment=shipment,
                            occurred_at=event.get('datetime'),
                            package_me_id=me_id,
                            defaults={
                                'status': event.get('status', ''),
                                'description': event.get('description', ''),
                                'location': event.get('location', ''),
                            }
                        )

                # Persistir tracking codes
                if tracking_codes:
                    shipment.melhorenvio_tracking_code = tracking_codes[0]   # retrocompat
                    shipment.melhorenvio_tracking_codes = tracking_codes     # lista completa

                # Determinar status geral a partir do pacote menos avançado
                if pkg_statuses:
                    least_advanced_raw = min(pkg_statuses, key=_status_rank)
                    overall_status = self._map_status(least_advanced_raw)
                    shipment.status = overall_status

                    if overall_status == 'delivered' and not shipment.delivered_at:
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