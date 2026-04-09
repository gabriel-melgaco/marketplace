import { describe, it, expect, vi, beforeEach } from 'vitest';
import { stripeConnectService } from '@/services/stripeConnectService';

// ── Mock axios ───────────────────────────────────────────────────────────────

const { mockGet, mockPost, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock('@/api/axios', () => ({
  default: {
    get: mockGet,
    post: mockPost,
    delete: mockDelete,
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('stripeConnectService', () => {
  describe('createConnectedAccount()', () => {
    it('POSTs to /payments/connect/create/ and returns response', async () => {
      const payload = { account_id: 'acct_123', message: 'Account created' };
      mockPost.mockResolvedValueOnce({ data: payload });
      const result = await stripeConnectService.createConnectedAccount();
      expect(mockPost).toHaveBeenCalledWith('/payments/connect/create/');
      expect(result).toEqual(payload);
    });

    it('propagates errors', async () => {
      mockPost.mockRejectedValueOnce(new Error('Already exists'));
      await expect(stripeConnectService.createConnectedAccount()).rejects.toThrow('Already exists');
    });
  });

  describe('getOnboardingLink()', () => {
    it('POSTs to /payments/connect/onboarding-link/ and returns url + expires_at', async () => {
      const payload = { url: 'https://connect.stripe.com/onboard/xyz', expires_at: 1700000000 };
      mockPost.mockResolvedValueOnce({ data: payload });
      const result = await stripeConnectService.getOnboardingLink();
      expect(mockPost).toHaveBeenCalledWith('/payments/connect/onboarding-link/');
      expect(result).toEqual(payload);
    });
  });

  describe('getAccountStatus()', () => {
    it('GETs /payments/connect/status/ and returns status', async () => {
      const payload = {
        has_account: true,
        ready_to_receive_payments: false,
        onboarding_complete: false,
        requirements_status: 'currently_due',
      };
      mockGet.mockResolvedValueOnce({ data: payload });
      const result = await stripeConnectService.getAccountStatus();
      expect(mockGet).toHaveBeenCalledWith('/payments/connect/status/');
      expect(result).toEqual(payload);
    });

    it('returns requirements_status=null when not due', async () => {
      const payload = {
        has_account: true,
        ready_to_receive_payments: true,
        onboarding_complete: true,
        requirements_status: null,
      };
      mockGet.mockResolvedValueOnce({ data: payload });
      const result = await stripeConnectService.getAccountStatus();
      expect(result.requirements_status).toBeNull();
    });
  });

  describe('syncAccountStatus()', () => {
    it('POSTs to /payments/connect/sync/ and returns sync result', async () => {
      const payload = {
        seller_verified: true,
        ready_to_receive_payments: true,
        details_submitted: true,
        onboarding_complete: true,
        pending_verification: false,
        updated: true,
      };
      mockPost.mockResolvedValueOnce({ data: payload });
      const result = await stripeConnectService.syncAccountStatus();
      expect(mockPost).toHaveBeenCalledWith('/payments/connect/sync/');
      expect(result).toEqual(payload);
    });

    it('returns updated=false when nothing changed', async () => {
      const payload = {
        seller_verified: true,
        ready_to_receive_payments: true,
        details_submitted: true,
        onboarding_complete: true,
        pending_verification: false,
        updated: false,
      };
      mockPost.mockResolvedValueOnce({ data: payload });
      const result = await stripeConnectService.syncAccountStatus();
      expect(result.updated).toBe(false);
    });
  });

  describe('disconnectAccount()', () => {
    it('DELETEs /payments/connect/disconnect/ and returns message', async () => {
      const payload = { message: 'Account disconnected', stripe_deleted: true, stripe_error: null };
      mockDelete.mockResolvedValueOnce({ data: payload });
      const result = await stripeConnectService.disconnectAccount();
      expect(mockDelete).toHaveBeenCalledWith('/payments/connect/disconnect/');
      expect(result).toEqual(payload);
    });

    it('includes stripe_error when Stripe deletion fails gracefully', async () => {
      const payload = {
        message: 'Account disconnected locally',
        stripe_deleted: false,
        stripe_error: 'No such account',
      };
      mockDelete.mockResolvedValueOnce({ data: payload });
      const result = await stripeConnectService.disconnectAccount();
      expect(result.stripe_deleted).toBe(false);
      expect(result.stripe_error).toBe('No such account');
    });

    it('propagates errors', async () => {
      mockDelete.mockRejectedValueOnce(new Error('Not found'));
      await expect(stripeConnectService.disconnectAccount()).rejects.toThrow('Not found');
    });
  });
});
