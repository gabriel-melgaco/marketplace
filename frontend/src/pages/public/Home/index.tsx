import { useState, useEffect } from "react";
import { Package } from "lucide-react";
import { productService } from "@/services/productService";
import { Footer } from "@/components/layout/Footer";
import { StateButton } from "@/components/ui/StateButton";
import { ProductCard } from "@/components/ui/ProductCard";
import { ProductGridSkeleton } from "@/components/skeletons/ProductCardSkeleton";
import type { MarketplaceListing } from "@/types/product";

export default function Home() {
  const [listings, setListings] = useState<MarketplaceListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function fetchListings() {
      try {
        setLoading(true);
        setError(null);
        const data = await productService.getListings();
        if (!cancelled) {
          setListings(data);
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

  return (
    <div className="min-h-screen bg-blue-900">
      {/* Botão Estado */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-6">
        <StateButton />
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

        {!loading && !error && listings.length === 0 && (
          <div className="text-center py-20">
            <Package size={48} className="mx-auto mb-4 text-white/60" />
            <p className="text-white/80 text-lg">Nenhum produto encontrado.</p>
          </div>
        )}

        {!loading && !error && listings.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
            {listings.map((listing) => (
              <ProductCard key={listing.id} listing={listing} />
            ))}
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
