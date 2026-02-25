import { useState, useEffect } from "react";
import type { HTMLAttributes } from "react";
import { Link } from "react-router-dom";
import axios from "@/api/axios";
import { TiShoppingCart } from "react-icons/ti";
import Logo from "@/assets/logo1.png";
import { Sidebar } from "@/components/layout/Sidebar";
import { useAuth } from "@/contexts/AuthContext";
import type { ProductCategory } from "@/types/product";

interface HeaderProps extends HTMLAttributes<HTMLDivElement> {}

function Header(props: HeaderProps) {
  const [selectedCategory, setSelectedCategory] = useState("Todos");
  const [categories, setCategories] = useState<ProductCategory[]>([]);

  const { isAuthenticated } = useAuth();

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
            <Link
              to="/cart"
              aria-label="Carrinho de compras"
              className="relative text-text-primary hover:text-secundary transition-colors"
            >
              <TiShoppingCart className="w-7 h-7 md:w-8 md:h-8" />
            </Link>
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
              {categories.map((category) => (
                <Link
                  to={`/products?category=${category.slug}`}
                  key={category.id}
                  onClick={() => setSelectedCategory(category.name)}
                  className={`px-3 py-1.5 text-s rounded whitespace-nowrap transition-colors ${
                    selectedCategory === category.name
                      ? "bg-white text-header font-semibold"
                      : "bg-blue-900 text-white hover:bg-white/20"
                  }`}
                >
                  {category.name}
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

export default Header;
