import api from "@/api/axios";
import type {
  MarketplaceListing,
  MarketplaceListingDetail,
  SearchProductsResponse,
  CreateListingRequest,
  UpdateListingRequest,
  FilterOptionsResponse,
  ProductListItem,
  PaginatedResponse,
} from "@/types/product";

// Re-export for consumers
export type { PaginatedResponse };

export interface ToggleActiveResponse {
  message: string;
  is_active: boolean;
}

export interface IncrementViewResponse {
  message: string;
  views: number;
}

export interface MarkAsSoldResponse {
  message: string;
  listing: MarketplaceListingDetail;
}

export const productService = {
  // ============================================
  // LISTINGS - BROWSING
  // ============================================

  async getListings(params?: {
    brand__slug?: string;
    condition__slug?: string;
    product__category__slug?: string;
    ordering?: string;
    page?: number;
  }) {
    const response = await api.get<PaginatedResponse<MarketplaceListing>>(
      "/products/listings/",
      { params },
    );
    return response.data;
  },

  async getListingById(id: number) {
    const response = await api.get<MarketplaceListingDetail>(
      `/products/listings/${id}/`,
    );
    return response.data;
  },

  async incrementListingView(id: number) {
    const response = await api.post<IncrementViewResponse>(`/products/listings/${id}/increment-view/`);
    return response.data;
  },

  async getMyListings(params?: { page?: number }) {
    const response = await api.get<PaginatedResponse<MarketplaceListing>>(
      "/products/my-listings/",
      { params },
    );
    return response.data;
  },

  // ============================================
  // LISTINGS - MANAGEMENT
  // ============================================

  async createListing(data: CreateListingRequest) {
    const response = await api.post<MarketplaceListingDetail>(
      "/products/listings/create/",
      data,
    );
    return response.data;
  },

  async updateListing(id: number, data: UpdateListingRequest) {
    const response = await api.put<MarketplaceListingDetail>(
      `/products/listings/${id}/update/`,
      data,
    );
    return response.data;
  },

  async partialUpdateListing(id: number, data: Partial<UpdateListingRequest>) {
    const response = await api.patch<MarketplaceListingDetail>(
      `/products/listings/${id}/update/`,
      data,
    );
    return response.data;
  },

  async deleteListing(id: number) {
    await api.delete(`/products/listings/${id}/delete/`);
  },

  async toggleListingActive(id: number) {
    const response = await api.post<ToggleActiveResponse>(`/products/listings/${id}/activate/`);
    return response.data;
  },

  async markListingAsSold(id: number) {
    const response = await api.post<MarkAsSoldResponse>(`/products/listings/${id}/mark-as-sold/`);
    return response.data;
  },

  // ============================================
  // SEARCH & FILTERING
  // ============================================

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

  async getFeaturedListings() {
    const response = await api.get<MarketplaceListing[]>("/products/search/featured/");
    return response.data;
  },

  async getRecentListings() {
    const response = await api.get<MarketplaceListing[]>("/products/search/recent/");
    return response.data;
  },

  async getFilterOptions() {
    const response = await api.get<FilterOptionsResponse>(
      "/products/search/filters/options/",
    );
    return response.data;
  },

  // ============================================
  // PRODUCTS (CATALOG)
  // ============================================

  async getProducts(params?: {
    category__slug?: string;
    series__slug?: string;
    search?: string;
    ordering?: string;
    page?: number;
  }): Promise<PaginatedResponse<ProductListItem>> {
    const response = await api.get<PaginatedResponse<ProductListItem>>(
      "/products/products/",
      { params },
    );
    return response.data;
  },

  async getProductBySlug(slug: string) {
    const response = await api.get<ProductListItem>(`/products/products/${slug}/`);
    return response.data;
  },

  async getProductListings(slug: string, params?: { page?: number }) {
    const response = await api.get<PaginatedResponse<MarketplaceListing>>(
      `/products/products/${slug}/listings/`,
      { params },
    );
    return response.data;
  },

  // ============================================
  // DEPRECATED - OLD ENDPOINTS
  // ============================================

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
