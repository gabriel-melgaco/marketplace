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

import hashlib
import hmac
import logging
import secrets
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Maximum age (seconds) accepted for a seller OAuth state token.
# The seller has this window to complete the ME authorization page.
_SELLER_STATE_MAX_AGE_SECONDS = 600  # 10 minutes


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

    # =====================================================================
    # Métodos por vendedor (per-seller OAuth2)
    # =====================================================================

    # ------------------------------------------------------------------
    # State token helpers (HMAC-signed, time-limited)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_state_signing_key() -> bytes:
        """
        Retorna a chave de assinatura para tokens de state OAuth.

        Usa MELHOR_ENVIO_STATE_SECRET se configurado, caso contrário usa
        SECRET_KEY do Django. É recomendável definir MELHOR_ENVIO_STATE_SECRET
        como uma chave dedicada de pelo menos 32 bytes aleatórios.
        """
        raw = getattr(
            settings,
            'MELHOR_ENVIO_STATE_SECRET',
            settings.SECRET_KEY,
        )
        return raw.encode('utf-8') if isinstance(raw, str) else raw

    @staticmethod
    def generate_seller_state(seller_id: int) -> str:
        """
        Gera um token de state OAuth HMAC-assinado para o vendedor.

        Formato (URL-safe, sem separadores suspeitos):
            <timestamp>.<nonce>.<hmac_hex>

        - timestamp: Unix time em segundos (para validação de TTL)
        - nonce: 16 bytes aleatórios em hex (evita replays paralelos)
        - hmac_hex: HMAC-SHA256 de "<seller_id>:<timestamp>:<nonce>"

        Args:
            seller_id: ID inteiro do vendedor

        Returns:
            str: Token de state seguro, passável como query param
        """
        ts = str(int(time.time()))
        nonce = secrets.token_hex(16)
        message = f'{seller_id}:{ts}:{nonce}'.encode('utf-8')
        sig = hmac.new(
            MelhorEnvioOAuthService._get_state_signing_key(),
            message,
            hashlib.sha256,
        ).hexdigest()
        return f'{seller_id}.{ts}.{nonce}.{sig}'

    @staticmethod
    def verify_seller_state(state: str) -> int:
        """
        Verifica e decodifica um token de state gerado por generate_seller_state.

        Valida a assinatura HMAC e o TTL. Levanta MelhorEnvioOAuthError se
        o state for inválido, adulterado ou expirado.

        Args:
            state: Token de state recebido no callback OAuth

        Returns:
            int: seller_id extraído do state validado

        Raises:
            MelhorEnvioOAuthError: Se assinatura inválida, TTL expirado ou
                                   formato incorreto
        """
        try:
            parts = state.split('.')
            if len(parts) != 4:
                raise ValueError('Formato inválido')
            seller_id_str, ts_str, nonce, received_sig = parts

            # Verificar TTL
            ts = int(ts_str)
            age = int(time.time()) - ts
            if age < 0 or age > _SELLER_STATE_MAX_AGE_SECONDS:
                raise MelhorEnvioOAuthError(
                    f'State OAuth expirado (age={age}s, max={_SELLER_STATE_MAX_AGE_SECONDS}s). '
                    'Solicite uma nova URL de autorização.'
                )

            # Verificar HMAC (constant-time comparison)
            message = f'{seller_id_str}:{ts_str}:{nonce}'.encode('utf-8')
            expected_sig = hmac.new(
                MelhorEnvioOAuthService._get_state_signing_key(),
                message,
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(expected_sig, received_sig):
                raise MelhorEnvioOAuthError(
                    'Assinatura do state OAuth inválida. '
                    'Possível tentativa de CSRF ou state adulterado.'
                )

            return int(seller_id_str)

        except MelhorEnvioOAuthError:
            raise
        except Exception as exc:
            raise MelhorEnvioOAuthError(
                f'State OAuth inválido ou mal-formado: {exc}'
            ) from exc

    def get_seller_authorization_url(self, seller, state: str = None) -> str:
        """
        Gera a URL de autorização OAuth 2.0 para um vendedor específico.

        O parâmetro state é um token HMAC-assinado que contém o seller.id,
        um timestamp e um nonce. O callback verifica a assinatura antes de
        processar o código, prevenindo ataques CSRF/state-forgery.

        Args:
            seller: Instância de CustomUser (vendedor)
            state: Token de state pré-gerado. Se None, gera automaticamente
                   via generate_seller_state(seller.id).

        Returns:
            str: URL completa de autorização do Melhor Envio
        """
        if not self.client_id:
            raise MelhorEnvioOAuthError(
                'MELHOR_ENVIO_CLIENT_ID não configurado no settings.'
            )

        seller_redirect_uri = getattr(
            settings,
            'MELHOR_ENVIO_SELLER_REDIRECT_URI',
            self.redirect_uri
        )

        if not seller_redirect_uri:
            raise MelhorEnvioOAuthError(
                'MELHOR_ENVIO_SELLER_REDIRECT_URI (ou MELHOR_ENVIO_REDIRECT_URI) '
                'não configurado no settings.'
            )

        oauth_state = state if state is not None else self.generate_seller_state(seller.id)

        params = {
            'client_id': self.client_id,
            'redirect_uri': seller_redirect_uri,
            'response_type': 'code',
            'scope': (
                'cart-read cart-write companies-read coupons-read '
                'notifications-read orders-read purchases-read '
                'shipping-calculate shipping-cancel shipping-checkout '
                'shipping-companies shipping-generate shipping-preview '
                'shipping-print shipping-share shipping-tracking '
                'ecommerce-shipping transactions-read users-read'
            ),
            'state': oauth_state,
        }

        query_string = '&'.join(f'{k}={v}' for k, v in params.items())
        return f'{self.base_url}/oauth/authorize?{query_string}'

    def exchange_seller_code_for_token(self, code: str, seller) -> 'SellerMelhorEnvioToken':
        """
        Troca o código de autorização pelos tokens de acesso do vendedor e persiste.

        Args:
            code: Código de autorização recebido no callback OAuth
            seller: Instância de CustomUser (vendedor)

        Returns:
            SellerMelhorEnvioToken: Token salvo no banco de dados

        Raises:
            MelhorEnvioOAuthError: Se a troca falhar
        """
        from ..models import SellerMelhorEnvioToken

        if not self.client_id or not self.client_secret:
            raise MelhorEnvioOAuthError(
                'MELHOR_ENVIO_CLIENT_ID e MELHOR_ENVIO_CLIENT_SECRET são obrigatórios.'
            )

        seller_redirect_uri = getattr(
            settings,
            'MELHOR_ENVIO_SELLER_REDIRECT_URI',
            self.redirect_uri
        )

        payload = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': seller_redirect_uri,
            'code': code,
        }

        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

        logger.info(
            f'Trocando código OAuth para vendedor {seller.email} '
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
                f'Erro HTTP ao trocar código OAuth para vendedor {seller.email}: '
                f'{e.response.status_code if e.response else "N/A"} - {error_detail}'
            )
            raise MelhorEnvioOAuthError(
                f'Falha ao trocar código de autorização do vendedor: {error_detail}'
            )
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao trocar código OAuth para vendedor {seller.email}: {str(e)}')
            raise MelhorEnvioOAuthError(f'Erro de conexão: {str(e)}')

        expires_in = token_data.get('expires_in', 2592000)
        now = timezone.now()
        expires_at = now + timedelta(seconds=expires_in)
        refresh_token_expires_at = now + timedelta(days=45)

        token_record, created = SellerMelhorEnvioToken.objects.update_or_create(
            seller=seller,
            environment=self.environment,
            defaults={
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token', ''),
                'token_type': token_data.get('token_type', 'Bearer'),
                'expires_at': expires_at,
                'refresh_token_expires_at': refresh_token_expires_at,
                'scope': token_data.get('scope', ''),
                'is_active': True,
                'last_refreshed_at': now,
            }
        )

        action = 'criado' if created else 'atualizado'
        logger.info(
            f'Token OAuth vendedor {seller.email} {action}: '
            f'id={token_record.id}, expires_at={expires_at}'
        )

        # Buscar e cachear informações da conta ME do vendedor
        try:
            self._cache_seller_me_info(token_record)
        except Exception as e:
            logger.warning(
                f'Não foi possível cachear dados da conta ME para vendedor {seller.email}: {e}'
            )

        return token_record

    def refresh_seller_token(self, seller) -> 'SellerMelhorEnvioToken':
        """
        Renova o access_token do vendedor usando o refresh_token.

        Args:
            seller: Instância de CustomUser (vendedor)

        Returns:
            SellerMelhorEnvioToken: Token atualizado

        Raises:
            MelhorEnvioOAuthError: Se renovação falhar, refresh_token expirado,
                                   ou vendedor não tiver token ativo
        """
        from ..models import SellerMelhorEnvioToken

        try:
            token_record = SellerMelhorEnvioToken.objects.get(
                seller=seller,
                environment=self.environment,
                is_active=True
            )
        except SellerMelhorEnvioToken.DoesNotExist:
            raise MelhorEnvioOAuthError(
                f'Vendedor {seller.email} não possui token OAuth ativo para '
                f'o ambiente {self.environment}. '
                'É necessário conectar a conta Melhor Envio primeiro.'
            )

        if token_record.is_refresh_token_expired():
            raise MelhorEnvioOAuthError(
                f'refresh_token do vendedor {seller.email} expirado (validade de 45 dias). '
                'É necessário reconectar a conta Melhor Envio via fluxo OAuth.'
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
            f'Renovando access_token OAuth do vendedor {seller.email} '
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
                f'Erro HTTP ao renovar token OAuth do vendedor {seller.email}: '
                f'{e.response.status_code if e.response else "N/A"} - {error_detail}'
            )
            raise MelhorEnvioOAuthError(
                f'Falha ao renovar token do vendedor {seller.email}: {error_detail}'
            )
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro de conexão ao renovar token do vendedor {seller.email}: {str(e)}')
            raise MelhorEnvioOAuthError(f'Erro de conexão: {str(e)}')

        expires_in = token_data.get('expires_in', 2592000)
        now = timezone.now()
        expires_at = now + timedelta(seconds=expires_in)

        token_record.access_token = token_data['access_token']
        token_record.expires_at = expires_at
        token_record.last_refreshed_at = now
        token_record.token_type = token_data.get('token_type', 'Bearer')

        new_refresh_token = token_data.get('refresh_token')
        if new_refresh_token:
            token_record.refresh_token = new_refresh_token
            token_record.refresh_token_expires_at = now + timedelta(days=45)

        if token_data.get('scope'):
            token_record.scope = token_data['scope']

        token_record.save()

        logger.info(
            f'Token OAuth vendedor {seller.email} renovado: '
            f'id={token_record.id}, novo expires_at={expires_at}'
        )

        return token_record

    def get_valid_seller_token(self, seller) -> str:
        """
        Retorna um access_token válido para o vendedor, renovando se necessário.

        Verifica a expiração do token. Se expirado, chama refresh_seller_token
        antes de retornar o access_token.

        Args:
            seller: Instância de CustomUser (vendedor)

        Returns:
            str: access_token válido

        Raises:
            MelhorEnvioOAuthError: Se não houver token ativo ou renovação falhar
        """
        from ..models import SellerMelhorEnvioToken
        from .melhor_envio_service import ShippingValidationError

        try:
            token_record = SellerMelhorEnvioToken.objects.get(
                seller=seller,
                environment=self.environment,
                is_active=True
            )
        except SellerMelhorEnvioToken.DoesNotExist:
            raise ShippingValidationError(
                f'Vendedor {seller.email} não possui conta do Melhor Envio conectada. '
                'Solicite que o vendedor conecte sua conta em /api/logistics/me/connect/'
            )

        if token_record.is_expired():
            logger.info(
                f'access_token do vendedor {seller.email} expirado, renovando automaticamente'
            )
            token_record = self.refresh_seller_token(seller)
            logger.info(f'access_token do vendedor {seller.email} renovado com sucesso')

        return token_record.access_token

    def get_seller_oauth_headers(self, seller) -> dict:
        """
        Retorna headers HTTP com Bearer token válido do vendedor.

        Args:
            seller: Instância de CustomUser (vendedor)

        Returns:
            dict: Headers com Authorization Bearer do token OAuth do vendedor

        Raises:
            MelhorEnvioOAuthError: Se não houver token ativo para o vendedor
        """
        access_token = self.get_valid_seller_token(seller)
        contact_email = getattr(settings, 'MELHOR_ENVIO_USER_AGENT_EMAIL', 'contato@seuapp.com')

        return {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': f'Marketplace App ({contact_email})',
        }

    def get_seller_token_status(self, seller) -> dict:
        """
        Retorna informações diagnósticas sobre o token do vendedor.

        Args:
            seller: Instância de CustomUser (vendedor)

        Returns:
            dict: Status do token com informações de conexão e expiração
        """
        from ..models import SellerMelhorEnvioToken

        try:
            token_record = SellerMelhorEnvioToken.objects.get(
                seller=seller,
                environment=self.environment,
                is_active=True
            )
        except SellerMelhorEnvioToken.DoesNotExist:
            return {
                'connected': False,
                'environment': self.environment,
                'message': (
                    'Conta Melhor Envio não conectada. '
                    'Acesse /api/logistics/me/connect/ para conectar.'
                ),
            }

        now = timezone.now()
        return {
            'connected': True,
            'environment': self.environment,
            'me_email': token_record.me_email,
            'me_user_id': token_record.me_user_id,
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

    def deactivate_seller_token(self, seller) -> bool:
        """
        Desativa o token do vendedor (desconecta a conta ME).

        Args:
            seller: Instância de CustomUser (vendedor)

        Returns:
            bool: True se token foi desativado, False se não havia token ativo
        """
        from ..models import SellerMelhorEnvioToken

        updated = SellerMelhorEnvioToken.objects.filter(
            seller=seller,
            environment=self.environment,
            is_active=True
        ).update(is_active=False)

        if updated:
            logger.info(
                f'Token OAuth do vendedor {seller.email} desativado '
                f'(ambiente: {self.environment})'
            )

        return updated > 0

    def _cache_seller_me_info(self, token_record) -> None:
        """
        Busca e armazena informações da conta ME do vendedor no token record.

        Chama GET /api/v2/me com o token do vendedor e persiste firstname,
        email, document e user_id para uso no bloco 'from' do carrinho.

        Args:
            token_record: Instância de SellerMelhorEnvioToken
        """
        if self.is_sandbox:
            api_base = 'https://sandbox.melhorenvio.com.br/api/v2'
        else:
            api_base = 'https://melhorenvio.com.br/api/v2'

        contact_email = getattr(settings, 'MELHOR_ENVIO_USER_AGENT_EMAIL', 'contato@seuapp.com')
        headers = {
            'Authorization': f'Bearer {token_record.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': f'Marketplace App ({contact_email})',
        }

        response = requests.get(f'{api_base}/me', headers=headers, timeout=15)
        response.raise_for_status()
        account_data = response.json()

        # Extrair document: pode conter formatação, remover
        raw_doc = account_data.get('document') or account_data.get('cpf') or ''
        clean_doc = ''.join(c for c in str(raw_doc) if c.isdigit())

        token_record.me_user_id = str(account_data.get('id') or '')
        token_record.me_email = account_data.get('email') or ''
        token_record.me_document = clean_doc
        token_record.me_firstname = account_data.get('firstname') or ''

        # Tentar criar/atualizar o Address de envio a partir da conta ME
        try:
            address_record = self._sync_seller_me_address(token_record.seller, account_data)
            token_record.me_address = address_record
        except Exception as exc:
            logger.warning(
                f'Não foi possível sincronizar endereço ME para vendedor '
                f'{token_record.seller.email}: {exc}'
            )

        token_record.save(update_fields=[
            'me_user_id', 'me_email', 'me_document', 'me_firstname', 'me_address', 'updated_at',
        ])

        logger.info(
            f'Dados ME cacheados para vendedor {token_record.seller.email}: '
            f'email={token_record.me_email}, doc={clean_doc[:4]}***'
        )

    def _sync_seller_me_address(self, seller, account_data: dict):
        """
        Cria ou atualiza o endereço de envio do vendedor com os dados da conta ME.

        Args:
            seller: Instância de CustomUser
            account_data: Resposta completa de GET /api/v2/me

        Returns:
            Address: Instância criada ou atualizada
        """
        from ..models import Address

        addr = account_data.get('address') or {}

        # Extrair zipcode — ME retorna "12086-000", normalizar para "12086000"
        raw_zip = addr.get('postal_code') or ''
        zipcode = ''.join(c for c in str(raw_zip) if c.isdigit())

        # Extrair cidade — pode ser dict {"city": "Taubaté", "state": {...}} ou string
        # Melhor Envio retorna city como dict aninhado quando usa /api/v2/me
        city_raw = addr.get('city') or ''
        if isinstance(city_raw, dict):
            city = city_raw.get('city') or ''
            state_raw = city_raw.get('state') or {}
            state = (state_raw.get('state_abbr') or '') if isinstance(state_raw, dict) else ''
        else:
            city = str(city_raw)
            state = ''

        # Fallback para campo flat 'uf' quando state não foi extraído do dict aninhado
        # me_cart_minimal_test usa me_address.get('uf') como fallback — replicar aqui
        if not state:
            state = addr.get('uf') or addr.get('state_abbr') or ''

        # Normalizar state_abbr para maiúsculas (ME pode retornar 'Pr', 'sp', etc.)
        # A API do ME exige siglas em maiúsculas: 'SP', 'PR', 'MG', etc.
        state = state.upper().strip()

        # Extrair telefone — pode ser dict {"phone": "12996...", "country_code": "55"} ou string
        phone_raw = account_data.get('phone') or ''
        if isinstance(phone_raw, dict):
            phone = phone_raw.get('phone') or ''
        else:
            phone = str(phone_raw)
        phone = ''.join(c for c in phone if c.isdigit())[:20]

        firstname = account_data.get('firstname') or ''
        lastname = account_data.get('lastname') or ''
        recipient_name = f'{firstname} {lastname}'.strip() or seller.get_full_name() or seller.email

        street = addr.get('address') or ''
        number = addr.get('number') or 's/n'
        complement = addr.get('complement') or None
        neighborhood = addr.get('district') or ''

        if not zipcode or not city:
            raise ValueError('Conta ME não possui endereço completo (zipcode ou city ausente)')

        address, _ = Address.objects.update_or_create(
            user=seller,
            address_type='shipping',
            defaults={
                'nickname': 'Endereço Melhor Envio',
                'is_shipping_address': True,
                'is_active': True,
                'recipient_name': recipient_name,
                'recipient_phone': phone,
                'zipcode': zipcode,
                'street': street,
                'number': number,
                'complement': complement,
                'neighborhood': neighborhood,
                'city': city,
                'state': state,
                'country': 'BR',
            }
        )

        logger.info(
            f'Endereço ME sincronizado para vendedor {seller.email}: '
            f'{zipcode} - {city}/{state}'
        )
        return address

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
