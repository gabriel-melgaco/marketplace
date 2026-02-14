import api from "@/api/axios";
import type { MarketplaceListing, MarketplaceListingDetail, SearchProductsResponse } from "@/types/product";

export const productService = {
  async getAll() {
    const response = await api.get("/products/");
    return response.data;
  },

  async getListings() {
    const response = await api.get<MarketplaceListing[]>(
      "/products/listings/",
    );
    return response.data;
  },

  async getById(id: string) {
    const response = await api.get(`/products/${id}/`);
    return response.data;
  },

  async getListingById(id: number) {
    const response = await api.get<MarketplaceListingDetail>(
      `/products/listings/${id}/`,
    );
    return response.data;
  },

  async incrementListingView(id: number) {
    const response = await api.post(`/products/listings/${id}/increment-view/`);
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

  async searchListings(term: string) {
    const normalizedTerm = term.trim();
    if (!normalizedTerm) return { results: [] };

    const response = await api.get<SearchProductsResponse>(
      "/products/search/",
      {
        params: { q: normalizedTerm },
      },
    );
    return response.data;
  },
};
