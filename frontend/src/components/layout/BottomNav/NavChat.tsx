import { NavLink } from "react-router-dom";
import { MessageCircle } from "lucide-react";

export function NavChat() {
  return (
    <NavLink
      to="/chat"
      className={({ isActive }) =>
        `flex flex-col items-center gap-[3px] text-[10.5px] font-medium p-1 transition-colors duration-150 ${
          isActive ? "text-ink-1" : "text-ink-3 hover:text-ink-2"
        }`
      }
    >
      <MessageCircle size={20} strokeWidth={2} />
      <span>Chat</span>
    </NavLink>
  );
}
