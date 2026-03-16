import { useState, useEffect } from "react";
import type { HTMLAttributes } from "react";
import { Link, useLocation } from "react-router-dom";
import { productService } from "@/services/productService";
import Logo from "@/assets/logo1.png";
import { Sidebar } from "@/components/layout/Sidebar";
import { CartDrawer } from "@/components/layout/CartDrawer";
import { useAuth } from "@/contexts/AuthContext";
import type { CategorySimple } from "@/types/product";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { useChatContext } from "@/contexts/ChatContext";

interface HeaderProps extends HTMLAttributes<HTMLDivElement> {}

function Header(props: HeaderProps) {
  const [categories, setCategories] = useState<CategorySimple[]>([]);
  const { isAuthenticated } = useAuth();
  const { totalUnread } = useChatContext();
  const location = useLocation();

  useEffect(() => {
    async function fetchCategories() {
      try {
        const data = await productService.getListings({ page_size: 100 });
        const seen = new Set<string>();
        const unique: CategorySimple[] = [];
        for (const listing of data.results) {
          const cat = listing.category;
          if (cat && !seen.has(cat.slug)) {
            seen.add(cat.slug);
            unique.push(cat);
          }
        }
        setCategories(unique);
      } catch (error) {
        console.error("Erro ao buscar categorias:", error);
      }
    }
    fetchCategories();
  }, []);

  return (
    <header className="flex-shrink-0 sticky top-0 left-0 w-full z-50 bg-header shadow-lg">
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
              className="relative text-text-primary focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-1 focus:ring-offset-transparent rounded-lg"
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
                  className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold leading-none"
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
              className="hidden md:inline-flex text-sm font-medium text-text-primary hover:text-secundary transition-colors"
            >
              Entrar
            </Link>

            <Link
              to="/register"
              className="hidden md:inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-secundary rounded-lg hover:bg-secundary/80 transition-colors"
            >
              Cadastrar
            </Link>

            <Sidebar />
          </div>
        )}
      </nav>

      {categories.length > 0 && (
        <div className="border-t border-white">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 py-2">
            <div className="flex md:justify-center gap-2 overflow-x-auto no-scrollbar">
              {categories.map((category) => {
                const isActive =
                  location.pathname === "/products" &&
                  location.search.includes(`category=${category.slug}`);
                return (
                  <Link
                    to={`/products?category=${category.slug}`}
                    key={category.id}
                    className={`px-3 py-1.5 text-s rounded whitespace-nowrap transition-colors ${
                      isActive
                        ? "bg-white text-header font-semibold"
                        : "bg-blue-900 text-white hover:bg-white/20"
                    }`}
                  >
                    {category.name}
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

export default Header;
