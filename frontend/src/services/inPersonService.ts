import api from "@/api/axios";

// ─── Types ────────────────────────────────────────────────────────────────────

export type MeetingStatus =
  | "pending_schedule"
  | "scheduled"
  | "confirmed"
  | "in_progress"
  | "completed"
  | "cancelled"
  | "no_show";

export interface InPersonDelivery {
  id: number;
  order?: string; // order UUID — present in API response even if not in OpenAPI schema
  seller: number;
  seller_name: string;
  buyer: number;
  buyer_name: string;
  meeting_status: MeetingStatus;
  meeting_location_name?: string;
  meeting_address?: string;
  meeting_notes?: string;
  scheduled_date?: string | null;
  scheduled_time?: string | null;
  seller_contact_phone?: string;
  buyer_contact_phone?: string;
  seller_confirmed: boolean;
  buyer_confirmed: boolean;
  seller_confirmed_at?: string | null;
  buyer_confirmed_at?: string | null;
  is_fully_confirmed: boolean;
  seller_completed: boolean;
  buyer_completed: boolean;
  seller_completed_at?: string | null;
  buyer_completed_at?: string | null;
  is_fully_completed: boolean;
  completion_notes?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface InPersonDeliveryUpdateRequest {
  meeting_status?: MeetingStatus;
  meeting_location_name?: string;
  meeting_address?: string;
  meeting_notes?: string;
  scheduled_date?: string | null;
  scheduled_time?: string | null;
  completion_notes?: string;
}

export interface ListInPersonDeliveriesResponse {
  deliveries: InPersonDelivery[];
  count: number;
}

// ─── Service ─────────────────────────────────────────────────────────────────

export const inPersonService = {
  async list(params?: { role?: "seller" | "buyer"; status?: MeetingStatus }) {
    const response = await api.get<ListInPersonDeliveriesResponse>(
      "/logistics/in-person/",
      { params },
    );
    return response.data;
  },

  async get(id: number) {
    const response = await api.get<InPersonDelivery>(
      `/logistics/in-person/${id}/`,
    );
    return response.data;
  },

  async confirm(id: number) {
    const response = await api.post<{ message: string; delivery: InPersonDelivery }>(
      `/logistics/in-person/${id}/confirm/`,
    );
    return response.data;
  },

  async update(id: number, data: InPersonDeliveryUpdateRequest) {
    const response = await api.patch<{ message: string; delivery: InPersonDelivery }>(
      `/logistics/in-person/${id}/update/`,
      data,
    );
    return response.data;
  },

  async complete(id: number, completionNotes?: string) {
    const response = await api.post<{ message: string; delivery: InPersonDelivery }>(
      `/logistics/in-person/${id}/complete/`,
      completionNotes ? { completion_notes: completionNotes } : {},
    );
    return response.data;
  },

  async cancel(id: number, cancellationReason?: string) {
    const response = await api.post<{ message: string; delivery: InPersonDelivery }>(
      `/logistics/in-person/${id}/cancel/`,
      cancellationReason ? { cancellation_reason: cancellationReason } : {},
    );
    return response.data;
  },
};
