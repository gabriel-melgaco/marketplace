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
  requirements_status: "currently_due" | "past_due" | null;
}

export interface SyncAccountStatusResponse {
  seller_verified: boolean;
  ready_to_receive_payments: boolean;
  details_submitted: boolean;
  onboarding_complete: boolean;
  pending_verification: boolean;
  updated: boolean;
}

export interface DisconnectAccountResponse {
  message: string;
  stripe_deleted: boolean;
  stripe_error: string | null;
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

  async syncAccountStatus() {
    const response = await api.post<SyncAccountStatusResponse>("/payments/connect/sync/");
    return response.data;
  },

  async disconnectAccount() {
    const response = await api.delete<DisconnectAccountResponse>("/payments/connect/disconnect/");
    return response.data;
  },
};
