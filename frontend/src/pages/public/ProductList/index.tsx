import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Search, SearchX } from "lucide-react";
import { productService } from "@/services/productService";
import { ProductCard } from "@/components/ui/ProductCard";
import type { MarketplaceListing } from "@/types/product";

const SEARCH_PARAM = "q";

function SearchSkeleton() {
  return (
    <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="bg-white rounded-xl shadow-md overflow-hidden animate-pulse"
        >
          <div className="aspect-4/3 bg-gray-200" />
          <div className="p-3 space-y-2">
            <div className="h-4 bg-gray-200 rounded w-3/4" />
            <div className="h-5 bg-gray-200 rounded w-1/2" />
            <div className="h-3 bg-gray-200 rounded w-2/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ProductList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [products, setProducts] = useState<MarketplaceListing[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchTerm = useMemo(
    () => searchParams.get(SEARCH_PARAM)?.trim() ?? "",
    [searchParams],
  );

  useEffect(() => {
    setQuery(searchTerm);
  }, [searchTerm]);

  useEffect(() => {
    if (!searchTerm) {
      setProducts([]);
      setError(null);
      return;
    }

    let cancelled = false;

    const fetchProducts = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await productService.searchListings(searchTerm);
        if (cancelled) return;
        setProducts(data.results);
      } catch {
        if (cancelled) return;
        setError("Não foi possível carregar os produtos.");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    fetchProducts();
    return () => {
      cancelled = true;
    };
  }, [searchTerm]);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = query.trim();
    if (!normalized) {
      setSearchParams({});
      return;
    }
    setSearchParams({ [SEARCH_PARAM]: normalized });
  };

  return (
    <div className="min-h-screen bg-blue-900 pb-24">
      <div className="px-4 py-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-4">
        Buscar Produtos
      </h1>

      <form onSubmit={handleSubmit} className="flex gap-3 mb-6">
        <div className="relative flex-1">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
          />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar produto por palavra-chave..."
            className="w-full h-11 rounded-lg pl-10 pr-3 bg-white text-gray-900 border-2 border-gray-800 focus:border-blue-700 focus:ring-2 focus:ring-blue-200 outline-none transition-colors"
          />
        </div>
        <button
          type="submit"
          className="h-11 px-5 rounded-lg bg-blue-700 hover:bg-blue-600 active:bg-blue-800 text-white font-semibold transition-colors shadow-md"
        >
          Buscar
        </button>
      </form>

      {!searchTerm && (
        <div className="text-center py-16">
          <Search size={48} className="mx-auto text-white/40 mb-4" />
          <p className="text-white/70 text-lg">
            Digite uma palavra-chave para buscar produtos.
          </p>
        </div>
      )}

      {isLoading && <SearchSkeleton />}

      {error && (
        <div className="text-center py-12">
          <p className="text-red-200 text-lg">{error}</p>
        </div>
      )}

      {!isLoading && !error && searchTerm && products.length === 0 && (
        <div className="text-center py-16">
          <SearchX size={48} className="mx-auto text-white/40 mb-4" />
          <p className="text-white/70 text-lg">
            Nenhum produto encontrado para "<strong>{searchTerm}</strong>".
          </p>
          <p className="text-white/50 text-sm mt-2">
            Tente buscar com outras palavras-chave.
          </p>
        </div>
      )}

      {!isLoading && !error && products.length > 0 && (
        <>
          <p className="text-white/70 text-sm mb-4">
            {products.length} {products.length === 1 ? "resultado" : "resultados"} para "<strong>{searchTerm}</strong>"
          </p>
          <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {products.map((listing) => (
              <ProductCard key={listing.id} listing={listing} />
            ))}
          </div>
        </>
      )}
      </div>
    </div>
  );
}
