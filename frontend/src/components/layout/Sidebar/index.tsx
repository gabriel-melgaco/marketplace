import { useState, useEffect, useRef } from "react";
import { FaUserCircle } from "react-icons/fa";
import { CgClose } from "react-icons/cg";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export function Sidebar() {
  const [isOpen, setIsOpen] = useState(false);
  const { isAuthenticated, logout } = useAuth();
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  const menu = [
    { label: "Entrar", path: "/login" },
    { label: "Cadastrar", path: "/register" },
  ];

  const loggedMenu = [
    { label: "Minha Conta", path: "/profile" },
    { label: "Configurações", path: "/settings" },
  ];

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
      {/* Botão Avatar */}
      <button
        onClick={() => setIsOpen(true)}
        aria-label={isAuthenticated ? "Abrir menu da conta" : "Abrir menu"}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        className="focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-1 focus:ring-offset-transparent rounded-lg"
      >
        {isAuthenticated ? (
          <FaUserCircle className="w-8 h-8 md:w-10 md:h-10 text-text-primary cursor-pointer" aria-hidden="true" />
        ) : (
          <FaUserCircle className="w-8 h-8 md:w-10 md:h-10 md:hidden text-text-primary cursor-pointer" aria-hidden="true" />
        )}
      </button>

      {/* Overlay */}
      <div
        className={`
          fixed inset-0 z-40 bg-black/40 transition-opacity
          ${isOpen ? "opacity-100" : "opacity-0 pointer-events-none"}
        `}
        onClick={() => setIsOpen(false)}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="sidebar-heading"
        className={`
          fixed top-0 bottom-0 right-0 z-50
          w-1/2 md:w-1/4
          bg-white shadow-xl
          transform transition-transform duration-300
          ${isOpen ? "translate-x-0" : "translate-x-full"}
          flex flex-col
        `}
      >
        {/* Header do drawer */}
        <div className="flex items-center justify-between px-4 py-4 border-b">
          <span id="sidebar-heading" className="font-semibold text-lg text-gray-900">
            {isAuthenticated ? "Minha Conta" : "Menu"}
          </span>
          <button
            ref={closeButtonRef}
            onClick={() => setIsOpen(false)}
            aria-label="Fechar menu"
            className="w-9 h-9 flex items-center justify-center rounded-xl text-gray-500 hover:text-gray-900 hover:bg-gray-100 active:bg-gray-200 transition focus:outline-none focus:ring-2 focus:ring-blue-900/40"
          >
            <CgClose className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        {/* Conteúdo */}
        <nav className="flex-1 overflow-y-auto" aria-label="Menu da conta">
          {isAuthenticated ? (
            <>
              {loggedMenu.map((item) => (
                <Link
                  key={item.label}
                  to={item.path}
                  onClick={() => setIsOpen(false)}
                  className="block px-4 py-3 text-gray-800 hover:bg-secundary hover:text-text-primary transition cursor-pointer"
                >
                  {item.label}
                </Link>
              ))}

              <button
                onClick={() => {
                  logout();
                  setIsOpen(false);
                }}
                className="w-full text-left px-4 py-3 text-red-600 font-medium hover:bg-red-600 hover:text-white transition cursor-pointer"
              >
                Sair
              </button>
            </>
          ) : (
            <>
              {menu.map((item) => (
                <Link
                  key={item.label}
                  to={item.path}
                  onClick={() => setIsOpen(false)}
                  className="block px-4 py-3 text-gray-800 hover:bg-secundary hover:text-text-primary transition"
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
