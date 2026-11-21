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
        className="flex items-center gap-2 px-4 py-2 bg-bg-1 border border-white/10 rounded-lg hover:bg-bg-2 transition text-ink-1 focus:outline-none focus:ring-2 focus:ring-gold/40"
      >
        <SlidersHorizontal size={16} className="text-ink-2" />
        {activeLabel ? (
          <>
            <span>{activeLabel}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleClear();
              }}
              className="ml-1 p-0.5 rounded-full hover:bg-bg-3 transition"
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
        <div className="absolute top-full left-0 mt-2 w-72 bg-bg-2 rounded-xl shadow-lg border border-white/10 z-50">
          {/* Tabs */}
          <div className="flex border-b border-white/10">
            <button
              onClick={() => setActiveTab("estados")}
              className={`flex-1 py-2.5 text-sm font-medium transition ${
                activeTab === "estados"
                  ? "text-gold border-b-2 border-gold"
                  : "text-ink-2 hover:text-ink-1"
              }`}
            >
              Estados
            </button>
            <button
              onClick={() => setActiveTab("categorias")}
              className={`flex-1 py-2.5 text-sm font-medium transition ${
                activeTab === "categorias"
                  ? "text-gold border-b-2 border-gold"
                  : "text-ink-2 hover:text-ink-1"
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
                  className={`w-full text-left px-4 py-2.5 text-sm hover:bg-bg-3 transition flex items-center justify-between ${
                    selectedState === state.uf
                      ? "bg-gold/10 text-gold font-semibold"
                      : "text-ink-1"
                  }`}
                >
                  <span>{state.name}</span>
                  <span className="text-ink-2 text-xs">{state.uf}</span>
                </button>
              ))}

            {activeTab === "categorias" &&
              (categories.length === 0 ? (
                <p className="px-4 py-6 text-sm text-ink-2 text-center">
                  Nenhuma categoria encontrada.
                </p>
              ) : (
                categories.map((category) => (
                  <button
                    key={category.id}
                    onClick={() => handleSelectCategory(category.slug)}
                    className={`w-full text-left px-4 py-2.5 text-sm hover:bg-bg-3 transition ${
                      isCategoryActive(category.slug)
                        ? "bg-gold/10 text-gold font-semibold"
                        : "text-ink-1"
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
