import type { NotificationMetadata, NotificationType } from "../types/notifications";

export interface NotificationMeta {
  label: string;
  icon: string;
  colorClass: string;
  bgClass: string;
  route?: (metadata: NotificationMetadata) => string;
}

const NOTIFICATION_META: Record<NotificationType, NotificationMeta> = {
  order_created: {
    label: "Pedido Criado",
    icon: "ShoppingBagIcon",
    colorClass: "text-blue-600",
    bgClass: "bg-blue-50",
    route: () => "/mypurchase",
  },
  order_status_changed: {
    label: "Status do Pedido",
    icon: "ArrowPathIcon",
    colorClass: "text-indigo-600",
    bgClass: "bg-indigo-50",
    route: () => "/mypurchase",
  },
  payment_confirmed: {
    label: "Pagamento Confirmado",
    icon: "CheckCircleIcon",
    colorClass: "text-green-600",
    bgClass: "bg-green-50",
    route: () => "/mypurchase",
  },
  payment_failed: {
    label: "Falha no Pagamento",
    icon: "XCircleIcon",
    colorClass: "text-red-600",
    bgClass: "bg-red-50",
    route: () => "/payment/failed",
  },
  dispute_opened: {
    label: "Disputa Aberta",
    icon: "ExclamationTriangleIcon",
    colorClass: "text-orange-600",
    bgClass: "bg-orange-50",
    route: () => "/mypurchase",
  },
  shipment_created: {
    label: "Envio Criado",
    icon: "TruckIcon",
    colorClass: "text-cyan-600",
    bgClass: "bg-cyan-50",
    route: () => "/mypurchase",
  },
  shipment_status_updated: {
    label: "Envio Atualizado",
    icon: "MapPinIcon",
    colorClass: "text-cyan-600",
    bgClass: "bg-cyan-50",
    route: () => "/mypurchase",
  },
  delivery_scheduled: {
    label: "Entrega Agendada",
    icon: "CalendarIcon",
    colorClass: "text-teal-600",
    bgClass: "bg-teal-50",
    route: () => "/mypurchase",
  },
  delivery_confirmed: {
    label: "Entrega Confirmada",
    icon: "HomeIcon",
    colorClass: "text-green-700",
    bgClass: "bg-green-50",
    route: () => "/mypurchase",
  },
  new_message: {
    label: "Nova Mensagem",
    icon: "ChatBubbleLeftIcon",
    colorClass: "text-purple-600",
    bgClass: "bg-purple-50",
    route: (meta) => {
      const id = meta.chat_id ?? meta.conversation_id;
      return id ? `/conversations/${id}` : "/conversations";
    },
  },
  seller_verified: {
    label: "Vendedor Verificado",
    icon: "BadgeCheckIcon",
    colorClass: "text-emerald-600",
    bgClass: "bg-emerald-50",
    route: () => "/dashboard",
  },
  listing_blocked: {
    label: "Anúncio Bloqueado",
    icon: "NoSymbolIcon",
    colorClass: "text-red-600",
    bgClass: "bg-red-50",
    route: () => "/dashboard",
  },
  listing_created: {
    label: "Anúncio Publicado",
    icon: "TagIcon",
    colorClass: "text-blue-600",
    bgClass: "bg-blue-50",
    route: () => "/dashboard",
  },
};

/**
 * Returns visual metadata for a notification type.
 * Accepts a plain string so runtime-unknown types from WebSocket messages
 * are handled safely — unknown types return the fallback object.
 */
export function getNotificationMeta(type: string): NotificationMeta {
  return (
    (NOTIFICATION_META as Record<string, NotificationMeta>)[type] ?? {
      label: "Notificação",
      icon: "BellIcon",
      colorClass: "text-gray-600",
      bgClass: "bg-gray-50",
    }
  );
}

/**
 * Formats a creation timestamp as a human-readable relative string.
 * Accepts an optional `now` parameter so callers can pass a stable
 * Date instance (e.g., from a 1-minute interval) to keep the list
 * up-to-date without re-mounting items.
 */
export function formatNotificationDate(
  isoString: string,
  now = new Date(),
): string {
  const date = new Date(isoString);
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMin < 1) return "agora mesmo";
  if (diffMin < 60) return `há ${diffMin} min`;
  if (diffHours < 24) return `há ${diffHours}h`;
  if (diffDays < 7) return `há ${diffDays}d`;

  return date.toLocaleDateString("pt-BR", { day: "numeric", month: "short" });
}

export const NOTIFICATION_TYPE_GROUPS: {
  groupLabel: string;
  types: NotificationType[];
}[] = [
  {
    groupLabel: "Pedidos",
    types: ["order_created", "order_status_changed"],
  },
  {
    groupLabel: "Pagamentos",
    types: ["payment_confirmed", "payment_failed", "dispute_opened"],
  },
  {
    groupLabel: "Envio e Entrega",
    types: [
      "shipment_created",
      "shipment_status_updated",
      "delivery_scheduled",
      "delivery_confirmed",
    ],
  },
  {
    groupLabel: "Mensagens",
    types: ["new_message"],
  },
  {
    groupLabel: "Conta e Anúncios",
    types: ["seller_verified", "listing_created", "listing_blocked"],
  },
];
