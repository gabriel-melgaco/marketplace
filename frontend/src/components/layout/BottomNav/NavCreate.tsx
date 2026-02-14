import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";

export function NavCreate() {
  const navigate = useNavigate();

  return (
    <button
      onClick={() => navigate("/create-listing")}
      className="group flex flex-col items-center gap-1 text-white transition cursor-pointer"
    >
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
  );
}
