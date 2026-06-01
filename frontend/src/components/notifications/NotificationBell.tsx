import React, { useRef, useState, useEffect } from "react";
import { useNotificationContext } from "@/contexts/NotificationContext";
import { NotificationList } from "./NotificationList";

interface NotificationBellProps {
  className?: string;
}

export function NotificationBell({ className = "" }: NotificationBellProps) {
  const { unreadCount, isConnected } = useNotificationContext();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const bellButtonRef = useRef<HTMLButtonElement>(null);
  const [mobileTop, setMobileTop] = useState("70px");

  // Calcula posição do painel mobile dinamicamente
  useEffect(() => {
    if (isOpen && bellButtonRef.current) {
      const rect = bellButtonRef.current.getBoundingClientRect();
      setMobileTop(`${rect.bottom + 12}px`);
    }
  }, [isOpen]);

  // Click fora + ESC
  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setIsOpen(false);
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        ref={bellButtonRef}
        type="button"
        aria-label={`Notificações${unreadCount > 0 ? ` — ${unreadCount} não lidas` : ""}`}
        aria-haspopup="true"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((prev) => !prev)}
        className="relative text-ink-2 p-2 rounded-xl border border-transparent hover:bg-bg-2 hover:border-white/[0.12] hover:text-ink-1 transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-6 h-6 md:w-7 md:h-7"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"
          />
        </svg>

        {unreadCount > 0 && (
          <span
            aria-hidden="true"
            className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-gold text-gold-deep ring-2 ring-bg-0 text-[10px] font-bold leading-none"
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}

        <span
          aria-hidden="true"
          title={isConnected ? "Conectado" : "Desconectado"}
          className={`absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border border-bg-1 ${
            isConnected ? "bg-green-400" : "bg-gray-400"
          }`}
        />
      </button>

      {isOpen && (
        <>
          {/* ── MOBILE: fixed, centralizado na tela ── */}
          <div
            className="sm:hidden fixed left-4 right-4 z-50"
            style={{ top: mobileTop }}
          >
            <div
              aria-hidden="true"
              className="absolute right-4 -top-2.25 w-4 h-4 bg-bg-1 border-l border-t border-white/10 rotate-45 z-10"
            />
            <div
              role="dialog"
              aria-modal="true"
              aria-label="Painel de notificações"
              className="relative bg-bg-1 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] border border-white/10 flex flex-col overflow-hidden max-h-[75vh]"
            >
              <NotificationList onClose={() => setIsOpen(false)} />
            </div>
          </div>

          {/* ── DESKTOP: absolute à direita do sino, largura generosa ── */}
          <div className="hidden sm:block absolute right-0 top-full mt-3 z-50 w-105">
            <div
              aria-hidden="true"
              className="absolute right-3 -top-2.25 w-4 h-4 bg-bg-1 border-l border-t border-white/10 rotate-45 z-10"
            />
            <div
              role="dialog"
              aria-modal="true"
              aria-label="Painel de notificações"
              className="relative bg-bg-1 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] border border-white/10 flex flex-col overflow-hidden max-h-[70vh]"
            >
              <NotificationList onClose={() => setIsOpen(false)} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
