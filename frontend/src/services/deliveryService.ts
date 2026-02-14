import api from "@/api/axios";

export interface OrderDelivery {
  seller_id: number;
  seller_name: string;
  delivery_method: string;
  shipment?: any;
  in_person?: any;
}

export interface CreateOrderDeliveriesRequest {
  order_id: string;
  deliveries: any[];
}

export interface CreateOrderDeliveriesResponse {
  order_id: string;
  order_number: string;
  deliveries: OrderDelivery[];
  count: number;
}

export interface OrderDeliveriesDetailsResponse {
  order_id: string;
  order_number: string;
  buyer: any;
  deliveries: OrderDelivery[];
  total_shipping_cost: string;
}

export interface ListUserDeliveriesResponse {
  as_buyer: OrderDelivery[];
  as_seller: OrderDelivery[];
}

export const deliveryService = {
  async createOrderDeliveries(data: CreateOrderDeliveriesRequest) {
    const response = await api.post<CreateOrderDeliveriesResponse>("/logistics/deliveries/create/", data);
    return response.data;
  },

  async getOrderDeliveries(orderId: string) {
    const response = await api.get<OrderDeliveriesDetailsResponse>(`/logistics/deliveries/order/${orderId}/`);
    return response.data;
  },

  async getUserDeliveries() {
    const response = await api.get<ListUserDeliveriesResponse>("/logistics/deliveries/user/");
    return response.data;
  },
};
