import api from "@/api/axios";
import { tokenStorage } from "@/utils/tokenStorage";
import type { User } from "@/types/auth";

export interface SocialAccount {
  id: number;
  provider: string;
  uid: string;
  extra_data: any;
  date_joined: string;
}

export interface GoogleSocialLoginRequest {
  code: string;
  redirect_uri: string;
}

interface GoogleSocialLoginApiResponse {
  access: string;
  refresh: string;
  access_expiration: string;
  refresh_expiration: string;
  user: {
    pk: number;
    username: string;
    email: string;
    first_name: string;
    last_name: string;
  };
}

export interface GoogleSocialLoginResponse {
  access: string;
  refresh: string;
  access_expiration: string;
  refresh_expiration: string;
  user: User;
}

export interface SocialConnectRequest {
  code: string;
  redirect_uri?: string;
}

export interface SocialConnectResponse {
  message: string;
  account: SocialAccount;
}

function mapSocialUserToUser(apiUser: GoogleSocialLoginApiResponse["user"]): User {
  const fullName = [apiUser.first_name, apiUser.last_name]
    .filter(Boolean)
    .join(" ");

  return {
    id: apiUser.pk,
    email: apiUser.email,
    full_name: fullName,
    birthday: "",
    cpf: "",
    picture: "",
    is_active: true,
  };
}

export const socialAuthService = {
  async listSocialAccounts() {
    const response = await api.get<SocialAccount[]>("/auth/social/accounts/");
    return response.data;
  },

  async disconnectSocialAccount(id: number) {
    await api.delete(`/auth/social/accounts/${id}/`);
  },

  async googleLogin(data: GoogleSocialLoginRequest): Promise<GoogleSocialLoginResponse> {
    const response = await api.post<GoogleSocialLoginApiResponse>(
      "/auth/social/google/",
      { code: data.code, redirect_uri: data.redirect_uri },
    );

    const user = mapSocialUserToUser(response.data.user);

    tokenStorage.saveTokens({
      access: response.data.access,
      refresh: response.data.refresh,
      access_expiration: response.data.access_expiration,
      refresh_expiration: response.data.refresh_expiration,
    });
    tokenStorage.saveUser(user);

    return {
      access: response.data.access,
      refresh: response.data.refresh,
      access_expiration: response.data.access_expiration,
      refresh_expiration: response.data.refresh_expiration,
      user,
    };
  },

  async googleConnect(data: SocialConnectRequest) {
    const response = await api.post<SocialConnectResponse>("/auth/social/google/connect/", data);
    return response.data;
  },
};
