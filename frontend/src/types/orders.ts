export type ShipmentStatus =
  | "created"
  | "pending"
  | "released"
  | "generated"
  | "posted"
  | "in_transit"
  | "out_for_delivery"
  | "delivered"
  | "cancelled"
  | "returned";

export type OrderStatus =
  | "pending_payment"
  | "paid"
  | "processing"
  | "shipped"
  | "delivered"
  | "completed"
  | "cancelled"
  | "failed";

export interface OrderItemListing {
  id: number;
  title: string;
  price: string;
  images: Array<{ image_url: string; is_primary: boolean; order: number }>;
  product: { name: string };
  primary_image?: string | null;
}

export interface SellerOrderItem {
  id: number;
  listing: OrderItemListing;
  quantity: number;
  unit_price: string;
  subtotal: string;
}

export interface SellerOrderAddress {
  recipient_name?: string;
  street: string;
  number: string;
  complement?: string;
  neighborhood: string;
  city: string;
  state: string;
  zipcode: string;
  recipient_phone?: string;
}

export interface SellerBuyer {
  id: number;
  full_name: string;
  email: string;
}

export interface SellerShipment {
  id: number;
  order: string;
  seller: number;
  tracking_code?: string;
  service_id: number;
  service_name: string;
  carrier_name: string;
  shipping_cost: string;
  status: ShipmentStatus;
  label_url?: string;
  tracking_url?: string;
  melhorenvio_tracking_code?: string;
  estimated_delivery_date?: string;
  created_at: string;
  updated_at: string;
}

export interface SellerOrderDetail {
  id: string;
  order_number: string;
  buyer: SellerBuyer;
  items: SellerOrderItem[];
  total: string;
  status: OrderStatus;
  status_display: string;
  payment_method: string;
  shipping_address: SellerOrderAddress | null;
  shipping_cost?: string;
  buyer_notes?: string;
  has_in_person: boolean;
  has_melhor_envio: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaginatedSaleListItem {
  id: string;
  order_number: string;
  buyer_name: string;
  seller_name: string;
  total: string;
  status: OrderStatus;
  status_display: string;
  items_count: number;
  has_in_person: boolean;
  has_melhor_envio: boolean;
  created_at: string;
  items?: SellerOrderItem[];
}

export interface PaginatedSaleList {
  count: number;
  next: string | null;
  previous: string | null;
  results: PaginatedSaleListItem[];
}
