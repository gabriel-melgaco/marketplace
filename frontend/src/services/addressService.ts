import api from "@/api/axios";

export type AddressType = "home" | "work" | "shipping" | "other";

export interface Address {
  id: number;
  address_type: AddressType;
  nickname?: string;
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
  is_default: boolean;
  is_active: boolean;
  is_shipping_address: boolean;
  created_at: string;
  updated_at: string;
}

export interface AddressCreateRequest {
  address_type?: AddressType;
  nickname?: string;
  recipient_name: string;
  recipient_phone: string;
  zipcode: string;
  street: string;
  number: string;
  complement?: string;
  neighborhood: string;
  city: string;
  state: string;
  is_default?: boolean;
  is_shipping_address?: boolean;
}

export interface CEPLookupRequest {
  zipcode: string;
}

export interface CEPLookupResponse {
  zipcode: string;
  street: string;
  neighborhood: string;
  city: string;
  state: string;
}

export const addressService = {
  async listAddresses() {
    const response = await api.get<Address[]>("/logistics/addresses/");
    return response.data;
  },

  async getAddress(id: number) {
    const response = await api.get<Address>(`/logistics/addresses/${id}/`);
    return response.data;
  },

  async createAddress(data: AddressCreateRequest) {
    const response = await api.post<Address>("/logistics/addresses/", data);
    return response.data;
  },

  async updateAddress(id: number, data: Partial<AddressCreateRequest>) {
    const response = await api.patch<Address>(`/logistics/addresses/${id}/`, data);
    return response.data;
  },

  async deleteAddress(id: number) {
    await api.delete(`/logistics/addresses/${id}/`);
  },

  async setDefaultAddress(id: number) {
    const response = await api.post<Address>(`/logistics/addresses/${id}/set-default/`);
    return response.data;
  },

  async getShippingAddresses() {
    const response = await api.get<Address[]>("/logistics/addresses/shipping/");
    return response.data;
  },

  async lookupCEP(data: CEPLookupRequest) {
    const response = await api.post<CEPLookupResponse>("/logistics/cep/lookup/", data);
    return response.data;
  },
};
