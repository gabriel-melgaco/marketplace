import { useCallback, useEffect, useState } from 'react';
import { chatService } from '@/services/chatService';
import type { Conversation, ConversationType, ConversationStatus } from '@/types/chat';

interface UseConversationsReturn {
  conversations: Conversation[];
  isLoading: boolean;
  error: string | null;
  createOrOpenConversation: (
    recipientId: number,
    type: ConversationType,
    options?: { listingId?: number; orderId?: string },
  ) => Promise<string>;
  refresh: () => Promise<void>;
}

export function useConversations(
  status: ConversationStatus = 'active',
): UseConversationsReturn {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await chatService.listConversations(status);
      setConversations(data);
    } catch (err: unknown) {
      const responseData = (err as { response?: { data?: unknown } })?.response?.data;
      if (responseData && typeof responseData === 'object') {
        const msgs = (Object.values(responseData).flat() as unknown[]).filter(
          (v): v is string => typeof v === 'string',
        );
        setError(msgs.join(' ') || 'Erro ao carregar conversas.');
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Erro ao carregar conversas.');
      }
    } finally {
      setIsLoading(false);
    }
  }, [status]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const createOrOpenConversation = useCallback(
    async (
      recipientId: number,
      type: ConversationType,
      options?: { listingId?: number; orderId?: string },
    ): Promise<string> => {
      const conversation = await chatService.createConversation(recipientId, type, options);
      await refresh();
      return conversation.id;
    },
    [refresh],
  );

  return { conversations, isLoading, error, createOrOpenConversation, refresh };
}
