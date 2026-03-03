export interface ProductCategory {
  id: string;
  name: string;
  slug: string;
  parent: string;
  children: {
    id: string;
    name: string;
    slug: string;
  }[];
  is_active: boolean;
}

export interface ProductSimple {
  id: number;
  name: string;
  slug: string;
  code: string | null;
}

export interface BrandSimple {
  id: number;
  name: string;
  slug: string;
  logo: string | null;
}

export interface Condition {
  id: number;
  name: string;
  slug: string;
}

export interface MarketplaceListingImage {
  id: number;
  image_url: string;
  object_name: string;
  is_primary: boolean;
  order: number;
  created_at: string;
}

export interface CategorySimple {
  id: number;
  name: string;
  slug: string;
}

export interface SeriesSimple {
  id: number;
  name: string;
  slug: string;
}

export interface ProductDetail {
  id: number;
  category: CategorySimple | null;
  series: SeriesSimple | null;
  name: string;
  slug: string;
  code: string | null;
  description: string;
}

export interface BrandDetail {
  id: number;
  name: string;
  slug: string;
  logo: string | null;
  website: string;
  is_active: boolean;
}

export interface SellerShippingAddress {
  id: number;
  city: string;
  state: string;
  neighborhood: string;
}

export interface SellerShippingAddressDetail {
  id: number;
  address_type: string;
  nickname: string;
  recipient_name: string;
  recipient_phone: string;
  zipcode: string;
  street: string;
  number: string;
  complement: string;
  neighborhood: string;
  city: string;
  state: string;
  country: string;
  is_default: boolean;
  is_active: boolean;
  is_shipping_address: boolean;
  created_at: string;
}

export interface MarketplaceListing {
  id: number;
  product: ProductSimple;
  seller: number;
  seller_name: string;
  title: string;
  price: string;
  brand: BrandSimple;
  quantity: number;
  is_active: boolean;
  description: string;
  condition: Condition;
  views_count: number;
  created_at: string;
  updated_at: string;
  sold_at: string | null;
  images: MarketplaceListingImage[];
  primary_image: string | null;
  shipping_address: SellerShippingAddress | null;
}

export interface SearchProductsResponse {
  results: MarketplaceListing[];
}

export interface ListingPackageRequest {
  weight_kg: string;
  height_cm: string;
  width_cm: string;
  length_cm: string;
  description?: string;
}

export interface CreateListingRequest {
  product: number;
  title: string;
  brand: number;
  condition: number;
  description: string;
  price: string;
  quantity?: number;
  packages: ListingPackageRequest[];
  seller_shipping_address?: number | null;
}

export interface UpdateListingRequest {
  product?: number;
  title?: string;
  brand?: number;
  condition?: number;
  description?: string;
  price?: string;
  quantity?: number;
  is_active?: boolean;
  packages?: ListingPackageRequest[];
  seller_shipping_address?: number | null;
}

export interface PresignedUrlRequest {
  file_name: string;
  content_type: string;
}

export interface PresignedUrlResponse {
  upload_url: string;
  file_url: string;
  object_name: string;
}

export interface AddListingImageRequest {
  image_url: string;
  object_name: string;
  is_primary?: boolean;
  order?: number;
}

export interface FilterOptionsResponse {
  categories: { id: number; name: string; slug: string }[];
  brands: { id: number; name: string; slug: string }[];
  conditions: { id: number; name: string; slug: string }[];
  price_range: { min: number; max: number };
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ProductListItem {
  id: number;
  name: string;
  slug: string;
  code: string | null;
}

/**
 * Representa um pacote retornado pela API dentro de um listing.
 * O backend retorna packages como array em:
 *   GET  /products/listings/{id}/
 *   POST /products/listings/create/
 */
export interface ListingPackage {
  id?: number;
  weight_kg: string;
  height_cm: string;
  width_cm: string;
  length_cm: string;
  description?: string;
}

export interface MarketplaceListingDetail {
  id: number;
  product: ProductDetail;
  brand: BrandDetail;
  condition: Condition;
  images: MarketplaceListingImage[];
  seller: number;
  seller_name: string;
  seller_email: string;
  shipping_address: SellerShippingAddressDetail | null;
  title: string;
  price: string;
  quantity: number;
  is_active: boolean;
  description: string;
  views_count: number;
  /**
   * Campos legados: dimensões no objeto raiz (alguns endpoints antigos).
   * Prefira usar packages[0] quando disponível.
   */
  weight_kg: string | null;
  height_cm: string | null;
  width_cm: string | null;
  length_cm: string | null;
  /** Array de pacotes — presente em create e detail */
  packages?: ListingPackage[];
  created_at: string;
  updated_at: string;
  sold_at: string | null;
}

export interface FormData {
  product: string;
  title: string;
  brand: string;
  condition: string;
  description: string;
  price: string;
  quantity: string;
  weight_kg: string;
  height_cm: string;
  width_cm: string;
  length_cm: string;
  package_description: string;
}

export interface PendingImage {
  id: string;
  file: File;
  previewUrl: string;
  isPrimary: boolean;
}
