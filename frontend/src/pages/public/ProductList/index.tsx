import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { productService } from "@/services/productService";
import type { MarketplaceListing } from "@/types/product";

const SEARCH_PARAM = "q";

export function ProductList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [products, setProducts] = useState<MarketplaceListing[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchTerm = useMemo(
    () => searchParams.get(SEARCH_PARAM)?.trim() ?? "",
    [searchParams]
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
      } catch (err) {
        if (cancelled) return;
        setError("Não foi possível carregar os produtos.");
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
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
    <div className="px-4 py-6">
      <h1 className="text-2xl font-bold text-white mb-4">
        Listagem de Produtos
      </h1>

      <form onSubmit={handleSubmit} className="flex gap-3 mb-6">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar produto por palavra-chave"
          className="flex-1 h-10 rounded-lg px-3 bg-white text-gray-900"
        />
        <button
          type="submit"
          className="h-10 px-4 rounded-lg bg-blue-700 text-white font-semibold"
        >
          Buscar
        </button>
      </form>

      {!searchTerm && (
        <p className="text-white/80">
          Digite uma palavra para buscar produtos.
        </p>
      )}

      {isLoading && <p className="text-white/80">Buscando produtos...</p>}

      {error && <p className="text-red-200">{error}</p>}

      {!isLoading && !error && searchTerm && products.length === 0 && (
        <p className="text-white/80">
          Nenhum produto encontrado para "{searchTerm}".
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {products.map((listing) => (
          <div
            key={listing.id}
            className="rounded-lg bg-white p-4 shadow-md flex flex-col gap-2"
          >
            <div className="font-semibold text-gray-900">
              {listing.product.name}
            </div>
            <div className="text-blue-800 font-bold">
              R$ {listing.price}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
