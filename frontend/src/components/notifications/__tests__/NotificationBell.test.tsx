import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { fireEvent } from '@testing-library/dom';
import userEvent from '@testing-library/user-event';
import { NotificationBell } from '../NotificationBell';

// ─── Mock the context ─────────────────────────────────────────────────────────

const mockContextValue = {
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
};

vi.mock('@/contexts/NotificationContext', () => ({
  useNotificationContext: () => mockContextValue,
}));

// ─── Mock NotificationList to isolate NotificationBell ───────────────────────

vi.mock('../NotificationList', () => ({
  NotificationList: ({ onClose }: { onClose?: () => void }) => (
    <div data-testid="notification-list">
      <button onClick={onClose}>close-list</button>
    </div>
  ),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

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
  });
}

beforeEach(() => {
  resetContext();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('NotificationBell', () => {
  describe('aria-label', () => {
    it('renders button with aria-label "Notificações" when unreadCount is 0', () => {
      setContext({ unreadCount: 0 });
      render(<NotificationBell />);

      expect(screen.getByRole('button', { name: 'Notificações' })).toBeInTheDocument();
    });

    it('includes unread count in aria-label when unreadCount is 3', () => {
      setContext({ unreadCount: 3 });
      render(<NotificationBell />);

      expect(
        screen.getByRole('button', { name: 'Notificações — 3 não lidas' })
      ).toBeInTheDocument();
    });
  });

  describe('badge', () => {
    it('does NOT render a badge when unreadCount is 0', () => {
      setContext({ unreadCount: 0 });
      render(<NotificationBell />);

      // Badge text is the count, so "0" or any number text should be absent
      // The badge span is conditionally rendered only when unreadCount > 0
      expect(screen.queryByText('0')).not.toBeInTheDocument();
    });

    it('shows "5" in the badge when unreadCount is 5', () => {
      setContext({ unreadCount: 5 });
      render(<NotificationBell />);

      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('shows "99+" when unreadCount is 100', () => {
      setContext({ unreadCount: 100 });
      render(<NotificationBell />);

      expect(screen.getByText('99+')).toBeInTheDocument();
    });

    it('shows "99" (not "99+") when unreadCount is exactly 99', () => {
      setContext({ unreadCount: 99 });
      render(<NotificationBell />);

      expect(screen.getByText('99')).toBeInTheDocument();
      expect(screen.queryByText('99+')).not.toBeInTheDocument();
    });
  });

  describe('open / close behavior', () => {
    it('aria-expanded is false initially', () => {
      render(<NotificationBell />);

      const button = screen.getByRole('button', { name: /Notificações/i });
      expect(button).toHaveAttribute('aria-expanded', 'false');
    });

    it('aria-expanded is true after clicking the button', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);

      const button = screen.getByRole('button', { name: /Notificações/i });
      await user.click(button);

      expect(button).toHaveAttribute('aria-expanded', 'true');
    });

    it('renders NotificationList (mock) after clicking the button', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);

      const button = screen.getByRole('button', { name: /Notificações/i });
      await user.click(button);

      expect(screen.getByTestId('notification-list')).toBeInTheDocument();
    });

    it('hides the panel after clicking the button a second time', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);

      const button = screen.getByRole('button', { name: /Notificações/i });
      await user.click(button);
      expect(screen.getByTestId('notification-list')).toBeInTheDocument();

      await user.click(button);
      expect(screen.queryByTestId('notification-list')).not.toBeInTheDocument();
    });

    it('closes the panel when clicking outside', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);

      const button = screen.getByRole('button', { name: /Notificações/i });
      await user.click(button);
      expect(screen.getByTestId('notification-list')).toBeInTheDocument();

      fireEvent.mouseDown(document.body);

      expect(screen.queryByTestId('notification-list')).not.toBeInTheDocument();
    });

    it('closes the panel when pressing Escape', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);

      const button = screen.getByRole('button', { name: /Notificações/i });
      await user.click(button);
      expect(screen.getByTestId('notification-list')).toBeInTheDocument();

      fireEvent.keyDown(document, { key: 'Escape' });

      expect(screen.queryByTestId('notification-list')).not.toBeInTheDocument();
    });
  });

  describe('connection status dot', () => {
    it('has bg-green-400 class when isConnected is true', () => {
      setContext({ isConnected: true });
      render(<NotificationBell />);

      const dot = screen.getByTitle('Conectado');
      expect(dot).toHaveClass('bg-green-400');
    });

    it('has bg-gray-400 class when isConnected is false', () => {
      setContext({ isConnected: false });
      render(<NotificationBell />);

      const dot = screen.getByTitle('Desconectado');
      expect(dot).toHaveClass('bg-gray-400');
    });
  });

  describe('dialog accessibility', () => {
    it('dialog has aria-modal="true" when open', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);

      await user.click(screen.getByRole('button', { name: /Notificações/i }));

      const dialog = screen.getByRole('dialog');
      expect(dialog).toHaveAttribute('aria-modal', 'true');
    });
  });
});
