import api from "@/api/axios";

export interface InPersonDelivery {
  id: number;
  order: string;
  seller: number;
  buyer: number;
  meeting_location_name: string;
  meeting_address: any;
  scheduled_date?: string;
  scheduled_time?: string;
  meeting_notes?: string;
  seller_contact_phone: string;
  buyer_contact_phone: string;
  meeting_status: string;
  seller_confirmed_at?: string;
  buyer_confirmed_at?: string;
  completed_at?: string;
  cancelled_at?: string;
  cancellation_reason?: string;
  created_at: string;
  updated_at: string;
}

export interface ListInPersonDeliveriesResponse {
  deliveries: InPersonDelivery[];
}

export interface InPersonDeliveryUpdateRequest {
  meeting_location_name?: string;
  meeting_address?: any;
  scheduled_date?: string;
  scheduled_time?: string;
  meeting_notes?: string;
}

export interface UpdateMeetingResponse {
  message: string;
  delivery: InPersonDelivery;
}

export interface ConfirmMeetingResponse {
  message: string;
  delivery: InPersonDelivery;
}

export interface CompleteInPersonDeliveryRequest {
  completion_notes?: string;
}

export interface CompleteInPersonDeliveryResponse {
  message: string;
  delivery: InPersonDelivery;
}

export interface CancelInPersonDeliveryRequest {
  cancellation_reason?: string;
}

export interface CancelInPersonDeliveryResponse {
  message: string;
  delivery: InPersonDelivery;
}

export const inPersonDeliveryService = {
  async listInPersonDeliveries(params?: { role?: "buyer" | "seller"; status?: string }) {
    const response = await api.get<ListInPersonDeliveriesResponse>("/logistics/in-person/", { params });
    return response.data;
  },

  async getInPersonDelivery(id: number) {
    const response = await api.get<InPersonDelivery>(`/logistics/in-person/${id}/`);
    return response.data;
  },

  async updateMeeting(id: number, data: InPersonDeliveryUpdateRequest) {
    const response = await api.patch<UpdateMeetingResponse>(`/logistics/in-person/${id}/update/`, data);
    return response.data;
  },

  async confirmMeeting(id: number) {
    const response = await api.post<ConfirmMeetingResponse>(`/logistics/in-person/${id}/confirm/`);
    return response.data;
  },

  async completeDelivery(id: number, data?: CompleteInPersonDeliveryRequest) {
    const response = await api.post<CompleteInPersonDeliveryResponse>(`/logistics/in-person/${id}/complete/`, data);
    return response.data;
  },

  async cancelDelivery(id: number, data?: CancelInPersonDeliveryRequest) {
    const response = await api.post<CancelInPersonDeliveryResponse>(`/logistics/in-person/${id}/cancel/`, data);
    return response.data;
  },
};
