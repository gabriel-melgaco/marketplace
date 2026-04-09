import api from "@/api/axios";

export interface CustomUser {
  id: number;
  email: string;
  full_name: string;
  cpf: string;
  birthday: string;
  picture?: string;
  is_active?: boolean;
  is_seller: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomUserUpdateRequest {
  full_name?: string;
  cpf?: string;
  birthday?: string;
  picture?: string;
}

export const userService = {
  async getCurrentUser() {
    const response = await api.get<CustomUser>("/auth/user/");
    return response.data;
  },

  async updateCurrentUser(data: CustomUserUpdateRequest) {
    const response = await api.patch<CustomUser>("/auth/user/", data);
    return response.data;
  },

  async replaceCurrentUser(data: CustomUserUpdateRequest) {
    const response = await api.put<CustomUser>("/auth/user/", data);
    return response.data;
  },

  async deleteCurrentUser() {
    await api.delete("/auth/user/");
  },
};
