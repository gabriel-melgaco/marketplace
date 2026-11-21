# Marketplace Academia

Multi-vendor REST API for buying and selling gym equipment in Brazil. Sellers create individual listings; buyers browse, add items to the cart, and complete purchases from multiple sellers in a single checkout. Each order is automatically split by seller, payments are routed via Stripe Connect, and shipping is orchestrated by Melhor Envio with per-seller OAuth2 credentials.

## Repository Structure

```
marketplace_academia/
├── backend/    # Django API (Python 3.12)
└── frontend/   # React + Vite + Tailwind CSS interface
```

---

## Backend

### Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | Django 5.1 + Django REST Framework 3.15 |
| ASGI / WebSocket | Daphne 4 + Django Channels 4 |
| Database | PostgreSQL (production) / SQLite (development) |
| Cache | Redis (django-redis) |
| Task queue | Celery 5 + Celery Beat (Redis broker) |
| Authentication | JWT via HttpOnly cookies (drf-auth-kit + simplejwt) |
| Social login | Google OAuth2 (django-allauth) |
| Payments | Stripe (Payment Intents + Connect) |
| Shipping | Melhor Envio API v2 (per-seller OAuth2) |
| Image storage | MinIO (S3-compatible) |
| Transactional email | Resend (SMTP) |
| ZIP code lookup | ViaCEP |
| Documentation | drf-spectacular (Swagger UI + Redoc) |
| Observability | structlog |
| Security | argon2-cffi, cryptography |
| Testing | pytest + pytest-django |
| Containerization | Docker |

### App Architecture

```
backend/
├── api/                  # Settings, ASGI, Celery, root URLs
├── authentication/       # Custom user, registration, social login
├── products/             # Catalog: categories, brands, series, conditions, listings
├── orders/               # Cart, orders, status state machine
├── payments/             # Stripe PaymentIntent, Connect, refunds, payouts
├── logistics/            # Shipping (Melhor Envio), shipments, addresses, in-person delivery
├── chats/                # Real-time messages via WebSocket
├── notifications/        # In-app notification feed + preferences
└── storage/              # Image upload and management via MinIO
```

### Main Features

#### Authentication
- Registration with required email (CPF, date of birth, full name)
- Mandatory email verification before the first login
- Email/password login with JWT via HttpOnly cookies
- Social login with Google OAuth2
- Password reset and change
- Access token: 24h | Refresh token: 30 days

#### Products and Catalog
- Hierarchy: Category → Product → Listing (`MarketplaceListing`)
- Filters by brand, series, condition, price, and seller
- Full listing management by the seller (create, edit, activate/deactivate, mark as sold)
- Per-listing image upload (stored in MinIO)
- Listing creation blocked if the seller has no active Melhor Envio token

#### Cart and Orders
- Persistent cart per authenticated user
- Multi-vendor checkout: one `Order` automatically created per seller
- Snapshot of price, address, and product data at purchase time
- Order state machine with audit trail:

```
pending_payment → paid → processing → shipped → delivered
                                               ↘ refunded
                                    ↘ cancelled / failed
```

- Automatic cancellation of unpaid orders after a configurable time (Celery)
- Automatic delivery confirmation after a configurable period without buyer response

#### Payments (Stripe)
- Server-side PaymentIntent creation with per-seller split calculation
- Payment confirmation automatically triggers shipment creation
- Configurable platform fee (default: 10%)
- Seller payout scheduled via Celery Beat after delivery confirmation
- **Stripe Connect**: seller onboarding with hosted link, status sync, and disconnection
- **Refunds** with a non-unilateral flow:

```
requested → seller_reviewing → approved / rejected
                             ↘ escalated → platform_decision → refunded
```

- Automatic deadline expiration via Celery Beat (escalation, seller review)

#### Logistics (Melhor Envio)
- Per-seller OAuth2 authentication with HMAC-SHA256 in the state parameter (anti-CSRF)
- Real-time shipping quotes (PAC, SEDEX, Jadlog, Mini, Azul, Total Express)
- Automatic shipment creation on payment confirmation
- Label generation and download by the seller
- **Dual delivery per item**: carrier (`shipping`) or in-person (`in_person`)
- `OrderDelivery` orchestrates the global status; `InPersonDelivery` manages meeting scheduling
- ZIP code lookup via ViaCEP

#### Real-Time Chat
- WebSocket via Django Channels + Redis Channel Layer
- Conversation types: buyer↔seller, buyer↔support, group support
- Paginated message history via REST
- Unread message tracking per participant
- JWT middleware for WebSocket handshake authentication

#### Notifications
- In-app notification feed with read/unread tracking
- Per-user delivery preferences (in-app, email, or both)
- Automatically triggered by state changes in orders, payments, and refunds
- Delivery via WebSocket (real-time) + Celery (asynchronous)

### API Conventions

| Convention | Detail |
|------------|--------|
| Base URL (local) | `http://localhost:8000/api/` |
| Interactive documentation | `/api/docs/` (Swagger UI) and `/api/redoc/` (Redoc) |
| Primary keys | UUID for Orders, RefundRequests, Conversations; integer for the rest |
| Field naming | `snake_case` |
| Dates | ISO 8601 with timezone |
| Monetary values | Decimal strings in BRL (e.g., `"149.90"`) |
| Pagination | Page-number, default size 20 (`?page=2`) |
| Language | Brazilian Portuguese |
| Currency | BRL |

### How to Run (Development)

**Prerequisites:** Python 3.12, Redis running locally.

```bash
cd backend

# Create the virtual environment and install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install --no-deps drf-auth-kit==1.1.1

# Configure environment variables
cp .env.example .env   # edit with your credentials

# Run migrations
python manage.py migrate

# Start the ASGI server (Daphne)
python manage.py runserver

# In another terminal — Celery worker
celery -A api worker -l info

# In another terminal — Celery Beat (scheduled tasks)
celery -A api beat -l info
```

### Docker

```bash
cd backend
docker build -t marketplace-academia-backend .
docker run -p 5000:5000 --env-file .env marketplace-academia-backend
```

### Tests

```bash
cd backend
pytest
```

### Environment Variables

```env
# Django
SECRET_KEY=
DEBUG=
ALLOWED_HOSTS=
TRUSTED_ORIGINS=
ALLOWED_ORIGINS=
ENVIRONMENT=prd        # omit to use SQLite in dev

# Database (production)
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

# Email (Resend)
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
MELHOR_ENVIO_TOKEN=          # fallback for quotes without an active OAuth connection
MELHOR_ENVIO_SANDBOX=True
MELHOR_ENVIO_WEBHOOK_SECRET=

# Business rules
PLATFORM_FEE_PERCENTAGE=10
PAYOUT_DAYS=7
AUTO_CONFIRM_DELIVERY_DAYS=20
ORDER_PAYMENT_TIMEOUT_MINUTES=30
```

### External Integrations

| Service | Purpose |
|---------|---------|
| **Stripe** | Payment processing, multi-vendor split, webhooks |
| **Melhor Envio** | Shipping quotes, shipment creation, labels, tracking |
| **ViaCEP** | Address lookup by ZIP code |
| **Google OAuth2** | Social login |
| **MinIO** | Listing image storage (S3-compatible) |
| **Resend** | Transactional emails (verification, password reset) |
| **Redis** | Cache, Celery broker, WebSocket channel layer |
