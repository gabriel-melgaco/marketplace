import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useNotifications } from '../useNotifications';
import { MockWebSocket, getLastWsInstance } from '@/test/MockWebSocket';
import type { Notification } from '@/types/notifications';

// ─── Mock notificationsApi ────────────────────────────────────────────────────

vi.mock('@/services/notificationsApi', () => ({
  notificationsApi: {
    list: vi.fn(),
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
    getUnreadCount: vi.fn(),
  },
}));

// Import after mock to get the mocked version
import { notificationsApi } from '@/services/notificationsApi';

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const makeNotification = (overrides: Partial<Notification> = {}): Notification => ({
  id: 'n1',
  notification_type: 'order_created',
  title: 'Pedido criado',
  body: 'Seu pedido foi criado.',
  metadata: {},
  is_read: false,
  created_at: '2024-06-15T10:00:00Z',
  read_at: null,
  ...overrides,
});

const DEFAULT_LIST_RESPONSE = {
  count: 2,
  next: null,
  previous: null,
  results: [
    makeNotification({ id: 'n1' }),
    makeNotification({ id: 'n2', is_read: true }),
  ],
};

function getDefaultOptions() {
  return {
    getAccessToken: () => localStorage.getItem('@access_token'),
    wsBaseUrl: 'ws://localhost',
  };
}

// ─── Setup / teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  vi.stubGlobal('WebSocket', MockWebSocket);
  MockWebSocket.reset();
  localStorage.setItem('@access_token', 'test-token');
  vi.mocked(notificationsApi.list).mockResolvedValue(DEFAULT_LIST_RESPONSE);
  vi.mocked(notificationsApi.markAsRead).mockResolvedValue(
    makeNotification({ id: 'n1', is_read: true, read_at: new Date().toISOString() })
  );
  vi.mocked(notificationsApi.markAllAsRead).mockResolvedValue({ marked: 2 });
});

afterEach(() => {
  vi.restoreAllMocks();
  MockWebSocket.reset();
});

// ─── Group 1: Initial load ────────────────────────────────────────────────────

describe('Initial load', () => {
  it('loads notifications on mount when token is present', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => {
      expect(result.current.notifications).toHaveLength(2);
    });

    expect(notificationsApi.list).toHaveBeenCalledWith({ page: 1 });
  });

  it('does NOT call the API when token is absent', async () => {
    localStorage.clear();
    vi.mocked(notificationsApi.list).mockClear();

    renderHook(() => useNotifications(getDefaultOptions()));

    // Flush microtasks and effect queue
    await act(async () => { await Promise.resolve(); });

    expect(notificationsApi.list).not.toHaveBeenCalled();
  });

  it('sets hasMore=true when response.next is not null', async () => {
    vi.mocked(notificationsApi.list).mockResolvedValueOnce({
      ...DEFAULT_LIST_RESPONSE,
      next: 'http://api/notifications/?page=2',
    });

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.hasMore).toBe(true);
  });

  it('sets hasMore=false when response.next is null', async () => {
    vi.mocked(notificationsApi.list).mockResolvedValueOnce({
      ...DEFAULT_LIST_RESPONSE,
      next: null,
    });

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.hasMore).toBe(false);
  });

  it('sets error when list() rejects', async () => {
    vi.mocked(notificationsApi.list).mockRejectedValueOnce(new Error('Network failure'));

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => {
      expect(result.current.error).toBe('Não foi possível carregar as notificações.');
    });
  });

  it('isLoading goes true then false during fetch', async () => {
    let resolveList!: (value: typeof DEFAULT_LIST_RESPONSE) => void;
    vi.mocked(notificationsApi.list).mockReturnValueOnce(
      new Promise((res) => { resolveList = res; })
    );

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    // Should be loading initially
    expect(result.current.isLoading).toBe(true);

    act(() => {
      resolveList(DEFAULT_LIST_RESPONSE);
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });
});

// ─── Group 2: WebSocket connection ───────────────────────────────────────────

describe('WebSocket connection', () => {
  it('creates WebSocket with URL containing ?token=test-token when token present', async () => {
    renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    const ws = getLastWsInstance();
    expect(ws.url).toContain('?token=test-token');
  });

  it('does NOT create WebSocket when token is absent', () => {
    localStorage.clear();

    renderHook(() => useNotifications(getDefaultOptions()));

    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it('isConnected becomes true on onopen', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));

    act(() => {
      getLastWsInstance().simulateOpen();
    });

    expect(result.current.isConnected).toBe(true);
  });

  it('reconnectAttemptRef resets to 0 on successful open after previous failures', async () => {
    vi.useFakeTimers();

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await act(async () => {
      await Promise.resolve();
    });

    // Simulate an unexpected close to trigger a reconnect attempt
    act(() => {
      getLastWsInstance().simulateClose(1006);
    });

    // Fast-forward timers to trigger reconnect
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    // Now simulate successful open on the new connection
    act(() => {
      getLastWsInstance().simulateOpen();
    });

    // After successful open, isConnected should be true
    expect(result.current.isConnected).toBe(true);
    // Error should be cleared
    expect(result.current.error).toBeNull();

    vi.useRealTimers();
  });
});

// ─── Group 3: Incoming messages ──────────────────────────────────────────────

describe('Incoming WebSocket messages', () => {
  it('updates unreadCount from type: "unread_count" message', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    act(() => getLastWsInstance().simulateOpen());

    act(() => {
      getLastWsInstance().simulateMessage({ type: 'unread_count', count: 7 });
    });

    expect(result.current.unreadCount).toBe(7);
  });

  it('prepends notification to list and increments unreadCount from type: "notification" message', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => {
      expect(result.current.notifications).toHaveLength(2);
    });

    act(() => getLastWsInstance().simulateOpen());

    const incoming = makeNotification({ id: 'n_new', title: 'New!' });

    act(() => {
      getLastWsInstance().simulateMessage({ type: 'notification', data: incoming });
    });

    expect(result.current.notifications[0].id).toBe('n_new');
    expect(result.current.notifications).toHaveLength(3);
    expect(result.current.unreadCount).toBe(1);
  });

  it('does NOT add a duplicate notification if the ID already exists', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    act(() => getLastWsInstance().simulateOpen());

    // Send a notification with an ID that already exists in the list
    const duplicate = makeNotification({ id: 'n1' });
    act(() => {
      getLastWsInstance().simulateMessage({ type: 'notification', data: duplicate });
    });

    expect(result.current.notifications).toHaveLength(2);
  });

  it('does not crash and remains functional when receiving malformed JSON', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    act(() => getLastWsInstance().simulateOpen());

    // Directly fire a non-JSON MessageEvent
    act(() => {
      const badEvent = new MessageEvent('message', { data: 'not valid json {{{{' });
      getLastWsInstance().onmessage?.(badEvent);
    });

    // Hook must still be usable
    expect(result.current.notifications).toBeDefined();
    expect(result.current.isConnected).toBe(true);
  });
});

// ─── Group 4: Reconnection logic ─────────────────────────────────────────────

describe('Reconnection logic', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('schedules reconnect on unexpected close code 1006', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await act(async () => { await Promise.resolve(); });

    act(() => getLastWsInstance().simulateOpen());

    const instancesBefore = MockWebSocket.instances.length;

    act(() => {
      getLastWsInstance().simulateClose(1006);
    });

    // After close, isConnected is false
    expect(result.current.isConnected).toBe(false);

    // Advance timers so the reconnect fires
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    expect(MockWebSocket.instances.length).toBeGreaterThan(instancesBefore);
  });

  it('does NOT schedule reconnect on normal close code 1000', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await act(async () => { await Promise.resolve(); });

    act(() => getLastWsInstance().simulateOpen());
    const instancesBefore = MockWebSocket.instances.length;

    act(() => {
      getLastWsInstance().simulateClose(1000);
    });

    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    // No new WebSocket instance created
    expect(MockWebSocket.instances.length).toBe(instancesBefore);
  });

  it('does NOT reconnect on close code 4003 (Forbidden)', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await act(async () => { await Promise.resolve(); });

    act(() => getLastWsInstance().simulateOpen());
    const instancesBefore = MockWebSocket.instances.length;

    act(() => {
      getLastWsInstance().simulateClose(4003);
    });

    await act(async () => {
      vi.advanceTimersByTime(60_000);
      await Promise.resolve();
    });

    expect(MockWebSocket.instances.length).toBe(instancesBefore);
  });

  it('does NOT reconnect on close code 4004 (Not Found)', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await act(async () => { await Promise.resolve(); });

    act(() => getLastWsInstance().simulateOpen());
    const instancesBefore = MockWebSocket.instances.length;

    act(() => {
      getLastWsInstance().simulateClose(4004);
    });

    await act(async () => {
      vi.advanceTimersByTime(60_000);
      await Promise.resolve();
    });

    expect(MockWebSocket.instances.length).toBe(instancesBefore);
  });

  it('sets a permanent error after 10 failed reconnect attempts', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await act(async () => { await Promise.resolve(); });

    // Exhaust all reconnect attempts by simulating 10 closes
    for (let i = 0; i <= 10; i++) {
      act(() => {
        const ws = getLastWsInstance();
        ws.simulateClose(1006);
      });

      await act(async () => {
        vi.advanceTimersByTime(60_000);
        await Promise.resolve();
      });

      // Simulate open on the new instance if one was created (except last)
      if (i < 10 && MockWebSocket.instances.length > i + 1) {
        // don't open, just let it close again
      }
    }

    expect(result.current.error).toBe(
      'Não foi possível reconectar ao servidor de notificações. Recarregue a página.'
    );
  });

  it('code 4001: calls onTokenExpired; if it returns a token, schedules reconnect', async () => {
    const mockOnTokenExpired = vi.fn().mockResolvedValue('new-token');

    const { result } = renderHook(() =>
      useNotifications({
        ...getDefaultOptions(),
        onTokenExpired: mockOnTokenExpired,
      })
    );

    await act(async () => { await Promise.resolve(); });

    act(() => getLastWsInstance().simulateOpen());
    const instancesBefore = MockWebSocket.instances.length;

    act(() => {
      getLastWsInstance().simulateClose(4001);
    });

    await act(async () => {
      await Promise.resolve();
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    expect(mockOnTokenExpired).toHaveBeenCalled();
    expect(MockWebSocket.instances.length).toBeGreaterThan(instancesBefore);
  });

  it('code 4001: sets error when onTokenExpired returns null', async () => {
    // Use real timers for this test because waitFor internally uses setTimeout
    vi.useRealTimers();

    const mockOnTokenExpired = vi.fn().mockResolvedValue(null);

    const { result } = renderHook(() =>
      useNotifications({
        ...getDefaultOptions(),
        onTokenExpired: mockOnTokenExpired,
      })
    );

    await act(async () => { await Promise.resolve(); });

    act(() => getLastWsInstance().simulateOpen());

    act(() => {
      getLastWsInstance().simulateClose(4001);
    });

    // Wait for the async onTokenExpired to resolve and state to update
    await waitFor(() => {
      expect(result.current.error).toBe('Sessão expirada. Faça login novamente.');
    }, { timeout: 3000 });
  });
});

// ─── Group 5: markAsRead optimistic update ────────────────────────────────────

describe('markAsRead', () => {
  it('immediately marks notification as read before API resolves', async () => {
    let resolveMarkAsRead!: (value: Notification) => void;
    vi.mocked(notificationsApi.markAsRead).mockReturnValueOnce(
      new Promise((res) => { resolveMarkAsRead = res; })
    );

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    act(() => {
      result.current.markAsRead('n1');
    });

    // Optimistic update must be immediate — n1 should be read before API settles
    expect(result.current.notifications.find((n) => n.id === 'n1')?.is_read).toBe(true);

    // Cleanup: resolve the pending promise
    act(() => resolveMarkAsRead(makeNotification({ id: 'n1', is_read: true })));
  });

  it('decrements unreadCount immediately', async () => {
    // Set initial unreadCount by simulating WS message
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    act(() => getLastWsInstance().simulateOpen());

    act(() => {
      getLastWsInstance().simulateMessage({ type: 'unread_count', count: 3 });
    });

    expect(result.current.unreadCount).toBe(3);

    act(() => {
      result.current.markAsRead('n1');
    });

    expect(result.current.unreadCount).toBe(2);
  });

  it('reverts is_read to false and restores count on API failure', async () => {
    vi.mocked(notificationsApi.markAsRead).mockRejectedValueOnce(new Error('API Error'));

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    // Seed the unreadCount to a non-zero value so we can verify rollback
    act(() => getLastWsInstance().simulateOpen());
    act(() => {
      getLastWsInstance().simulateMessage({ type: 'unread_count', count: 3 });
    });

    expect(result.current.unreadCount).toBe(3);

    let caughtError: unknown;
    await act(async () => {
      try {
        await result.current.markAsRead('n1');
      } catch (err) {
        caughtError = err;
      }
    });

    expect(caughtError).toBeDefined();
    // n1 must be reverted to unread
    expect(result.current.notifications.find((n) => n.id === 'n1')?.is_read).toBe(false);
    // Count was 3, decremented optimistically to 2, then reverted to 3
    expect(result.current.unreadCount).toBe(3);
  });

  it('re-throws the error to the caller', async () => {
    const apiError = new Error('Unauthorized');
    vi.mocked(notificationsApi.markAsRead).mockRejectedValueOnce(apiError);

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));
    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    await expect(
      act(async () => {
        await result.current.markAsRead('n1');
      })
    ).rejects.toThrow('Unauthorized');
  });
});

// ─── Group 6: markAllAsRead optimistic update ─────────────────────────────────

describe('markAllAsRead', () => {
  it('sets is_read: true on all notifications immediately', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    await act(async () => {
      await result.current.markAllAsRead();
    });

    result.current.notifications.forEach((n) => {
      expect(n.is_read).toBe(true);
    });
  });

  it('sets unreadCount to 0 immediately', async () => {
    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    act(() => getLastWsInstance().simulateOpen());
    act(() => {
      getLastWsInstance().simulateMessage({ type: 'unread_count', count: 5 });
    });

    expect(result.current.unreadCount).toBe(5);

    await act(async () => {
      await result.current.markAllAsRead();
    });

    expect(result.current.unreadCount).toBe(0);
  });

  it('calls loadInitialNotifications (API list) on API failure', async () => {
    vi.mocked(notificationsApi.markAllAsRead).mockRejectedValueOnce(new Error('Server Error'));
    // Reset list mock call count
    vi.mocked(notificationsApi.list).mockClear();
    vi.mocked(notificationsApi.list).mockResolvedValue(DEFAULT_LIST_RESPONSE);

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    // list was called once on mount; clear count
    vi.mocked(notificationsApi.list).mockClear();

    let caughtError: unknown;
    await act(async () => {
      try {
        await result.current.markAllAsRead();
      } catch (err) {
        caughtError = err;
      }
    });

    expect(caughtError).toBeDefined();
    // loadInitialNotifications should have been called
    expect(notificationsApi.list).toHaveBeenCalledWith({ page: 1 });
  });

  it('re-throws error to caller', async () => {
    vi.mocked(notificationsApi.markAllAsRead).mockRejectedValueOnce(new Error('Fail'));
    vi.mocked(notificationsApi.list).mockResolvedValue(DEFAULT_LIST_RESPONSE);

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));
    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    await expect(
      act(async () => { await result.current.markAllAsRead(); })
    ).rejects.toThrow('Fail');
  });
});

// ─── Group 7: loadMore ────────────────────────────────────────────────────────

describe('loadMore', () => {
  it('appends page 2 results and deduplicates existing IDs', async () => {
    vi.mocked(notificationsApi.list).mockResolvedValueOnce({
      count: 4,
      next: 'http://api/notifications/?page=2',
      previous: null,
      results: [makeNotification({ id: 'n1' }), makeNotification({ id: 'n2' })],
    });

    const page2 = {
      count: 4,
      next: null,
      previous: 'http://api/notifications/?page=1',
      results: [
        makeNotification({ id: 'n2' }), // duplicate — should be filtered
        makeNotification({ id: 'n3' }),
        makeNotification({ id: 'n4' }),
      ],
    };
    vi.mocked(notificationsApi.list).mockResolvedValueOnce(page2);

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => {
      expect(result.current.notifications).toHaveLength(2);
      expect(result.current.hasMore).toBe(true);
    });

    await act(async () => {
      await result.current.loadMore();
    });

    // n2 should NOT be duplicated; total should be 4 (n1, n2, n3, n4)
    expect(result.current.notifications).toHaveLength(4);
    expect(result.current.notifications.map((n) => n.id)).toEqual(['n1', 'n2', 'n3', 'n4']);
  });

  it('does nothing when hasMore is false', async () => {
    vi.mocked(notificationsApi.list).mockResolvedValueOnce({
      ...DEFAULT_LIST_RESPONSE,
      next: null, // hasMore = false
    });

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(result.current.hasMore).toBe(false));

    vi.mocked(notificationsApi.list).mockClear();

    await act(async () => {
      await result.current.loadMore();
    });

    expect(notificationsApi.list).not.toHaveBeenCalled();
  });

  it('does nothing when isLoading is true (guards via isLoadingRef)', async () => {
    // First call: never resolves (simulates in-flight)
    let holdFirstResolve!: (v: typeof DEFAULT_LIST_RESPONSE) => void;
    vi.mocked(notificationsApi.list).mockReturnValueOnce(
      new Promise((res) => { holdFirstResolve = res; })
    );

    const { result } = renderHook(() => useNotifications(getDefaultOptions()));

    // isLoading is now true (initial fetch pending)
    expect(result.current.isLoading).toBe(true);

    // A loadMore call while loading should be a no-op
    vi.mocked(notificationsApi.list).mockClear();
    await act(async () => {
      await result.current.loadMore();
    });

    expect(notificationsApi.list).not.toHaveBeenCalled();

    // Cleanup: resolve the hanging fetch
    act(() => holdFirstResolve(DEFAULT_LIST_RESPONSE));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });
});

// ─── Group 8: Cleanup ─────────────────────────────────────────────────────────

describe('Cleanup on unmount', () => {
  it('closes the WebSocket with code 1000 on unmount', async () => {
    const { unmount } = renderHook(() => useNotifications(getDefaultOptions()));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));

    const ws = getLastWsInstance();
    const closeSpy = vi.spyOn(ws, 'close');

    act(() => unmount());

    expect(closeSpy).toHaveBeenCalledWith(1000, 'Componente desmontado');
  });

  it('cancels pending reconnect timer on unmount', async () => {
    vi.useFakeTimers();
    const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout');

    const { result, unmount } = renderHook(() => useNotifications(getDefaultOptions()));

    await act(async () => { await Promise.resolve(); });

    act(() => getLastWsInstance().simulateOpen());

    // Trigger a reconnect that will set a timer
    act(() => {
      getLastWsInstance().simulateClose(1006);
    });

    // Unmount before the timer fires
    act(() => unmount());

    expect(clearTimeoutSpy).toHaveBeenCalled();

    vi.useRealTimers();
  });
});
