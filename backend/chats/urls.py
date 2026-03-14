from django.urls import path

from chats.views import (
    ConversationListCreateView,
    ConversationDetailView,
    ConversationCloseView,
    MessageListView,
    MarkAsReadView,
)

app_name = 'chats'

urlpatterns = [
    # Conversations
    path(
        'conversations/',
        ConversationListCreateView.as_view(),
        name='conversation-list-create',
    ),
    path(
        'conversations/<uuid:pk>/',
        ConversationDetailView.as_view(),
        name='conversation-detail',
    ),
    path(
        'conversations/<uuid:pk>/close/',
        ConversationCloseView.as_view(),
        name='conversation-close',
    ),
    # Messages
    path(
        'conversations/<uuid:pk>/messages/',
        MessageListView.as_view(),
        name='message-list',
    ),
    path(
        'conversations/<uuid:pk>/messages/read/',
        MarkAsReadView.as_view(),
        name='message-mark-read',
    ),
]
