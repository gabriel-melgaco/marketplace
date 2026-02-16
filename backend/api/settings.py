from pathlib import Path
import os
from dotenv import load_dotenv
from datetime import timedelta


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY')

DEBUG = os.getenv('DEBUG', True)

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

#PARA LOGIN COM HTTPS
CSRF_TRUSTED_ORIGINS = os.getenv('TRUSTED_ORIGINS', '').split(',')

#PARA REQUISIÇÕES API COM HTTPS
CORS_ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '').split(',')


# Application definition
AUTH_USER_MODEL = 'authentication.CustomUser'


INSTALLED_APPS = [
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

]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'auth_kit.authentication.JWTCookieAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
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
    ],
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
    'ENUM_NAME_OVERRIDES': {
        'OrderStatusEnum': 'orders.models.Order.STATUS_CHOICES',
        'ShipmentStatusEnum': 'logistics.models.Shipment.STATUS_CHOICES',
        'DeliveryStatusEnum': 'logistics.models.OrderDelivery.DELIVERY_STATUS_CHOICES',
        'MeetingStatusEnum': 'logistics.models.InPersonDelivery.MEETING_STATUS_CHOICES',
        'PaymentMethodEnum': 'payments.models.Payment.PAYMENT_METHOD_CHOICES',
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
}

ACCOUNT_EMAIL_VERIFICATION = "mandatory"
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 7
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True


ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False

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
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY')
MINIO_BUCKET = os.getenv('MINIO_BUCKET')
MINIO_USE_SSL = False
MINIO_PUBLIC_URL = os.getenv('MINIO_PUBLIC_URL', f"http://{MINIO_ENDPOINT}")



# ==================================================================
# STRIPE CONFIGURATION
# ==================================================================
STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY', 'pk_test_...')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', 'sk_test_...')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_...')

# =================== MELHOR ENVIO CONFIGURATION ===================
MELHOR_ENVIO_TOKEN = os.getenv('MELHOR_ENVIO_TOKEN', '')
MELHOR_ENVIO_SANDBOX = os.getenv('MELHOR_ENVIO_SANDBOX', True)
MELHOR_ENVIO_WEBHOOK_SECRET = os.getenv('MELHOR_ENVIO_WEBHOOK_SECRET', '')
MELHOR_ENVIO_MAX_INSURANCE_VALUE = float(os.getenv('MELHOR_ENVIO_MAX_INSURANCE_VALUE', '1000.00'))
# =================== PAYMENT CONFIGURATION ===================
# Taxa da plataforma (%)
PLATFORM_FEE_PERCENTAGE = 10  # 10% de taxa

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
