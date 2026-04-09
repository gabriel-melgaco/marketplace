import api from "@/api/axios";
import type { PaginatedResponse } from "@/types/product";

export interface Brand {
  id: number;
  name: string;
  slug: string;
  logo?: string;
  website?: string;
  is_active: boolean;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  parent?: string;
  children: CategoryChildren[];
  is_active: boolean;
}

export interface CategoryChildren {
  id: number;
  name: string;
  slug: string;
}

export interface Series {
  id: number;
  name: string;
  slug: string;
  brand: number;
  description?: string;
}

export interface Condition {
  id: number;
  name: string;
  slug: string;
}

export interface ProductListItem {
  id: number;
  name: string;
  slug: string;
  code: string | null;
}

export interface MarketplaceListingItem {
  id: number;
  product: {
    id: number;
    name: string;
    slug: string;
  };
  price: string;
  condition: string;
  is_active: boolean;
}

export const catalogService = {
  // Brands
  async listBrands(params?: { page?: number }) {
    const response = await api.get<PaginatedResponse<Brand>>(
      "/products/brands/",
      { params },
    );
    return response.data;
  },

  async getBrand(slug: string) {
    const response = await api.get<Brand>(`/products/brands/${slug}/`);
    return response.data;
  },

  async getBrandListings(slug: string, params?: { page?: number }) {
    const response = await api.get<PaginatedResponse<MarketplaceListingItem>>(
      `/products/brands/${slug}/listings/`,
      { params },
    );
    return response.data;
  },

  // Categories
  async listCategories(params?: { page?: number }) {
    const response = await api.get<PaginatedResponse<Category>>(
      "/products/categories/",
      { params },
    );
    return response.data;
  },

  async getCategory(slug: string) {
    const response = await api.get<Category>(`/products/categories/${slug}/`);
    return response.data;
  },

  async getCategoryProducts(slug: string, params?: { page?: number }) {
    const response = await api.get<PaginatedResponse<ProductListItem>>(
      `/products/categories/${slug}/products/`,
      { params },
    );
    return response.data;
  },

  // Series
  async listSeries(params?: { page?: number }) {
    const response = await api.get<PaginatedResponse<Series>>(
      "/products/series/",
      { params },
    );
    return response.data;
  },

  async getSeries(slug: string) {
    const response = await api.get<Series>(`/products/series/${slug}/`);
    return response.data;
  },

  async getSeriesProducts(slug: string, params?: { page?: number }) {
    const response = await api.get<PaginatedResponse<ProductListItem>>(
      `/products/series/${slug}/products/`,
      { params },
    );
    return response.data;
  },

  // Conditions (NOT paginated)
  async listConditions() {
    const response = await api.get<Condition[]>("/products/conditions/");
    return response.data;
  },
};
