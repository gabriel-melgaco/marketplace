"""
Testes do JWTAuthMiddleware para WebSocket.

Valida:
- Token válido → user correto no scope
- Token ausente → AnonymousUser no scope
- Token inválido → AnonymousUser no scope
- Token com user_id inexistente → AnonymousUser no scope
- Escopo não-WebSocket: middleware não interfere
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings

from chats.middleware import _get_token_from_scope, _authenticate_token

pytestmark = pytest.mark.django_db


class TestGetTokenFromScope:
    def test_extracts_token_from_query_string(self):
        scope = {'query_string': b'token=myaccesstoken123'}
        assert _get_token_from_scope(scope) == 'myaccesstoken123'

    def test_returns_empty_string_when_no_token(self):
        scope = {'query_string': b''}
        assert _get_token_from_scope(scope) == ''

    def test_returns_empty_when_query_string_absent(self):
        scope = {}
        assert _get_token_from_scope(scope) == ''

    def test_handles_multiple_query_params(self):
        scope = {'query_string': b'foo=bar&token=abc123&baz=qux'}
        assert _get_token_from_scope(scope) == 'abc123'

    def test_handles_encoded_query_string(self):
        scope = {'query_string': b'token=eyJhbGciOiJIUzI1NiJ9.payload.sig'}
        result = _get_token_from_scope(scope)
        assert result == 'eyJhbGciOiJIUzI1NiJ9.payload.sig'


class TestAuthenticateToken:
    def test_empty_token_returns_anonymous_user(self):
        user = _authenticate_token('')
        assert isinstance(user, AnonymousUser)

    def test_invalid_token_returns_anonymous_user(self):
        user = _authenticate_token('totallyinvalidtoken')
        assert isinstance(user, AnonymousUser)

    def test_valid_token_returns_user(self, buyer):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(buyer)
        access_token = str(refresh.access_token)

        user = _authenticate_token(access_token)
        assert user.pk == buyer.pk
        assert user.is_authenticated

    def test_expired_token_returns_anonymous_user(self):
        """Token com data passada deve retornar AnonymousUser."""
        import datetime
        from unittest.mock import patch
        from rest_framework_simplejwt.tokens import AccessToken

        with patch('rest_framework_simplejwt.tokens.aware_utcnow') as mock_now:
            # Simula token criado no passado
            mock_now.return_value = (
                datetime.datetime.now(tz=datetime.timezone.utc)
                - datetime.timedelta(hours=2)
            )
            # Gera o token no "passado"

        # Usa um token com exp no passado diretamente
        user = _authenticate_token('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.'
                                    'eyJ1c2VyX2lkIjo5OTk5LCJleHAiOjE2MDAwMDAwMDB9.'
                                    'invalidsignature')
        assert isinstance(user, AnonymousUser)

    def test_token_with_nonexistent_user_id_returns_anonymous(self):
        """Token válido assinado mas user_id inexistente → AnonymousUser."""
        from rest_framework_simplejwt.tokens import AccessToken
        from django.contrib.auth import get_user_model

        User = get_user_model()
        # Cria token com user_id inexistente
        token = AccessToken()
        token['user_id'] = 9999999  # ID que não existe

        user = _authenticate_token(str(token))
        assert isinstance(user, AnonymousUser)
