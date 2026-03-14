from django.urls import re_path

from chats.consumers import ChatConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/chats/(?P<conversation_id>[0-9a-f-]+)/$",
        ChatConsumer.as_asgi(),
    ),
]
