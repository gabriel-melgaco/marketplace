import api from "@/api/axios";

export interface SellerMEStatusResponse {
  connected: boolean;
  environment: string;
  me_email: string | null;
  access_token: string | null;
  is_expired: boolean | null;
  expires_at: string | null;
  expires_in_seconds: number | null;
  is_refresh_token_expired: boolean | null;
  last_refreshed_at: string | null;
  message?: string;
}

export interface SellerMEConnectResponse {
  authorization_url: string;
}

export const logisticsService = {
  async getMelhorEnvioStatus(): Promise<SellerMEStatusResponse> {
    const response = await api.get<SellerMEStatusResponse>("/logistics/me/status/");
    return response.data;
  },

  async getMelhorEnvioConnectUrl(): Promise<SellerMEConnectResponse> {
    const response = await api.get<SellerMEConnectResponse>("/logistics/me/connect/");
    return response.data;
  },
};
