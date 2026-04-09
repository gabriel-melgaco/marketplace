import api from '@/api/axios';
import type {
  Conversation,
  ConversationType,
  ConversationStatus,
  ChatMessage,
} from '@/types/chat';

export const chatService = {
  /**
   * Creates a new conversation or returns an existing one between the current
   * user and the given recipient. The backend is expected to be idempotent for
   * the same (recipient, type, listing) tuple.
   */
  async createConversation(
    recipientId: number,
    type: ConversationType,
    options?: { listingId?: number; orderId?: string },
  ): Promise<Conversation> {
    const payload: Record<string, unknown> = {
      recipient_id: recipientId,
      conversation_type: type,
    };
    if (options?.listingId !== undefined) {
      payload.listing_id = options.listingId;
    }
    if (options?.orderId !== undefined) {
      payload.order_id = options.orderId;
    }
    const response = await api.post<Conversation>('/chats/conversations/', payload);
    return response.data;
  },

  /**
   * Returns all conversations for the current user, optionally filtered by
   * status. Results arrive newest-first from the API.
   */
  async listConversations(status?: ConversationStatus): Promise<Conversation[]> {
    const params: Record<string, string> = {};
    if (status) {
      params.status = status;
    }
    const response = await api.get<Conversation[]>('/chats/conversations/', { params });
    return response.data;
  },

  /**
   * Fetches a page of messages for a conversation.
   * Pass `beforeId` to load older messages (cursor-based pagination).
   * Default page size is 50 messages.
   */
  async getMessages(
    conversationId: string,
    options?: { beforeId?: string; limit?: number },
  ): Promise<ChatMessage[]> {
    const params: Record<string, string | number> = {
      limit: options?.limit ?? 50,
    };
    if (options?.beforeId) {
      params.before = options.beforeId;
    }
    const response = await api.get<ChatMessage[]>(
      `/chats/conversations/${conversationId}/messages/`,
      { params },
    );
    return response.data;
  },

  /**
   * Marks all messages up to and including `lastMessageId` as read.
   */
  async markAsRead(conversationId: string, lastMessageId: string): Promise<void> {
    await api.post(`/chats/conversations/${conversationId}/messages/read/`, {
      last_message_id: lastMessageId,
    });
  },

  /**
   * Closes a support conversation. Only applicable to buyer_support and
   * seller_support conversation types.
   */
  async closeConversation(conversationId: string): Promise<Conversation> {
    const response = await api.patch<Conversation>(
      `/chats/conversations/${conversationId}/close/`,
    );
    return response.data;
  },
};
