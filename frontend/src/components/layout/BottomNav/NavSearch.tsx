import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";

export function NavSearch() {
  const navigate = useNavigate();

  const handleSearch = () => {
    const term = window.prompt("Buscar produto por palavra-chave:");
    if (!term) return;

    const normalizedTerm = term.trim();
    if (!normalizedTerm) return;

    navigate(`/productlist?q=${encodeURIComponent(normalizedTerm)}`);
  };

  return (
    <button
      onClick={handleSearch}
      className="flex flex-col items-center gap-1 text-white hover:text-blue-800 transition cursor-pointer"
    >
      <Search size={24} />
      <span className="text-xs">Busca</span>
    </button>
  );
}
