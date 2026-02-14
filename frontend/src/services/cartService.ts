import api from "@/api/axios";

export interface CartItem {
  id: number;
  listing: any;
  quantity: number;
  subtotal: string;
  seller_id: number;
  seller_name: string;
  added_at: string;
}

export interface Cart {
  id: number;
  items: CartItem[];
  total: string;
  items_count: number;
  sellers: number[];
  created_at: string;
  updated_at: string;
}

export interface AddToCartRequest {
  listing: number;
  quantity?: number;
}

export interface UpdateCartItemRequest {
  quantity: number;
}

export const cartService = {
  async getCart() {
    const response = await api.get<Cart>("/orders/cart/");
    return response.data;
  },

  async addItem(data: AddToCartRequest) {
    const response = await api.post<Cart>("/orders/cart/add/", data);
    return response.data;
  },

  async updateItem(itemId: number, data: UpdateCartItemRequest) {
    const response = await api.patch<Cart>(`/orders/cart/items/${itemId}/`, data);
    return response.data;
  },

  async removeItem(itemId: number) {
    const response = await api.delete<Cart>(`/orders/cart/items/${itemId}/remove/`);
    return response.data;
  },

  async clearCart() {
    const response = await api.delete<Cart>("/orders/cart/clear/");
    return response.data;
  },
};
