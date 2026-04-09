import { tokenStorage } from '@/utils/tokenStorage';
import { refreshAccessToken } from '@/api/axios';
import type { ChatMessage } from '@/types/chat';

const WS_BASE_URL = (import.meta.env.VITE_WS_URL as string | undefined) ?? 'wss://api.megdev.com.br';
const MAX_RECONNECT_DELAY = 30_000;

export interface ReadReceipt {
  conversation_id: string;
  last_message_id: string;
  user_id: number;
  read_at: string;
}

export interface TypingEvent {
  conversation_id: string;
  user_id: number;
  user_name: string;
}

export interface NewConversationEvent {
  conversation_id: string;
  conversation_type: string;
}

export interface ChatErrorEvent {
  code: string;
  message: string;
}

export interface ChatSocketHandlers {
  onConnect?: () => void;
  onDisconnect?: (code: number) => void;
  onMessage?: (message: ChatMessage) => void;
  onReadReceipt?: (receipt: ReadReceipt) => void;
  onTyping?: (event: TypingEvent) => void;
  onNewConversation?: (event: NewConversationEvent) => void;
  onError?: (event: ChatErrorEvent) => void;
}

export class ChatSocket {
  private conversationId: string;
  private token: string;
  private handlers: ChatSocketHandlers;
  private ws: WebSocket | null = null;
  private reconnectDelay = 1000;
  private shouldReconnect = true;

  constructor(conversationId: string, token: string, handlers: ChatSocketHandlers = {}) {
    this.conversationId = conversationId;
    this.token = token;
    this.handlers = handlers;
  }

  connect(): void {
    const url = `${WS_BASE_URL}/ws/chats/${this.conversationId}/?token=${this.token}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      this.handlers.onConnect?.();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data as string) as { type: string } & Record<string, unknown>;
        this._dispatch(data);
      } catch {
        // ignore malformed messages
      }
    };

    this.ws.onclose = async (event: CloseEvent) => {
      this.handlers.onDisconnect?.(event.code);

      if (!this.shouldReconnect) return;

      if (event.code === 4001) {
        const newToken = await refreshAccessToken();
        if (newToken) {
          this.token = newToken;
          this.connect();
        }
        return;
      }

      // 4003 = not a participant, 4004 = not found — do not reconnect
      if (event.code === 4003 || event.code === 4004) return;

      // All other codes (including 1000) — exponential backoff
      setTimeout(() => {
        if (this.shouldReconnect) this.connect();
      }, this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, MAX_RECONNECT_DELAY);
    };

    this.ws.onerror = () => {
      // onerror is always followed by onclose; logging only
    };
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING)
    ) {
      this.ws.close(1000, 'Desconectado pelo usuário');
    }
    this.ws = null;
  }

  sendMessage(content: string): void {
    this._send({ type: 'message.send', content });
  }

  markAsRead(lastMessageId: string): void {
    this._send({ type: 'message.read', last_message_id: lastMessageId });
  }

  sendTyping(): void {
    this._send({ type: 'typing.start' });
  }

  private _send(data: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  private _dispatch(data: { type: string } & Record<string, unknown>): void {
    switch (data.type) {
      case 'new_message':
        this.handlers.onMessage?.(data.message as ChatMessage);
        break;
      case 'message_read':
        this.handlers.onReadReceipt?.(data.receipt as ReadReceipt);
        break;
      case 'typing':
        this.handlers.onTyping?.(data.typing as TypingEvent);
        break;
      case 'new_conversation':
        this.handlers.onNewConversation?.(data.conversation as NewConversationEvent);
        break;
      case 'error':
        this.handlers.onError?.(data as unknown as ChatErrorEvent);
        break;
    }
  }
}

// Re-export tokenStorage so existing test files that import it from here
// continue to work without modification.
export { tokenStorage };
