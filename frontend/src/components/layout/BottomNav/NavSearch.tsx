import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";

export function NavSearch() {
  const navigate = useNavigate();

  const handleSearch = async () => {
    try {
      // Dynamically import SweetAlert2 to avoid adding it to the initial bundle
      const Swal = (await import("sweetalert2")).default;

      const { value: term } = await Swal.fire({
        title: "Buscar produto",
        html: '<div class="flex items-center justify-center gap-2 mb-2"><svg class="w-5 h-5 text-blue-900" fill="currentColor" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg></div>',
        input: "text",
        inputPlaceholder: "Digite uma palavra-chave...",
        showCancelButton: true,
        confirmButtonText: "Buscar",
        cancelButtonText: "Cancelar",
        confirmButtonColor: "#1e3a8a",
        cancelButtonColor: "#9ca3af",
        inputValidator: (value: string | null) => {
          if (!value?.trim()) {
            return "Digite algo para buscar";
          }
        },
        customClass: {
          popup: "rounded-2xl shadow-xl border border-gray-100",
          title: "text-lg font-semibold text-gray-900",
          htmlContainer: "py-2",
          input: "rounded-lg border-2 border-gray-300 focus:border-blue-900 focus:ring-2 focus:ring-blue-100 text-base py-2 px-4 transition-colors",
          confirmButton:
            "bg-blue-900 hover:bg-blue-800 active:bg-blue-950 text-white font-semibold py-2 px-6 rounded-lg transition-colors",
          cancelButton:
            "bg-gray-200 hover:bg-gray-300 active:bg-gray-400 text-gray-900 font-semibold py-2 px-6 rounded-lg transition-colors ml-2",
          container: "font-sans",
        },
        buttonsStyling: false,
        didOpen: (modal) => {
          const input = modal.querySelector("input");
          if (input) {
            input.focus();
            input.select();
          }
        },
      });

      // Early exit if user cancelled or didn't provide input
      if (!term) return;

      const normalizedTerm = term.trim();
      navigate(`/productlist?q=${encodeURIComponent(normalizedTerm)}`);
    } catch (error) {
      // Silently fail if SweetAlert fails to load or render
      console.error("Search dialog failed to open:", error);
    }
  };

  return (
    <button
      type="button"
      onClick={handleSearch}
      aria-label="Buscar produtos"
      className="flex flex-col items-center gap-1 text-white hover:text-blue-800 focus:outline-none transition cursor-pointer"
    >
      <Search size={24} />
      <span className="text-xs">Busca</span>
    </button>
  );
}
