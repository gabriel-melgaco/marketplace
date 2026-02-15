import { Link } from "react-router-dom";
import { Home } from "lucide-react";

export function NavHome() {
  return (
    <Link
      to="/"
      className="flex flex-col items-center gap-1 text-white hover:text-blue-800 transition"
    >
      <Home size={24} />
      <span className="text-xs font-semibold">Início</span>
    </Link>
  );
}
