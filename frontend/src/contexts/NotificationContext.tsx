import React, { createContext, useContext, ReactNode } from 'react';
import { useNotifications } from '@/hooks/useNotifications';
import { Notification } from '@/types/notifications';
import { tokenStorage } from '@/utils/tokenStorage';
import { refreshAccessToken } from '@/api/axios';

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
  // refreshAccessToken is shared with the axios interceptor — prevents the
  // race condition where both a WS 4001 close and an HTTP 401 try to refresh
  // the token simultaneously.
  const notificationsState = useNotifications({
    getAccessToken,
    onTokenExpired: refreshAccessToken,
    wsBaseUrl: WS_BASE_URL,
  });

  return (
    <NotificationContext.Provider value={notificationsState}>
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
