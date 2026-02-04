import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import ShippingQuote, Shipment, ShipmentTracking, Address


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
        """
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
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_detail = e.response.text if e.response else str(e)
            raise Exception(f'Erro HTTP ao calcular frete: {e.response.status_code} - {error_detail}')
        except requests.exceptions.RequestException as e:
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
            # Buscar endereço de envio do vendedor
            seller_address = Address.objects.filter(
                user=seller,
                is_shipping_address=True,
                is_active=True
            ).first()
            
            if not seller_address:
                quotes_by_seller[seller.id] = {
                    'error': 'Vendedor não possui endereço de envio cadastrado',
                    'seller_name': seller.get_full_name() or seller.email,
                    'seller_id': seller.id
                }
                continue
            
            # Preparar produtos para API (OPÇÃO 1 - Recomendada)
            products = []
            total_value = 0
            
            for item in items:
                listing = item.listing
                product_data = {
                    'id': str(listing.id),
                    'width': float(listing.width_cm),
                    'height': float(listing.height_cm),
                    'length': float(listing.length_cm),
                    'weight': float(listing.weight_kg),
                    'insurance_value': float(listing.price),
                    'quantity': item.quantity
                }
                products.append(product_data)
                total_value += float(listing.price) * item.quantity
            
            # Opções adicionais
            options = {
                'insurance_value': total_value,
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
                
                # Salvar cotação no banco
                quote = ShippingQuote.objects.create(
                    user=user,
                    seller=seller,
                    origin_zipcode=seller_address.zipcode,
                    origin_address=seller_address.to_dict(),
                    destination_zipcode=destination_zipcode,
                    destination_address={},
                    weight=sum(p['weight'] * p['quantity'] for p in products),
                    height=max(p['height'] for p in products),
                    width=max(p['width'] for p in products),
                    length=sum(p['length'] * p['quantity'] for p in products),
                    declared_value=total_value,
                    quotes_data=quotes_data,
                    expires_at=timezone.now() + timedelta(hours=24)
                )
                
                quotes_by_seller[seller.id] = {
                    'quote_id': quote.id,
                    'seller_name': seller.get_full_name() or seller.email,
                    'seller_id': seller.id,
                    'seller_city': seller_address.city,
                    'seller_state': seller_address.state,
                    'services': self._format_services(quotes_data),
                    'total_value': total_value,
                    'items_count': len(items)
                }
                
            except Exception as e:
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
            dict: Dados do envio criado no carrinho
        """
        url = f'{self.base_url}/me/cart'
        
        # Buscar endereço do vendedor
        seller_address = Address.objects.filter(
            user=seller,
            is_shipping_address=True,
            is_active=True
        ).first()
        
        if not seller_address:
            raise Exception(f'Vendedor não possui endereço de envio cadastrado')
        
        # Filtrar itens do vendedor
        seller_items = order.items.filter(seller=seller)
        if not seller_items.exists():
            raise Exception(f'Nenhum item do vendedor encontrado neste pedido')
        
        # Preparar produtos
        products = []
        for item in seller_items:
            products.append({
                'name': item.product_name,
                'quantity': item.quantity,
                'unitary_value': float(item.unit_price)
            })
        
        # Preparar volumes (dimensões dos produtos)
        volumes = []
        for item in seller_items:
            volumes.append({
                'height': float(item.height_cm),
                'width': float(item.width_cm),
                'length': float(item.length_cm),
                'weight': float(item.weight_kg)
            })
        
        # Montar payload
        payload = {
            'service': shipping_service_id,
            'from': {
                'name': seller.get_full_name() or seller.email,
                'phone': seller_address.recipient_phone,
                'email': seller.email,
                'document': getattr(seller, 'cpf', ''),
                'company_document': getattr(seller, 'cnpj', ''),
                'postal_code': seller_address.zipcode.replace('-', ''),
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
                'document': order.shipping_address.get('document', ''),
                'postal_code': order.shipping_address['zipcode'].replace('-', ''),
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
                'insurance_value': float(sum(item.subtotal for item in seller_items)),
                'receipt': False,
                'own_hand': False,
                'collect': False
            }
        }
        
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_detail = e.response.text if hasattr(e, 'response') and e.response else str(e)
            raise Exception(f'Erro ao adicionar envio ao carrinho: {error_detail}')
    
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
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_detail = e.response.text if hasattr(e, 'response') and e.response else str(e)
            raise Exception(f'Erro no checkout: {error_detail}')
    
    def create_shipment(self, order, seller, shipping_service_id):
        """
        Cria envio completo (adiciona ao carrinho + faz checkout)
        
        Args:
            order: Pedido
            seller: Vendedor
            shipping_service_id: ID do serviço de frete
            
        Returns:
            Shipment: Instância do envio criado
        """
        # PASSO 1: Adicionar ao carrinho
        cart_data = self.create_shipment_in_cart(order, seller, shipping_service_id)
        melhorenvio_order_id = cart_data.get('id')
        
        if not melhorenvio_order_id:
            raise Exception('ID do pedido não retornado ao adicionar no carrinho')
        
        # PASSO 2: Fazer checkout
        checkout_result = self.checkout_cart([melhorenvio_order_id])
        
        # Verificar se checkout foi bem-sucedido
        purchase = checkout_result.get('purchase', {})
        if purchase.get('status') != 'paid':
            # Em sandbox, pagamento é aprovado em até 5 minutos
            # Em produção, depende do método de pagamento
            pass
        
        # Criar registro de Shipment
        shipment = Shipment.objects.create(
            order=order,
            seller=seller,
            melhorenvio_order_id=melhorenvio_order_id,
            carrier_name=cart_data.get('service', {}).get('company', {}).get('name', ''),
            carrier_service=cart_data.get('service', {}).get('name', ''),
            shipping_cost=cart_data.get('price', 0),
            insurance_value=cart_data.get('insurance_value', 0),
            weight=cart_data.get('weight', 0),
            height=cart_data.get('height', 0),
            width=cart_data.get('width', 0),
            length=cart_data.get('length', 0),
            origin_address=cart_data.get('from', {}),
            destination_address=cart_data.get('to', {}),
            status='pending'  # Aguardando pagamento
        )
        
        return shipment
    
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
            response = requests.post(
                generate_url, 
                json=generate_payload, 
                headers=self.headers, 
                timeout=30
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            error_detail = e.response.text if hasattr(e, 'response') and e.response else str(e)
            raise Exception(f'Erro ao gerar etiqueta: {error_detail}')
        
        # Obter URL para impressão
        print_url = f'{self.base_url}/me/shipment/print'
        print_payload = {
            'mode': 'private',
            'orders': [shipment.melhorenvio_order_id]
        }
        
        try:
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
            
            return label_url
            
        except requests.exceptions.RequestException as e:
            error_detail = e.response.text if hasattr(e, 'response') and e.response else str(e)
            raise Exception(f'Erro ao obter URL da etiqueta: {error_detail}')
    
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
            
            return data
            
        except requests.exceptions.RequestException as e:
            error_detail = e.response.text if hasattr(e, 'response') and e.response else str(e)
            raise Exception(f'Erro ao rastrear envio: {error_detail}')
    
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