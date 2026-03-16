import api from "@/api/axios";
import {
  Notification,
  PaginatedResponse,
  NotificationPreference,
} from "@/types/notifications";

interface ListParams {
  page?: number;
  isRead?: boolean;
}

export const notificationsApi = {
  async list({ page = 1, isRead }: ListParams = {}): Promise<PaginatedResponse<Notification>> {
    const params: Record<string, string | number> = { page };
    if (isRead !== undefined) {
      params.read = isRead ? 'true' : 'false';
    }
    const { data } = await api.get<PaginatedResponse<Notification>>('/notifications/', { params });
    return data;
  },

  async markAsRead(notificationId: string): Promise<Notification> {
    const { data } = await api.post<Notification>(`/notifications/${notificationId}/read/`);
    return data;
  },

  async markAllAsRead(): Promise<{ marked: number }> {
    const { data } = await api.post<{ marked: number }>('/notifications/read-all/');
    return data;
  },

  async getUnreadCount(): Promise<number> {
    const { data } = await api.get<{ count: number }>('/notifications/unread-count/');
    return data.count;
  },

  async getPreferences(): Promise<NotificationPreference> {
    const { data } = await api.get<NotificationPreference>('/notifications/preferences/');
    return data;
  },

  async updatePreferences(partial: Partial<NotificationPreference>): Promise<NotificationPreference> {
    const { data } = await api.patch<NotificationPreference>('/notifications/preferences/', partial);
    return data;
  },
};
