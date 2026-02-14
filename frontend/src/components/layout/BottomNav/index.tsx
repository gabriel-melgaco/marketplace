import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Search,
  Menu,
  Plus,
  MessageCircle,
  Home,
  ShoppingBag,
  Package,
  Settings,
} from "lucide-react";

export function BottomNav() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();

  const handleSearch = () => {
    const term = window.prompt("Buscar produto por palavra-chave:");
    if (!term) return;

    const normalizedTerm = term.trim();
    if (!normalizedTerm) return;

    navigate(`/productlist?q=${encodeURIComponent(normalizedTerm)}`);
  };

  return (
    <div>
      {/* Menu Inferior */}
      <nav className="fixed bottom-0 left-0 right-0 bg-black border-t shadow-lg">
        <div className="max-w-7xl mx-auto flex justify-around items-center py-3">
          <Link
            to="/"
            className="flex flex-col items-center gap-1 text-white hover:text-blue-800 transition"
          >
            <Home size={24} />
            <span className="text-xs font-semibold">Início</span>
          </Link>

          <button
            onClick={handleSearch}
            className="flex flex-col items-center gap-1 text-white hover:text-blue-800 transition cursor-pointer"
          >
            <Search size={24} />
            <span className="text-xs">Busca</span>
          </button>

          <button className="group flex flex-col items-center gap-1 text-white transition cursor-pointer">
            <div
              className="w-12 h-12 bg-white transition rounded-full flex items-center justify-center -mt-6 shadow-lg
                  group-hover:bg-blue-900"
            >
              <Plus
                size={28}
                className="text-blue-900 transition group-hover:text-white"
              />
            </div>

            <span className="text-xs transition group-hover:text-blue-900">
              Anunciar
            </span>
          </button>

          <button className="flex flex-col items-center gap-1 text-white hover:text-blue-800 transition cursor-pointer">
            <MessageCircle size={24} />
            <span className="text-xs">Chat</span>
          </button>

          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex flex-col items-center gap-1 text-white hover:text-blue-800 transition relative cursor-pointer"
          >
            <Menu size={24} />
            <span className="text-xs">Menu</span>

            {menuOpen && (
              <div className="absolute bottom-full right-0 mb-2 w-56 bg-white rounded-lg shadow-xl py-2 text-gray-800 border">
                <button className="w-full px-4 py-3 text-left hover:bg-gray-100 flex items-center gap-3">
                  <ShoppingBag size={18} /> Minhas Vendas
                </button>
                <button className="w-full px-4 py-3 text-left hover:bg-gray-100 flex items-center gap-3">
                  <Package size={18} /> Minhas Compras
                </button>
                <button className="w-full px-4 py-3 text-left hover:bg-gray-100 flex items-center gap-3">
                  <Settings size={18} /> Painel Administrativo
                </button>
              </div>
            )}
          </button>
        </div>
      </nav>
    </div>
  );
}
