export type ConversationType = 'buyer_seller' | 'buyer_support' | 'seller_support';
export type ConversationStatus = 'active' | 'closed' | 'archived';

export interface ChatParticipantUser {
  id: number;
  email: string;
  full_name: string;
  picture?: string | null;
}

export interface ChatParticipant {
  id: number;        // participant record ID
  user: ChatParticipantUser;
  role: string;
  last_read_at: string | null;
  joined_at: string;
  is_active: boolean;
}

export interface ChatMessage {
  id: string;
  sender_id: number;
  sender_name: string;
  content: string;
  created_at: string;
  is_read: boolean;
}

export interface Conversation {
  id: string;
  conversation_type: ConversationType;
  status: ConversationStatus;
  participants: ChatParticipant[];
  unread_count: number;
  last_message: ChatMessage | null;
  listing_id: number | null;
  order_id: string | null;
  updated_at: string;
}
