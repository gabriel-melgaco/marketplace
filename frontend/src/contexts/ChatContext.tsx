import React, { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react';
import { chatService } from '@/services/chatService';
import { useAuth } from '@/contexts/AuthContext';

interface ChatContextValue {
  totalUnread: number;
  refreshUnread: () => Promise<void>;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [totalUnread, setTotalUnread] = useState(0);

  const refreshUnread = useCallback(async () => {
    if (!isAuthenticated) {
      setTotalUnread(0);
      return;
    }
    try {
      const conversations = await chatService.listConversations('active');
      const total = conversations.reduce((sum, c) => sum + c.unread_count, 0);
      setTotalUnread(total);
    } catch {
      // Silent fail — badge is non-critical
    }
  }, [isAuthenticated]);

  useEffect(() => {
    refreshUnread();
  }, [refreshUnread]);

  return (
    <ChatContext.Provider value={{ totalUnread, refreshUnread }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatContext deve ser usado dentro de ChatProvider.');
  return ctx;
}
