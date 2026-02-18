"""
Serviço OAuth 2.0 para integração com Melhor Envio.

PROBLEMA RESOLVIDO:
O webhook do Melhor Envio só é disparado para etiquetas criadas com um token
OAuth 2.0 do aplicativo onde o webhook foi configurado. Etiquetas criadas com
tokens pessoais ou tokens de outras integrações NÃO acionam o webhook.

FLUXO OAuth 2.0:
1. Usuário acessa a URL de autorização do Melhor Envio
2. Melhor Envio redireciona para o callback com um `code`
3. Este serviço troca o `code` por access_token + refresh_token
4. Os tokens são armazenados no banco de dados (MelhorEnvioOAuthToken)
5. Antes de cada chamada à API, o access_token é verificado e renovado se necessário

CICLO DE VIDA DOS TOKENS:
- access_token: validade de 30 dias
- refresh_token: validade de 45 dias
- A renovação deve ocorrer automaticamente antes da expiração
"""

import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class MelhorEnvioOAuthError(Exception):
    """Erro no fluxo OAuth 2.0 do Melhor Envio."""
    pass


class MelhorEnvioOAuthService:
    """
    Gerencia o ciclo de vida dos tokens OAuth 2.0 do Melhor Envio.

    Responsabilidades:
    - Trocar código de autorização por tokens
    - Renovar access_token usando refresh_token automaticamente
    - Fornecer headers de autenticação válidos para todas as chamadas à API
    - Persistir tokens no banco de dados
    """

    def __init__(self):
        self.is_sandbox = getattr(settings, 'MELHOR_ENVIO_SANDBOX', True)
        self.client_id = getattr(settings, 'MELHOR_ENVIO_CLIENT_ID', '')
        self.client_secret = getattr(settings, 'MELHOR_ENVIO_CLIENT_SECRET', '')
        self.redirect_uri = getattr(settings, 'MELHOR_ENVIO_REDIRECT_URI', '')

        if self.is_sandbox:
            self.base_url = 'https://sandbox.melhorenvio.com.br'
        else:
            self.base_url = 'https://melhorenvio.com.br'

        self.token_url = f'{self.base_url}/oauth/token'
        self.environment = 'sandbox' if self.is_sandbox else 'production'

    @property
    def user_agent(self):
        """User-Agent obrigatório conforme documentação do Melhor Envio."""
        contact_email = getattr(settings, 'MELHOR_ENVIO_USER_AGENT_EMAIL', 'contato@seuapp.com')
        return f'Marketplace App ({contact_email})'

    def get_authorization_url(self) -> str:
        """
        Gera a URL de autorização OAuth 2.0 para redirecionar o usuário.

        Returns:
            str: URL completa para redirecionar o usuário ao Melhor Envio

        Usage:
            url = oauth_service.get_authorization_url()
            # Redirecionar o usuário para esta URL
        """
        if not self.client_id:
            raise MelhorEnvioOAuthError(
                'MELHOR_ENVIO_CLIENT_ID não configurado no settings. '
                'Configure as credenciais do aplicativo Melhor Envio.'
            )
        if not self.redirect_uri:
            raise MelhorEnvioOAuthError(
                'MELHOR_ENVIO_REDIRECT_URI não configurado no settings.'
            )

        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': 'cart-read cart-write companies-read coupons-read notifications-read orders-read purchases-read shipping-calculate shipping-cancel shipping-checkout shipping-companies shipping-generate shipping-preview shipping-print shipping-share shipping-tracking ecommerce-shipping transactions-read users-read',
        }

        query_string = '&'.join(f'{k}={v}' for k, v in params.items())
        return f'{self.base_url}/oauth/authorize?{query_string}'

    def exchange_code_for_token(self, code: str) -> 'MelhorEnvioOAuthToken':
        """
        Troca o código de autorização pelos tokens de acesso.

        Args:
            code: Código de autorização recebido no callback OAuth

        Returns:
            MelhorEnvioOAuthToken: Token salvo no banco de dados

        Raises:
            MelhorEnvioOAuthError: Se a troca falhar
        """
        from ..models import MelhorEnvioOAuthToken

        if not self.client_id or not self.client_secret:
            raise MelhorEnvioOAuthError(
                'MELHOR_ENVIO_CLIENT_ID e MELHOR_ENVIO_CLIENT_SECRET são obrigatórios. '
                'Configure as credenciais do aplicativo Melhor Envio no settings.'
            )

        payload = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'code': code,
        }

        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

        logger.info(
            f'Trocando código de autorização por tokens OAuth '
            f'(ambiente: {self.environment})'
        )

        try:
            response = requests.post(
                self.token_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            token_data = response.json()
        except requests.exceptions.HTTPError as e:
            error_detail = 'Resposta não disponível'
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except Exception:
                    error_detail = e.response.text
            logger.error(
                f'Erro HTTP ao trocar código OAuth: {e.response.status_code if e.response else "N/A"} '
                f'- {error_detail}'
            )
            raise MelhorEnvioOAuthError(
                f'Falha ao trocar código de autorização: {error_detail}'
            )
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao trocar código OAuth: {str(e)}')
            raise MelhorEnvioOAuthError(f'Erro de conexão: {str(e)}')

        return self._save_token_data(token_data, source='authorization_code')

    def refresh_access_token(self, token_record=None) -> 'MelhorEnvioOAuthToken':
        """
        Renova o access_token usando o refresh_token.

        Args:
            token_record: MelhorEnvioOAuthToken a ser renovado.
                          Se None, busca o token ativo do ambiente atual.

        Returns:
            MelhorEnvioOAuthToken: Token atualizado

        Raises:
            MelhorEnvioOAuthError: Se renovação falhar ou refresh_token expirado
        """
        from ..models import MelhorEnvioOAuthToken

        if token_record is None:
            token_record = self._get_active_token_record()

        if token_record is None:
            raise MelhorEnvioOAuthError(
                f'Nenhum token OAuth ativo encontrado para o ambiente {self.environment}. '
                'É necessário autorizar o aplicativo primeiro via fluxo OAuth.'
            )

        if token_record.is_refresh_token_expired():
            raise MelhorEnvioOAuthError(
                'refresh_token expirado (validade de 45 dias). '
                'É necessário reautorizar o aplicativo via fluxo OAuth.'
            )

        payload = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': token_record.refresh_token,
        }

        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

        logger.info(
            f'Renovando access_token OAuth do Melhor Envio '
            f'(ambiente: {self.environment}, token id: {token_record.id})'
        )

        try:
            response = requests.post(
                self.token_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            token_data = response.json()
        except requests.exceptions.HTTPError as e:
            error_detail = 'Resposta não disponível'
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                except Exception:
                    error_detail = e.response.text
            logger.error(
                f'Erro HTTP ao renovar token OAuth: '
                f'{e.response.status_code if e.response else "N/A"} - {error_detail}'
            )
            raise MelhorEnvioOAuthError(f'Falha ao renovar token: {error_detail}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao renovar token OAuth: {str(e)}')
            raise MelhorEnvioOAuthError(f'Erro de conexão: {str(e)}')

        # Atualizar o registro existente com os novos tokens
        return self._update_token_record(token_record, token_data)

    def get_valid_token(self) -> str:
        """
        Retorna um access_token válido, renovando-o automaticamente se necessário.

        Esta é a função principal usada por MelhorEnvioService antes de cada
        chamada à API. Garante que o token usado é sempre válido.

        Returns:
            str: access_token válido

        Raises:
            MelhorEnvioOAuthError: Se não houver token ativo ou renovação falhar
        """
        token_record = self._get_active_token_record()

        if token_record is None:
            raise MelhorEnvioOAuthError(
                f'Nenhum token OAuth 2.0 ativo encontrado para o ambiente "{self.environment}". '
                'Para resolver:\n'
                '1. Acesse GET /api/logistics/webhooks/melhor-envio/authorize/ para obter a URL de autorização\n'
                '2. Autorize o aplicativo no Melhor Envio\n'
                '3. O callback em /api/logistics/webhooks/melhor-envio/callback/ '
                'salvará os tokens automaticamente'
            )

        if token_record.is_expired():
            logger.info(
                f'access_token expirado, renovando automaticamente '
                f'(token id: {token_record.id}, ambiente: {self.environment})'
            )
            token_record = self.refresh_access_token(token_record)
            logger.info(f'access_token renovado com sucesso (novo token id: {token_record.id})')

        return token_record.access_token

    def get_oauth_headers(self) -> dict:
        """
        Retorna headers HTTP prontos com Bearer token válido.

        Utilizado por MelhorEnvioService para todas as chamadas à API.
        Substitui o uso do MELHOR_ENVIO_TOKEN estático.

        Returns:
            dict: Headers com Authorization Bearer do token OAuth 2.0

        Raises:
            MelhorEnvioOAuthError: Se não houver token ativo
        """
        access_token = self.get_valid_token()
        contact_email = getattr(settings, 'MELHOR_ENVIO_USER_AGENT_EMAIL', 'contato@seuapp.com')

        return {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': f'Marketplace App ({contact_email})',
        }

    def _get_active_token_record(self):
        """
        Busca o token OAuth ativo para o ambiente atual.

        Returns:
            MelhorEnvioOAuthToken | None
        """
        from ..models import MelhorEnvioOAuthToken

        return MelhorEnvioOAuthToken.objects.filter(
            environment=self.environment,
            is_active=True
        ).order_by('-created_at').first()

    def _save_token_data(self, token_data: dict, source: str) -> 'MelhorEnvioOAuthToken':
        """
        Salva novos tokens no banco de dados, desativando tokens anteriores.

        Args:
            token_data: Resposta da API de tokens do Melhor Envio
            source: Origem do token ('authorization_code' ou 'refresh_token')

        Returns:
            MelhorEnvioOAuthToken: Novo registro criado
        """
        from ..models import MelhorEnvioOAuthToken

        expires_in = token_data.get('expires_in', 2592000)  # 30 dias em segundos
        now = timezone.now()
        expires_at = now + timedelta(seconds=expires_in)

        # refresh_token dura 45 dias
        refresh_token_expires_at = now + timedelta(days=45)

        # Desativar tokens anteriores deste ambiente
        MelhorEnvioOAuthToken.objects.filter(
            environment=self.environment,
            is_active=True
        ).update(is_active=False)

        token_record = MelhorEnvioOAuthToken.objects.create(
            environment=self.environment,
            access_token=token_data['access_token'],
            refresh_token=token_data.get('refresh_token', ''),
            token_type=token_data.get('token_type', 'Bearer'),
            expires_at=expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
            scope=token_data.get('scope', ''),
            is_active=True,
        )

        logger.info(
            f'Token OAuth salvo com sucesso (source: {source}, ambiente: {self.environment}, '
            f'id: {token_record.id}, expires_at: {expires_at})'
        )

        return token_record

    def _update_token_record(self, token_record, token_data: dict) -> 'MelhorEnvioOAuthToken':
        """
        Atualiza um registro de token existente com novos dados.

        Args:
            token_record: Registro existente de MelhorEnvioOAuthToken
            token_data: Novos dados de token da API

        Returns:
            MelhorEnvioOAuthToken: Registro atualizado
        """
        expires_in = token_data.get('expires_in', 2592000)
        now = timezone.now()
        expires_at = now + timedelta(seconds=expires_in)

        token_record.access_token = token_data['access_token']
        token_record.expires_at = expires_at
        token_record.last_refreshed_at = now
        token_record.token_type = token_data.get('token_type', 'Bearer')

        # refresh_token pode ou não ser retornado na renovação
        new_refresh_token = token_data.get('refresh_token')
        if new_refresh_token:
            token_record.refresh_token = new_refresh_token
            token_record.refresh_token_expires_at = now + timedelta(days=45)

        if token_data.get('scope'):
            token_record.scope = token_data['scope']

        token_record.save()

        logger.info(
            f'Token OAuth atualizado (id: {token_record.id}, '
            f'novo expires_at: {expires_at})'
        )

        return token_record

    def get_token_status(self) -> dict:
        """
        Retorna o status atual do token OAuth para diagnóstico.

        Returns:
            dict: Status do token com informações de expiração
        """
        token_record = self._get_active_token_record()

        if token_record is None:
            return {
                'has_token': False,
                'environment': self.environment,
                'message': 'Nenhum token OAuth ativo. Autorize o aplicativo via fluxo OAuth.',
            }

        now = timezone.now()
        return {
            'has_token': True,
            'environment': self.environment,
            'token_id': token_record.id,
            'is_expired': token_record.is_expired(),
            'expires_at': token_record.expires_at.isoformat(),
            'expires_in_seconds': max(0, int((token_record.expires_at - now).total_seconds())),
            'is_refresh_token_expired': token_record.is_refresh_token_expired(),
            'refresh_token_expires_at': (
                token_record.refresh_token_expires_at.isoformat()
                if token_record.refresh_token_expires_at else None
            ),
            'last_refreshed_at': (
                token_record.last_refreshed_at.isoformat()
                if token_record.last_refreshed_at else None
            ),
            'scope': token_record.scope,
            'created_at': token_record.created_at.isoformat(),
        }
