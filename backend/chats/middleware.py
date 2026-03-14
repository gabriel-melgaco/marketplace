"""
JWT Auth Middleware for Django Channels WebSocket connections.

Extracts the JWT access token from the `?token=<jwt>` query parameter,
validates it with SimpleJWT, and injects the authenticated user (or
AnonymousUser on failure) into the ASGI scope before the consumer runs.
"""

import logging
from urllib.parse import parse_qs

from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)
User = get_user_model()


def _get_token_from_scope(scope: dict) -> str:
    """Extract the raw JWT string from the WebSocket query string."""
    query_string = scope.get('query_string', b'').decode('utf-8')
    params = parse_qs(query_string)
    tokens = params.get('token', [])
    return tokens[0] if tokens else ''


def _authenticate_token(token: str):
    """
    Validate `token` with SimpleJWT and return the corresponding User.

    Returns AnonymousUser if the token is absent, invalid, or the user
    does not exist.
    """
    if not token:
        return AnonymousUser()

    try:
        # Import here to avoid top-level circular import issues
        from rest_framework_simplejwt.tokens import UntypedToken
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

        validated = UntypedToken(token)
        user_id = validated.payload.get('user_id')
        if not user_id:
            logger.warning("JWT payload missing 'user_id' claim.")
            return AnonymousUser()

        return User.objects.get(pk=user_id)

    except Exception as exc:
        logger.warning("WebSocket JWT authentication failed: %s", exc)
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    ASGI middleware that authenticates WebSocket connections via JWT.

    Token is read from the `token` query parameter:
        ws://host/ws/chats/<id>/?token=<access_token>

    The resolved user is placed in `scope['user']` before the inner
    application (URLRouter → consumer) handles the connection.
    """

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            token = _get_token_from_scope(scope)
            # Run the blocking DB lookup in a thread pool
            from channels.db import database_sync_to_async
            scope['user'] = await database_sync_to_async(_authenticate_token)(token)

        return await super().__call__(scope, receive, send)
