"""
Testes de integração com configurações do Django.

Valida:
- 'chats' em INSTALLED_APPS
- 'channels' em INSTALLED_APPS
- ASGI_APPLICATION aponta para api.asgi.application
- CHANNEL_LAYERS está configurado com Redis
- Migrations do app chats estão aplicadas sem pendências
"""

import pytest
from django.conf import settings


pytestmark = pytest.mark.django_db


class TestInstalledApps:
    def test_chats_in_installed_apps(self):
        assert 'chats' in settings.INSTALLED_APPS, (
            "'chats' não está em INSTALLED_APPS"
        )

    def test_channels_in_installed_apps(self):
        assert 'channels' in settings.INSTALLED_APPS, (
            "'channels' não está em INSTALLED_APPS"
        )


class TestAsgiApplication:
    def test_asgi_application_setting_exists(self):
        assert hasattr(settings, 'ASGI_APPLICATION'), (
            "ASGI_APPLICATION não está definido nas settings"
        )

    def test_asgi_application_points_to_correct_module(self):
        assert settings.ASGI_APPLICATION == 'api.asgi.application', (
            f"ASGI_APPLICATION incorreto: {settings.ASGI_APPLICATION}"
        )


class TestChannelLayers:
    def test_channel_layers_configured(self):
        assert hasattr(settings, 'CHANNEL_LAYERS'), (
            "CHANNEL_LAYERS não está configurado"
        )
        assert 'default' in settings.CHANNEL_LAYERS

    def test_channel_layers_uses_redis_backend(self):
        backend = settings.CHANNEL_LAYERS['default']['BACKEND']
        assert 'Redis' in backend, (
            f"CHANNEL_LAYERS não usa Redis. Backend atual: {backend}"
        )

    def test_channel_layers_config_has_hosts(self):
        config = settings.CHANNEL_LAYERS['default']['CONFIG']
        assert 'hosts' in config, (
            "CHANNEL_LAYERS.CONFIG não tem chave 'hosts'"
        )

    def test_channel_layers_config_has_no_invalid_db_param(self):
        """
        BUG DETECTADO: channels_redis 4.x não aceita 'db' como parâmetro direto.
        O banco Redis deve ser especificado na URL do host.
        Este teste documenta o bug e verifica se foi corrigido.
        """
        config = settings.CHANNEL_LAYERS['default']['CONFIG']
        assert 'db' not in config, (
            "CHANNEL_LAYERS.CONFIG contém 'db' como parâmetro direto, "
            "o que não é suportado pelo channels_redis 4.x. "
            "Use o formato de URL: 'redis://localhost:6379/2' em 'hosts'."
        )

    def test_channel_layer_can_be_instantiated(self):
        """
        Verifica que o channel layer pode ser instanciado sem TypeError.
        Isso falha com channels_redis 4.x quando 'db' está em CONFIG.
        """
        from channels.layers import get_channel_layer
        try:
            layer = get_channel_layer()
            assert layer is not None
        except TypeError as e:
            pytest.fail(
                f"Falha ao instanciar channel layer: {e}. "
                "Verifique a configuração CHANNEL_LAYERS."
            )


class TestMigrations:
    def test_chats_migrations_are_applied(self):
        from django.db import connection
        cursor = connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'chats_%'"
        )
        tables = [r[0] for r in cursor.fetchall()]
        expected = [
            'chats_conversation',
            'chats_conversationparticipant',
            'chats_message',
            'chats_messagestatus',
        ]
        for table in expected:
            assert table in tables, f"Tabela '{table}' não encontrada. Migrations não aplicadas?"

    def test_no_pending_migrations(self):
        """Verifica que não há migrations pendentes para o app chats."""
        from io import StringIO
        from django.core.management import call_command

        out = StringIO()
        call_command(
            'migrate',
            '--check',
            app_label='chats',
            stdout=out,
            stderr=out,
        )
        # Se chegou aqui sem SystemExit, não há migrations pendentes
