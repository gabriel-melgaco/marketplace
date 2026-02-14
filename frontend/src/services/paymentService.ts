import api from "@/api/axios";

export interface Payment {
  id: number;
  order: string;
  amount: string;
  status: string;
  payment_method: string;
  stripe_payment_intent_id?: string;
  created_at: string;
  updated_at: string;
}

export interface PaymentIntentCreateRequest {
  order_id: string;
}

export interface PaymentConfirmRequest {
  payment_intent_id: string;
}

export interface RefundRequest {
  payment_id: number;
  amount?: number;
  reason?: string;
}

export interface SellerPayout {
  id: number;
  seller: number;
  amount: string;
  status: string;
  stripe_payout_id?: string;
  created_at: string;
  updated_at: string;
}

export interface BalanceResponse {
  pending: number;
  processing: number;
  completed: number;
  total_available: number;
}

export const paymentService = {
  async listPayments() {
    const response = await api.get<Payment[]>("/payments/");
    return response.data;
  },

  async getPayment(id: number) {
    const response = await api.get<Payment>(`/payments/${id}/`);
    return response.data;
  },

  async createPaymentIntent(data: PaymentIntentCreateRequest) {
    const response = await api.post<Payment>("/payments/create-intent/", data);
    return response.data;
  },

  async getPaymentStatus(paymentIntentId: string) {
    const response = await api.get<Payment>(`/payments/status/${paymentIntentId}/`);
    return response.data;
  },

  async confirmPayment(data: PaymentConfirmRequest) {
    const response = await api.post<Payment>("/payments/confirm/", data);
    return response.data;
  },

  async requestRefund(data: RefundRequest) {
    const response = await api.post<Payment>("/payments/refund/", data);
    return response.data;
  },

  async getBalance() {
    const response = await api.get<BalanceResponse>("/payments/balance/");
    return response.data;
  },

  async listPayouts() {
    const response = await api.get<SellerPayout[]>("/payments/payouts/");
    return response.data;
  },

  async getPayout(id: number) {
    const response = await api.get<SellerPayout>(`/payments/payouts/${id}/`);
    return response.data;
  },
};
