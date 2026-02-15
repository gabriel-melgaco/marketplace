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
  created_at: string;
}

export interface OrderCreateRequest {
  shipping_address_id: number;
  shipping_services: Record<string, any>;
  payment_method: string;
  buyer_notes?: string;
}

export interface OrderUpdateStatusRequest {
  status: string;
}

export const orderService = {
  // Buyer endpoints
  async listOrders() {
    const response = await api.get<OrderList[]>("/orders/");
    return response.data;
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
    const response = await api.get<OrderList[]>("/orders/sales/");
    return response.data;
  },

  async getSale(id: string) {
    const response = await api.get<Order>(`/orders/sales/${id}/`);
    return response.data;
  },

  async updateOrderStatus(id: string, data: OrderUpdateStatusRequest) {
    const response = await api.post<Order>(`/orders/sales/${id}/update-status/`, data);
    return response.data;
  },
};
