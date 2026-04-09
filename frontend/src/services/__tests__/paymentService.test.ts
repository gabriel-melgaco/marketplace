import { describe, it, expect, vi, beforeEach } from 'vitest';
import { paymentService } from '@/services/paymentService';

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

// ── Fixtures ──────────────────────────────────────────────────────────────────

const PAYMENT = {
  id: 1,
  order: 'order-uuid',
  order_number: 'ORD-001',
  user: 10,
  user_email: 'buyer@test.com',
  stripe_payment_intent_id: 'pi_123',
  stripe_charge_id: 'ch_123',
  transfer_group: 'tg_1',
  amount: '199.90',
  currency: 'brl',
  status: 'succeeded',
  payment_method: 'credit_card',
  platform_fee_total: '5.00',
  description: 'Compra #1',
  failure_message: '',
  receipt_url: 'https://receipt.url',
  refund_amount: null,
  refund_reason: '',
  refunded_at: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:01:00Z',
  paid_at: '2024-01-01T00:00:30Z',
  splits: [],
};

const SPLIT = {
  id: 1,
  payment: 1,
  order_number: 'ORD-001',
  seller: 5,
  seller_email: 'seller@test.com',
  gross_amount: '199.90',
  product_amount: '190.00',
  shipping_amount: '9.90',
  platform_fee_amount: '5.00',
  net_amount: '194.90',
  shipping_status: 'released',
  stripe_transfer_id: 'tr_1',
  transfer_status: 'dispatched',
  error_message: '',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:01:00Z',
};

const BALANCE = {
  stripe_available: 10000,
  stripe_pending: 500,
  stripe_in_transit: 0,
  stripe_balance_error: false,
  pending_transfers: '0.00',
  dispatched_transfers: '194.90',
  failed_transfers: '0.00',
  splits_count: 1,
};

const REFUND = {
  id: 'rr-uuid',
  payment: 1,
  order: 'order-uuid',
  order_number: 'ORD-001',
  requested_by: 10,
  requested_by_email: 'buyer@test.com',
  status: 'requested',
  status_display: 'Solicitado',
  refund_type: 'remorse',
  refund_type_display: 'Arrependimento',
  amount_requested: '199.90',
  amount_approved: null,
  reason_buyer: 'Changed my mind',
  reason_seller: '',
  reason_platform: '',
  evidence_urls: [],
  seller_evidence_urls: [],
  seller_deadline: null,
  escalation_deadline: null,
  decided_by: null,
  decided_by_email: null,
  stripe_refund_id: '',
  metadata: {},
  created_at: '2024-01-02T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
  resolved_at: null,
  history: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('paymentService', () => {
  describe('listPayments()', () => {
    it('GETs /payments/ and returns the list', async () => {
      mockGet.mockResolvedValueOnce({ data: [PAYMENT] });
      const result = await paymentService.listPayments();
      expect(mockGet).toHaveBeenCalledWith('/payments/');
      expect(result).toEqual([PAYMENT]);
    });
  });

  describe('getPayment()', () => {
    it('GETs /payments/:id/ and returns the payment', async () => {
      mockGet.mockResolvedValueOnce({ data: PAYMENT });
      const result = await paymentService.getPayment(1);
      expect(mockGet).toHaveBeenCalledWith('/payments/1/');
      expect(result).toEqual(PAYMENT);
    });
  });

  describe('getPaymentStatus()', () => {
    it('GETs /payments/status/:intentId/ and returns payment', async () => {
      mockGet.mockResolvedValueOnce({ data: PAYMENT });
      const result = await paymentService.getPaymentStatus('pi_123');
      expect(mockGet).toHaveBeenCalledWith('/payments/status/pi_123/');
      expect(result).toEqual(PAYMENT);
    });
  });

  describe('getBalance()', () => {
    it('GETs /payments/balance/ and returns balance', async () => {
      mockGet.mockResolvedValueOnce({ data: BALANCE });
      const result = await paymentService.getBalance();
      expect(mockGet).toHaveBeenCalledWith('/payments/balance/');
      expect(result).toEqual(BALANCE);
    });
  });

  describe('listPayouts()', () => {
    it('GETs /payments/payouts/ and returns the list', async () => {
      mockGet.mockResolvedValueOnce({ data: [SPLIT] });
      const result = await paymentService.listPayouts();
      expect(mockGet).toHaveBeenCalledWith('/payments/payouts/');
      expect(result).toEqual([SPLIT]);
    });
  });

  describe('getPayout()', () => {
    it('GETs /payments/payouts/:id/ and returns the split', async () => {
      mockGet.mockResolvedValueOnce({ data: SPLIT });
      const result = await paymentService.getPayout(1);
      expect(mockGet).toHaveBeenCalledWith('/payments/payouts/1/');
      expect(result).toEqual(SPLIT);
    });
  });

  describe('createRefundRequest()', () => {
    it('POSTs to /payments/refund-requests/create/ and returns refund', async () => {
      mockPost.mockResolvedValueOnce({ data: REFUND });
      const body = {
        payment_id: 1,
        refund_type: 'remorse' as const,
        amount_requested: '199.90',
        reason_buyer: 'Changed my mind',
      };
      const result = await paymentService.createRefundRequest(body);
      expect(mockPost).toHaveBeenCalledWith('/payments/refund-requests/create/', body);
      expect(result).toEqual(REFUND);
    });
  });

  describe('listRefundRequests()', () => {
    it('GETs /payments/refund-requests/ and returns list', async () => {
      mockGet.mockResolvedValueOnce({ data: [REFUND] });
      const result = await paymentService.listRefundRequests();
      expect(mockGet).toHaveBeenCalledWith('/payments/refund-requests/');
      expect(result).toEqual([REFUND]);
    });
  });

  describe('getRefundRequest()', () => {
    it('GETs /payments/refund-requests/:id/', async () => {
      mockGet.mockResolvedValueOnce({ data: REFUND });
      const result = await paymentService.getRefundRequest('rr-uuid');
      expect(mockGet).toHaveBeenCalledWith('/payments/refund-requests/rr-uuid/');
      expect(result).toEqual(REFUND);
    });
  });

  describe('approveRefundRequest()', () => {
    it('POSTs to /payments/refund-requests/:id/approve/', async () => {
      const approved = { ...REFUND, status: 'approved' };
      mockPost.mockResolvedValueOnce({ data: approved });
      const result = await paymentService.approveRefundRequest('rr-uuid', { amount_approved: '199.90' });
      expect(mockPost).toHaveBeenCalledWith('/payments/refund-requests/rr-uuid/approve/', { amount_approved: '199.90' });
      expect(result.status).toBe('approved');
    });
  });

  describe('rejectRefundRequest()', () => {
    it('POSTs to /payments/refund-requests/:id/reject/', async () => {
      const rejected = { ...REFUND, status: 'rejected' };
      mockPost.mockResolvedValueOnce({ data: rejected });
      const result = await paymentService.rejectRefundRequest('rr-uuid', { reason: 'no reason' });
      expect(mockPost).toHaveBeenCalledWith('/payments/refund-requests/rr-uuid/reject/', { reason: 'no reason' });
      expect(result.status).toBe('rejected');
    });
  });

  describe('escalateRefundRequest()', () => {
    it('POSTs to /payments/refund-requests/:id/escalate/', async () => {
      const escalated = { ...REFUND, status: 'escalated' };
      mockPost.mockResolvedValueOnce({ data: escalated });
      const result = await paymentService.escalateRefundRequest('rr-uuid');
      expect(mockPost).toHaveBeenCalledWith('/payments/refund-requests/rr-uuid/escalate/');
      expect(result.status).toBe('escalated');
    });
  });

  describe('withdrawRefundRequest()', () => {
    it('POSTs to /payments/refund-requests/:id/withdraw/', async () => {
      const withdrawn = { ...REFUND, status: 'withdrawn' };
      mockPost.mockResolvedValueOnce({ data: withdrawn });
      const result = await paymentService.withdrawRefundRequest('rr-uuid');
      expect(mockPost).toHaveBeenCalledWith('/payments/refund-requests/rr-uuid/withdraw/');
      expect(result.status).toBe('withdrawn');
    });
  });

  describe('decidePlatformRefund()', () => {
    it('POSTs to /payments/refund-requests/:id/decide/ with approve=true', async () => {
      const decided = { ...REFUND, status: 'platform_approved' };
      mockPost.mockResolvedValueOnce({ data: decided });
      const result = await paymentService.decidePlatformRefund('rr-uuid', { approve: true, reason: 'valid claim' });
      expect(mockPost).toHaveBeenCalledWith('/payments/refund-requests/rr-uuid/decide/', {
        approve: true,
        reason: 'valid claim',
      });
      expect(result.status).toBe('platform_approved');
    });

    it('POSTs with approve=false for platform rejection', async () => {
      const decided = { ...REFUND, status: 'platform_rejected' };
      mockPost.mockResolvedValueOnce({ data: decided });
      const result = await paymentService.decidePlatformRefund('rr-uuid', { approve: false, reason: 'invalid' });
      expect(mockPost).toHaveBeenCalledWith('/payments/refund-requests/rr-uuid/decide/', {
        approve: false,
        reason: 'invalid',
      });
      expect(result.status).toBe('platform_rejected');
    });
  });

  describe('error propagation', () => {
    it('listPayments() propagates API errors', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network error'));
      await expect(paymentService.listPayments()).rejects.toThrow('Network error');
    });

    it('createRefundRequest() propagates API errors', async () => {
      mockPost.mockRejectedValueOnce(new Error('403 Forbidden'));
      await expect(
        paymentService.createRefundRequest({
          payment_id: 1,
          refund_type: 'remorse',
          amount_requested: '100',
          reason_buyer: 'x',
        })
      ).rejects.toThrow('403 Forbidden');
    });
  });
});

// ── Novos describes complementares ───────────────────────────────────────────

describe('createPaymentIntent()', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('faz POST para /payments/create-intent/ com order_id e payment_method', async () => {
    const intentResponse = {
      payment_id: 42,
      client_secret: 'pi_abc_secret_xyz',
      amount: 19990,
      currency: 'brl',
      payment_method: 'credit_card',
    };
    mockPost.mockResolvedValueOnce({ data: intentResponse });
    await paymentService.createPaymentIntent({
      order_id: '101',
      payment_method: 'credit_card',
    });
    expect(mockPost).toHaveBeenCalledWith('/payments/create-intent/', {
      order_id: '101',
      payment_method: 'credit_card',
    });
  });

  it('inclui save_payment_method=true quando informado', async () => {
    mockPost.mockResolvedValueOnce({
      data: { payment_id: 1, client_secret: 'pi_x_secret_y', amount: 100, currency: 'brl', payment_method: 'credit_card' },
    });
    await paymentService.createPaymentIntent({
      order_id: '101',
      payment_method: 'credit_card',
      save_payment_method: true,
    });
    expect(mockPost).toHaveBeenCalledWith(
      '/payments/create-intent/',
      expect.objectContaining({ save_payment_method: true }),
    );
  });

  it('retorna objeto com client_secret', async () => {
    const intentResponse = {
      payment_id: 42,
      client_secret: 'pi_abc_secret_xyz',
      amount: 19990,
      currency: 'brl',
      payment_method: 'credit_card',
    };
    mockPost.mockResolvedValueOnce({ data: intentResponse });
    const result = await paymentService.createPaymentIntent({
      order_id: '101',
      payment_method: 'credit_card',
    });
    expect(result.client_secret).toBe('pi_abc_secret_xyz');
  });

  it('propaga erro da API', async () => {
    mockPost.mockRejectedValueOnce(new Error('Pagamento rejeitado'));
    await expect(
      paymentService.createPaymentIntent({ order_id: '101', payment_method: 'credit_card' }),
    ).rejects.toThrow('Pagamento rejeitado');
  });
});

describe('createIntentsBatch()', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('faz POST para /payments/create-intents-batch/ com array order_ids e payment_method', async () => {
    mockPost.mockResolvedValueOnce({ data: [] });
    await paymentService.createIntentsBatch(['101', '102'], 'credit_card');
    expect(mockPost).toHaveBeenCalledWith('/payments/create-intents-batch/', {
      order_ids: ['101', '102'],
      payment_method: 'credit_card',
    });
  });

  it('retorna array de respostas', async () => {
    const batchResponse = [
      { payment_id: 1, client_secret: 'pi_a_secret_b', amount: 100, currency: 'brl', payment_method: 'credit_card' },
      { payment_id: 2, client_secret: 'pi_c_secret_d', amount: 200, currency: 'brl', payment_method: 'credit_card' },
    ];
    mockPost.mockResolvedValueOnce({ data: batchResponse });
    const result = await paymentService.createIntentsBatch(['101', '102'], 'credit_card');
    expect(result).toHaveLength(2);
    expect(result[0].client_secret).toBe('pi_a_secret_b');
  });

  it('propaga erro da API', async () => {
    mockPost.mockRejectedValueOnce(new Error('Erro em lote'));
    await expect(
      paymentService.createIntentsBatch(['101'], 'credit_card'),
    ).rejects.toThrow('Erro em lote');
  });
});

describe('listScheduledPayouts()', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('faz GET para /payments/payouts/scheduled/', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    await paymentService.listScheduledPayouts();
    expect(mockGet).toHaveBeenCalledWith('/payments/payouts/scheduled/');
  });
});

describe('confirmPayment — método removido (deprecated)', () => {
  it('confirmPayment NÃO existe em paymentService', () => {
    expect((paymentService as Record<string, unknown>)['confirmPayment']).toBeUndefined();
  });
});

describe('getBalance() — campos de resposta', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('faz GET para /payments/balance/', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        stripe_available: 5000,
        stripe_pending: 200,
        stripe_in_transit: 0,
        stripe_balance_error: false,
        pending_transfers: '0.00',
        dispatched_transfers: '100.00',
        failed_transfers: '0.00',
        splits_count: 2,
      },
    });
    await paymentService.getBalance();
    expect(mockGet).toHaveBeenCalledWith('/payments/balance/');
  });

  it('retorna resposta com campos stripe_available, stripe_pending, stripe_balance_error', async () => {
    const balanceData = {
      stripe_available: 5000,
      stripe_pending: 200,
      stripe_in_transit: 0,
      stripe_balance_error: false,
      pending_transfers: '0.00',
      dispatched_transfers: '100.00',
      failed_transfers: '0.00',
      splits_count: 2,
    };
    mockGet.mockResolvedValueOnce({ data: balanceData });
    const result = await paymentService.getBalance();
    expect(result).toHaveProperty('stripe_available');
    expect(result).toHaveProperty('stripe_pending');
    expect(result).toHaveProperty('stripe_balance_error');
  });
});
