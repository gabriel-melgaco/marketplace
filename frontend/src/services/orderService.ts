import api from "@/api/axios";

export interface OrderItem {
  id: number;
  listing: any;
  quantity: number;
  unit_price: string;
  subtotal: string;
}

export interface Order {
  id: string;
  order_number: string;
  buyer: any;
  items: OrderItem[];
  total: string;
  status: string;
  status_display: string;
  payment_method: string;
  shipping_address: any;
  buyer_notes?: string;
  created_at: string;
  updated_at: string;
}

export interface OrderList {
  id: string;
  order_number: string;
  total: string;
  status: string;
  status_display: string;
  created_at: string;
}

export interface ItemDelivery {
  listing_id: number;
  delivery_method: "melhor_envio" | "in_person";
  service_id?: number;
}

export interface OrderCreateRequest {
  shipping_address_id: number;
  items_delivery: ItemDelivery[];
  payment_method: string;
  buyer_notes?: string;
}

export interface OrderUpdateStatusRequest {
  status: string;
}

type PaginatedOrMaybeNot<T> = T[] | { results: T[] };

function toArray<T>(data: PaginatedOrMaybeNot<T>): T[] {
  return Array.isArray(data) ? data : (data.results ?? []);
}

export const orderService = {
  // Buyer endpoints
  async listOrders() {
    const response = await api.get<PaginatedOrMaybeNot<OrderList>>("/orders/");
    return toArray(response.data);
  },

  async getOrder(id: string) {
    const response = await api.get<Order>(`/orders/${id}/`);
    return response.data;
  },

  async createOrder(data: OrderCreateRequest) {
    const response = await api.post<Order>("/orders/create/", data);
    return response.data;
  },

  async cancelOrder(id: string) {
    const response = await api.post<Order>(`/orders/${id}/cancel/`);
    return response.data;
  },

  // Seller endpoints
  async listSales() {
    const response =
      await api.get<PaginatedOrMaybeNot<OrderList>>("/orders/sales/");
    return toArray(response.data);
  },

  async getSale(id: string) {
    const response = await api.get<Order>(`/orders/sales/${id}/`);
    return response.data;
  },

  async updateOrderStatus(id: string, data: OrderUpdateStatusRequest) {
    const response = await api.post<Order>(
      `/orders/sales/${id}/update-status/`,
      data,
    );
    return response.data;
  },
};
