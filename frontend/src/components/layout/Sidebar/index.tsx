import { useState } from "react";
import { FaUserCircle } from "react-icons/fa";
import { CgClose } from "react-icons/cg";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export function Sidebar() {
  const [isOpen, setIsOpen] = useState(false);
  const { isAuthenticated, logout } = useAuth();

  const menu = [
    { label: "Entrar", path: "/login" },
    { label: "Cadastrar", path: "/register" },
  ];

  const loggedMenu = [
    { label: "Minha Conta", path: "/profile" },
    { label: "Configurações", path: "/settings" },
  ];

  return (
    <>
      {/* Botão Avatar */}
      <button onClick={() => setIsOpen(true)}>
        {isAuthenticated ? (
          <FaUserCircle className="w-8 h-8 md:w-10 md:h-10 text-text-primary cursor-pointer" />
        ) : (
          <FaUserCircle className="w-8 h-8 md:w-10 md:h-10 md:hidden text-text-primary cursor-pointer" />
        )}
      </button>

      {/* Overlay */}
      <div
        className={`
          fixed inset-0 z-40 bg-black/40 transition-opacity
          ${isOpen ? "opacity-100" : "opacity-0 pointer-events-none"}
        `}
        onClick={() => setIsOpen(false)}
      />

      {/* Drawer */}
      <aside
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
          <span className="font-semibold text-lg"></span>
          <button onClick={() => setIsOpen(false)}>
            <CgClose className="w-8 h-8 cursor-pointer  " />
          </button>
        </div>

        {/* Conteúdo */}
        <nav className="flex-1 overflow-y-auto">
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
                className="w-full text-left px-4 py-3 text-red-600 text-bold hover:bg-red-600 hover:text-white transition cursor-pointer"
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
