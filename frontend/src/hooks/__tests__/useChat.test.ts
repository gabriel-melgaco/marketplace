import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { MockWebSocket, getLastWsInstance } from '@/test/MockWebSocket';
import { useChat } from '@/hooks/useChat';

// ── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('@/api/axios', () => ({
  default: {},
  refreshAccessToken: vi.fn().mockResolvedValue(null),
}));

vi.mock('@/utils/tokenStorage', () => ({
  tokenStorage: {
    getAccessToken: vi.fn(() => 'test-token'),
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

function makeMessage(overrides = {}) {
  return {
    id: 'msg-1',
    sender_id: 42,
    sender_name: 'Alice',
    content: 'Hello!',
    created_at: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useChat', () => {
  describe('initial state', () => {
    it('starts with empty messages, disconnected, no typingUsers', () => {
      const { result } = renderHook(() => useChat('conv-1'));
      expect(result.current.messages).toEqual([]);
      expect(result.current.connected).toBe(false);
      expect(result.current.typingUsers).toEqual([]);
    });

    it('creates a WebSocket with the conversationId in the URL', () => {
      renderHook(() => useChat('conv-abc'));
      expect(getLastWsInstance().url).toContain('/chats/conv-abc/');
    });

    it('does NOT create a WebSocket when conversationId is null', () => {
      renderHook(() => useChat(null));
      expect(MockWebSocket.instances).toHaveLength(0);
    });

    it('does NOT create a WebSocket when conversationId is undefined', () => {
      renderHook(() => useChat(undefined));
      expect(MockWebSocket.instances).toHaveLength(0);
    });
  });

  describe('connection lifecycle', () => {
    it('sets connected=true on WS open', () => {
      const { result } = renderHook(() => useChat('conv-1'));
      act(() => getLastWsInstance().simulateOpen());
      expect(result.current.connected).toBe(true);
    });

    it('sets connected=false on WS close', () => {
      const { result } = renderHook(() => useChat('conv-1'));
      act(() => {
        getLastWsInstance().simulateOpen();
        getLastWsInstance().simulateClose(1000);
      });
      expect(result.current.connected).toBe(false);
    });

    it('disconnects and cleans up on unmount', () => {
      const { unmount } = renderHook(() => useChat('conv-1'));
      const ws = getLastWsInstance();
      act(() => ws.simulateOpen());
      unmount();
      expect(ws.readyState).toBe(MockWebSocket.CLOSED);
    });

    it('creates a new WS when conversationId changes', () => {
      const { rerender } = renderHook(({ id }) => useChat(id), {
        initialProps: { id: 'conv-1' },
      });
      expect(MockWebSocket.instances).toHaveLength(1);
      rerender({ id: 'conv-2' });
      expect(MockWebSocket.instances).toHaveLength(2);
      expect(getLastWsInstance().url).toContain('/chats/conv-2/');
    });
  });

  describe('incoming messages', () => {
    it('appends new_message to messages state', () => {
      const { result } = renderHook(() => useChat('conv-1'));
      act(() => getLastWsInstance().simulateOpen());
      const msg = makeMessage();
      act(() => getLastWsInstance().simulateMessage({ type: 'new_message', message: msg }));
      expect(result.current.messages).toHaveLength(1);
      expect(result.current.messages[0]).toEqual(msg);
    });

    it('auto-marks as read when a message arrives', () => {
      renderHook(() => useChat('conv-1'));
      const ws = getLastWsInstance();
      act(() => ws.simulateOpen());
      const msg = makeMessage({ id: 'msg-42' });
      act(() => ws.simulateMessage({ type: 'new_message', message: msg }));
      const sent = ws.sentMessages.map((m) => JSON.parse(m));
      expect(sent).toContainEqual({ type: 'message.read', last_message_id: 'msg-42' });
    });

    it('accumulates multiple messages in order', () => {
      const { result } = renderHook(() => useChat('conv-1'));
      const ws = getLastWsInstance();
      act(() => ws.simulateOpen());
      act(() => ws.simulateMessage({ type: 'new_message', message: makeMessage({ id: 'a', content: 'first' }) }));
      act(() => ws.simulateMessage({ type: 'new_message', message: makeMessage({ id: 'b', content: 'second' }) }));
      expect(result.current.messages).toHaveLength(2);
      expect(result.current.messages[0].content).toBe('first');
      expect(result.current.messages[1].content).toBe('second');
    });
  });

  describe('typing indicator', () => {
    it('adds user to typingUsers on typing event', () => {
      const { result } = renderHook(() => useChat('conv-1'));
      act(() => getLastWsInstance().simulateOpen());
      act(() =>
        getLastWsInstance().simulateMessage({
          type: 'typing',
          typing: { conversation_id: 'conv-1', user_id: 5, user_name: 'Bob' },
        })
      );
      expect(result.current.typingUsers).toContain('Bob');
    });

    it('clears typingUsers after 3 seconds', () => {
      const { result } = renderHook(() => useChat('conv-1'));
      act(() => getLastWsInstance().simulateOpen());
      act(() =>
        getLastWsInstance().simulateMessage({
          type: 'typing',
          typing: { conversation_id: 'conv-1', user_id: 5, user_name: 'Bob' },
        })
      );
      expect(result.current.typingUsers).toContain('Bob');
      act(() => vi.advanceTimersByTime(3000));
      expect(result.current.typingUsers).toHaveLength(0);
    });

    it('resets the 3 s timer on subsequent typing events', () => {
      const { result } = renderHook(() => useChat('conv-1'));
      const ws = getLastWsInstance();
      act(() => ws.simulateOpen());
      act(() =>
        ws.simulateMessage({ type: 'typing', typing: { conversation_id: 'conv-1', user_id: 5, user_name: 'Bob' } })
      );
      act(() => vi.advanceTimersByTime(2000));
      // Fire another typing event — timer should reset
      act(() =>
        ws.simulateMessage({ type: 'typing', typing: { conversation_id: 'conv-1', user_id: 5, user_name: 'Bob' } })
      );
      act(() => vi.advanceTimersByTime(2000));
      // 4 s total but timer was reset at 2 s → only 2 s elapsed since last event
      expect(result.current.typingUsers).toContain('Bob');
      act(() => vi.advanceTimersByTime(1000)); // 3 s since last reset → now clear
      expect(result.current.typingUsers).toHaveLength(0);
    });

    it('deduplicates the same user in typingUsers', () => {
      const { result } = renderHook(() => useChat('conv-1'));
      const ws = getLastWsInstance();
      act(() => ws.simulateOpen());
      const typingEvent = { type: 'typing', typing: { conversation_id: 'conv-1', user_id: 5, user_name: 'Bob' } };
      act(() => ws.simulateMessage(typingEvent));
      act(() => ws.simulateMessage(typingEvent));
      expect(result.current.typingUsers.filter((u) => u === 'Bob')).toHaveLength(1);
    });
  });

  describe('sendMessage()', () => {
    it('sends message content over the WS', () => {
      renderHook(() => useChat('conv-1'));
      const ws = getLastWsInstance();
      act(() => ws.simulateOpen());
      const { result } = renderHook(() => useChat('conv-1'));
      // Use a dedicated hook instance for cleaner access
      const { result: r2 } = renderHook(() => useChat('conv-2'));
      const ws2 = getLastWsInstance();
      act(() => ws2.simulateOpen());
      act(() => r2.current.sendMessage('hey there'));
      const sent = ws2.sentMessages.map((m) => JSON.parse(m));
      expect(sent).toContainEqual({ type: 'message.send', content: 'hey there' });
    });

    it('sendMessage is stable (same reference across renders)', () => {
      const { result, rerender } = renderHook(() => useChat('conv-1'));
      const ref1 = result.current.sendMessage;
      rerender();
      expect(result.current.sendMessage).toBe(ref1);
    });
  });

  describe('notifyTyping()', () => {
    it('sends typing.start over the WS', () => {
      const { result } = renderHook(() => useChat('conv-1'));
      const ws = getLastWsInstance();
      act(() => ws.simulateOpen());
      act(() => result.current.notifyTyping());
      expect(ws.sentMessages.map((m) => JSON.parse(m))).toContainEqual({ type: 'typing.start' });
    });

    it('notifyTyping is stable (same reference across renders)', () => {
      const { result, rerender } = renderHook(() => useChat('conv-1'));
      const ref1 = result.current.notifyTyping;
      rerender();
      expect(result.current.notifyTyping).toBe(ref1);
    });
  });

  describe('cleanup', () => {
    it('clears typing timer on unmount', () => {
      const { result, unmount } = renderHook(() => useChat('conv-1'));
      const ws = getLastWsInstance();
      act(() => ws.simulateOpen());
      act(() =>
        ws.simulateMessage({ type: 'typing', typing: { conversation_id: 'conv-1', user_id: 5, user_name: 'Bob' } })
      );
      expect(result.current.typingUsers).toContain('Bob');
      // Unmount before timer fires — should not throw or cause act() warnings
      expect(() => unmount()).not.toThrow();
    });
  });
});
