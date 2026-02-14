import api from "@/api/axios";
import { tokenStorage } from "@/utils/tokenStorage";

export interface SocialAccount {
  id: number;
  provider: string;
  uid: string;
  extra_data: any;
  date_joined: string;
}

export interface GoogleSocialLoginRequest {
  code: string;
  redirect_uri?: string;
}

export interface GoogleSocialLoginResponse {
  access: string;
  refresh: string;
  access_expiration: string;
  refresh_expiration: string;
  user: any;
}

export interface SocialConnectRequest {
  code: string;
  redirect_uri?: string;
}

export interface SocialConnectResponse {
  message: string;
  account: SocialAccount;
}

export const socialAuthService = {
  async listSocialAccounts() {
    const response = await api.get<SocialAccount[]>("/auth/social/accounts/");
    return response.data;
  },

  async disconnectSocialAccount(id: number) {
    await api.delete(`/auth/social/accounts/${id}/`);
  },

  async googleLogin(data: GoogleSocialLoginRequest) {
    const response = await api.post<GoogleSocialLoginResponse>("/auth/social/google/", data);

    // Save tokens and user data
    tokenStorage.saveTokens({
      access: response.data.access,
      refresh: response.data.refresh,
      access_expiration: response.data.access_expiration,
      refresh_expiration: response.data.refresh_expiration,
    });
    tokenStorage.saveUser(response.data.user);

    return response.data;
  },

  async googleConnect(data: SocialConnectRequest) {
    const response = await api.post<SocialConnectResponse>("/auth/social/google/connect/", data);
    return response.data;
  },
};
