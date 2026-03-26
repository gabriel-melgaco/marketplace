import api from "@/api/axios";

// ─── Payment ─────────────────────────────────────────────────────────────────

export type PaymentStatus =
  | "pending"
  | "processing"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "refunded";

export type PaymentMethodType =
  | "credit_card"
  | "debit_card"
  | "pix"
  | "boleto";

export interface Payment {
  id: number;
  order: string;               // UUID do pedido
  order_number: string;
  user: number;
  user_email: string;

  stripe_payment_intent_id: string;
  stripe_charge_id: string;
  transfer_group: string;

  amount: string;
  currency: string;
  status: PaymentStatus;
  payment_method: PaymentMethodType;

  platform_fee_total: string | null;
  description: string;
  failure_message: string;
  receipt_url: string;

  refund_amount: string | null;
  refund_reason: string;
  refunded_at: string | null;

  created_at: string;
  updated_at: string;
  paid_at: string | null;

  splits: PaymentSplit[];
}

// ─── Payment Split (repasse por vendedor) ────────────────────────────────────

export type TransferStatus = "pending" | "dispatched" | "failed";
export type ShippingStatus = "held" | "released" | "refunded";

export interface PaymentSplit {
  id: number;
  payment: number;
  order_number: string;
  seller: number;
  seller_email: string;

  gross_amount: string;
  product_amount: string;
  shipping_amount: string;
  platform_fee_amount: string;
  net_amount: string;

  shipping_status: ShippingStatus;
  stripe_transfer_id: string;
  transfer_status: TransferStatus;
  error_message: string;

  created_at: string;
  updated_at: string;
}

// ─── Seller Balance ───────────────────────────────────────────────────────────

export interface SellerBalanceResponse {
  stripe_available: number | null;
  stripe_pending: number | null;
  stripe_in_transit: number | null;
  stripe_balance_error: boolean;
  pending_transfers: string;
  dispatched_transfers: string;
  failed_transfers: string;
  splits_count: number;
}

// ─── Refund Requests ─────────────────────────────────────────────────────────

export type RefundRequestStatus =
  | "requested"
  | "seller_reviewing"
  | "auto_approved"
  | "approved"
  | "rejected"
  | "escalated"
  | "platform_approved"
  | "platform_rejected"
  | "stripe_refund_pending"
  | "refunded"
  | "withdrawn"
  | "closed";

export type RefundType =
  | "remorse"
  | "defective"
  | "not_received"
  | "duplicate_charge"
  | "platform_decision";

export type ActorType = "buyer" | "seller" | "system" | "platform";

export interface RefundRequestHistory {
  id: number;
  refund_request: string;
  from_status: string;
  to_status: string;
  changed_by: number | null;
  changed_by_email: string | null;
  actor_type: ActorType;
  notes: string;
  created_at: string;
}

export interface RefundRequest {
  id: string;
  payment: number;
  order: string;
  order_number: string;

  requested_by: number;
  requested_by_email: string;

  status: RefundRequestStatus;
  status_display: string;
  refund_type: RefundType;
  refund_type_display: string;

  amount_requested: string;
  amount_approved: string | null;

  reason_buyer: string;
  reason_seller: string;
  reason_platform: string;

  evidence_urls: string[];
  seller_evidence_urls: string[];

  seller_deadline: string | null;
  escalation_deadline: string | null;

  decided_by: number | null;
  decided_by_email: string | null;

  stripe_refund_id: string;
  metadata: Record<string, unknown>;

  created_at: string;
  updated_at: string;
  resolved_at: string | null;

  history: RefundRequestHistory[];
}

export interface CreateRefundRequestBody {
  payment_id: number;
  refund_type: RefundType;
  amount_requested: string;
  reason_buyer: string;
  evidence_urls?: string[];
}

export interface ApproveRefundRequestBody {
  amount_approved: string;
}

export interface RejectRefundRequestBody {
  reason: string;
  evidence_urls?: string[];
}

export interface PlatformDecideBody {
  approve: boolean;
  reason: string;
}

// ─── Payment Intent ───────────────────────────────────────────────────────────

export interface CreatePaymentIntentRequest {
  order_id: string;
  payment_method: PaymentMethodType;
  save_payment_method?: boolean;
}

export interface CreatePaymentIntentResponse {
  payment_id: number;
  client_secret: string;
  amount: number;
  currency: string;
  payment_method: string;
  reused?: boolean;
}

// ─── Scheduled Payout ─────────────────────────────────────────────────────────

export interface ScheduledPayout {
  id: number;
  payment: number;
  order_number: string;
  seller: number;
  seller_email: string;
  gross_amount: string;
  product_amount: string;
  shipping_amount: string;
  platform_fee_amount: string;
  net_amount: string;
  shipping_status: ShippingStatus;
  stripe_transfer_id: string;
  transfer_status: TransferStatus;
  error_message: string;
  scheduled_date?: string;
  created_at: string;
  updated_at: string;
}

// ─── Service ─────────────────────────────────────────────────────────────────

export const paymentService = {
  // ── Payments ──────────────────────────────────────────────────────────────

  async listPayments() {
    const response = await api.get<Payment[]>("/payments/");
    return response.data;
  },

  async getPayment(id: number) {
    const response = await api.get<Payment>(`/payments/${id}/`);
    return response.data;
  },

  async getPaymentStatus(paymentIntentId: string) {
    const response = await api.get<Payment>(`/payments/status/${paymentIntentId}/`);
    return response.data;
  },

  async createPaymentIntent(data: CreatePaymentIntentRequest) {
    const response = await api.post<CreatePaymentIntentResponse>("/payments/create-intent/", data);
    return response.data;
  },

  // ── Balance & Payouts ─────────────────────────────────────────────────────

  async getBalance() {
    const response = await api.get<SellerBalanceResponse>("/payments/balance/");
    return response.data;
  },

  async listPayouts() {
    const response = await api.get<PaymentSplit[]>("/payments/payouts/");
    return response.data;
  },

  async listScheduledPayouts() {
    const response = await api.get<ScheduledPayout[]>("/payments/payouts/scheduled/");
    return response.data;
  },

  async getPayout(id: number) {
    const response = await api.get<PaymentSplit>(`/payments/payouts/${id}/`);
    return response.data;
  },

  // ── Refund Requests ───────────────────────────────────────────────────────

  async createRefundRequest(data: CreateRefundRequestBody) {
    const response = await api.post<RefundRequest>("/payments/refund-requests/create/", data);
    return response.data;
  },

  async listRefundRequests() {
    const response = await api.get<RefundRequest[]>("/payments/refund-requests/");
    return response.data;
  },

  async getRefundRequest(id: string) {
    const response = await api.get<RefundRequest>(`/payments/refund-requests/${id}/`);
    return response.data;
  },

  async approveRefundRequest(id: string, data: ApproveRefundRequestBody) {
    const response = await api.post<RefundRequest>(`/payments/refund-requests/${id}/approve/`, data);
    return response.data;
  },

  async rejectRefundRequest(id: string, data: RejectRefundRequestBody) {
    const response = await api.post<RefundRequest>(`/payments/refund-requests/${id}/reject/`, data);
    return response.data;
  },

  async escalateRefundRequest(id: string) {
    const response = await api.post<RefundRequest>(`/payments/refund-requests/${id}/escalate/`);
    return response.data;
  },

  async withdrawRefundRequest(id: string) {
    const response = await api.post<RefundRequest>(`/payments/refund-requests/${id}/withdraw/`);
    return response.data;
  },

  async decidePlatformRefund(id: string, data: PlatformDecideBody) {
    const response = await api.post<RefundRequest>(`/payments/refund-requests/${id}/decide/`, data);
    return response.data;
  },
};
