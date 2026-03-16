import { useCallback, useEffect, useRef, useState } from 'react';
import { notificationsApi } from '@/services/notificationsApi';
import type { Notification, WsIncomingMessage } from '@/types/notifications';

const RECONNECT_BASE_DELAY_MS = 1_000;
const RECONNECT_MAX_DELAY_MS = 30_000;
const RECONNECT_MAX_ATTEMPTS = 10;
const WS_CLOSE_UNAUTHENTICATED = 4001;
const WS_CLOSE_FORBIDDEN = 4003;
const WS_CLOSE_NOT_FOUND = 4004;

interface UseNotificationsOptions {
  getAccessToken: () => string | null;
  onTokenExpired?: () => Promise<string | null>;
  wsBaseUrl?: string;
}

interface UseNotificationsReturn {
  notifications: Notification[];
  unreadCount: number;
  isConnected: boolean;
  isLoading: boolean;
  hasMore: boolean;
  error: string | null;
  markAsRead: (notificationId: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
}

export function useNotifications(options: UseNotificationsOptions): UseNotificationsReturn {
  const { getAccessToken, onTokenExpired, wsBaseUrl } = options;

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentPageRef = useRef(1);
  const isMountedRef = useRef(true);
  const isReconnectingRef = useRef(false);
  // Ref that always holds the latest connect function — prevents stale closures
  // inside scheduleReconnect's setTimeout callback.
  const connectRef = useRef<() => void>(() => {});
  // Ref guard for loadMore — avoids stale closure issues with the isLoading state
  // captured inside the IntersectionObserver callback.
  const isLoadingRef = useRef(false);

  const getWsUrl = useCallback((): string | null => {
    const token = getAccessToken();
    if (!token) return null;
    const base =
      wsBaseUrl ??
      window.location.origin.replace(/^https/, 'wss').replace(/^http/, 'ws');
    // NOTE: The JWT is in the URL query string because the backend WebSocket
    // consumer authenticates via ?token=. This is a known limitation — the
    // token will appear in server access logs and browser network history.
    // Prefer first-frame auth if the backend is ever updated to support it.
    return `${base}/ws/notifications/?token=${token}`;
  }, [getAccessToken, wsBaseUrl]);

  const loadInitialNotifications = useCallback(async () => {
    if (!isMountedRef.current) return;
    isLoadingRef.current = true;
    setIsLoading(true);
    setError(null);
    try {
      const response = await notificationsApi.list({ page: 1 });
      if (!isMountedRef.current) return;
      setNotifications(response.results);
      setHasMore(response.next !== null);
      currentPageRef.current = 1;
    } catch (err) {
      if (!isMountedRef.current) return;
      setError('Não foi possível carregar as notificações.');
      console.error('[useNotifications] loadInitialNotifications error:', err);
    } finally {
      isLoadingRef.current = false;
      if (isMountedRef.current) setIsLoading(false);
    }
  }, []);

  const handleIncomingMessage = useCallback((message: WsIncomingMessage) => {
    if (message.type === 'unread_count') {
      setUnreadCount(message.count);
      return;
    }
    if (message.type === 'notification') {
      const incoming = message.data;
      setUnreadCount((prev) => prev + 1);
      setNotifications((prev) => {
        const alreadyExists = prev.some((n) => n.id === incoming.id);
        if (alreadyExists) return prev;
        return [incoming, ...prev];
      });
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (isReconnectingRef.current) return;
    if (reconnectAttemptRef.current >= RECONNECT_MAX_ATTEMPTS) {
      setError('Não foi possível reconectar ao servidor de notificações. Recarregue a página.');
      return;
    }
    isReconnectingRef.current = true;
    const attempt = reconnectAttemptRef.current;
    const delay = Math.min(
      RECONNECT_BASE_DELAY_MS * 2 ** attempt + Math.random() * 500,
      RECONNECT_MAX_DELAY_MS
    );
    console.info(`[useNotifications] Reconectando em ${Math.round(delay)}ms (tentativa ${attempt + 1}/${RECONNECT_MAX_ATTEMPTS})...`);
    reconnectTimerRef.current = setTimeout(() => {
      reconnectAttemptRef.current += 1;
      isReconnectingRef.current = false;
      connectRef.current(); // always calls the latest version via ref
    }, delay);
  }, []);

  const connect = useCallback(() => {
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    const url = getWsUrl();
    if (!url) {
      console.warn('[useNotifications] Sem token — conexão WebSocket adiada.');
      return;
    }

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMountedRef.current) return;
      console.info('[useNotifications] WebSocket conectado.');
      setIsConnected(true);
      setError(null);
      reconnectAttemptRef.current = 0;
      isReconnectingRef.current = false;
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!isMountedRef.current) return;
      try {
        const message: WsIncomingMessage = JSON.parse(event.data as string);
        handleIncomingMessage(message);
      } catch (e) {
        console.warn('[useNotifications] Mensagem WS inválida:', event.data, e);
      }
    };

    ws.onerror = (event) => {
      console.warn('[useNotifications] Erro no WebSocket:', event);
    };

    ws.onclose = async (event: CloseEvent) => {
      if (!isMountedRef.current) return;
      setIsConnected(false);
      wsRef.current = null;

      console.info(`[useNotifications] WebSocket fechado. Código: ${event.code}`);

      if (event.code === WS_CLOSE_FORBIDDEN || event.code === WS_CLOSE_NOT_FOUND) {
        return;
      }

      if (event.code === WS_CLOSE_UNAUTHENTICATED && onTokenExpired) {
        console.info('[useNotifications] Token expirado. Tentando renovar...');
        const newToken = await onTokenExpired();
        // Guard: component may have unmounted while we awaited the refresh
        if (!isMountedRef.current) return;
        if (newToken) {
          scheduleReconnect();
        } else {
          setError('Sessão expirada. Faça login novamente.');
        }
        return;
      }

      if (event.code === 1000) return;

      scheduleReconnect();
    };
  }, [getWsUrl, onTokenExpired, handleIncomingMessage, scheduleReconnect]);

  // Keep the ref in sync with the latest connect function on every render
  connectRef.current = connect;

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'Componente desmontado');
      wsRef.current = null;
    }
  }, []);

  const markAsRead = useCallback(async (notificationId: string) => {
    setNotifications((prev) =>
      prev.map((n) =>
        n.id === notificationId ? { ...n, is_read: true, read_at: new Date().toISOString() } : n
      )
    );
    setUnreadCount((prev) => Math.max(0, prev - 1));
    try {
      await notificationsApi.markAsRead(notificationId);
    } catch (err) {
      setNotifications((prev) =>
        prev.map((n) =>
          n.id === notificationId ? { ...n, is_read: false, read_at: null } : n
        )
      );
      setUnreadCount((prev) => prev + 1);
      console.error('[useNotifications] markAsRead error:', err);
      throw err;
    }
  }, []);

  const markAllAsRead = useCallback(async () => {
    const now = new Date().toISOString();
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true, read_at: now })));
    setUnreadCount(0);
    try {
      await notificationsApi.markAllAsRead();
    } catch (err) {
      await loadInitialNotifications();
      console.error('[useNotifications] markAllAsRead error:', err);
      throw err;
    }
  }, [loadInitialNotifications]);

  const loadMore = useCallback(async () => {
    if (isLoadingRef.current || !hasMore) return;
    isLoadingRef.current = true;
    setIsLoading(true);
    try {
      const nextPage = currentPageRef.current + 1;
      const response = await notificationsApi.list({ page: nextPage });
      if (!isMountedRef.current) return;
      setNotifications((prev) => {
        const existingIds = new Set(prev.map((n) => n.id));
        const newItems = response.results.filter((n) => !existingIds.has(n.id));
        return [...prev, ...newItems];
      });
      setHasMore(response.next !== null);
      currentPageRef.current = nextPage;
    } catch (err) {
      console.error('[useNotifications] loadMore error:', err);
    } finally {
      isLoadingRef.current = false;
      if (isMountedRef.current) setIsLoading(false);
    }
  }, [hasMore]);

  const refresh = useCallback(async () => {
    currentPageRef.current = 1;
    setHasMore(true);
    await loadInitialNotifications();
  }, [loadInitialNotifications]);

  useEffect(() => {
    isMountedRef.current = true;
    // Only load and connect when an access token is available — avoids
    // firing unauthenticated REST requests for logged-out users.
    if (getAccessToken()) {
      loadInitialNotifications();
      connect();
    }
    return () => {
      isMountedRef.current = false;
      disconnect();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    notifications,
    unreadCount,
    isConnected,
    isLoading,
    hasMore,
    error,
    markAsRead,
    markAllAsRead,
    loadMore,
    refresh,
  };
}
