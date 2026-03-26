import api from "@/api/axios";
import type { SellerShipment } from "@/types/orders";

export interface ShippingQuote {
  id: number;
  service_id: number;
  service_name: string;
  carrier_name: string;
  price: number;
  delivery_time: number;
  created_at: string;
}

export interface CalculateShippingRequest {
  shipping_address_id: number;
}

export interface CalculateShippingResponse {
  quotes_by_seller: Record<string, any>;
  shipping_address: any;
  shipping_address_id: number;
  total_items: number;
  total_value: number;
}

export interface Shipment {
  id: number;
  order: string;
  seller: number;
  tracking_code?: string;
  service_id: number;
  service_name: string;
  carrier_name: string;
  shipping_cost: string;
  status: string;
  label_url?: string;
  tracking_url?: string;
  melhorenvio_tracking_code?: string;
  estimated_delivery_date?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateShipmentsRequest {
  order_id: string;
  shipping_services?: Record<string, number>;
}

export interface CreateShipmentsResponse {
  shipments: Shipment[];
  created_count: number;
  order_status: string;
}

export interface GenerateLabelResponse {
  label_url: string;
  tracking_code: string;
  message: string;
}

export interface TrackShipmentResponse {
  tracking_code: string;
  status: string;
  tracking_events: any[];
  updated_at: string;
}

export interface OrderShipmentsResponse {
  order_id: string;
  shipments: SellerShipment[];
}

export interface SellerMEBalanceResponse {
  balance: string;
  currency: string;
  environment: string;
}

export const shippingService = {
  async getMEBalance() {
    const response = await api.get<SellerMEBalanceResponse>("/logistics/me/balance/");
    return response.data;
  },

  async calculateShipping(data: CalculateShippingRequest) {
    const response = await api.post<CalculateShippingResponse>("/logistics/shipping/calculate/", data);
    return response.data;
  },

  async getSavedQuotes() {
    const response = await api.get<ShippingQuote[]>("/logistics/shipping/quotes/");
    return response.data;
  },

  async listShipments() {
    const response = await api.get<Shipment[]>("/logistics/shipments/");
    return response.data;
  },

  async getShipment(id: number) {
    const response = await api.get<Shipment>(`/logistics/shipments/${id}/`);
    return response.data;
  },

  async createShipments(data: CreateShipmentsRequest) {
    const response = await api.post<CreateShipmentsResponse>("/logistics/shipments/create/", data);
    return response.data;
  },

  async getOrderShipments(orderId: string) {
    const response = await api.get<OrderShipmentsResponse>(`/logistics/shipments/order/${orderId}/`);
    return response.data;
  },

  async generateLabel(shipmentId: number) {
    const response = await api.post<GenerateLabelResponse>(`/logistics/shipments/${shipmentId}/label/`);
    return response.data;
  },

  async trackShipment(shipmentId: number) {
    const response = await api.post<TrackShipmentResponse>(`/logistics/shipments/${shipmentId}/track/`);
    return response.data;
  },

  async markAsShipped(shipmentId: number, trackingCode: string) {
    const response = await api.post<Shipment>(`/logistics/shipments/${shipmentId}/ship/`, {
      tracking_code: trackingCode,
    });
    return response.data;
  },
};
