import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useNotificationContext } from "@/contexts/NotificationContext";
import type { Notification } from "@/types/notifications";
import {
  formatNotificationDate,
  getNotificationMeta,
} from "@/utils/notificationUtils";

interface NotificationListProps {
  onClose?: () => void;
}

export function NotificationList({ onClose }: NotificationListProps) {
  const {
    notifications,
    isLoading,
    hasMore,
    markAsRead,
    markAllAsRead,
    loadMore,
  } = useNotificationContext();

  const [selected, setSelected] = useState<Notification | null>(null);

  // Tick every minute so relative timestamps stay up-to-date
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  // Prevent double-click on "mark all" during in-flight request
  const [isMarkingAll, setIsMarkingAll] = useState(false);
  const handleMarkAllAsRead = async () => {
    if (isMarkingAll) return;
    setIsMarkingAll(true);
    try {
      await markAllAsRead();
    } finally {
      setIsMarkingAll(false);
    }
  };

  const observerRef = useRef<IntersectionObserver | null>(null);
  const sentinelRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (observerRef.current) observerRef.current.disconnect();
      // Do not observe when list is empty — avoids firing loadMore before
      // the initial load completes, which would cause the loading loop.
      if (!node || !hasMore || notifications.length === 0) return;
      observerRef.current = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting && hasMore && !isLoading) {
            loadMore();
          }
        },
        { threshold: 0.1 },
      );
      observerRef.current.observe(node);
    },
    [hasMore, isLoading, loadMore, notifications.length],
  );

  const unreadNotifications = notifications.filter((n) => !n.is_read);

  return (
    <>
      <div className="flex flex-col flex-1 min-h-0">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
          <h2 className="text-sm font-semibold text-ink-1">
            Notificações
            {unreadNotifications.length > 0 && (
              <span className="ml-2 text-xs font-normal text-ink-3">
                ({unreadNotifications.length} não{" "}
                {unreadNotifications.length === 1 ? "lida" : "lidas"})
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            {unreadNotifications.length > 0 && (
              <button
                type="button"
                onClick={handleMarkAllAsRead}
                disabled={isMarkingAll}
                aria-label="Marcar todas as notificações como lidas"
                className="text-xs text-gold hover:text-gold/80 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Marcar todas como lidas
              </button>
            )}
            {onClose && (
              <button
                type="button"
                aria-label="Fechar notificações"
                onClick={onClose}
                className="p-1 rounded hover:bg-bg-3 text-ink-3 hover:text-ink-1"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            )}
          </div>
        </div>

        <div className="overflow-y-auto flex-1 min-h-0">
          {/* Initial loading spinner — only when list is still empty */}
          {isLoading && notifications.length === 0 && (
            <div className="flex justify-center py-8">
              <div
                role="status"
                aria-label="Carregando notificações"
                className="h-5 w-5 rounded-full border-2 border-gold border-t-transparent animate-spin"
              />
            </div>
          )}

          {/* Empty state — only shown after loading completes with no results */}
          {notifications.length === 0 && !isLoading && (
            <div className="flex flex-col items-center justify-center py-12 text-ink-3">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-10 w-10 mb-2"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                />
              </svg>
              <p className="text-sm">Nenhuma notificação por aqui</p>
            </div>
          )}

          {notifications.map((notification) => (
            <NotificationItem
              key={notification.id}
              notification={notification}
              now={now}
              onMarkRead={() => markAsRead(notification.id)}
              onClose={onClose}
              onSelect={setSelected}
            />
          ))}

          {hasMore && <div ref={sentinelRef} className="h-4" />}

          {/* Pagination spinner — only when appending to an existing list */}
          {isLoading && notifications.length > 0 && (
            <div className="flex justify-center py-4">
              <div
                role="status"
                aria-label="Carregando mais notificações"
                className="h-5 w-5 rounded-full border-2 border-gold border-t-transparent animate-spin"
              />
            </div>
          )}

          {!hasMore && notifications.length > 0 && (
            <p className="text-center text-xs text-ink-3 py-4">
              Fim das notificações
            </p>
          )}
        </div>
      </div>

      <NotificationDetailDrawer
        notification={selected}
        onClose={() => setSelected(null)}
        onMarkRead={(id) => markAsRead(id)}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// NotificationItem
// ---------------------------------------------------------------------------

interface NotificationItemProps {
  notification: Notification;
  now: Date;
  onMarkRead: () => Promise<void>;
  onClose?: () => void;
  onSelect: (notification: Notification) => void;
}

function NotificationItem({
  notification,
  now,
  onMarkRead,
  onClose,
  onSelect,
}: NotificationItemProps) {
  const navigate = useNavigate();
  const meta = getNotificationMeta(notification.notification_type);
  const route = meta.route?.(notification.metadata);

  const handleClick = async () => {
    if (!notification.is_read) {
      await onMarkRead();
    }
    if (route) {
      navigate(route);
      onClose?.();
    } else {
      onSelect(notification);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`w-full text-left flex gap-3 px-4 py-3 hover:bg-bg-3 transition-colors border-b border-white/[0.06] ${
        !notification.is_read ? "bg-gold/5" : ""
      }`}
      aria-label={`${notification.title}${notification.is_read ? " (lida)" : " (não lida)"}`}
    >
      <div
        className={`flex-shrink-0 h-9 w-9 rounded-full flex items-center justify-center ${meta.bgClass}`}
        aria-hidden="true"
      >
        <span className={`text-xs font-bold ${meta.colorClass}`}>
          {meta.label.charAt(0)}
        </span>
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-1">
          <p
            className={`text-sm leading-snug ${notification.is_read ? "text-ink-2 font-normal" : "text-ink-1 font-semibold"}`}
          >
            {notification.title}
          </p>
          {!notification.is_read && (
            <span
              aria-hidden="true"
              className="flex-shrink-0 mt-1 h-2 w-2 rounded-full bg-gold"
            />
          )}
        </div>
        <p className="text-xs text-ink-2 mt-0.5 line-clamp-2">
          {notification.body}
        </p>
        <p className="text-xs text-ink-3 mt-1">
          {formatNotificationDate(notification.created_at, now)}
        </p>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// NotificationDetailDrawer
// ---------------------------------------------------------------------------

interface NotificationDetailDrawerProps {
  notification: Notification | null;
  onClose: () => void;
  onMarkRead: (id: string) => Promise<void>;
}

function NotificationDetailDrawer({
  notification,
  onClose,
  onMarkRead,
}: NotificationDetailDrawerProps) {
  const meta = notification
    ? getNotificationMeta(notification.notification_type)
    : null;

  // Mark as read when the drawer opens for an unread notification
  useEffect(() => {
    if (notification && !notification.is_read) {
      onMarkRead(notification.id).catch(() => {
        // Non-critical: drawer still opens even if the API call fails
      });
    }
    // Only re-run when the notification identity changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notification?.id]);

  // Close on ESC
  useEffect(() => {
    if (!notification) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [notification, onClose]);

  if (!notification) return null;

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black/50 z-[59]"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside
        role="dialog"
        aria-modal={true}
        aria-labelledby="notif-detail-title"
        className="fixed top-0 bottom-0 right-0 z-[60] w-full sm:w-96 bg-bg-1 border-l border-white/10 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] flex flex-col transform transition-transform duration-300 translate-x-0"
      >
        {/* Header */}
        <div className="flex justify-between items-start px-5 py-4 border-b border-white/10">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className={`w-10 h-10 flex-shrink-0 bg-gold/10 border border-gold/30 rounded-xl flex items-center justify-center ${meta?.bgClass ?? ""}`}
              aria-hidden="true"
            >
              <span className={`text-sm font-bold ${meta?.colorClass ?? "text-ink-3"}`}>
                {meta?.label.charAt(0) ?? "N"}
              </span>
            </div>
            <h2
              id="notif-detail-title"
              className="font-display text-base font-semibold text-ink-1 truncate"
            >
              {notification.title}
            </h2>
          </div>
          <button
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center hover:bg-bg-3 text-ink-3 hover:text-ink-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <p className="text-sm text-ink-2 leading-relaxed whitespace-pre-wrap">
            {notification.body}
          </p>
          <p className="text-xs text-ink-3 mt-3">
            {formatNotificationDate(notification.created_at)}
          </p>
        </div>
      </aside>
    </>
  );
}
