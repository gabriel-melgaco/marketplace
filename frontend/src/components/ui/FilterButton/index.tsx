import { useState, useRef, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { ChevronDown, SlidersHorizontal, X } from "lucide-react";
import { BRAZILIAN_STATES } from "@/constants/brazilianStates";
import { productService } from "@/services/productService";
import type { CategorySimple } from "@/types/product";

type FilterTab = "estados" | "categorias";

interface FilterButtonProps {
  selectedState?: string;
  selectedCategory?: string;
}

export function FilterButton({ selectedState, selectedCategory }: FilterButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<FilterTab>("estados");
  const [categories, setCategories] = useState<CategorySimple[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    async function fetchCategories() {
      try {
        const data = await productService.getListings({ page_size: 100 });
        const seen = new Set<string>();
        const unique: CategorySimple[] = [];
        for (const listing of data.results) {
          const cat = listing.category;
          if (cat && !seen.has(cat.slug)) {
            seen.add(cat.slug);
            unique.push(cat);
          }
        }
        setCategories(unique);
      } catch (error) {
        console.error("Erro ao buscar categorias:", error);
      }
    }
    fetchCategories();
  }, []);

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
      if (event.key === "Escape" && isOpen) setIsOpen(false);
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

  const handleSelectCategory = (slug: string) => {
    setIsOpen(false);
    navigate(`/products?category=${slug}`);
  };

  const handleClear = () => {
    setIsOpen(false);
    navigate("/");
  };

  const activeStateLabel = selectedState
    ? BRAZILIAN_STATES.find((s) => s.uf === selectedState)?.name ?? selectedState
    : null;

  const activeCategoryLabel = selectedCategory
    ? (categories.find((c) => c.slug === selectedCategory)?.name ?? selectedCategory)
    : null;

  const activeLabel = activeStateLabel ?? activeCategoryLabel;

  const isCategoryActive = (slug: string) =>
    location.pathname === "/products" &&
    location.search.includes(`category=${slug}`);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 bg-white border-2 border-gray-300 rounded-lg hover:bg-gray-50 transition"
      >
        <SlidersHorizontal size={16} />
        {activeLabel ? (
          <>
            <span>{activeLabel}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleClear();
              }}
              className="ml-1 p-0.5 rounded-full hover:bg-gray-200 transition"
              aria-label="Limpar filtro"
            >
              <X size={14} />
            </button>
          </>
        ) : (
          <>
            <span>Filtrar</span>
            <ChevronDown size={16} />
          </>
        )}
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-72 bg-white rounded-xl shadow-lg border border-gray-200 z-50">
          {/* Tabs */}
          <div className="flex border-b border-gray-200">
            <button
              onClick={() => setActiveTab("estados")}
              className={`flex-1 py-2.5 text-sm font-medium transition ${
                activeTab === "estados"
                  ? "text-blue-700 border-b-2 border-blue-700"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Estados
            </button>
            <button
              onClick={() => setActiveTab("categorias")}
              className={`flex-1 py-2.5 text-sm font-medium transition ${
                activeTab === "categorias"
                  ? "text-blue-700 border-b-2 border-blue-700"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Categorias
            </button>
          </div>

          {/* Content */}
          <div className="max-h-72 overflow-y-auto">
            {activeTab === "estados" &&
              BRAZILIAN_STATES.map((state) => (
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

            {activeTab === "categorias" &&
              (categories.length === 0 ? (
                <p className="px-4 py-6 text-sm text-gray-400 text-center">
                  Nenhuma categoria encontrada.
                </p>
              ) : (
                categories.map((category) => (
                  <button
                    key={category.id}
                    onClick={() => handleSelectCategory(category.slug)}
                    className={`w-full text-left px-4 py-2.5 text-sm hover:bg-blue-50 transition ${
                      isCategoryActive(category.slug)
                        ? "bg-blue-50 text-blue-800 font-semibold"
                        : "text-gray-700"
                    }`}
                  >
                    {category.name}
                  </button>
                ))
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
