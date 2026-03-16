import { useCallback, useEffect, useRef, useState } from 'react';
import { ChatSocket, ChatMessage } from '@/services/ChatSocket';
import { tokenStorage } from '@/utils/tokenStorage';

interface UseChatReturn {
  messages: ChatMessage[];
  connected: boolean;
  typingUsers: string[];
  sendMessage: (content: string) => void;
  notifyTyping: () => void;
}

export function useChat(conversationId: string | null | undefined): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const [typingUsers, setTypingUsers] = useState<string[]>([]);

  const socketRef = useRef<ChatSocket | null>(null);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!conversationId) return;

    const token = tokenStorage.getAccessToken() ?? '';

    socketRef.current = new ChatSocket(conversationId, token, {
      onConnect: () => setConnected(true),

      onDisconnect: () => setConnected(false),

      onMessage: (message) => {
        setMessages((prev) => [...prev, message]);
        // Auto-mark as read on receipt
        socketRef.current?.markAsRead(message.id);
      },

      onReadReceipt: () => {
        // Read receipts are informational — no state change needed here
      },

      onTyping: ({ user_name }) => {
        setTypingUsers((prev) => [...new Set([...prev, user_name])]);
        // Clear typing indicator after 3 s without new events
        if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
        typingTimerRef.current = setTimeout(() => setTypingUsers([]), 3000);
      },
    });

    socketRef.current.connect();

    return () => {
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      socketRef.current?.disconnect();
      socketRef.current = null;
    };
  }, [conversationId]);

  const sendMessage = useCallback((content: string) => {
    socketRef.current?.sendMessage(content);
  }, []);

  const notifyTyping = useCallback(() => {
    socketRef.current?.sendTyping();
  }, []);

  return { messages, connected, typingUsers, sendMessage, notifyTyping };
}
