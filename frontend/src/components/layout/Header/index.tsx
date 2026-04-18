import type { HTMLAttributes } from "react";
import { Link } from "react-router-dom";
import Logo from "@/assets/logo1.png";
import { Sidebar } from "@/components/layout/Sidebar";
import { CartDrawer } from "@/components/layout/CartDrawer";
import { useAuth } from "@/contexts/AuthContext";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { useChatContext } from "@/contexts/ChatContext";

interface HeaderProps extends HTMLAttributes<HTMLDivElement> {}

function Header(props: HeaderProps) {
  const { isAuthenticated } = useAuth();
  const { totalUnread } = useChatContext();

  return (
    <header className="flex-shrink-0 sticky top-0 left-0 w-full z-50 bg-bg-1 border-b border-white/10 shadow-[0_1px_0_rgba(245,158,11,0.08)]">
      <nav
        {...props}
        className={`max-w-7xl mx-auto h-14 md:h-16 flex items-center justify-between px-4 sm:px-6 ${props.className ?? ""}`}
      >
        <Link to="/" aria-label="Página inicial">
          <img
            src={Logo}
            alt="Logo"
            className="h-8 md:h-10 w-auto object-contain"
          />
        </Link>

        {isAuthenticated ? (
          <div className="flex items-center gap-3 md:gap-5">
            <NotificationBell />
            {/* Chat messages link */}
            <Link
              to="/conversations"
              aria-label={`Mensagens${totalUnread > 0 ? ` — ${totalUnread} não lidas` : ''}`}
              className="relative p-2 rounded-xl hover:bg-bg-2 border border-transparent hover:border-white/[0.12] text-ink-2 hover:text-ink-1 transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-1 focus-visible:ring-offset-transparent"
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
                  d="M2.25 12.76c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.076-4.076a1.526 1.526 0 011.037-.443 48.282 48.282 0 005.68-.494c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"
                />
              </svg>
              {totalUnread > 0 && (
                <span
                  aria-hidden="true"
                  className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-gold text-gold-deep ring-2 ring-bg-0 text-[10px] font-bold leading-none"
                >
                  {totalUnread > 99 ? '99+' : totalUnread}
                </span>
              )}
            </Link>
            <CartDrawer />
            <Sidebar />
          </div>
        ) : (
          <div className="flex items-center gap-3 md:gap-4">
            <Link
              to="/login"
              className="hidden md:inline-flex text-sm font-medium text-ink-2 hover:text-ink-1 transition-colors"
            >
              Entrar
            </Link>

            <Link
              to="/register"
              className="hidden md:inline-flex items-center px-4 py-2 text-sm font-semibold bg-gold text-gold-deep rounded-lg hover:bg-gold/90 transition-colors"
            >
              Cadastrar
            </Link>

            <Sidebar />
          </div>
        )}
      </nav>

    </header>
  );
}

export default Header;
