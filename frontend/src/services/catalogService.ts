import api from "@/api/axios";

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
  async listBrands() {
    const response = await api.get<Brand[]>("/products/brands/");
    return response.data;
  },

  async getBrand(slug: string) {
    const response = await api.get<Brand>(`/products/brands/${slug}/`);
    return response.data;
  },

  async getBrandListings(slug: string) {
    const response = await api.get<MarketplaceListingItem[]>(`/products/brands/${slug}/listings/`);
    return response.data;
  },

  // Categories
  async listCategories() {
    const response = await api.get<Category[]>("/products/categories/");
    return response.data;
  },

  async getCategory(slug: string) {
    const response = await api.get<Category>(`/products/categories/${slug}/`);
    return response.data;
  },

  async getCategoryProducts(slug: string) {
    const response = await api.get<ProductListItem[]>(`/products/categories/${slug}/products/`);
    return response.data;
  },

  // Series
  async listSeries() {
    const response = await api.get<Series[]>("/products/series/");
    return response.data;
  },

  async getSeries(slug: string) {
    const response = await api.get<Series>(`/products/series/${slug}/`);
    return response.data;
  },

  async getSeriesProducts(slug: string) {
    const response = await api.get<ProductListItem[]>(`/products/series/${slug}/products/`);
    return response.data;
  },

  // Conditions
  async listConditions() {
    const response = await api.get<Condition[]>("/products/conditions/");
    return response.data;
  },
};
