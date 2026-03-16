import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useNotificationPreferences } from '../useNotificationPreferences';
import type { NotificationPreference } from '@/types/notifications';

// ─── Mock notificationsApi ────────────────────────────────────────────────────

vi.mock('@/services/notificationsApi', () => ({
  notificationsApi: {
    getPreferences: vi.fn(),
    updatePreferences: vi.fn(),
  },
}));

import { notificationsApi } from '@/services/notificationsApi';

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const makePreferences = (overrides: Partial<NotificationPreference> = {}): NotificationPreference => ({
  order_created_ws: true,
  order_created_email: true,
  order_status_changed_ws: true,
  order_status_changed_email: true,
  payment_confirmed_ws: true,
  payment_confirmed_email: true,
  payment_failed_ws: true,
  payment_failed_email: true,
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

const DEFAULT_PREFS = makePreferences();

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(notificationsApi.getPreferences).mockResolvedValue(DEFAULT_PREFS);
  vi.mocked(notificationsApi.updatePreferences).mockImplementation(async (partial) => ({
    ...DEFAULT_PREFS,
    ...partial,
  }));
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useNotificationPreferences', () => {
  it('calls getPreferences() on mount', async () => {
    renderHook(() => useNotificationPreferences());

    await waitFor(() => {
      expect(notificationsApi.getPreferences).toHaveBeenCalledOnce();
    });
  });

  it('isLoading is true during fetch, false after', async () => {
    let resolvePrefs!: (v: NotificationPreference) => void;
    vi.mocked(notificationsApi.getPreferences).mockReturnValueOnce(
      new Promise((res) => { resolvePrefs = res; })
    );

    const { result } = renderHook(() => useNotificationPreferences());

    expect(result.current.isLoading).toBe(true);

    act(() => resolvePrefs(DEFAULT_PREFS));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  it('sets error when getPreferences() rejects', async () => {
    vi.mocked(notificationsApi.getPreferences).mockRejectedValueOnce(new Error('Network Error'));

    const { result } = renderHook(() => useNotificationPreferences());

    await waitFor(() => {
      expect(result.current.error).toBe('Não foi possível carregar as preferências.');
    });
  });

  it('stores fetched preferences in state', async () => {
    const { result } = renderHook(() => useNotificationPreferences());

    await waitFor(() => expect(result.current.preferences).not.toBeNull());
    expect(result.current.preferences).toEqual(DEFAULT_PREFS);
  });

  describe('updatePreferences', () => {
    it('applies optimistic update before PATCH resolves', async () => {
      let resolvePatch!: (v: NotificationPreference) => void;
      vi.mocked(notificationsApi.updatePreferences).mockReturnValueOnce(
        new Promise((res) => { resolvePatch = res; })
      );

      const { result } = renderHook(() => useNotificationPreferences());
      await waitFor(() => expect(result.current.preferences).not.toBeNull());

      act(() => {
        result.current.updatePreferences({ order_created_ws: false });
      });

      // Optimistic: should be false immediately
      expect(result.current.preferences?.order_created_ws).toBe(false);

      // Cleanup
      act(() => resolvePatch({ ...DEFAULT_PREFS, order_created_ws: false }));
      await waitFor(() => expect(result.current.isSaving).toBe(false));
    });

    it('commits the server response after successful PATCH', async () => {
      const serverResponse = makePreferences({ order_created_ws: false, order_created_email: false });
      vi.mocked(notificationsApi.updatePreferences).mockResolvedValueOnce(serverResponse);

      const { result } = renderHook(() => useNotificationPreferences());
      await waitFor(() => expect(result.current.preferences).not.toBeNull());

      await act(async () => {
        await result.current.updatePreferences({ order_created_ws: false, order_created_email: false });
      });

      expect(result.current.preferences).toEqual(serverResponse);
    });

    it('rolls back to previous state on error', async () => {
      vi.mocked(notificationsApi.updatePreferences).mockRejectedValueOnce(new Error('Save failed'));

      const { result } = renderHook(() => useNotificationPreferences());
      await waitFor(() => expect(result.current.preferences).not.toBeNull());

      const originalPrefs = result.current.preferences;

      let caughtError: unknown;
      await act(async () => {
        try {
          await result.current.updatePreferences({ order_created_ws: false });
        } catch (err) {
          caughtError = err;
        }
      });

      expect(caughtError).toBeDefined();
      expect(result.current.preferences).toEqual(originalPrefs);
    });

    it('sets error message on failure', async () => {
      vi.mocked(notificationsApi.updatePreferences).mockRejectedValueOnce(new Error('Save failed'));

      const { result } = renderHook(() => useNotificationPreferences());
      await waitFor(() => expect(result.current.preferences).not.toBeNull());

      await act(async () => {
        try {
          await result.current.updatePreferences({ order_created_ws: false });
        } catch {
          // expected
        }
      });

      expect(result.current.error).toBe('Não foi possível salvar as preferências.');
    });

    it('re-throws the error to the caller', async () => {
      const apiError = new Error('Conflict');
      vi.mocked(notificationsApi.updatePreferences).mockRejectedValueOnce(apiError);

      const { result } = renderHook(() => useNotificationPreferences());
      await waitFor(() => expect(result.current.preferences).not.toBeNull());

      await expect(
        act(async () => {
          await result.current.updatePreferences({ order_created_ws: false });
        })
      ).rejects.toThrow('Conflict');
    });

    it('is a no-op when preferences is null', async () => {
      vi.mocked(notificationsApi.getPreferences).mockRejectedValueOnce(new Error('Fetch failed'));

      const { result } = renderHook(() => useNotificationPreferences());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      expect(result.current.preferences).toBeNull();

      // Should not throw and should not call updatePreferences
      await act(async () => {
        await result.current.updatePreferences({ order_created_ws: false });
      });

      expect(notificationsApi.updatePreferences).not.toHaveBeenCalled();
    });
  });

  describe('togglePreference', () => {
    it('inverts a true value to false', async () => {
      const prefs = makePreferences({ new_message_ws: true });
      vi.mocked(notificationsApi.getPreferences).mockResolvedValueOnce(prefs);

      const serverResponse = makePreferences({ new_message_ws: false });
      vi.mocked(notificationsApi.updatePreferences).mockResolvedValueOnce(serverResponse);

      const { result } = renderHook(() => useNotificationPreferences());
      await waitFor(() => expect(result.current.preferences?.new_message_ws).toBe(true));

      await act(async () => {
        await result.current.togglePreference('new_message_ws');
      });

      expect(notificationsApi.updatePreferences).toHaveBeenCalledWith({ new_message_ws: false });
    });

    it('inverts a false value to true', async () => {
      const prefs = makePreferences({ new_message_email: false });
      vi.mocked(notificationsApi.getPreferences).mockResolvedValueOnce(prefs);

      const serverResponse = makePreferences({ new_message_email: true });
      vi.mocked(notificationsApi.updatePreferences).mockResolvedValueOnce(serverResponse);

      const { result } = renderHook(() => useNotificationPreferences());
      await waitFor(() => expect(result.current.preferences?.new_message_email).toBe(false));

      await act(async () => {
        await result.current.togglePreference('new_message_email');
      });

      expect(notificationsApi.updatePreferences).toHaveBeenCalledWith({ new_message_email: true });
    });
  });

  describe('isSaving', () => {
    it('is true while the PATCH is in flight, false after', async () => {
      let resolvePatch!: (v: NotificationPreference) => void;
      vi.mocked(notificationsApi.updatePreferences).mockReturnValueOnce(
        new Promise((res) => { resolvePatch = res; })
      );

      const { result } = renderHook(() => useNotificationPreferences());
      await waitFor(() => expect(result.current.preferences).not.toBeNull());

      act(() => {
        result.current.updatePreferences({ order_created_ws: false });
      });

      expect(result.current.isSaving).toBe(true);

      act(() => resolvePatch({ ...DEFAULT_PREFS, order_created_ws: false }));

      await waitFor(() => expect(result.current.isSaving).toBe(false));
    });
  });
});
