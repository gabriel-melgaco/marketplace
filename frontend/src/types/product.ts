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
  seller_shipping_address: SellerShippingAddress | null;
}

export interface SearchProductsResponse {
  results: MarketplaceListing[];
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
  seller_shipping_address: SellerShippingAddressDetail | null;
  price: string;
  quantity: number;
  is_active: boolean;
  description: string;
  views_count: number;
  weight_kg: string | null;
  height_cm: string | null;
  width_cm: string | null;
  length_cm: string | null;
  created_at: string;
  updated_at: string;
  sold_at: string | null;
}
