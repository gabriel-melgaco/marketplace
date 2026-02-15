import api from "@/api/axios";

export interface CreateConnectedAccountResponse {
  account_id: string;
  message: string;
}

export interface OnboardingLinkResponse {
  url: string;
  expires_at: number;
}

export interface AccountStatusResponse {
  has_account: boolean;
  ready_to_receive_payments: boolean;
  onboarding_complete: boolean;
  requirements_status?: string;
}

export interface CreateCheckoutRequest {
  order_id: string;
}

export interface CreateCheckoutResponse {
  checkout_url: string;
  session_id: string;
  platform_fee: number;
}

export const stripeConnectService = {
  async createConnectedAccount() {
    const response = await api.post<CreateConnectedAccountResponse>("/payments/connect/create/");
    return response.data;
  },

  async getOnboardingLink() {
    const response = await api.post<OnboardingLinkResponse>("/payments/connect/onboarding-link/");
    return response.data;
  },

  async getAccountStatus() {
    const response = await api.get<AccountStatusResponse>("/payments/connect/status/");
    return response.data;
  },

  async createCheckoutWithConnect(data: CreateCheckoutRequest) {
    const response = await api.post<CreateCheckoutResponse>("/payments/connect/checkout/", data);
    return response.data;
  },
};
