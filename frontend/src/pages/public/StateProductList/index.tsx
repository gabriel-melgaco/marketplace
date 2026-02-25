import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Package } from "lucide-react";
import { productService } from "@/services/productService";
import { Footer } from "@/components/layout/Footer";
import { StateButton } from "@/components/ui/StateButton";
import { ProductCard } from "@/components/ui/ProductCard";
import { ProductGridSkeleton } from "@/components/skeletons/ProductCardSkeleton";
import { STATE_NAMES } from "@/constants/brazilianStates";
import type { MarketplaceListing } from "@/types/product";

export function StateProductList() {
  const { uf } = useParams<{ uf: string }>();
  const [allListings, setAllListings] = useState<MarketplaceListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  const stateUF = uf?.toUpperCase() ?? "";
  const isValidState = stateUF && stateUF in STATE_NAMES;
  const stateName = STATE_NAMES[stateUF] ?? stateUF;

  useEffect(() => {
    let cancelled = false;

    async function fetchListings() {
      try {
        setLoading(true);
        setError(null);
        // TODO: Optimize - add backend API support for filtering by state
        // Currently fetches all listings and filters client-side
        const data = await productService.getListings();
        if (!cancelled) {
          setAllListings(data.results);
        }
      } catch (err) {
        console.error("Erro ao buscar listings:", err);
        if (!cancelled) {
          setError("Erro ao carregar produtos. Tente novamente.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchListings();
    return () => {
      cancelled = true;
    };
  }, [retryCount]);

  const filteredListings = allListings.filter((listing) => {
    const addr = listing.seller_shipping_address;
    if (!addr || !addr.state) return false;
    return addr.state.trim().toUpperCase() === stateUF;
  });

  if (!isValidState) {
    return (
      <div className="min-h-screen bg-blue-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-6">
          <StateButton />
        </div>
        <div className="text-center py-20">
          <Package size={48} className="mx-auto mb-4 text-white/60" />
          <p className="text-white text-lg mb-4">
            Estado "{stateUF}" não é válido.
          </p>
          <Link
            to="/"
            className="inline-block px-4 py-2 bg-white text-blue-900 rounded-lg font-medium hover:bg-gray-100 transition"
          >
            Voltar para o início
          </Link>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-blue-900">
      {/* Botão Estado */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-6">
        <StateButton selectedState={stateUF} />
      </div>

      {/* Título */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-4">
        <h1 className="text-white text-xl font-bold">
          Produtos em {stateName}
        </h1>
      </div>

      {/* Produtos */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8 pb-24">
        {loading && <ProductGridSkeleton />}

        {error && (
          <div className="text-center py-20">
            <p className="text-white text-lg mb-4">{error}</p>
            <button
              onClick={() => setRetryCount((c) => c + 1)}
              className="px-4 py-2 bg-white text-blue-900 rounded-lg font-medium hover:bg-gray-100 transition"
            >
              Tentar novamente
            </button>
          </div>
        )}

        {!loading && !error && filteredListings.length === 0 && (
          <div className="text-center py-20">
            <Package size={48} className="mx-auto mb-4 text-white/60" />
            <p className="text-white/80 text-lg">
              Nenhum produto encontrado em {stateName}.
            </p>
          </div>
        )}

        {!loading && !error && filteredListings.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
            {filteredListings.map((listing) => (
              <ProductCard key={listing.id} listing={listing} />
            ))}
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
