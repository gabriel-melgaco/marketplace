"""
ASGI config for api project.

Supports both HTTP (Django) and WebSocket (Django Channels) via
ProtocolTypeRouter. WebSocket connections are authenticated at the
ASGI layer by JWTAuthMiddleware before reaching the consumer.
"""

import os

import django
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')

# Django must be set up before importing Channels/routing modules that
# import models.
django.setup()

from django.conf import settings  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from chats.middleware import JWTAuthMiddleware  # noqa: E402
from chats.routing import websocket_urlpatterns  # noqa: E402

django_asgi_app = get_asgi_application()

_ws_stack = JWTAuthMiddleware(URLRouter(websocket_urlpatterns))

# In production, enforce Origin validation. In development (DEBUG=True),
# skip it so tools like wscat (which send no Origin header) work out of the box.
if not settings.DEBUG:
    _ws_stack = AllowedHostsOriginValidator(_ws_stack)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": _ws_stack,
})
