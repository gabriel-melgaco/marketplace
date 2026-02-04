import { useState } from "react";
import type { HTMLAttributes } from "react";
import { Link } from "react-router-dom";
import { TiShoppingCart } from "react-icons/ti";
import Logo from "@/assets/logo1.png";
import { Sidebar } from "@/components/layout/Sidebar";
import { useAuth } from "@/contexts/AuthContext";

interface HeaderProps extends HTMLAttributes<HTMLDivElement> {}

function Header(props: HeaderProps) {
  const [selectedCategory, setSelectedCategory] = useState("Todos");

  const { isAuthenticated } = useAuth();

  const categories = [
    "Cardio",
    "Musculação",
    "Pesos Livres",
    "Funcional & Cross Training",
  ];

  return (
    <header className="sticky top-0 left-0 w-full z-50 bg-header transition-all duration-300">
      <div
        {...props}
        className={`max-w-7xl mx-auto h-14 md:h-18 flex items-center justify-between px-4 ${props.className ?? ""}`}
      >
        <Link to="/">
          <img src={Logo} alt="Logo" className="w-32 md:w-40 cursor-pointer" />
        </Link>

        {isAuthenticated ? (
          <div className="flex items-center gap-6 justify-center">
            <Sidebar />
            <TiShoppingCart className="text-white w-8 h-8 md:w-10 md:h-10 mb-1" />
          </div>
        ) : (
          <div className="flex items-center gap-4">
            <Link to="/login">
              <p className="text-text-primary underline text-lg cursor-pointer hidden md:block">
                Entrar
              </p>
            </Link>

            <Link to="/register">
              <p className="bg-secundary px-4 py-2 text-lg text-white hover:bg-white hover:text-secundary rounded-lg cursor-pointer hidden md:block">
                Cadastrar
              </p>
            </Link>

            <Sidebar />
          </div>
        )}
      </div>

      {/* categorias */}
      <div className="px-4 py-6 border-t-4 border-t-amber-100 border">
        <div className="max-w-7xl mx-auto flex md:justify-center gap-4 overflow-x-auto no-scrollbar">
          {categories.map((category) => (
            <button
              key={category}
              onClick={() => setSelectedCategory(category)}
              className={`px-4 py-2 rounded-lg whitespace-nowrap transition flex items-center gap-2 cursor-pointer ${
                selectedCategory === category
                  ? "bg-white text-blue-900 font-semibold"
                  : "bg-blue-900 text-white hover:bg-blue-600"
              }`}
            >
              {category === "Cardio"}
              {category === "Musculação"}
              {category === "Pesos Livres"}
              {category === "Funcional & Cross Training"}
              {category}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

export default Header;
