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

export interface CepLookupResponse {
  zipcode: string;
  street: string;
  neighborhood: string;
  city: string;
  state: string;
  complement: string;
}

export interface AddressData {
  id: number;
  address_type: string;
  nickname?: string;
  recipient_name?: string;
  recipient_phone?: string;
  zipcode: string;
  street: string;
  number: string;
  complement?: string;
  neighborhood: string;
  city: string;
  state: string;
  country: string;
  is_default: boolean;
  is_active: boolean;
}

export interface CreateAddressRequest {
  address_type: string;        // "Residencial" | "Comercial" | "Outro"
  nickname: string;
  recipient_name: string;
  recipient_phone: string;
  zipcode: string;
  street: string;
  number: string;
  complement?: string;
  neighborhood: string;
  city: string;
  state: string;
  country?: string;
  is_default?: boolean;
  is_shipping_address?: boolean;
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

  async lookupCep(cep: string): Promise<CepLookupResponse> {
    const cleanCep = cep.replace(/\D/g, "");
    const response = await api.post<CepLookupResponse>("/logistics/cep/lookup/", { zipcode: cleanCep });
    return response.data;
  },

  async getAddresses(): Promise<AddressData[]> {
    const response = await api.get<{ results: AddressData[] } | AddressData[]>("/logistics/addresses/");
    const data = response.data;
    if (Array.isArray(data)) return data;
    return data.results ?? [];
  },

  async createAddress(data: CreateAddressRequest): Promise<AddressData> {
    const response = await api.post<AddressData>("/logistics/addresses/", data);
    return response.data;
  },

  async updateAddress(id: number, data: Partial<CreateAddressRequest>): Promise<AddressData> {
    const response = await api.patch<AddressData>(`/logistics/addresses/${id}/`, data);
    return response.data;
  },

  async setDefaultAddress(id: number): Promise<void> {
    await api.post(`/logistics/addresses/${id}/set-default/`);
  },

  async deleteAddress(id: number): Promise<void> {
    await api.delete(`/logistics/addresses/${id}/`);
  },
};
