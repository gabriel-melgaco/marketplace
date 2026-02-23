#!/usr/bin/env python3
"""
Teste de integração para /api/orders/create/
Executa contra servidor ao vivo (produção ou localhost).

Uso:
    python test_order_create_integration.py [base_url]

Exemplos:
    python test_order_create_integration.py http://localhost:8000
    python test_order_create_integration.py https://api.megdev.com.br

Variáveis de ambiente:
    BUYER_EMAIL      Email do comprador  (padrão: gabrielmelgacomwpp@gmail.com)
    BUYER_PASSWORD   Senha do comprador  (OBRIGATÓRIO)
    SERVICE_ID       ID do serviço de frete (padrão: 2 = SEDEX)
    LISTING_ID       ID fixo do produto a comprar (opcional, descoberto automaticamente)
"""

import sys
import os
import json
import time
import requests

# ─── Configuração ─────────────────────────────────────────────────────────────

BASE_URL       = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://localhost:8000'
BUYER_EMAIL    = os.getenv('BUYER_EMAIL',    'gabrielmelgacomwpp@gmail.com')
BUYER_PASSWORD = os.getenv('BUYER_PASSWORD', '')
SERVICE_ID     = int(os.getenv('SERVICE_ID', '2'))
LISTING_ID     = os.getenv('LISTING_ID', '')

# ─── Cores ─────────────────────────────────────────────────────────────────────

GREEN  = '\033[92m'
RED    = '\033[91m'
BLUE   = '\033[94m'
YELLOW = '\033[93m'
BOLD   = '\033[1m'
RESET  = '\033[0m'

OK   = f'{GREEN}✓{RESET}'
FAIL = f'{RED}✗{RESET}'
INFO = f'{BLUE}→{RESET}'
WARN = f'{YELLOW}!{RESET}'

# ─── Helpers ───────────────────────────────────────────────────────────────────

passed = []
failed = []


def section(title):
    print(f'\n{BOLD}{title}{RESET}')


def step_ok(msg):
    passed.append(msg)
    print(f'  {OK} {msg}')


def step_fail(msg, detail=''):
    failed.append(msg)
    print(f'  {FAIL} {RED}{msg}{RESET}')
    if detail:
        print(f'       {detail[:300]}')


def abort(msg, detail=''):
    step_fail(msg, detail)
    print_summary()
    sys.exit(1)


def print_summary():
    total = len(passed) + len(failed)
    print(f'\n{"─"*50}')
    print(f'{BOLD}Resultado: {len(passed)}/{total} verificações passaram{RESET}')
    if failed:
        print(f'{RED}Falhas:{RESET}')
        for f in failed:
            print(f'  {FAIL} {f}')
    print()


def pretty(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f'\n{BOLD}━━━ Teste de Integração — /api/orders/create/ ━━━{RESET}')
    print(f'  {INFO} Server:  {BASE_URL}')
    print(f'  {INFO} Buyer:   {BUYER_EMAIL}')
    print(f'  {INFO} Service: {SERVICE_ID}')

    if not BUYER_PASSWORD:
        abort('BUYER_PASSWORD não definido.',
              'Defina: export BUYER_PASSWORD="sua_senha"')

    session = requests.Session()
    session.headers.update({'Content-Type': 'application/json'})

    # ─────────────────────────────────────────────────────────────────────────
    section('1. Autenticação')

    r = session.post(f'{BASE_URL}/api/auth/login/', json={
        'email': BUYER_EMAIL,
        'password': BUYER_PASSWORD,
    })

    if r.status_code != 200:
        abort(f'Login falhou (HTTP {r.status_code})', r.text)

    step_ok(f'Login como {BUYER_EMAIL} (HTTP {r.status_code})')

    # auth_kit pode retornar token no body ou setar cookie
    body = r.json()
    access_token = body.get('access') or body.get('access_token') or body.get('token')
    if access_token:
        session.headers['Authorization'] = f'Bearer {access_token}'
        step_ok('Token JWT obtido do body')
    else:
        cookies = dict(r.cookies)
        if any('token' in k.lower() or 'jwt' in k.lower() or 'access' in k.lower()
               for k in cookies):
            step_ok('Token JWT obtido via cookie')
        else:
            step_ok('Sessão autenticada (cookies)')

    # Atualiza CSRF se presente
    if 'csrftoken' in session.cookies:
        session.headers['X-CSRFToken'] = session.cookies['csrftoken']

    # ─────────────────────────────────────────────────────────────────────────
    section('2. Endereço de entrega')

    r = session.get(f'{BASE_URL}/api/logistics/addresses/')
    if r.status_code != 200:
        abort(f'Falha ao listar endereços (HTTP {r.status_code})', r.text)

    addresses_data = r.json()
    addresses = addresses_data.get('results', addresses_data) \
        if isinstance(addresses_data, dict) else addresses_data

    shipping = [a for a in addresses
                if a.get('is_shipping_address') or a.get('address_type') == 'shipping']

    if not shipping:
        abort('Comprador não possui endereço de entrega cadastrado.',
              'Cadastre um endereço antes de rodar o teste.')

    address = shipping[0]
    address_id = address['id']
    step_ok(f'Endereço: {address.get("city")}/{address.get("state")} '
            f'(CEP {address.get("zipcode")}, id={address_id})')

    # ─────────────────────────────────────────────────────────────────────────
    section('3. Produto disponível')

    if LISTING_ID:
        r = session.get(f'{BASE_URL}/api/products/listings/{LISTING_ID}/')
        if r.status_code != 200:
            abort(f'Listing {LISTING_ID} não encontrado (HTTP {r.status_code})', r.text)
        listing = r.json()
        step_ok(f'Usando LISTING_ID={LISTING_ID} fixo')
    else:
        r = session.get(f'{BASE_URL}/api/products/listings/', params={'page_size': 20})
        if r.status_code != 200:
            abort(f'Falha ao listar produtos (HTTP {r.status_code})', r.text)

        listings_data = r.json()
        all_listings = listings_data.get('results', listings_data) \
            if isinstance(listings_data, dict) else listings_data

        if not all_listings:
            abort('Nenhum produto disponível no marketplace.')

        # Pula produtos do próprio comprador
        listing = None
        for lst in all_listings:
            seller = lst.get('seller')
            seller_email = lst.get('seller_email') or (
                seller.get('email') if isinstance(seller, dict) else None
            )
            if seller_email != BUYER_EMAIL and lst.get('quantity', 0) > 0:
                listing = lst
                break

        if not listing:
            listing = all_listings[0]  # fallback

    listing_id = listing['id']
    seller_field = listing.get('seller')
    seller_id = seller_field.get('id') if isinstance(seller_field, dict) else seller_field
    listing_title = listing.get('title') or listing.get('name', 'N/A')
    listing_price = listing.get('price', 'N/A')

    step_ok(f'Produto: "{listing_title}" | R${listing_price} | '
            f'listing_id={listing_id} | seller_id={seller_id}')

    # ─────────────────────────────────────────────────────────────────────────
    section('4. Carrinho')

    r = session.delete(f'{BASE_URL}/api/orders/cart/clear/')
    if r.status_code in (200, 204):
        step_ok('Carrinho limpo')
    else:
        print(f'  {WARN} Limpeza do carrinho retornou HTTP {r.status_code} (ignorado)')

    r = session.post(f'{BASE_URL}/api/orders/cart/add/', json={
        'listing': listing_id,
        'quantity': 1,
    })
    if r.status_code not in (200, 201):
        abort(f'Falha ao adicionar ao carrinho (HTTP {r.status_code})', r.text)

    cart_data = r.json()
    items = cart_data.get('items', [])
    step_ok(f'Item adicionado (listing={listing_id}), '
            f'{len(items)} item(s) no carrinho')

    # ─────────────────────────────────────────────────────────────────────────
    section('5. Cálculo de frete')

    r = session.post(f'{BASE_URL}/api/logistics/shipping/calculate/', json={
        'shipping_address_id': address_id,
    })
    if r.status_code != 200:
        abort(f'Falha ao calcular frete (HTTP {r.status_code})', r.text)

    quote_data = r.json()
    quotes_by_seller = quote_data.get('quotes_by_seller', {})

    if not quotes_by_seller:
        abort('Nenhuma cotação de frete disponível.',
              pretty(quote_data))

    shipping_services = {}
    for sid_str, seller_quote in quotes_by_seller.items():
        services = seller_quote.get('services', [])

        # Tenta o service_id solicitado; fallback para o primeiro disponível
        chosen = next((s for s in services if s['id'] == SERVICE_ID), None)
        if not chosen:
            chosen = next((s for s in services
                           if s.get('price') is not None and float(s.get('price', 0)) > 0),
                          None)
        if not chosen and services:
            chosen = services[0]

        if not chosen:
            abort(f'Nenhum serviço de frete disponível para vendedor {sid_str}.',
                  f'Serviços: {pretty(services)}')

        shipping_services[sid_str] = {
            'delivery_method': 'shipping',
            'service_id': chosen['id'],
            'cost': float(chosen.get('price', 0)),
        }

        name = chosen.get('name', 'N/A')
        price = chosen.get('price', 'N/A')
        days = chosen.get('delivery_time', '?')
        step_ok(f'Vendedor {sid_str}: {name} | R${price} | {days} dias '
                f'(service_id={chosen["id"]})')

    # ─────────────────────────────────────────────────────────────────────────
    section('6. Criação do pedido')

    payload = {
        'shipping_address_id': address_id,
        'shipping_services': shipping_services,
        'payment_method': 'credit_card',
    }

    print(f'  {INFO} Payload enviado:')
    for line in pretty(payload).splitlines():
        print(f'       {line}')

    t0 = time.time()
    r = session.post(f'{BASE_URL}/api/orders/create/', json=payload)
    elapsed = time.time() - t0

    print(f'  {INFO} Resposta: HTTP {r.status_code} ({elapsed:.2f}s)')

    if r.status_code == 201:
        order = r.json()
        step_ok(f'Pedido criado: {order.get("order_number", "N/A")} | '
                f'total=R${order.get("total", "N/A")} | '
                f'status={order.get("status", "N/A")}')

        # Verificações adicionais na resposta
        if order.get('status') == 'pending_payment':
            step_ok('Status correto: pending_payment')
        else:
            step_fail(f'Status inesperado: {order.get("status")}')

        if order.get('order_number', '').startswith('ORD-'):
            step_ok(f'Número do pedido no formato correto: {order["order_number"]}')
        else:
            step_fail(f'Formato de order_number inesperado: {order.get("order_number")}')

        if float(order.get('total', 0)) > 0:
            step_ok(f'Total > 0: R${order["total"]}')
        else:
            step_fail('Total zerado ou ausente')

    else:
        try:
            err = r.json()
            detail = pretty(err)
        except Exception:
            detail = r.text
        abort(f'Criação de pedido falhou (HTTP {r.status_code})', detail)

    # ─────────────────────────────────────────────────────────────────────────
    print_summary()

    if not failed:
        print(f'{GREEN}{BOLD}TODOS OS TESTES PASSARAM{RESET}')
        sys.exit(0)
    else:
        print(f'{RED}{BOLD}ALGUNS TESTES FALHARAM{RESET}')
        sys.exit(1)


if __name__ == '__main__':
    main()
