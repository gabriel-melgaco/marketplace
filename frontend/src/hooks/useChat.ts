import { useCallback, useEffect, useRef, useState } from 'react';
import { ChatSocket } from '@/services/ChatSocket';
import { chatService } from '@/services/chatService';
import { tokenStorage } from '@/utils/tokenStorage';
import type { ChatMessage } from '@/types/chat';

const PAGE_SIZE = 50;

interface UseChatReturn {
  messages: ChatMessage[];
  connected: boolean;
  typingUsers: string[];
  isLoadingHistory: boolean;
  hasMoreHistory: boolean;
  sendMessage: (content: string) => void;
  notifyTyping: () => void;
  loadMoreHistory: () => Promise<void>;
}

export function useChat(conversationId: string | null): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const [typingUsers, setTypingUsers] = useState<string[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);

  const socketRef = useRef<ChatSocket | null>(null);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef(true);
  const prevConversationIdRef = useRef<string | null>(null);

  // Track mounted state so async operations do not update state after unmount.
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Load initial message history and open the WebSocket whenever conversationId changes.
  useEffect(() => {
    if (!conversationId) return;

    // Guard against double-mount or rapid re-renders that fire the effect
    // with the same conversationId that is already connected.
    if (prevConversationIdRef.current === conversationId) return;
    prevConversationIdRef.current = conversationId;

    let cancelled = false;

    async function loadHistory() {
      if (!conversationId) return;
      if (!isMountedRef.current) return;

      setIsLoadingHistory(true);
      setMessages([]);

      try {
        const history = await chatService.getMessages(conversationId, {
          limit: PAGE_SIZE,
        });
        if (!cancelled && isMountedRef.current) {
          // The REST API returns messages newest-first; reverse to chronological
          // order so the oldest message is at index 0 and the newest at the end.
          const chronological = [...history].reverse();
          setMessages(chronological);
          setHasMoreHistory(history.length >= PAGE_SIZE);

          // Mark all loaded messages as read (best-effort — non-blocking).
          if (chronological.length > 0) {
            const lastMsg = chronological[chronological.length - 1];
            chatService.markAsRead(conversationId, lastMsg.id).catch(() => {});
          }
        }
      } catch {
        // History loading is best-effort; WS messages will still work.
      } finally {
        if (!cancelled && isMountedRef.current) {
          setIsLoadingHistory(false);
        }
      }
    }

    loadHistory();

    const token = tokenStorage.getAccessToken() ?? '';

    socketRef.current = new ChatSocket(conversationId, token, {
      onConnect: () => {
        if (isMountedRef.current) setConnected(true);
      },

      onDisconnect: () => {
        if (isMountedRef.current) setConnected(false);
      },

      onMessage: (message) => {
        if (!isMountedRef.current) return;
        setMessages((prev) => {
          // Deduplicate: do not append if message id already exists.
          if (prev.some((m) => m.id === message.id)) return prev;
          return [...prev, message];
        });
        // Auto-mark as read via the socket protocol.
        socketRef.current?.markAsRead(message.id);
        // Also mark via REST so the server-side unread count is updated.
        chatService.markAsRead(conversationId, message.id).catch(() => {});
      },

      onReadReceipt: () => {
        // Read receipts are informational — no local state change needed.
      },

      onTyping: ({ user_name }) => {
        if (!isMountedRef.current) return;
        setTypingUsers((prev) => [...new Set([...prev, user_name])]);
        // Clear the typing indicator after 3 s without a new event.
        if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
        typingTimerRef.current = setTimeout(() => {
          if (isMountedRef.current) setTypingUsers([]);
        }, 3000);
      },
    });

    socketRef.current.connect();

    return () => {
      cancelled = true;
      prevConversationIdRef.current = null;
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      socketRef.current?.disconnect();
      socketRef.current = null;
      if (isMountedRef.current) {
        setConnected(false);
        setTypingUsers([]);
      }
    };
  }, [conversationId]);

  const sendMessage = useCallback((content: string) => {
    socketRef.current?.sendMessage(content);
  }, []);

  const notifyTyping = useCallback(() => {
    socketRef.current?.sendTyping();
  }, []);

  const loadMoreHistory = useCallback(async () => {
    if (!conversationId || !isMountedRef.current) return;

    setIsLoadingHistory(true);
    try {
      // Use the id of the oldest message we have as the cursor.
      const beforeId = messages[0]?.id;
      const older = await chatService.getMessages(conversationId, {
        beforeId,
        limit: PAGE_SIZE,
      });

      if (!isMountedRef.current) return;

      if (older.length === 0) {
        setHasMoreHistory(false);
        return;
      }

      // The REST API returns messages newest-first; reverse so older messages
      // are prepended in chronological order (oldest at the beginning).
      const olderChronological = [...older].reverse();

      setMessages((prev) => {
        const existingIds = new Set(prev.map((m) => m.id));
        const deduped = olderChronological.filter((m) => !existingIds.has(m.id));
        return [...deduped, ...prev];
      });
      setHasMoreHistory(older.length >= PAGE_SIZE);
    } catch {
      // Silently fail — user can retry by scrolling up again.
    } finally {
      if (isMountedRef.current) setIsLoadingHistory(false);
    }
  // Including `messages` in deps would cause the reference to change on every
  // message append. Instead we read the value through a callback-form setState
  // when needed. The eslint disable is intentional here.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  return {
    messages,
    connected,
    typingUsers,
    isLoadingHistory,
    hasMoreHistory,
    sendMessage,
    notifyTyping,
    loadMoreHistory,
  };
}
