import { useState, useEffect } from "react";
import type { HTMLAttributes } from "react";
import { Link, useLocation } from "react-router-dom";
import axios from "@/api/axios";
import Logo from "@/assets/logo1.png";
import { Sidebar } from "@/components/layout/Sidebar";
import { CartDrawer } from "@/components/layout/CartDrawer";
import { useAuth } from "@/contexts/AuthContext";
import type { ProductCategory } from "@/types/product";
import { FaBell } from "react-icons/fa";

interface HeaderProps extends HTMLAttributes<HTMLDivElement> {}

function Header(props: HeaderProps) {
  const [categories, setCategories] = useState<ProductCategory[]>([]);
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  useEffect(() => {
    async function fetchCategories() {
      try {
        const response = await axios.get<{
          count: number;
          next: string | null;
          results: ProductCategory[];
        }>("/products/categories/");
        setCategories(response.data.results);
      } catch (error) {
        console.error("Erro ao buscar categorias:", error);
      }
    }
    fetchCategories();
  }, []);

  return (
    <header className="sticky top-0 left-0 w-full z-50 bg-header shadow-lg">
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
            <button
              aria-label="Notificações"
              className="relative text-text-primary focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-1 focus:ring-offset-transparent rounded-lg"
            >
              <FaBell className="w-6 h-6 md:w-7 md:h-7" aria-hidden="true" />
            </button>
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
