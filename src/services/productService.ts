import api from "@/api/axios";

export const productService = {
  async getAll() {
    const response = await api.get("/products/");
    return response.data;
  },

  async getById(id: string) {
    const response = await api.get(`/products/${id}/`);
    return response.data;
  },

  async create(data: any) {
    const response = await api.post("/products/", data);
    return response.data;
  },

  async update(id: string, data: any) {
    const response = await api.put(`/products/${id}/`, data);
    return response.data;
  },

  async delete(id: string) {
    await api.delete(`/products/${id}/`);
  },
};
