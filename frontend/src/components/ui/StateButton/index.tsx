import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, X } from "lucide-react";
import { BRAZILIAN_STATES } from "@/constants/brazilianStates";

interface StateButtonProps {
  /** Currently selected state UF (2-letter code like "SP", "RJ") */
  selectedState?: string;
}

export function StateButton({ selectedState }: StateButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const handleSelectState = (uf: string) => {
    setIsOpen(false);
    navigate(`/estado/${uf}`);
  };

  const handleClearState = () => {
    setIsOpen(false);
    navigate("/");
  };

  const currentStateName = selectedState
    ? BRAZILIAN_STATES.find((s) => s.uf === selectedState)?.name
    : null;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 bg-white border-2 border-gray-300 rounded-lg hover:bg-gray-50 transition"
      >
        {currentStateName ? (
          <>
            {currentStateName}
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleClearState();
              }}
              className="ml-1 p-0.5 rounded-full hover:bg-gray-200 transition"
              aria-label="Limpar estado"
            >
              <X size={14} />
            </button>
          </>
        ) : (
          <>
            Estado <ChevronDown size={20} />
          </>
        )}
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-64 max-h-80 overflow-y-auto bg-white rounded-xl shadow-lg border border-gray-200 z-50">
          {BRAZILIAN_STATES.map((state) => (
            <button
              key={state.uf}
              onClick={() => handleSelectState(state.uf)}
              className={`w-full text-left px-4 py-2.5 text-sm hover:bg-blue-50 transition flex items-center justify-between ${
                selectedState === state.uf
                  ? "bg-blue-50 text-blue-800 font-semibold"
                  : "text-gray-700"
              }`}
            >
              <span>{state.name}</span>
              <span className="text-gray-400 text-xs">{state.uf}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
