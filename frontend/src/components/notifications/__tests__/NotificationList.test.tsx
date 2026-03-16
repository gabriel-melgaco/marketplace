import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NotificationList } from '../NotificationList';
import type { Notification } from '@/types/notifications';

// ─── Mock react-router-dom ────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

// ─── Mock @/contexts/NotificationContext ──────────────────────────────────────

const mockContextValue = {
  notifications: [] as Notification[],
  unreadCount: 0,
  isConnected: false,
  isLoading: false,
  hasMore: false,
  error: null,
  markAsRead: vi.fn(),
  markAllAsRead: vi.fn(),
  loadMore: vi.fn(),
  refresh: vi.fn(),
};

vi.mock('@/contexts/NotificationContext', () => ({
  useNotificationContext: () => mockContextValue,
}));

// ─── Mock IntersectionObserver ────────────────────────────────────────────────

let ioCallback: IntersectionObserverCallback;
const mockObserver = {
  observe: vi.fn(),
  disconnect: vi.fn(),
};

const MockIntersectionObserver = vi.fn(function (
  this: IntersectionObserver,
  cb: IntersectionObserverCallback
) {
  ioCallback = cb;
  return mockObserver;
} as unknown as typeof IntersectionObserver);

vi.stubGlobal('IntersectionObserver', MockIntersectionObserver);

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const makeNotification = (overrides: Partial<Notification> = {}): Notification => ({
  id: 'n1',
  notification_type: 'order_created',
  title: 'Pedido criado',
  body: 'Seu pedido foi criado.',
  metadata: {},
  is_read: false,
  created_at: new Date().toISOString(),
  read_at: null,
  ...overrides,
});

function setContext(overrides: Partial<typeof mockContextValue>) {
  Object.assign(mockContextValue, { ...mockContextValue, ...overrides });
}

function resetContext() {
  Object.assign(mockContextValue, {
    notifications: [],
    unreadCount: 0,
    isConnected: false,
    isLoading: false,
    hasMore: false,
    error: null,
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
    loadMore: vi.fn(),
    refresh: vi.fn(),
  });
}

beforeEach(() => {
  resetContext();
  vi.clearAllMocks();
  mockObserver.observe.mockClear();
  mockObserver.disconnect.mockClear();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('NotificationList', () => {
  describe('empty state', () => {
    it('shows empty state message when no notifications and not loading', () => {
      setContext({ notifications: [], isLoading: false });
      render(<NotificationList />);

      expect(screen.getByText('Nenhuma notificação por aqui')).toBeInTheDocument();
    });

    it('does NOT show empty state when isLoading is true', () => {
      setContext({ notifications: [], isLoading: true });
      render(<NotificationList />);

      expect(screen.queryByText('Nenhuma notificação por aqui')).not.toBeInTheDocument();
    });
  });

  describe('loading spinner', () => {
    it('shows spinner when isLoading is true', () => {
      setContext({ isLoading: true });
      render(<NotificationList />);

      // The spinner is the animate-spin div
      const spinner = document.querySelector('.animate-spin');
      expect(spinner).toBeInTheDocument();
    });
  });

  describe('notification items', () => {
    it('renders one button per notification', () => {
      const notifications = [
        makeNotification({ id: 'n1' }),
        makeNotification({ id: 'n2' }),
        makeNotification({ id: 'n3' }),
      ];
      setContext({ notifications });
      render(<NotificationList />);

      // Each notification renders as a button with an aria-label including the title
      const notifButtons = screen
        .getAllByRole('button')
        .filter((btn) => btn.getAttribute('aria-label')?.includes('Pedido criado'));
      expect(notifButtons).toHaveLength(3);
    });

    it('unread notification has a blue dot indicator', () => {
      setContext({
        notifications: [makeNotification({ id: 'n1', is_read: false })],
      });
      render(<NotificationList />);

      // The blue dot is a span with bg-blue-500
      const dot = document.querySelector('.bg-blue-500');
      expect(dot).toBeInTheDocument();
    });

    it('read notification has no blue dot indicator', () => {
      setContext({
        notifications: [makeNotification({ id: 'n1', is_read: true })],
      });
      render(<NotificationList />);

      const dot = document.querySelector('.bg-blue-500');
      expect(dot).not.toBeInTheDocument();
    });

    it('clicking an unread notification calls markAsRead with its ID', async () => {
      const markAsRead = vi.fn().mockResolvedValue(undefined);
      setContext({
        notifications: [makeNotification({ id: 'n1', is_read: false })],
        markAsRead,
      });
      const user = userEvent.setup();
      render(<NotificationList />);

      const notifButton = screen.getByRole('button', {
        name: /Pedido criado \(não lida\)/i,
      });
      await user.click(notifButton);

      expect(markAsRead).toHaveBeenCalledWith('n1');
    });

    it('clicking an unread new_message notification calls navigate with the correct route', async () => {
      const markAsRead = vi.fn().mockResolvedValue(undefined);
      setContext({
        notifications: [
          makeNotification({
            id: 'msg1',
            notification_type: 'new_message',
            title: 'Nova Mensagem',
            is_read: false,
            metadata: { chat_id: '42' },
          }),
        ],
        markAsRead,
      });
      const user = userEvent.setup();
      render(<NotificationList />);

      const notifButton = screen.getByRole('button', {
        name: /Nova Mensagem \(não lida\)/i,
      });
      await user.click(notifButton);

      expect(mockNavigate).toHaveBeenCalledWith('/chats/42');
    });

    it('does NOT call markAsRead when clicking an already-read notification', async () => {
      const markAsRead = vi.fn().mockResolvedValue(undefined);
      setContext({
        notifications: [makeNotification({ id: 'n1', is_read: true })],
        markAsRead,
      });
      const user = userEvent.setup();
      render(<NotificationList />);

      const notifButton = screen.getByRole('button', {
        name: /Pedido criado \(lida\)/i,
      });
      await user.click(notifButton);

      expect(markAsRead).not.toHaveBeenCalled();
    });
  });

  describe('"Marcar todas como lidas" button', () => {
    it('shows the button when there are unread notifications', () => {
      setContext({
        notifications: [makeNotification({ id: 'n1', is_read: false })],
      });
      render(<NotificationList />);

      expect(screen.getByText('Marcar todas como lidas')).toBeInTheDocument();
    });

    it('hides the button when all notifications are read', () => {
      setContext({
        notifications: [makeNotification({ id: 'n1', is_read: true })],
      });
      render(<NotificationList />);

      expect(screen.queryByText('Marcar todas como lidas')).not.toBeInTheDocument();
    });

    it('has disabled attribute while in-flight (markAllAsRead never resolves)', async () => {
      // markAllAsRead that never settles
      const markAllAsRead = vi.fn().mockReturnValue(new Promise(() => {}));
      setContext({
        notifications: [makeNotification({ id: 'n1', is_read: false })],
        markAllAsRead,
      });
      const user = userEvent.setup();
      render(<NotificationList />);

      const markAllButton = screen.getByText('Marcar todas como lidas');
      await user.click(markAllButton);

      // After click the button should be disabled (in-flight)
      await waitFor(() => {
        expect(markAllButton).toBeDisabled();
      });
    });
  });

  describe('close button', () => {
    it('calls onClose prop when close button is clicked', async () => {
      const onClose = vi.fn();
      setContext({ notifications: [] });
      const user = userEvent.setup();
      render(<NotificationList onClose={onClose} />);

      const closeButton = screen.getByRole('button', {
        name: /Fechar notificações/i,
      });
      await user.click(closeButton);

      expect(onClose).toHaveBeenCalledOnce();
    });
  });

  describe('sentinel and infinite scroll', () => {
    it('sentinel div is present when hasMore is true', () => {
      setContext({
        notifications: [makeNotification({ id: 'n1' })],
        hasMore: true,
      });
      render(<NotificationList />);

      // The sentinel is observed via IntersectionObserver; mockObserver.observe should be called
      expect(mockObserver.observe).toHaveBeenCalled();
    });

    it('sentinel div is absent (observer not called with node) when hasMore is false', () => {
      setContext({
        notifications: [makeNotification({ id: 'n1' })],
        hasMore: false,
      });
      render(<NotificationList />);

      // When hasMore is false, sentinelRef callback receives null or is never mounted
      // The IntersectionObserver may still be constructed but observe should not be called
      // OR observe is called with null (the component calls disconnect then returns early)
      const observedNodes = mockObserver.observe.mock.calls.map((c) => c[0]);
      const hasRealNode = observedNodes.some((node) => node !== null && node !== undefined);
      expect(hasRealNode).toBe(false);
    });

    it('shows "Fim das notificações" when !hasMore and notifications.length > 0', () => {
      setContext({
        notifications: [makeNotification({ id: 'n1' })],
        hasMore: false,
      });
      render(<NotificationList />);

      expect(screen.getByText('Fim das notificações')).toBeInTheDocument();
    });

    it('does NOT show "Fim das notificações" when notifications list is empty', () => {
      setContext({ notifications: [], hasMore: false });
      render(<NotificationList />);

      expect(screen.queryByText('Fim das notificações')).not.toBeInTheDocument();
    });

    it('IntersectionObserver triggers loadMore when sentinel intersects and !isLoading', () => {
      const loadMore = vi.fn().mockResolvedValue(undefined);
      setContext({
        notifications: [makeNotification({ id: 'n1' })],
        hasMore: true,
        isLoading: false,
        loadMore,
      });
      render(<NotificationList />);

      // Simulate intersection
      act(() => {
        ioCallback(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          mockObserver as unknown as IntersectionObserver
        );
      });

      expect(loadMore).toHaveBeenCalledOnce();
    });

    it('IntersectionObserver does NOT trigger loadMore when isLoading is true', () => {
      const loadMore = vi.fn().mockResolvedValue(undefined);
      setContext({
        notifications: [makeNotification({ id: 'n1' })],
        hasMore: true,
        isLoading: true,
        loadMore,
      });
      render(<NotificationList />);

      act(() => {
        ioCallback(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          mockObserver as unknown as IntersectionObserver
        );
      });

      expect(loadMore).not.toHaveBeenCalled();
    });
  });
});
