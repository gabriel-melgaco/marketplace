# Marketplace Academia

API REST multi-vendor para compra e venda de equipamentos de academia no Brasil. Vendedores cadastram anúncios individuais; compradores navegam, adicionam ao carrinho e finalizam compras de múltiplos vendedores em um único checkout. Cada pedido é dividido automaticamente por vendedor, os pagamentos são roteados via Stripe Connect e o frete é orquestrado pelo Melhor Envio com credenciais OAuth2 por vendedor.

## Estrutura do Repositório

```
marketplace_academia/
├── backend/    # API Django (Python 3.12)
└── frontend/   # Interface React + Vite + Tailwind CSS
```

---

## Backend

### Stack Tecnológica

| Camada | Tecnologia |
|--------|------------|
| Framework | Django 5.1 + Django REST Framework 3.15 |
| ASGI / WebSocket | Daphne 4 + Django Channels 4 |
| Banco de dados | PostgreSQL (produção) / SQLite (desenvolvimento) |
| Cache | Redis (django-redis) |
| Fila de tarefas | Celery 5 + Celery Beat (Redis broker) |
| Autenticação | JWT via HttpOnly cookies (drf-auth-kit + simplejwt) |
| Login social | Google OAuth2 (django-allauth) |
| Pagamentos | Stripe (Payment Intents + Connect) |
| Frete | Melhor Envio API v2 (OAuth2 por vendedor) |
| Storage de imagens | MinIO (S3-compatible) |
| E-mail transacional | Resend (SMTP) |
| CEP | ViaCEP |
| Documentação | drf-spectacular (Swagger UI + Redoc) |
| Observabilidade | structlog |
| Segurança | argon2-cffi, cryptography |
| Testes | pytest + pytest-django |
| Containerização | Docker |

### Arquitetura dos Apps

```
backend/
├── api/                  # Configurações, ASGI, Celery, URLs raiz
├── authentication/       # Usuário customizado, registro, login social
├── products/             # Catálogo: categorias, marcas, séries, condições, anúncios
├── orders/               # Carrinho, pedidos, state machine de status
├── payments/             # Stripe PaymentIntent, Connect, reembolsos, repasses
├── logistics/            # Frete (Melhor Envio), envios, endereços, entrega presencial
├── chats/                # Mensagens em tempo real via WebSocket
├── notifications/        # Feed de notificações in-app + preferências
└── storage/              # Upload e gestão de imagens via MinIO
```

### Funcionalidades Principais

#### Autenticação
- Registro com e-mail obrigatório (CPF, data de nascimento, nome completo)
- Verificação de e-mail mandatória antes do primeiro login
- Login por e-mail/senha com JWT via HttpOnly cookies
- Login social com Google OAuth2
- Reset e alteração de senha
- Access token: 24h | Refresh token: 30 dias

#### Produtos e Catálogo
- Hierarquia: Categoria → Produto → Anúncio (`MarketplaceListing`)
- Filtros por marca, série, condição, preço e vendedor
- Gestão completa do anúncio pelo vendedor (criar, editar, ativar/desativar, marcar como vendido)
- Upload de imagens por anúncio (armazenadas no MinIO)
- Criação de anúncio bloqueada se o vendedor não tiver token Melhor Envio ativo

#### Carrinho e Pedidos
- Carrinho persistente por usuário autenticado
- Checkout multi-vendor: um `Order` criado por vendedor automaticamente
- Snapshot de preço, endereço e dados do produto no momento da compra
- State machine de pedido com trilha de auditoria:

```
pending_payment → paid → processing → shipped → delivered
                                               ↘ refunded
                                    ↘ cancelled / failed
```

- Cancelamento automático de pedidos sem pagamento após tempo configurável (Celery)
- Confirmação automática de entrega após prazo configurável sem resposta do comprador

#### Pagamentos (Stripe)
- Criação de PaymentIntent server-side com cálculo de split por vendedor
- Confirmação de pagamento dispara criação de envios automaticamente
- Taxa de plataforma configurável (padrão: 10%)
- Repasse ao vendedor agendado via Celery Beat após entrega confirmada
- **Stripe Connect**: onboarding de vendedores com link hospedado, sincronização de status e desconexão
- **Reembolsos** com fluxo não-unilateral:

```
requested → seller_reviewing → approved / rejected
                             ↘ escalated → platform_decision → refunded
```

- Expiração automática de prazos via Celery Beat (escalada, revisão do vendedor)

#### Logística (Melhor Envio)
- Autenticação OAuth2 por vendedor com HMAC-SHA256 no state parameter (anti-CSRF)
- Cotação de frete em tempo real (PAC, SEDEX, Jadlog, Mini, Azul, Total Express)
- Criação automática de envio ao confirmar pagamento
- Geração e download de etiqueta pelo vendedor
- **Entrega dual por item**: transportadora (`shipping`) ou presencial (`in_person`)
- `OrderDelivery` orquestra o status global; `InPersonDelivery` gerencia agendamento de encontro
- Lookup de CEP via ViaCEP

#### Chat em Tempo Real
- WebSocket via Django Channels + Redis Channel Layer
- Tipos de conversa: comprador↔vendedor, comprador↔suporte, suporte em grupo
- Histórico de mensagens paginado via REST
- Controle de mensagens não lidas por participante
- Middleware JWT para autenticação no handshake WebSocket

#### Notificações
- Feed de notificações in-app com rastreamento leitura/não-lida
- Preferências de entrega por usuário (in-app, e-mail ou ambos)
- Disparadas automaticamente por mudanças de estado em pedidos, pagamentos e reembolsos
- Entrega via WebSocket (tempo real) + Celery (assíncrono)

### Convenções de API

| Convenção | Detalhe |
|-----------|---------|
| Base URL (local) | `http://localhost:8000/api/` |
| Documentação interativa | `/api/docs/` (Swagger UI) e `/api/redoc/` (Redoc) |
| Primary keys | UUID para Orders, RefundRequests, Conversations; inteiro para demais |
| Nomenclatura de campos | `snake_case` |
| Datas | ISO 8601 com timezone |
| Valores monetários | Strings decimal em BRL (ex: `"149.90"`) |
| Paginação | Page-number, tamanho padrão 20 (`?page=2`) |
| Idioma | Português brasileiro |
| Moeda | BRL |

### Como Executar (Desenvolvimento)

**Pré-requisitos:** Python 3.12, Redis rodando localmente.

```bash
cd backend

# Crie o ambiente virtual e instale as dependências
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install --no-deps drf-auth-kit==1.1.1

# Configure as variáveis de ambiente
cp .env.example .env   # edite com suas credenciais

# Execute as migrações
python manage.py migrate

# Inicie o servidor ASGI (Daphne)
python manage.py runserver

# Em outro terminal — worker Celery
celery -A api worker -l info

# Em outro terminal — Celery Beat (tarefas agendadas)
celery -A api beat -l info
```

### Docker

```bash
cd backend
docker build -t marketplace-academia-backend .
docker run -p 5000:5000 --env-file .env marketplace-academia-backend
```

### Testes

```bash
cd backend
pytest
```

### Variáveis de Ambiente

```env
# Django
SECRET_KEY=
DEBUG=
ALLOWED_HOSTS=
TRUSTED_ORIGINS=
ALLOWED_ORIGINS=
ENVIRONMENT=prd        # omitir para usar SQLite em dev

# Banco de dados (produção)
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_HOST=
POSTGRES_PORT=

# Redis
REDIS_PASSWORD=

# URLs
FRONTEND_BASE_URL=
BACKEND_BASE_URL=

# Google OAuth2
CLIENT_ID_OAUTH=
SECRET_KEY_OAUTH=

# E-mail (Resend)
RESEND_API_KEY=

# MinIO
MINIO_ENDPOINT=
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
MINIO_BUCKET=
MINIO_PUBLIC_URL=
MINIO_PUBLIC_ENDPOINT=
MINIO_USE_SSL=
MINIO_PUBLIC_USE_SSL=

# Stripe
STRIPE_PUBLIC_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_CONNECT_WEBHOOK_SECRET=

# Melhor Envio
MELHOR_ENVIO_CLIENT_ID=
MELHOR_ENVIO_CLIENT_SECRET=
MELHOR_ENVIO_STATE_SECRET=
MELHOR_ENVIO_SELLER_REDIRECT_URI=
MELHOR_ENVIO_TOKEN=          # fallback para cotações sem OAuth ativo
MELHOR_ENVIO_SANDBOX=True
MELHOR_ENVIO_WEBHOOK_SECRET=

# Regras de negócio
PLATFORM_FEE_PERCENTAGE=10
PAYOUT_DAYS=7
AUTO_CONFIRM_DELIVERY_DAYS=20
ORDER_PAYMENT_TIMEOUT_MINUTES=30
```

### Integrações Externas

| Serviço | Finalidade |
|---------|------------|
| **Stripe** | Processamento de pagamentos, split multi-vendor, webhooks |
| **Melhor Envio** | Cotação de frete, criação de envios, etiquetas, rastreamento |
| **ViaCEP** | Consulta de endereço por CEP |
| **Google OAuth2** | Login social |
| **MinIO** | Armazenamento de imagens de anúncios (S3-compatible) |
| **Resend** | E-mails transacionais (verificação, reset de senha) |
| **Redis** | Cache, broker Celery, channel layer WebSocket |
