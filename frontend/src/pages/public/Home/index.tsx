import { useState, useEffect } from "react";
import { Package, AlertTriangle, Link2 } from "lucide-react";
import { Link } from "react-router-dom";
import { productService } from "@/services/productService";
import { Footer } from "@/components/layout/Footer";
import { FilterButton } from "@/components/ui/FilterButton";
import { ProductCard } from "@/components/ui/ProductCard";
import { ProductGridSkeleton } from "@/components/skeletons/ProductCardSkeleton";
import { useAuth } from "@/contexts/AuthContext";
import { shippingService } from "@/services/shippingService";
import { stripeConnectService } from "@/services/stripeConnectService";
import type { MarketplaceListing } from "@/types/product";

// ─── Seller connections banner ────────────────────────────────────────────────

function SellerConnectionsBanner() {
  const { user } = useAuth();
  const [meConnected, setMeConnected] = useState<boolean | null>(null);
  const [stripeReady, setStripeReady] = useState<boolean | null>(null);

  useEffect(() => {
    if (!user?.is_seller) return;
    let cancelled = false;

    async function checkConnections() {
      const [meRes, stripeRes] = await Promise.allSettled([
        shippingService.getMEBalance(),
        stripeConnectService.getAccountStatus(),
      ]);
      if (cancelled) return;
      setMeConnected(meRes.status === "fulfilled");
      setStripeReady(
        stripeRes.status === "fulfilled" &&
          stripeRes.value.has_account &&
          stripeRes.value.ready_to_receive_payments
      );
    }

    checkConnections();
    return () => { cancelled = true; };
  }, [user]);

  if (!user?.is_seller) return null;
  if (meConnected === null && stripeReady === null) return null;

  const missing: { key: string; label: string; detail: string }[] = [];

  if (meConnected === false) {
    missing.push({
      key: "me",
      label: "Melhor Envio",
      detail: "Necessário para calcular e gerar etiquetas de envio dos seus produtos.",
    });
  }
  if (stripeReady === false) {
    missing.push({
      key: "stripe",
      label: "Stripe (pagamentos)",
      detail: "Necessário para receber os pagamentos das suas vendas na plataforma.",
    });
  }

  if (missing.length === 0) return null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-4">
      <div className="bg-yellow-50 border border-yellow-300 rounded-xl p-4 flex flex-col sm:flex-row sm:items-start gap-4">
        <div className="flex items-start gap-3 flex-1">
          <AlertTriangle size={20} className="text-yellow-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-yellow-900">
              {missing.length === 2
                ? "Conecte suas contas para começar a vender"
                : `Conecte o ${missing[0].label} para começar a vender`}
            </p>
            <ul className="mt-1 space-y-0.5">
              {missing.map(({ key, label, detail }) => (
                <li key={key} className="text-xs text-yellow-800">
                  <span className="font-semibold">{label}:</span> {detail}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <Link
          to="/account?section=connections"
          className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white text-xs font-semibold rounded-lg transition-colors"
        >
          <Link2 size={13} />
          Conectar contas
        </Link>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

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
          setListings(data.results);
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
    <div className="min-h-screen bg-bg-0">
      {/* Aviso de conexão para vendedores */}
      <SellerConnectionsBanner />

      {/* Hero */}
      <section className="px-[18px] pt-5 pb-3.5 max-w-7xl mx-auto">
        <div className="flex items-end justify-between mb-4">
          <h1 className="font-display font-extrabold text-[26px] md:text-[36px] lg:text-[48px] tracking-[-0.03em] leading-none text-ink-1">
            Equipamentos
            <br />
            <span className="text-gold">profissionais.</span>
          </h1>
          <div className="text-xs md:text-sm text-ink-3 tabular-nums">
            {listings.length} {listings.length === 1 ? "anúncio" : "anúncios"}
          </div>
        </div>
      </section>

      {/* Botão Estado */}
      <div className="max-w-7xl mx-auto px-[18px] pb-3">
        <FilterButton />
      </div>

      {/* Produtos */}
      <main className="pb-24">
        {loading && <ProductGridSkeleton />}

        {error && (
          <div className="text-center py-20">
            <p className="text-ink-1 text-lg mb-4">{error}</p>
            <button
              onClick={() => setRetryCount((c) => c + 1)}
              className="px-4 py-2 bg-gold text-gold-deep rounded-lg font-medium hover:bg-gold/90 transition"
            >
              Tentar novamente
            </button>
          </div>
        )}

        {!loading && !error && listings.length === 0 && (
          <div className="text-center py-20">
            <Package size={48} className="mx-auto mb-4 text-ink-3" />
            <p className="text-ink-2 text-lg">Nenhum produto encontrado.</p>
          </div>
        )}

        {!loading && !error && listings.length > 0 && (
          <div className="grid grid-cols-2 gap-2.5 px-3.5 md:grid-cols-3 md:gap-4 md:px-6 lg:grid-cols-4 lg:gap-6 lg:px-8 max-w-7xl mx-auto">
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
