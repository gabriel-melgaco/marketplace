import { useState } from "react";
import { Menu, ShoppingBag, Package, Settings } from "lucide-react";

export function NavMenu() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
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
  );
}
