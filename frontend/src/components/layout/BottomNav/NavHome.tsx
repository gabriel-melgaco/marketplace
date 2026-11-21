import { NavLink } from "react-router-dom";
import { Home } from "lucide-react";

export function NavHome() {
  return (
    <NavLink
      to="/"
      end
      className={({ isActive }) =>
        `flex flex-col items-center gap-[3px] text-[10.5px] font-medium p-1 transition-colors duration-150 ${
          isActive ? "text-ink-1" : "text-ink-3 hover:text-ink-2"
        }`
      }
    >
      <Home size={20} strokeWidth={2} />
      <span>Início</span>
    </NavLink>
  );
}
