import { useState, useEffect, useRef } from "react";
import { FaUserCircle } from "react-icons/fa";
import { CgClose } from "react-icons/cg";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { toPublicUrl } from "@/services/storageService";

// Module-level constants — defined outside component to avoid per-render allocation
const GUEST_MENU = [
  { label: "Entrar", path: "/login" },
  { label: "Cadastrar", path: "/register" },
];

const AUTH_MENU = [
  { label: "Mensagens", path: "/conversations" },
  { label: "Minha Conta", path: "/account" },
];

export function Sidebar() {
  const [isOpen, setIsOpen] = useState(false);
  const { isAuthenticated, logout, user } = useAuth();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const asideRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", handleEscape);
      // When closing, return focus to the trigger if focus is still inside the drawer.
      // This prevents the "aria-hidden on focused descendant" browser warning.
      if (asideRef.current?.contains(document.activeElement)) {
        triggerRef.current?.focus();
      }
    };
  }, [isOpen]);

  return (
    <>
      {/* Botão Avatar */}
      <button
        ref={triggerRef}
        onClick={() => setIsOpen(true)}
        aria-label={isAuthenticated ? "Abrir menu da conta" : "Abrir menu"}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        className="focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 rounded-lg"
      >
        {isAuthenticated ? (
          user?.picture ? (
            <img
              src={toPublicUrl(user.picture)}
              alt={user.full_name ?? "Avatar"}
              className="w-8 h-8 md:w-10 md:h-10 rounded-full object-cover cursor-pointer"
            />
          ) : (
            <FaUserCircle className="w-8 h-8 md:w-10 md:h-10 text-ink-2 cursor-pointer" aria-hidden="true" />
          )
        ) : (
          // md:hidden because the desktop header renders its own login link;
          // the avatar button is only needed on mobile when unauthenticated.
          <FaUserCircle className="w-8 h-8 md:w-10 md:h-10 md:hidden text-ink-2 cursor-pointer" aria-hidden="true" />
        )}
      </button>

      {/* Overlay */}
      <div
        className={`
          fixed inset-0 z-40 bg-black/60 transition-opacity
          ${isOpen ? "opacity-100" : "opacity-0 pointer-events-none"}
        `}
        onClick={() => setIsOpen(false)}
        aria-hidden="true"
      />

      {/* Drawer — aria-hidden when closed so screen readers cannot navigate into it */}
      <aside
        ref={asideRef}
        role="dialog"
        aria-modal="true"
        aria-label="Menu da conta"
        aria-hidden={!isOpen}
        className={`
          fixed top-0 bottom-0 right-0 z-50
          w-1/2 md:w-1/4
          bg-bg-1 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]
          transform transition-transform duration-300
          ${isOpen ? "translate-x-0" : "translate-x-full"}
          flex flex-col
        `}
      >
        {/* Header do drawer */}
        <div className="flex items-center justify-end px-4 py-4 border-b border-white/10">
          <button
            ref={closeButtonRef}
            onClick={() => setIsOpen(false)}
            aria-label="Fechar menu"
            className="w-9 h-9 flex items-center justify-center rounded-xl text-ink-3 hover:text-ink-1 hover:bg-bg-3 active:bg-bg-3 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40"
          >
            <CgClose className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        {/* Bloco de perfil do usuário autenticado */}
        {isAuthenticated && (
          <div className="px-4 py-4 border-b border-white/10 flex items-center gap-3">
            {user?.picture ? (
              <img
                className="rounded-full w-10 h-10 object-cover flex-shrink-0"
                src={toPublicUrl(user.picture)}
                alt={user.full_name ?? "Avatar"}
              />
            ) : (
              <FaUserCircle className="w-10 h-10 flex-shrink-0 text-ink-3" aria-hidden="true" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink-1 truncate">
                {user?.full_name ?? "Usuário"}
              </p>
              <p className="text-xs text-ink-3 truncate">
                {user?.email ?? ""}
              </p>
            </div>
          </div>
        )}

        {/* Conteúdo */}
        <nav className="flex-1 overflow-y-auto" aria-label="Navegação da conta">
          {isAuthenticated ? (
            <>
              {AUTH_MENU.map((item) => (
                <Link
                  key={item.label}
                  to={item.path}
                  onClick={() => setIsOpen(false)}
                  className="block px-4 py-3 text-ink-2 hover:bg-bg-3 hover:text-ink-1 transition-colors border-b border-white/[0.06] cursor-pointer"
                >
                  {item.label}
                </Link>
              ))}

              <button
                type="button"
                onClick={() => {
                  logout();
                  setIsOpen(false);
                }}
                className="w-full text-left px-4 py-3 text-red-400 font-medium hover:bg-red-500/10 hover:text-red-300 transition-colors cursor-pointer"
              >
                Sair
              </button>
            </>
          ) : (
            <>
              {GUEST_MENU.map((item) => (
                <Link
                  key={item.label}
                  to={item.path}
                  onClick={() => setIsOpen(false)}
                  className="block px-4 py-3 text-ink-2 hover:bg-bg-3 hover:text-ink-1 transition-colors border-b border-white/[0.06]"
                >
                  {item.label}
                </Link>
              ))}
            </>
          )}
        </nav>
      </aside>
    </>
  );
}
