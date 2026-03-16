export type NotificationType =
  | 'order_created'
  | 'order_status_changed'
  | 'payment_confirmed'
  | 'payment_failed'
  | 'dispute_opened'
  | 'shipment_created'
  | 'shipment_status_updated'
  | 'delivery_scheduled'
  | 'delivery_confirmed'
  | 'new_message'
  | 'seller_verified'
  | 'listing_blocked'
  | 'listing_created';

export interface NotificationMetadata {
  chat_id?: string;
  [key: string]: unknown;
}

export interface Notification {
  id: string;
  notification_type: NotificationType;
  title: string;
  body: string;
  metadata: NotificationMetadata;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
}

export interface WsNotificationPayload {
  type: 'notification';
  data: Notification;
}

export interface WsUnreadCountPayload {
  type: 'unread_count';
  count: number;
}

export type WsIncomingMessage = WsNotificationPayload | WsUnreadCountPayload;

export interface WsMarkReadMessage {
  type: 'mark_read';
  notification_id: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface NotificationPreference {
  order_created_ws: boolean;
  order_created_email: boolean;
  order_status_changed_ws: boolean;
  order_status_changed_email: boolean;
  payment_confirmed_ws: boolean;
  payment_confirmed_email: boolean;
  payment_failed_ws: boolean;
  payment_failed_email: boolean;
  dispute_opened_ws: boolean;
  dispute_opened_email: boolean;
  shipment_created_ws: boolean;
  shipment_created_email: boolean;
  shipment_status_updated_ws: boolean;
  shipment_status_updated_email: boolean;
  delivery_scheduled_ws: boolean;
  delivery_scheduled_email: boolean;
  delivery_confirmed_ws: boolean;
  delivery_confirmed_email: boolean;
  new_message_ws: boolean;
  new_message_email: boolean;
  seller_verified_ws: boolean;
  seller_verified_email: boolean;
  listing_blocked_ws: boolean;
  listing_blocked_email: boolean;
  listing_created_ws: boolean;
  listing_created_email: boolean;
}
