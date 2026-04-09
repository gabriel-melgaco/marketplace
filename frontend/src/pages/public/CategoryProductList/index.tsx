import { useState, useEffect } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { Package } from "lucide-react";
import { productService } from "@/services/productService";
import { catalogService } from "@/services/catalogService";
import { Footer } from "@/components/layout/Footer";
import { FilterButton } from "@/components/ui/FilterButton";
import { ProductCard } from "@/components/ui/ProductCard";
import { ProductGridSkeleton } from "@/components/skeletons/ProductCardSkeleton";
import type { MarketplaceListing } from "@/types/product";

export function CategoryProductList() {
  const [searchParams] = useSearchParams();
  const categorySlug = searchParams.get("category");

  const [listings, setListings] = useState<MarketplaceListing[]>([]);
  const [categoryName, setCategoryName] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        setLoading(true);
        setError(null);

        const listingsParams = categorySlug
          ? { product__category__slug: categorySlug }
          : undefined;

        const [listingsData, categoryData] = await Promise.all([
          productService.getListings(listingsParams),
          categorySlug
            ? catalogService.getCategory(categorySlug).catch(() => null)
            : null,
        ]);

        if (!cancelled) {
          setListings(listingsData.results);
          setCategoryName(categoryData?.name ?? "");
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

    fetchData();
    return () => {
      cancelled = true;
    };
  }, [categorySlug, retryCount]);

  const title = categoryName
    ? `Produtos em ${categoryName}`
    : categorySlug
      ? `Produtos em "${categorySlug}"`
      : "Todos os Produtos";

  return (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-800 to-blue-900">
      {/* Filtro */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-6">
        <FilterButton selectedCategory={categorySlug ?? undefined} />
      </div>

      {/* Titulo */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-4">
        <h1 className="text-white text-xl font-bold">{title}</h1>
        {!loading && !error && (
          <p className="text-white/60 text-sm mt-1">
            {listings.length}{" "}
            {listings.length === 1 ? "resultado" : "resultados"}
          </p>
        )}
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
            <p className="text-white/80 text-lg">
              Nenhum produto encontrado
              {categoryName ? ` em ${categoryName}` : ""}.
            </p>
            <Link
              to="/"
              className="inline-block mt-4 px-4 py-2 bg-white text-blue-900 rounded-lg font-medium hover:bg-gray-100 transition"
            >
              Voltar para o inicio
            </Link>
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
