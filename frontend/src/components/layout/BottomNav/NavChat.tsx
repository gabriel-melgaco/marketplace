import { useNavigate } from "react-router-dom";
import { MessageCircle } from "lucide-react";

export function NavChat() {
  const navigate = useNavigate();

  return (
    <button
      onClick={() => navigate("/chat")}
      className="flex flex-col items-center gap-1 text-white hover:text-blue-800 transition cursor-pointer"
    >
      <MessageCircle size={24} />
      <span className="text-xs">Chat</span>
    </button>
  );
}
