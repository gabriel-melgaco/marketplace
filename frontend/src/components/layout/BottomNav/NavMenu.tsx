import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { Menu, ShoppingBag, Package, LayoutDashboard } from "lucide-react";
import { CgClose } from "react-icons/cg";
import { ROUTES } from "@/routes/routePaths";

const menuItems = [
  { label: "Minhas Vendas", path: ROUTES.MY_SALES, icon: ShoppingBag },
  { label: "Minhas Compras", path: ROUTES.MY_PURCHASES, icon: Package },
  { label: "Painel Administrativo", path: ROUTES.DASHBOARD, icon: LayoutDashboard },
];

export function NavMenu() {
  const [isOpen, setIsOpen] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

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
    };
  }, [isOpen]);

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="flex flex-col items-center gap-[3px] text-[10.5px] font-medium p-1 transition-colors duration-150 text-ink-3 hover:text-ink-2 cursor-pointer"
        aria-label="Abrir menu"
        aria-expanded={isOpen}
      >
        <Menu size={20} strokeWidth={2} />
        <span>Menu</span>
      </button>

      {createPortal(
        <>
          {/* Overlay */}
          <div
            className={`
              fixed inset-0 z-[9998] bg-black/40 transition-opacity
              ${isOpen ? "opacity-100" : "opacity-0 pointer-events-none"}
            `}
            onClick={() => setIsOpen(false)}
            aria-hidden="true"
          />

          {/* Drawer */}
          <aside
            role="dialog"
            aria-modal="true"
            aria-labelledby="nav-menu-heading"
            className={`
              fixed top-0 bottom-0 right-0 z-[9999]
              w-3/5 md:w-1/2 lg:w-1/4
              bg-white shadow-xl
              transform transition-transform duration-300
              ${isOpen ? "translate-x-0" : "translate-x-full"}
              flex flex-col
            `}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-4 border-b">
              <span id="nav-menu-heading" className="font-semibold text-lg">
                Menu
              </span>
              <button
                ref={closeButtonRef}
                onClick={() => setIsOpen(false)}
                aria-label="Fechar menu"
              >
                <CgClose className="w-8 h-8" />
              </button>
            </div>

            {/* Menu items */}
            <nav className="flex-1 overflow-y-auto" aria-label="Menu principal">
              {menuItems.map((item) => (
                <Link
                  key={item.label}
                  to={item.path}
                  onClick={() => setIsOpen(false)}
                  className="flex items-center gap-3 px-4 py-3 text-gray-800 hover:bg-secundary hover:text-text-primary transition"
                >
                  <item.icon size={18} aria-hidden="true" />
                  {item.label}
                </Link>
              ))}
            </nav>
          </aside>
        </>,
        document.body,
      )}
    </>
  );
}
