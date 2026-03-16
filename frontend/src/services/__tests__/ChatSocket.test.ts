import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MockWebSocket, getLastWsInstance } from '@/test/MockWebSocket';
import { ChatSocket } from '@/services/ChatSocket';

// ── Mock refreshAccessToken ─────────────────────────────────────────────────

const { mockRefreshAccessToken } = vi.hoisted(() => ({
  mockRefreshAccessToken: vi.fn(),
}));

vi.mock('@/api/axios', () => ({
  default: {},
  refreshAccessToken: mockRefreshAccessToken,
}));

vi.mock('@/utils/tokenStorage', () => ({
  tokenStorage: {
    getAccessToken: vi.fn(() => 'test-token'),
    getRefreshToken: vi.fn(() => 'test-refresh'),
    saveTokens: vi.fn(),
    clearTokens: vi.fn(),
  },
}));

// ── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.stubGlobal('WebSocket', MockWebSocket);
  vi.useFakeTimers();
});

afterEach(() => {
  MockWebSocket.reset();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeSocket(handlers = {}) {
  return new ChatSocket('conv-123', 'tok-abc', handlers);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ChatSocket', () => {
  describe('connect()', () => {
    it('creates a WebSocket with the correct URL', () => {
      const socket = makeSocket();
      socket.connect();
      const ws = getLastWsInstance();
      expect(ws.url).toContain('/chats/conv-123/');
      expect(ws.url).toContain('token=tok-abc');
    });

    it('calls onConnect handler when WS opens', () => {
      const onConnect = vi.fn();
      const socket = makeSocket({ onConnect });
      socket.connect();
      getLastWsInstance().simulateOpen();
      expect(onConnect).toHaveBeenCalledTimes(1);
    });

    it('resets reconnect delay to 1000 on open', () => {
      const socket = makeSocket();
      // Manually inflate reconnectDelay via private access (cast)
      (socket as unknown as { reconnectDelay: number }).reconnectDelay = 8000;
      socket.connect();
      getLastWsInstance().simulateOpen();
      expect((socket as unknown as { reconnectDelay: number }).reconnectDelay).toBe(1000);
    });
  });

  describe('disconnect()', () => {
    it('calls onDisconnect with code 1000 and does not reconnect', () => {
      const onDisconnect = vi.fn();
      const socket = makeSocket({ onDisconnect });
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      socket.disconnect();

      // disconnect() sets shouldReconnect=false and calls ws.close(), which fires onclose
      expect(onDisconnect).toHaveBeenCalledWith(1000);
      // No new WS instance should be created
      expect(MockWebSocket.instances).toHaveLength(1);
    });
  });

  describe('sendMessage()', () => {
    it('sends { type: "message.send", content } over the WS', () => {
      const socket = makeSocket();
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      socket.sendMessage('hello world');
      expect(ws.sentMessages).toHaveLength(1);
      expect(JSON.parse(ws.sentMessages[0])).toEqual({ type: 'message.send', content: 'hello world' });
    });

    it('does not send when WS is not open', () => {
      const socket = makeSocket();
      socket.connect();
      // WS still CONNECTING — not opened yet
      socket.sendMessage('hello');
      expect(getLastWsInstance().sentMessages).toHaveLength(0);
    });
  });

  describe('markAsRead()', () => {
    it('sends { type: "message.read", last_message_id }', () => {
      const socket = makeSocket();
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      socket.markAsRead('msg-999');
      expect(JSON.parse(ws.sentMessages[0])).toEqual({ type: 'message.read', last_message_id: 'msg-999' });
    });
  });

  describe('sendTyping()', () => {
    it('sends { type: "typing.start" }', () => {
      const socket = makeSocket();
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      socket.sendTyping();
      expect(JSON.parse(ws.sentMessages[0])).toEqual({ type: 'typing.start' });
    });
  });

  describe('incoming message dispatch', () => {
    it('fires onMessage for new_message events', () => {
      const onMessage = vi.fn();
      const socket = makeSocket({ onMessage });
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      const msg = { id: 'm1', sender_id: 1, sender_name: 'Ana', content: 'oi', created_at: '2024-01-01T00:00:00Z' };
      ws.simulateMessage({ type: 'new_message', message: msg });
      expect(onMessage).toHaveBeenCalledWith(msg);
    });

    it('fires onReadReceipt for message_read events', () => {
      const onReadReceipt = vi.fn();
      const socket = makeSocket({ onReadReceipt });
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      const receipt = { conversation_id: 'c1', last_message_id: 'm1', user_id: 2, read_at: '2024-01-01T00:01:00Z' };
      ws.simulateMessage({ type: 'message_read', receipt });
      expect(onReadReceipt).toHaveBeenCalledWith(receipt);
    });

    it('fires onTyping for typing events', () => {
      const onTyping = vi.fn();
      const socket = makeSocket({ onTyping });
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      const typing = { conversation_id: 'c1', user_id: 2, user_name: 'Bob' };
      ws.simulateMessage({ type: 'typing', typing });
      expect(onTyping).toHaveBeenCalledWith(typing);
    });

    it('fires onNewConversation for new_conversation events', () => {
      const onNewConversation = vi.fn();
      const socket = makeSocket({ onNewConversation });
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      const conv = { conversation_id: 'c2', conversation_type: 'buyer_seller' };
      ws.simulateMessage({ type: 'new_conversation', conversation: conv });
      expect(onNewConversation).toHaveBeenCalledWith(conv);
    });

    it('fires onError for error events', () => {
      const onError = vi.fn();
      const socket = makeSocket({ onError });
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      ws.simulateMessage({ type: 'error', code: 'E001', message: 'something failed' });
      expect(onError).toHaveBeenCalledWith(expect.objectContaining({ code: 'E001', message: 'something failed' }));
    });

    it('ignores unknown event types without throwing', () => {
      const socket = makeSocket({});
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      expect(() => ws.simulateMessage({ type: 'unknown_future_event' })).not.toThrow();
    });

    it('ignores malformed (non-JSON) messages', () => {
      const socket = makeSocket({});
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      // Directly fire with raw non-JSON string
      const event = new MessageEvent('message', { data: 'not-json{{' });
      ws.onmessage?.(event);
      // Should not throw
    });
  });

  describe('reconnection', () => {
    it('reconnects with exponential backoff on unexpected close', () => {
      const socket = makeSocket();
      socket.connect();
      const ws1 = getLastWsInstance();
      ws1.simulateOpen();
      ws1.simulateClose(1006); // abnormal close

      vi.advanceTimersByTime(1000);
      expect(MockWebSocket.instances).toHaveLength(2);

      const ws2 = getLastWsInstance();
      ws2.simulateClose(1006);
      vi.advanceTimersByTime(2000); // next delay = 2000
      expect(MockWebSocket.instances).toHaveLength(3);
    });

    it('caps reconnect delay at 30 000 ms', () => {
      const socket = makeSocket();
      (socket as unknown as { reconnectDelay: number }).reconnectDelay = 16000;
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateClose(1006);
      // delay should be min(16000*2, 30000) = 30000
      expect((socket as unknown as { reconnectDelay: number }).reconnectDelay).toBe(30000);
    });

    it('does NOT reconnect on code 4003', () => {
      const socket = makeSocket();
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      ws.simulateClose(4003);
      vi.advanceTimersByTime(5000);
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    it('does NOT reconnect on code 4004', () => {
      const socket = makeSocket();
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      ws.simulateClose(4004);
      vi.advanceTimersByTime(5000);
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    it('reconnects on code 1000 (normal close) when shouldReconnect is true', () => {
      const socket = makeSocket();
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      ws.simulateClose(1000);
      vi.advanceTimersByTime(1000);
      expect(MockWebSocket.instances).toHaveLength(2);
    });

    it('calls refreshAccessToken and reconnects on code 4001', async () => {
      vi.useRealTimers();
      mockRefreshAccessToken.mockResolvedValueOnce('new-token');
      const socket = makeSocket();
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      ws.simulateClose(4001);

      // Drain the microtask queue so the async onclose body runs
      await new Promise<void>((resolve) => setTimeout(resolve, 0));

      expect(mockRefreshAccessToken).toHaveBeenCalledTimes(1);
      expect(MockWebSocket.instances).toHaveLength(2);
      expect(getLastWsInstance().url).toContain('token=new-token');
    });

    it('does NOT reconnect on code 4001 when refresh returns null', async () => {
      vi.useRealTimers();
      mockRefreshAccessToken.mockResolvedValueOnce(null);
      const socket = makeSocket();
      socket.connect();
      const ws = getLastWsInstance();
      ws.simulateOpen();
      ws.simulateClose(4001);

      await new Promise<void>((resolve) => setTimeout(resolve, 0));

      expect(MockWebSocket.instances).toHaveLength(1);
    });
  });
});
