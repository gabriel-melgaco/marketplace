import React, { createContext, useContext, ReactNode, useMemo } from 'react';
import { useNotifications } from '@/hooks/useNotifications';
import { Notification } from '@/types/notifications';
import { tokenStorage } from '@/utils/tokenStorage';
import { API_BASE_URL } from '@/utils/constants';

interface NotificationContextValue {
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

const NotificationContext = createContext<NotificationContextValue | null>(null);

function getAccessToken(): string | null {
  return tokenStorage.getAccessToken();
}

async function handleTokenExpired(): Promise<string | null> {
  try {
    const refreshToken = tokenStorage.getRefreshToken();
    if (!refreshToken) return null;
    const response = await fetch(`${API_BASE_URL}/auth/token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: refreshToken }),
    });
    if (!response.ok) return null;
    const data = await response.json() as { access: string; refresh?: string };
    tokenStorage.saveTokens({
      access: data.access,
      refresh: refreshToken,
      access_expiration: '',
      refresh_expiration: '',
    });
    return data.access;
  } catch {
    return null;
  }
}

// Derive WS URL from VITE_API_URL: https://api.host.com/api → wss://api.host.com
const WS_BASE_URL = (() => {
  const apiUrl = import.meta.env.VITE_API_URL as string | undefined;
  if (!apiUrl) return undefined;
  return apiUrl
    .replace(/\/api$/, '')
    .replace(/^https:\/\//, 'wss://')
    .replace(/^http:\/\//, 'ws://');
})();

export function NotificationProvider({ children }: { children: ReactNode }) {
  const notificationsState = useNotifications({
    getAccessToken,
    onTokenExpired: handleTokenExpired,
    wsBaseUrl: WS_BASE_URL,
  });

  const contextValue = useMemo<NotificationContextValue>(
    () => notificationsState,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      notificationsState.notifications,
      notificationsState.unreadCount,
      notificationsState.isConnected,
      notificationsState.isLoading,
      notificationsState.hasMore,
      notificationsState.error,
    ]
  );

  return (
    <NotificationContext.Provider value={contextValue}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotificationContext(): NotificationContextValue {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotificationContext deve ser usado dentro de NotificationProvider.');
  }
  return context;
}
