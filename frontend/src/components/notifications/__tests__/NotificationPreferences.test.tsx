import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NotificationPreferences } from '../NotificationPreferences';
import type { NotificationPreference } from '@/types/notifications';
import { NOTIFICATION_TYPE_GROUPS } from '@/utils/notificationUtils';

// ─── Mock useNotificationPreferences ─────────────────────────────────────────

const mockHookValue = {
  preferences: null as NotificationPreference | null,
  isLoading: false,
  isSaving: false,
  error: null as string | null,
  updatePreferences: vi.fn(),
  togglePreference: vi.fn(),
};

vi.mock('@/hooks/useNotificationPreferences', () => ({
  useNotificationPreferences: () => mockHookValue,
}));

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const makePreferences = (overrides: Partial<NotificationPreference> = {}): NotificationPreference => ({
  order_created_ws: true,
  order_created_email: true,
  order_status_changed_ws: true,
  order_status_changed_email: true,
  payment_confirmed_ws: true,
  payment_confirmed_email: true,
  payment_failed_ws: true,
  payment_failed_email: false,
  dispute_opened_ws: true,
  dispute_opened_email: true,
  shipment_created_ws: true,
  shipment_created_email: true,
  shipment_status_updated_ws: true,
  shipment_status_updated_email: true,
  delivery_scheduled_ws: true,
  delivery_scheduled_email: true,
  delivery_confirmed_ws: true,
  delivery_confirmed_email: true,
  new_message_ws: true,
  new_message_email: true,
  seller_verified_ws: true,
  seller_verified_email: true,
  listing_blocked_ws: true,
  listing_blocked_email: true,
  listing_created_ws: true,
  listing_created_email: true,
  ...overrides,
});

function setHook(overrides: Partial<typeof mockHookValue>) {
  Object.assign(mockHookValue, { ...mockHookValue, ...overrides });
}

function resetHook() {
  Object.assign(mockHookValue, {
    preferences: null,
    isLoading: false,
    isSaving: false,
    error: null,
    updatePreferences: vi.fn(),
    togglePreference: vi.fn(),
  });
}

beforeEach(() => {
  resetHook();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('NotificationPreferences', () => {
  describe('loading state', () => {
    it('shows a spinner when isLoading is true', () => {
      setHook({ isLoading: true, preferences: null });
      render(<NotificationPreferences />);

      const spinner = document.querySelector('.animate-spin');
      expect(spinner).toBeInTheDocument();
    });

    it('does NOT show the preference groups while loading', () => {
      setHook({ isLoading: true, preferences: null });
      render(<NotificationPreferences />);

      expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    });
  });

  describe('error fallback', () => {
    it('shows error message when preferences is null and error is set', () => {
      setHook({
        preferences: null,
        error: 'Não foi possível carregar as preferências.',
        isLoading: false,
      });
      render(<NotificationPreferences />);

      expect(
        screen.getByText('Não foi possível carregar as preferências.')
      ).toBeInTheDocument();
    });

    it('shows default fallback when preferences is null and error is null', () => {
      setHook({ preferences: null, error: null, isLoading: false });
      render(<NotificationPreferences />);

      // When preferences=null and no error, the component shows the fallback text
      expect(
        screen.getByText('Não foi possível carregar as preferências.')
      ).toBeInTheDocument();
    });
  });

  describe('preferences UI', () => {
    it('renders 5 group headings', () => {
      setHook({ preferences: makePreferences(), isLoading: false });
      render(<NotificationPreferences />);

      const expectedGroups = NOTIFICATION_TYPE_GROUPS.map((g) => g.groupLabel);
      expectedGroups.forEach((label) => {
        expect(screen.getByText(label)).toBeInTheDocument();
      });

      // Confirm exactly 5 groups rendered
      const headings = screen.getAllByRole('heading', { level: 3 });
      expect(headings).toHaveLength(5);
    });

    it('renders 26 role="switch" buttons (13 types × 2: ws + email)', () => {
      setHook({ preferences: makePreferences(), isLoading: false });
      render(<NotificationPreferences />);

      const switches = screen.getAllByRole('switch');
      expect(switches).toHaveLength(26);
    });

    it('renders aria-checked="true" for an enabled preference', () => {
      setHook({
        preferences: makePreferences({ order_created_ws: true }),
        isLoading: false,
      });
      render(<NotificationPreferences />);

      const wsSwitch = screen.getByRole('switch', {
        name: /Receber "Pedido Criado" em tempo real/i,
      });
      expect(wsSwitch).toHaveAttribute('aria-checked', 'true');
    });

    it('renders aria-checked="false" for a disabled preference', () => {
      setHook({
        preferences: makePreferences({ payment_failed_email: false }),
        isLoading: false,
      });
      render(<NotificationPreferences />);

      const emailSwitch = screen.getByRole('switch', {
        name: /Receber "Falha no Pagamento" por email/i,
      });
      expect(emailSwitch).toHaveAttribute('aria-checked', 'false');
    });

    it('clicking a toggle calls togglePreference with the correct key', async () => {
      const togglePreference = vi.fn().mockResolvedValue(undefined);
      setHook({
        preferences: makePreferences({ order_created_ws: true }),
        isLoading: false,
        togglePreference,
      });
      const user = userEvent.setup();
      render(<NotificationPreferences />);

      const wsSwitch = screen.getByRole('switch', {
        name: /Receber "Pedido Criado" em tempo real/i,
      });
      await user.click(wsSwitch);

      expect(togglePreference).toHaveBeenCalledWith('order_created_ws');
    });

    it('all toggles are disabled when isSaving is true', () => {
      setHook({
        preferences: makePreferences(),
        isLoading: false,
        isSaving: true,
      });
      render(<NotificationPreferences />);

      const switches = screen.getAllByRole('switch');
      switches.forEach((sw) => {
        expect(sw).toBeDisabled();
      });
    });

    it('shows saving banner when isSaving is true', () => {
      setHook({
        preferences: makePreferences(),
        isLoading: false,
        isSaving: true,
      });
      render(<NotificationPreferences />);

      expect(screen.getByText(/Salvando preferências.../i)).toBeInTheDocument();
    });

    it('shows error banner when error is set AND preferences are loaded', () => {
      setHook({
        preferences: makePreferences(),
        isLoading: false,
        error: 'Não foi possível salvar as preferências.',
      });
      render(<NotificationPreferences />);

      expect(
        screen.getByText('Não foi possível salvar as preferências.')
      ).toBeInTheDocument();
    });

    it('does NOT show saving banner when isSaving is false', () => {
      setHook({
        preferences: makePreferences(),
        isLoading: false,
        isSaving: false,
      });
      render(<NotificationPreferences />);

      expect(screen.queryByText(/Salvando preferências/i)).not.toBeInTheDocument();
    });
  });
});
