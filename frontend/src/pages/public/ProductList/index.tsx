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
          className="bg-bg-1 border border-white/10 rounded-xl overflow-hidden animate-pulse"
        >
          <div className="aspect-4/3 bg-white/5" />
          <div className="p-3 space-y-2">
            <div className="h-4 bg-white/5 rounded w-3/4" />
            <div className="h-5 bg-white/5 rounded w-1/2" />
            <div className="h-3 bg-white/5 rounded w-2/3" />
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

  const handleSearch = () => {
    const normalized = query.trim();
    if (!normalized) {
      setSearchParams({});
      return;
    }
    setSearchParams({ [SEARCH_PARAM]: normalized });
  };

  return (
    <div className="min-h-screen bg-bg-0 pb-24">
      <div className="px-4 py-6 max-w-6xl mx-auto">
        <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-4">
          Buscar Produtos
        </h1>

        <div className="flex gap-3 mb-6">
          <div className="relative flex-1">
            <Search
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
              placeholder="Buscar produto por palavra-chave..."
              className="w-full h-11 rounded-lg pl-10 pr-3 bg-bg-2 border border-white/10 text-ink-1 placeholder:text-ink-3 focus:border-gold/50 focus:ring-2 focus:ring-gold/20 outline-none transition-colors"
            />
          </div>
          <button
            type="button"
            onClick={handleSearch}
            className="h-11 px-5 rounded-lg bg-gold text-gold-deep font-semibold hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-0"
          >
            Buscar
          </button>
        </div>

        {!searchTerm && (
          <div className="text-center py-16">
            <Search size={48} className="mx-auto text-ink-3 mb-4" />
            <p className="text-ink-2 text-lg">
              Digite uma palavra-chave para buscar produtos.
            </p>
          </div>
        )}

        {isLoading && <SearchSkeleton />}

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 max-w-md mx-auto text-center py-12">
            <p className="text-red-400 text-lg">{error}</p>
          </div>
        )}

        {!isLoading && !error && searchTerm && products.length === 0 && (
          <div className="text-center py-16">
            <SearchX size={48} className="mx-auto text-ink-3 mb-4" />
            <p className="text-ink-2 text-lg">
              Nenhum produto encontrado para "<strong>{searchTerm}</strong>".
            </p>
            <p className="text-ink-3 text-sm mt-2">
              Tente buscar com outras palavras-chave.
            </p>
          </div>
        )}

        {!isLoading && !error && products.length > 0 && (
          <>
            <p className="text-ink-2 text-sm mb-4">
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
