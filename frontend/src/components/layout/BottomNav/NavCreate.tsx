import { NavLink } from "react-router-dom";
import { Plus } from "lucide-react";

export function NavCreate() {
  return (
    <NavLink
      to="/create-listing"
      className="relative flex flex-col items-center gap-0.75 text-[10.5px] font-medium text-ink-1 p-1"
    >
      <div
        className="absolute -top-6.5 w-13 h-13 rounded-full bg-gold flex items-center justify-center text-gold-deep ring-[6px] ring-bg-0"
        style={{ boxShadow: "var(--shadow-gold-glow)" }}
      >
        <Plus size={22} strokeWidth={2.5} />
      </div>
      <span className="mt-7.5">Anunciar</span>
    </NavLink>
  );
}
