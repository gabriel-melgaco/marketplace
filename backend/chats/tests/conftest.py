"""
Fixtures compartilhadas para os testes do sistema de chat.

Estratégia de isolamento:
- Banco de dados: cada test usa transação revertida (@pytest.mark.django_db)
- Cache Redis: usa LocMemCache sobrescrito via override_settings para evitar
  contaminação entre testes e dependência de Redis externo nos testes unitários
- Channel Layer: usa InMemoryChannelLayer para testes de consumer sem Redis real
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import override_settings

User = get_user_model()

# Sobrescreve channel layer com in-memory para testes (sem Redis real necessário)
CHANNEL_LAYERS_TEST = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# Sobrescreve cache com LocMemCache para testes (sem Redis externo necessário)
CACHES_TEST = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "chat-tests",
    }
}


@pytest.fixture
def buyer(db):
    """Usuário com perfil de comprador."""
    return User.objects.create_user(
        email="buyer@test.com",
        password="testpass123",
        full_name="Comprador Teste",
    )


@pytest.fixture
def seller(db):
    """Usuário com perfil de vendedor."""
    return User.objects.create_user(
        email="seller@test.com",
        password="testpass123",
        full_name="Vendedor Teste",
    )


@pytest.fixture
def support_staff(db):
    """Usuário staff de suporte."""
    return User.objects.create_user(
        email="support@test.com",
        password="testpass123",
        full_name="Suporte Teste",
        is_staff=True,
    )


@pytest.fixture
def outsider(db):
    """Usuário que não participa de nenhuma conversa nos testes."""
    return User.objects.create_user(
        email="outsider@test.com",
        password="testpass123",
        full_name="Forasteiro Teste",
    )


@pytest.fixture
def listing(db, seller):
    """
    MarketplaceListing mínimo criado via SQL direto para evitar acoplamento
    com a lógica de negócio do app products (brand logo NOT NULL, etc.).
    Usado exclusivamente para testar a deduplicação de conversas buyer_seller.
    """
    from products.models import Brand, Condition, Products, MarketplaceListing

    # Usa get_or_create para evitar violação de unique em runs repetidos
    from products.models import Category, Series
    brand, _ = Brand.objects.get_or_create(
        slug='chat-test-brand',
        defaults={'name': 'Chat Test Brand'},
    )
    condition, _ = Condition.objects.get_or_create(
        slug='chat-test-cond',
        defaults={'name': 'Chat Test Cond'},
    )
    category, _ = Category.objects.get_or_create(
        slug='chat-test-cat',
        defaults={'name': 'Chat Test Category'},
    )
    series, _ = Series.objects.get_or_create(
        slug='chat-test-series',
        defaults={'name': 'Chat Test Series'},
    )
    product, _ = Products.objects.get_or_create(
        slug='chat-test-product',
        defaults={
            'name': 'Chat Test Product',
            'category': category,
            'series': series,
        },
    )
    listing = MarketplaceListing.objects.create(
        product=product,
        seller=seller,
        brand=brand,
        condition=condition,
        title='Produto para Teste de Chat',
        price=50,
        quantity=1,
        shipping_method='correios',
        weight_kg=0.5,
        height_cm=10,
        width_cm=10,
        length_cm=10,
    )
    return listing


@pytest.fixture
def buyer_seller_conversation(db, buyer, seller):
    """Conversa ativa entre comprador e vendedor."""
    from chats.services import ConversationService
    with override_settings(CACHES=CACHES_TEST):
        return ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_seller',
            recipient_id=seller.pk,
        )


@pytest.fixture
def buyer_support_conversation(db, buyer, support_staff):
    """Conversa ativa entre comprador e suporte."""
    from chats.services import ConversationService
    with override_settings(CACHES=CACHES_TEST):
        return ConversationService.create_conversation(
            initiator=buyer,
            conversation_type='buyer_support',
            recipient_id=support_staff.pk,
        )


@pytest.fixture
def seller_support_conversation(db, seller, support_staff):
    """Conversa ativa entre vendedor e suporte."""
    from chats.services import ConversationService
    with override_settings(CACHES=CACHES_TEST):
        return ConversationService.create_conversation(
            initiator=seller,
            conversation_type='seller_support',
            recipient_id=support_staff.pk,
        )
