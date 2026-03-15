from pathlib import Path
import os
from dotenv import load_dotenv
from datetime import timedelta

DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY')

DEBUG = os.getenv('DEBUG', True)

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

#PARA LOGIN COM HTTPS
CSRF_TRUSTED_ORIGINS = os.getenv('TRUSTED_ORIGINS', '').split(',')

#PARA REQUISIÇÕES API COM HTTPS
CORS_ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '').split(',')
# Necessário para enviar cookies JWT em requisições cross-origin (ex: Vite :5173 → Django :8000)
CORS_ALLOW_CREDENTIALS = True


# Application definition
AUTH_USER_MODEL = 'authentication.CustomUser'


INSTALLED_APPS = [
    # Daphne must be first so it overrides runserver with ASGI support (WebSocket)
    'daphne',

    #ALLOWED ORIGINS
    'corsheaders',

    'django.contrib.sites',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'authentication',

    'rest_framework',
    #DRF Auth Kit Basic Config
    'allauth',
    'allauth.account',    
    'auth_kit',
    #Social Authentication Setup
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.github',
    'auth_kit.social',
    #Documentation
    'drf_spectacular',
    'products',

    'storage',

    'orders',

    'payments',

    'logistics',

    'chats',

    'channels',

    'notifications',

]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'auth_kit.authentication.JWTCookieAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}


SPECTACULAR_SETTINGS = {
    'TITLE': 'Gym Equipment Marketplace API',
    'DESCRIPTION': 'Complete REST API for a gym equipment marketplace platform with multi-vendor support, payment processing, shipping integration, and dual delivery options (shipping + in-person).',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'TAGS': [
        {'name': 'Authentication', 'description': 'User registration, login, profile management, and social authentication'},
        {'name': 'Products', 'description': 'Product catalog, categories, brands, marketplace listings, and search'},
        {'name': 'Cart', 'description': 'Shopping cart management'},
        {'name': 'Orders', 'description': 'Order creation, management, and buyer operations'},
        {'name': 'Seller Orders', 'description': 'Seller order management and status updates'},
        {'name': 'Payments', 'description': 'Payment intent creation, confirmation, refunds, and seller payouts'},
        {'name': 'Stripe Connect', 'description': 'Seller onboarding and connected account management'},
        {'name': 'Logistics - Addresses', 'description': 'Address management for buyers and sellers'},
        {'name': 'Logistics - Shipping', 'description': 'Shipping quotes, shipments, tracking, and label generation'},
        {'name': 'Logistics - Deliveries', 'description': 'Order delivery orchestration (dual delivery: shipping + in-person)'},
        {'name': 'Logistics - In-Person', 'description': 'In-person delivery management, meeting scheduling, and confirmation'},
        {'name': 'Logistics - Utilities', 'description': 'CEP/zipcode lookup and other utilities'},
        {'name': 'Chat', 'description': 'Real-time messaging between buyers, sellers, and support'},
        {'name': 'Notifications', 'description': 'User notifications, read status management, and delivery preferences'},
        {'name': 'Refund Requests', 'description': 'Non-unilateral refund request workflow: buyer → seller review → platform escalation'},
    ],
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
    'ENUM_NAME_OVERRIDES': {
        'OrderStatusEnum': 'orders.models.Order.STATUS_CHOICES',
        'ShipmentStatusEnum': 'logistics.models.Shipment.STATUS_CHOICES',
        'DeliveryStatusEnum': 'logistics.models.OrderDelivery.DELIVERY_STATUS_CHOICES',
        'MeetingStatusEnum': 'logistics.models.InPersonDelivery.MEETING_STATUS_CHOICES',
        'PaymentMethodEnum': 'payments.models.Payment.PAYMENT_METHOD_CHOICES',
        'ConversationTypeEnum': 'chats.models.Conversation.CONVERSATION_TYPE_CHOICES',
        'ConversationStatusEnum': 'chats.models.Conversation.STATUS_CHOICES',
        'ParticipantRoleEnum': 'chats.models.ConversationParticipant.ROLE_CHOICES',
        'MessageTypeEnum': 'chats.models.Message.MESSAGE_TYPE_CHOICES',
        'RefundRequestStatusEnum': 'payments.models.RefundRequest.STATUS_CHOICES',
        'RefundTypeEnum': 'payments.models.RefundRequest.REFUND_TYPE_CHOICES',
        # Resolve colisão de payment_method entre Payment (com choices) e Order (CharField sem choices)
        'PaymentMethodEnum': ['credit_card', 'debit_card', 'pix', 'boleto'],
    },
}

MIDDLEWARE = [
    #ALLOWED ORIGINS
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',

    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'api.wsgi.application'
ASGI_APPLICATION = 'api.asgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
ENVIRONMENT = os.getenv('ENVIRONMENT')
if ENVIRONMENT == 'prd':
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql_psycopg2",
            'NAME': os.getenv('POSTGRES_DB'),
            'USER': os.getenv('POSTGRES_USER'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
            'HOST': os.getenv('POSTGRES_HOST'),
            'PORT': os.getenv('POSTGRES_PORT'),
            },
        }
else:

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'pt-br'

TIME_ZONE = 'America/Sao_Paulo'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'


# ===================================================================
# AUTHENTICATION SETTINGS
# ===================================================================

AUTH_KIT = {
    "REGISTER_SERIALIZER": "authentication.serializers.CustomRegisterSerializer",
    # URL base do frontend usada como redirect_uri ao trocar o code com o Google.
    # O backend gera: {BASE_URL}/google — deve bater com o redirect_uri que o frontend
    # passa no início do fluxo OAuth e com o URI cadastrado no Google Cloud Console.
    "SOCIAL_LOGIN_CALLBACK_BASE_URL": os.getenv("FRONTEND_BASE_URL", "http://localhost:5173"),
    "SOCIAL_CONNECT_CALLBACK_BASE_URL": os.getenv("FRONTEND_BASE_URL", "http://localhost:5173"),
}

ACCOUNT_EMAIL_VERIFICATION = "mandatory"
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 7
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True


ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = None

ACCOUNT_SIGNUP_FIELDS = [
    'email*',
    'complete_name*',
    'cpf*',
    'birthday*',
    'password1*',
    'password2*',
]



SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
}

SITE_ID = 1

SOCIALACCOUNT_ADAPTER = 'authentication.adapters.CustomSocialAccountAdapter'


SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email', 'birthday'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
        'FETCH_USERINFO': True,
        'APP': {
            'client_id': os.getenv('CLIENT_ID_OAUTH'),
            'secret': os.getenv('SECRET_KEY_OAUTH'),
            'key': '',
        }
    },
}
# Access https://developers.google.com/oauthplayground/ for tests 
#====================================================================

# ===================================================================
# EMAIL API SETTINGS
# ==================================================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.resend.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'resend'
EMAIL_HOST_PASSWORD = os.getenv('RESEND_API_KEY')
DEFAULT_FROM_EMAIL = 'Meg Dev <no-reply@email.megdev.com.br>'
SERVER_EMAIL = DEFAULT_FROM_EMAIL


# ===================================================================
# MINIO BUCKET S3 SETTINGS
# ==================================================================
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_BUCKET = os.getenv("MINIO_BUCKET")

MINIO_USE_SSL = os.getenv("MINIO_USE_SSL", "false").lower() == "true"
MINIO_PUBLIC_USE_SSL = os.getenv("MINIO_PUBLIC_USE_SSL", "true").lower() == "true"

MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL")
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT")

if not MINIO_PUBLIC_URL or not MINIO_PUBLIC_ENDPOINT:
    raise RuntimeError("MinIO público não configurado corretamente")




# ==================================================================
# STRIPE CONFIGURATION
# ==================================================================
STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY', 'pk_test_...')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', 'sk_test_...')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_...')
STRIPE_CONNECT_WEBHOOK_SECRET = os.getenv('STRIPE_CONNECT_WEBHOOK_SECRET', '')

# URL base do frontend React — usada em callbacks OAuth/Stripe Connect
FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'https://marketplace.megdev.com.br')

# URL pública do backend — usada em callbacks do Stripe que precisam chegar no Django
BACKEND_BASE_URL = os.getenv('BACKEND_BASE_URL', 'https://api.megdev.com.br')

# =================== MELHOR ENVIO CONFIGURATION ===================

# Token legado (usado como fallback para cálculo de frete se OAuth por vendedor não estiver ativo)
# ATENÇÃO: Etiquetas criadas com este token NÃO acionam o webhook!
MELHOR_ENVIO_TOKEN = os.getenv('MELHOR_ENVIO_TOKEN', '')
MELHOR_ENVIO_SANDBOX = os.getenv('MELHOR_ENVIO_SANDBOX', 'True').lower() not in ('false', '0', 'no')
MELHOR_ENVIO_WEBHOOK_SECRET = os.getenv('MELHOR_ENVIO_WEBHOOK_SECRET', '')
MELHOR_ENVIO_MAX_INSURANCE_VALUE = float(os.getenv('MELHOR_ENVIO_MAX_INSURANCE_VALUE', '1000.00'))
# Envios não comerciais (CPF/pessoa física). Obrigatório para Correios sem contrato comercial.
MELHOR_ENVIO_NON_COMMERCIAL = os.getenv('MELHOR_ENVIO_NON_COMMERCIAL', 'True').lower() not in ('false', '0', 'no')

# Melhor Envio OAuth 2.0 — Credenciais do aplicativo (plataforma)
# Obtenha em: https://melhorenvio.com.br/painel/gerenciar/aplicativos
MELHOR_ENVIO_CLIENT_ID = os.getenv('MELHOR_ENVIO_CLIENT_ID', '')
MELHOR_ENVIO_CLIENT_SECRET = os.getenv('MELHOR_ENVIO_CLIENT_SECRET', '')

# URL de callback OAuth da plataforma (admin)
# Deve apontar para /api/logistics/webhooks/melhor-envio/callback/
MELHOR_ENVIO_REDIRECT_URI = os.getenv(
    'MELHOR_ENVIO_REDIRECT_URI',
    'https://api.megdev.com.br/api/logistics/webhooks/melhor-envio/callback/'
)

# URL de callback OAuth por vendedor
# Deve apontar para /api/logistics/me/callback/
MELHOR_ENVIO_SELLER_REDIRECT_URI = os.getenv(
    'MELHOR_ENVIO_SELLER_REDIRECT_URI',
    'https://api.megdev.com.br/api/logistics/me/callback/'
)

# Segredo para assinar o parâmetro state do OAuth (HMAC-SHA256, prevenção de CSRF)
# Gere com: python -c "import secrets; print(secrets.token_hex(32))"
MELHOR_ENVIO_STATE_SECRET = os.getenv('MELHOR_ENVIO_STATE_SECRET', '')

# Email para o User-Agent obrigatório nas chamadas à API
MELHOR_ENVIO_USER_AGENT_EMAIL = os.getenv('MELHOR_ENVIO_USER_AGENT_EMAIL', 'gabrielmelgacom@gmail.com')

MELHOR_ENVIO_PLATFORM_NAME = os.getenv('MELHOR_ENVIO_PLATFORM_NAME', 'Marketplace Academia')

# IDs de serviços ME solicitados na cotação (separados por vírgula).
# 1=PAC, 2=SEDEX, 3=Jadlog .Package, 4=Jadlog .Com, 7=Mini, 17=Azul, 18=Total Express
MELHOR_ENVIO_DEFAULT_SERVICES = os.getenv('MELHOR_ENVIO_DEFAULT_SERVICES', '1,2,3,4,7,17,18')


# =================== PAYMENT CONFIGURATION ===================
# Taxa da plataforma (%)
PLATFORM_FEE_PERCENTAGE = int(os.getenv('PLATFORM_FEE_PERCENTAGE', 10))

# Dias para liberar pagamento ao vendedor
PAYOUT_DAYS = 7  # Após 7 dias da confirmação da entrega

STOCK_STRATEGY = 'on_payment'
# =================== LOGISTICS CONFIGURATION ===================
# Auto-create shipments when payment is confirmed
AUTO_CREATE_SHIPMENTS = True

# =================== LOGGING ===================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'logistics': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'orders': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'payments': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


#=========================================================================
#-------------------------REDIS CONFIG------------------------------------
#========================================================================='
if ENVIRONMENT == "prd":
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"redis://:{os.getenv('REDIS_PASSWORD')}@redis:6379/1",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            }
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": "redis://localhost:6379/1",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            }
        }
    }

# =========================================================================
# DJANGO CHANNELS — WebSocket channel layer
# Uses Redis DB 2 (separate from Django cache on DB 1) to avoid eviction
# collisions. In production the Redis password is applied via the URL.
# =========================================================================
if ENVIRONMENT == 'prd':
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [f"redis://:{os.getenv('REDIS_PASSWORD')}@redis:6379/2"],
                "capacity": 100,
                "expiry": 60,
            },
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                # channels_redis 4.x não aceita 'db' como parâmetro direto.
                # O banco Redis é especificado via URL no campo 'hosts'.
                "hosts": ["redis://127.0.0.1:6379/2"],
                "capacity": 100,
                "expiry": 60,
            },
        }
    }

# Add chats logger
LOGGING['loggers']['chats'] = {
    'handlers': ['console'],
    'level': 'DEBUG',
    'propagate': False,
}

# Add notifications logger
LOGGING['loggers']['notifications'] = {
    'handlers': ['console'],
    'level': 'INFO',
    'propagate': False,
}

# =========================================================================
# CELERY CONFIGURATION
# Broker and result backend both use Redis DB 0 (separate from cache DB 1
# and channel layer DB 2).
# =========================================================================
if ENVIRONMENT == 'prd':
    _redis_pass = os.getenv('REDIS_PASSWORD', '')
    _redis_auth = f':{_redis_pass}@' if _redis_pass else ''
    CELERY_BROKER_URL = f'redis://{_redis_auth}redis:6379/0'
    CELERY_RESULT_BACKEND = f'redis://{_redis_auth}redis:6379/0'
else:
    CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
    CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/0'

CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
# Prevent tasks from running indefinitely
CELERY_TASK_SOFT_TIME_LIMIT = 300   # 5 min soft limit
CELERY_TASK_TIME_LIMIT = 600        # 10 min hard limit

# ----------------------
# Celery Beat Schedule
# ----------------------
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Escala RefundRequests cujo prazo do vendedor expirou (hourly)
    'expire-seller-review-hourly': {
        'task': 'payments.tasks.expire_seller_review_task',
        'schedule': crontab(minute=0),
    },
    # Fecha RefundRequests cuja janela de escalada do comprador expirou (hourly)
    'expire-buyer-escalation-hourly': {
        'task': 'payments.tasks.expire_buyer_escalation_window_task',
        'schedule': crontab(minute=15),
    },
    # Lembra vendedores cujo prazo vence em menos de 24h (daily 9h)
    'notify-seller-deadline-reminder-daily': {
        'task': 'payments.tasks.notify_seller_deadline_reminder_task',
        'schedule': crontab(hour=9, minute=0),
    },
}
