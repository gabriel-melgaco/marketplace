import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  Package,
  ShoppingBag,
  ShoppingCart,
  Star,
  TrendingUp,
  Plus,
  Eye,
  Edit,
  Trash2,
  ToggleLeft,
  ToggleRight,
  ChevronRight,
  AlertCircle,
  RefreshCw,
  DollarSign,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { productService } from "@/services/productService";
import { confirmDelete } from "@/utils/confirmDialog";
import Swal from "sweetalert2";
import { orderService } from "@/services/orderService";
import { reviewService } from "@/services/reviewService";
import { SaleOrderModal } from "@/components/ui/SaleOrderModal";
import { BuyerOrderModal } from "@/components/ui/BuyerOrderModal";
import { toPublicUrl } from "@/services/storageService";
import { createRoute } from "@/routes/routePaths";
import type { MarketplaceListing } from "@/types/product";
import type { OrderList } from "@/services/orderService";
import type { Review, ReviewStats } from "@/types/review";

// ─── Types ───────────────────────────────────────────────────────────────────

type Tab = "overview" | "listings" | "sales" | "purchases" | "reviews";

interface DashboardStats {
  totalSales: number;
  totalSalesRevenue: number;
  totalPurchases: number;
  activeListings: number;
  averageRating: number | null;
  totalReviews: number;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ORDER_STATUS_LABELS: Record<string, string> = {
  pending_payment: "Aguardando Pagamento",
  paid: "Pago",
  pending: "Pendente",
  processing: "Em Processamento",
  shipped: "Enviado",
  delivered: "Entregue",
  completed: "Concluído",
  cancelled: "Cancelado",
  failed: "Falhou",
};

const ORDER_STATUS_COLORS: Record<string, string> = {
  pending_payment: "bg-yellow-100 text-yellow-800",
  paid: "bg-blue-100 text-blue-800",
  pending: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  shipped: "bg-purple-100 text-purple-800",
  delivered: "bg-green-100 text-green-800",
  completed: "bg-green-100 text-green-800",
  cancelled: "bg-red-100 text-red-800",
  failed: "bg-red-100 text-red-800",
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatCard({
  icon: Icon,
  label,
  value,
  color,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color: string;
  accent: string;
}) {
  return (
    <div
      className={`relative bg-white rounded-xl shadow-sm overflow-hidden border-t-4 ${accent}`}
    >
      {/* Subtle tinted background strip */}
      <div className={`absolute inset-0 opacity-[0.03] ${color}`} />
      <div className="relative p-4">
        <div className="flex items-start justify-between mb-3">
          <div className={`p-2.5 rounded-xl ${color}`}>
            <Icon size={20} className="text-white" />
          </div>
        </div>
        <p className="text-2xl font-extrabold text-gray-900 leading-none">
          {value}
        </p>
        <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mt-1.5">
          {label}
        </p>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const label = ORDER_STATUS_LABELS[status] ?? status;
  const colorClass = ORDER_STATUS_COLORS[status] ?? "bg-gray-100 text-gray-700";
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${colorClass}`}
    >
      {label}
    </span>
  );
}

function ListingStatusBadge({ listing }: { listing: MarketplaceListing }) {
  if (listing.sold_at) {
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-500">
        Vendido
      </span>
    );
  }
  if (listing.is_active) {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-green-50 text-green-700 border border-green-200">
        <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
        Ativo
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-600 border border-red-200">
      <span className="w-1.5 h-1.5 rounded-full bg-red-400 inline-block" />
      Inativo
    </span>
  );
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => (
        <Star
          key={star}
          size={14}
          className={
            star <= rating
              ? "text-yellow-400 fill-yellow-400"
              : "text-gray-200 fill-gray-200"
          }
        />
      ))}
    </div>
  );
}

function SectionError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center gap-3 bg-red-50/50 rounded-xl border border-red-100">
      <AlertCircle size={32} className="text-red-400" />
      <p className="text-gray-600 text-sm">{message}</p>
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-1.5 text-sm font-semibold text-secundary hover:text-secundary/80 transition-colors"
      >
        <RefreshCw size={13} />
        Tentar novamente
      </button>
    </div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  subtitle,
  action,
}: {
  icon: React.ElementType;
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center gap-3">
      <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center">
        <Icon size={30} className="text-gray-400" />
      </div>
      <p className="text-gray-700 font-semibold text-sm">{title}</p>
      {subtitle && <p className="text-gray-400 text-xs max-w-xs">{subtitle}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

function SkeletonRow() {
  return (
    <div className="animate-pulse flex items-center gap-3 py-3.5 px-2">
      {/* Thumbnail */}
      <div className="w-14 h-14 bg-gray-100 rounded-xl shrink-0" />
      {/* Text lines */}
      <div className="flex-1 space-y-2.5 min-w-0">
        <div className="h-3.5 bg-gray-100 rounded-md w-3/4" />
        <div className="h-3 bg-gray-100 rounded-md w-1/3" />
        <div className="h-2.5 bg-gray-100 rounded-md w-1/2" />
      </div>
      {/* Badge placeholder */}
      <div className="h-5 bg-gray-100 rounded-full w-14 shrink-0" />
    </div>
  );
}

// ─── Section: Listings ────────────────────────────────────────────────────────

function ListingsSection() {
  const [listings, setListings] = useState<MarketplaceListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const loadListings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await productService.getMyListings();
      setListings(data.results);
    } catch {
      setError("Erro ao carregar seus anúncios.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadListings();
  }, [loadListings]);

  async function handleToggleActive(listing: MarketplaceListing) {
    if (listing.sold_at) return;
    setTogglingId(listing.id);
    try {
      await productService.toggleListingActive(listing.id);
      setListings((prev) =>
        prev.map((l) =>
          l.id === listing.id ? { ...l, is_active: !l.is_active } : l,
        ),
      );
    } catch {
      Swal.fire({
        icon: "error",
        title: "Erro",
        text: "Não foi possível alterar o status do anúncio.",
        toast: true,
        position: "top-end",
        showConfirmButton: false,
        timer: 3000,
      });
    } finally {
      setTogglingId(null);
    }
  }

  async function handleDelete(id: number) {
    const confirmed = await confirmDelete();
    if (!confirmed) return;
    try {
      await productService.deleteListing(id);
      setListings((prev) => prev.filter((l) => l.id !== id));
    } catch {
      Swal.fire({
        icon: "error",
        title: "Erro",
        text: "Não foi possível excluir o anúncio.",
        toast: true,
        position: "top-end",
        showConfirmButton: false,
        timer: 3000,
      });
    }
  }

  if (loading) {
    return (
      <div className="divide-y divide-gray-50">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonRow key={i} />
        ))}
      </div>
    );
  }

  if (error) return <SectionError message={error} onRetry={loadListings} />;

  if (listings.length === 0) {
    return (
      <EmptyState
        icon={Package}
        title="Você não tem anúncios ainda"
        subtitle="Crie seu primeiro anúncio e comece a vender no marketplace."
        action={
          <Link
            to="/create-listing"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-secundary text-white rounded-lg text-sm font-semibold hover:bg-secundary/90 transition-colors shadow-sm"
          >
            <Plus size={15} />
            Criar anúncio
          </Link>
        }
      />
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">
          {listings.length} anúncio{listings.length !== 1 ? "s" : ""}
        </p>
        <Link
          to="/create-listing"
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-secundary text-white rounded-lg text-xs font-semibold hover:bg-secundary/90 transition-colors"
        >
          <Plus size={13} />
          Novo anúncio
        </Link>
      </div>

      <div className="divide-y divide-gray-50">
        {listings.map((listing) => {
          const imgUrl = listing.primary_image
            ? toPublicUrl(listing.primary_image)
            : listing.images?.[0]?.image_url
              ? toPublicUrl(listing.images[0].image_url)
              : null;

          return (
            <div
              key={listing.id}
              className="flex items-center gap-3 py-3.5 hover:bg-gray-50 rounded-xl px-2 -mx-2 transition-colors group"
            >
              {/* Thumbnail */}
              <div className="w-14 h-14 bg-gray-100 rounded-xl overflow-hidden shrink-0 flex items-center justify-center border border-gray-100">
                {imgUrl ? (
                  <img
                    src={imgUrl}
                    alt={listing.title}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <Package size={20} className="text-gray-300" />
                )}
              </div>

              {/* Text content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-800 truncate leading-tight">
                  {listing.title || listing.product.name}
                </p>
                <p className="text-sm font-bold text-secundary mt-0.5">
                  R${" "}
                  {Number(listing.price).toLocaleString("pt-BR", {
                    minimumFractionDigits: 2,
                  })}
                </p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <Eye size={11} className="text-gray-300" />
                  <span className="text-xs text-gray-400">
                    {listing.views_count} visualizações
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 shrink-0">
                <ListingStatusBadge listing={listing} />

                {/* Toggle active */}
                {!listing.sold_at && (
                  <button
                    onClick={() => handleToggleActive(listing)}
                    disabled={togglingId === listing.id}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-secundary hover:bg-blue-50 transition-colors disabled:opacity-40"
                    title={listing.is_active ? "Desativar" : "Ativar"}
                    aria-label={
                      listing.is_active ? "Desativar anúncio" : "Ativar anúncio"
                    }
                  >
                    {listing.is_active ? (
                      <ToggleRight size={20} className="text-green-500" />
                    ) : (
                      <ToggleLeft size={20} />
                    )}
                  </button>
                )}

                {/* Edit */}
                <Link
                  to={createRoute.editAd(String(listing.id))}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-secundary hover:bg-blue-50 transition-colors"
                  title="Editar anúncio"
                  aria-label="Editar anúncio"
                >
                  <Edit size={15} />
                </Link>

                {/* Divider before destructive action */}
                <span
                  className="w-px h-5 bg-gray-200 mx-0.5"
                  aria-hidden="true"
                />

                {/* Delete */}
                <button
                  onClick={() => handleDelete(listing.id)}
                  className="p-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                  title="Excluir anúncio"
                  aria-label="Excluir anúncio"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Section: Sales ───────────────────────────────────────────────────────────

function SalesSection() {
  const [sales, setSales] = useState<OrderList[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSaleId, setSelectedSaleId] = useState<string | null>(null);

  const loadSales = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await orderService.listSales();
      setSales(data);
    } catch {
      setError("Erro ao carregar suas vendas.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSales();
  }, [loadSales]);

  if (loading) {
    return (
      <div className="divide-y divide-gray-50">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonRow key={i} />
        ))}
      </div>
    );
  }

  if (error) return <SectionError message={error} onRetry={loadSales} />;

  if (sales.length === 0) {
    return (
      <EmptyState
        icon={TrendingUp}
        title="Nenhuma venda realizada ainda"
        subtitle="Suas vendas aparecerão aqui quando alguém comprar seus anúncios."
      />
    );
  }

  return (
    <div>
      <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-5">
        {sales.length} venda{sales.length !== 1 ? "s" : ""}
      </p>
      <div className="divide-y divide-gray-50">
        {sales.map((sale) => (
          <div
            key={sale.id}
            onClick={() => setSelectedSaleId(sale.id)}
            className="flex items-center justify-between py-3.5 px-2 -mx-2 hover:bg-gray-50 rounded-xl transition-colors cursor-pointer"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-gray-800">
                Pedido #{sale.order_number}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                {new Date(sale.created_at).toLocaleDateString("pt-BR")}
              </p>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <p className="text-sm font-bold text-gray-800">
                R${" "}
                {Number(sale.total).toLocaleString("pt-BR", {
                  minimumFractionDigits: 2,
                })}
              </p>
              <StatusBadge status={sale.status} />
              <ChevronRight size={16} className="text-gray-300" />
            </div>
          </div>
        ))}
      </div>

      {selectedSaleId && (
        <SaleOrderModal
          orderId={selectedSaleId}
          onClose={() => setSelectedSaleId(null)}
          onOrderUpdated={loadSales}
        />
      )}
    </div>
  );
}

// ─── Section: Purchases ───────────────────────────────────────────────────────

function PurchasesSection() {
  const [orders, setOrders] = useState<OrderList[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);

  const loadOrders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await orderService.listOrders();
      setOrders(data);
    } catch {
      setError("Erro ao carregar suas compras.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOrders();
  }, [loadOrders]);

  if (loading) {
    return (
      <div className="divide-y divide-gray-50">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonRow key={i} />
        ))}
      </div>
    );
  }

  if (error) return <SectionError message={error} onRetry={loadOrders} />;

  if (orders.length === 0) {
    return (
      <EmptyState
        icon={ShoppingCart}
        title="Nenhuma compra realizada"
        subtitle="Seus pedidos de compra aparecerão aqui."
        action={
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-secundary text-white rounded-lg text-sm font-semibold hover:bg-secundary/90 transition-colors shadow-sm"
          >
            <ShoppingBag size={14} />
            Explorar produtos
          </Link>
        }
      />
    );
  }

  return (
    <div>
      <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-5">
        {orders.length} compra{orders.length !== 1 ? "s" : ""}
      </p>
      <div className="divide-y divide-gray-50">
        {orders.map((order) => (
          <div
            key={order.id}
            onClick={() => setSelectedOrderId(order.id)}
            className="flex items-center justify-between py-3.5 px-2 -mx-2 hover:bg-gray-50 rounded-xl transition-colors cursor-pointer"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-gray-800">
                Pedido #{order.order_number}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                {new Date(order.created_at).toLocaleDateString("pt-BR")}
              </p>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <p className="text-sm font-bold text-gray-800">
                R${" "}
                {Number(order.total).toLocaleString("pt-BR", {
                  minimumFractionDigits: 2,
                })}
              </p>
              <StatusBadge status={order.status} />
              <ChevronRight size={16} className="text-gray-300" />
            </div>
          </div>
        ))}
      </div>

      {selectedOrderId && (
        <BuyerOrderModal
          orderId={selectedOrderId}
          onClose={() => setSelectedOrderId(null)}
          onOrderCancelled={loadOrders}
        />
      )}
    </div>
  );
}

// ─── Section: Reviews ─────────────────────────────────────────────────────────

function ReviewsSection({ stats }: { stats: ReviewStats | null }) {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadReviews = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await reviewService.getReceivedReviews();
      setReviews(data.results);
    } catch {
      setError("Erro ao carregar avaliações.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReviews();
  }, [loadReviews]);

  return (
    <div>
      {/* Stats summary */}
      {stats && stats.total_reviews > 0 && (
        <div className="bg-linear-to-br from-blue-50 to-indigo-50 border border-blue-100 rounded-xl p-5 mb-6">
          <div className="flex flex-col sm:flex-row items-center gap-6">
            {/* Score */}
            <div className="flex flex-col items-center gap-1.5 sm:border-r sm:border-blue-200 sm:pr-6">
              <p className="text-5xl font-extrabold text-secundary leading-none">
                {stats.average_rating.toFixed(1)}
              </p>
              <StarRating rating={Math.round(stats.average_rating)} />
              <p className="text-xs text-gray-500 mt-0.5">
                {stats.total_reviews} avaliação
                {stats.total_reviews !== 1 ? "ões" : ""}
              </p>
            </div>

            {/* Breakdown bars */}
            <div className="flex-1 w-full space-y-2">
              {([5, 4, 3, 2, 1] as const).map((star) => {
                const count = stats.rating_breakdown[star] ?? 0;
                const pct =
                  stats.total_reviews > 0
                    ? Math.round((count / stats.total_reviews) * 100)
                    : 0;
                return (
                  <div key={star} className="flex items-center gap-2.5 text-xs">
                    <span className="w-3 text-right text-gray-500 font-medium tabular-nums">
                      {star}
                    </span>
                    <Star
                      size={10}
                      className="text-yellow-400 fill-yellow-400 shrink-0"
                    />
                    <div className="flex-1 bg-white/70 rounded-full h-2.5 overflow-hidden border border-blue-100">
                      <div
                        className="bg-yellow-400 h-full rounded-full transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="w-5 text-right text-gray-500 tabular-nums font-medium">
                      {count}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {loading && (
        <div className="divide-y divide-gray-50">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonRow key={i} />
          ))}
        </div>
      )}

      {!loading && error && (
        <SectionError message={error} onRetry={loadReviews} />
      )}

      {!loading && !error && reviews.length === 0 && (
        <EmptyState
          icon={Star}
          title="Nenhuma avaliação recebida"
          subtitle="As avaliações dos compradores aparecerão aqui após suas vendas."
        />
      )}

      {!loading && !error && reviews.length > 0 && (
        <div className="divide-y divide-gray-50">
          {reviews.map((review) => (
            <div key={review.id} className="py-4 px-2 -mx-2">
              <div className="flex items-start gap-3">
                {/* Avatar */}
                <div className="w-9 h-9 rounded-full bg-secundary/10 overflow-hidden shrink-0 flex items-center justify-center ring-2 ring-white">
                  {review.reviewer.picture ? (
                    <img
                      src={toPublicUrl(review.reviewer.picture)}
                      alt={review.reviewer.full_name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <span className="text-sm font-bold text-secundary">
                      {review.reviewer.full_name.charAt(0).toUpperCase()}
                    </span>
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-gray-800">
                      {review.reviewer.full_name}
                    </p>
                    <p className="text-xs text-gray-400">
                      {new Date(review.created_at).toLocaleDateString("pt-BR")}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <StarRating rating={review.rating} />
                    <span className="text-xs text-gray-400 font-medium">
                      {review.rating.toFixed(1)}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1 truncate">
                    Anúncio: {review.listing.title}
                  </p>
                  {review.comment && (
                    <p className="text-sm text-gray-600 mt-2 leading-relaxed bg-gray-50 rounded-lg px-3 py-2">
                      {review.comment}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Overview Section ─────────────────────────────────────────────────────────

function OverviewSection({
  stats,
  goToTab,
}: {
  stats: DashboardStats | null;
  goToTab: (tab: Tab) => void;
}) {
  const quickLinks: { label: string; tab: Tab; icon: React.ElementType }[] = [
    { label: "Meus Anúncios", tab: "listings", icon: Package },
    { label: "Minhas Vendas", tab: "sales", icon: TrendingUp },
    { label: "Minhas Compras", tab: "purchases", icon: ShoppingCart },
    { label: "Avaliações", tab: "reviews", icon: Star },
  ];

  return (
    <div className="space-y-6">
      {/* Stats grid — 2 cols on mobile, 4 on desktop */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          icon={TrendingUp}
          label="Vendas"
          value={stats?.totalSales ?? "—"}
          color="bg-emerald-500"
          accent="border-emerald-400"
        />
        <StatCard
          icon={DollarSign}
          label="Receita"
          value={
            stats?.totalSalesRevenue != null
              ? `R$ ${stats.totalSalesRevenue.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`
              : "—"
          }
          color="bg-blue-500"
          accent="border-blue-400"
        />
        <StatCard
          icon={Package}
          label="Anúncios ativos"
          value={stats?.activeListings ?? "—"}
          color="bg-orange-500"
          accent="border-orange-400"
        />
        <StatCard
          icon={Star}
          label="Avaliação média"
          value={
            stats?.averageRating != null
              ? `${stats.averageRating.toFixed(1)} ★`
              : "—"
          }
          color="bg-yellow-500"
          accent="border-yellow-400"
        />
      </div>

      {/* Quick navigation */}
      <div className="bg-white rounded-xl shadow-sm p-5">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">
          Acesso rápido
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {quickLinks.map(({ label, tab, icon: Icon }) => (
            <button
              key={tab}
              onClick={() => goToTab(tab)}
              className="flex flex-col items-center gap-2.5 p-4 bg-gray-50 hover:bg-blue-50 hover:border-secundary/30 border border-gray-100 rounded-xl transition-all group"
            >
              <div className="w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center group-hover:bg-secundary/10 transition-colors border border-gray-100">
                <Icon
                  size={20}
                  className="text-gray-400 group-hover:text-secundary transition-colors"
                />
              </div>
              <span className="text-xs font-semibold text-gray-500 group-hover:text-secundary transition-colors text-center leading-tight">
                {label}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Create listing CTA */}
      <div className="bg-white rounded-xl shadow-sm p-5">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">
          Criar novo anúncio
        </h3>
        <Link
          to="/create-listing"
          className="flex items-center justify-between p-4 bg-linear-to-r from-secundary/5 to-blue-50 hover:from-secundary/10 hover:to-blue-100 border border-secundary/15 rounded-xl transition-all group"
        >
          <div className="flex items-center gap-3.5">
            <div className="p-2.5 bg-secundary rounded-xl shadow-sm">
              <Plus size={18} className="text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-800">
                Anunciar produto
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                Publique um anúncio no marketplace
              </p>
            </div>
          </div>
          <ChevronRight
            size={18}
            className="text-gray-300 group-hover:text-secundary group-hover:translate-x-0.5 transition-all"
          />
        </Link>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "overview", label: "Visão Geral", icon: TrendingUp },
  { id: "listings", label: "Anúncios", icon: Package },
  { id: "sales", label: "Vendas", icon: ShoppingBag },
  { id: "purchases", label: "Compras", icon: ShoppingCart },
  { id: "reviews", label: "Avaliações", icon: Star },
];

export function Dashboard() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchStats() {
      try {
        const [listings, sales, purchases] = await Promise.allSettled([
          productService.getMyListings(),
          orderService.listSales(),
          orderService.listOrders(),
        ]);

        if (cancelled) return;

        const listingsData =
          listings.status === "fulfilled" ? listings.value.results : [];
        const salesData = sales.status === "fulfilled" ? sales.value : [];
        const purchasesData =
          purchases.status === "fulfilled" ? purchases.value : [];

        const activeListings = listingsData.filter(
          (l) => l.is_active && !l.sold_at,
        ).length;
        const completedSales = salesData.filter(
          (s) => s.status !== "cancelled",
        );
        const totalSalesRevenue = completedSales.reduce(
          (sum, s) => sum + Number(s.total),
          0,
        );

        setStats({
          totalSales: completedSales.length,
          totalSalesRevenue,
          totalPurchases: purchasesData.length,
          activeListings,
          averageRating: null,
          totalReviews: 0,
        });
      } catch {
        // stats are non-critical
      }
    }

    async function fetchReviewStats() {
      try {
        const data = await reviewService.getSellerStats();
        if (cancelled) return;
        setReviewStats(data);
        setStats((prev) =>
          prev
            ? {
                ...prev,
                averageRating: data.average_rating,
                totalReviews: data.total_reviews,
              }
            : prev,
        );
      } catch {
        // reviews endpoint may not exist yet - graceful fallback
      }
    }

    // fetchReviewStats runs after fetchStats to avoid a race where setStats(prev => ...)
    // receives prev=null (because fetchStats hasn't resolved yet) and silently drops the data.
    fetchStats().then(() => fetchReviewStats());
    return () => {
      cancelled = true;
    };
  }, []);

  const firstName = user?.full_name?.split(" ")[0] ?? "usuário";

  return (
    // bg-black is intentional: the dashboard uses a dark premium aesthetic distinct from the buyer-facing gray-50 pages
    <div className="min-h-screen bg-black pb-24">
      {/* ── Header banner ── */}
      <div className="relative bg-gray-800 overflow-hidden">
        {/* Decorative background shapes for depth */}
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 50%, #1761b9 0%, transparent 60%), radial-gradient(circle at 80% 20%, #1761b9 0%, transparent 50%)",
          }}
          aria-hidden="true"
        />
        <div className="relative max-w-4xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex items-center gap-4">
            <div>
              <p className="text-white/60 text-xs font-medium uppercase tracking-widest">
                Painel Administrativo
              </p>
              <h1 className="text-white text-xl font-bold mt-0.5">
                Olá, {firstName}!
              </h1>
              <p className="text-white/60 text-xs mt-0.5">
                Gerencie seus anúncios, vendas, compras e avaliações
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 mt-5 space-y-4">
        {/* ── Tab navigation ── */}
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
          <div
            role="tablist"
            aria-label="Seções do painel"
            className="flex overflow-x-auto no-scrollbar"
          >
            {TABS.map(({ id, label, icon: Icon }) => {
              const isActive = activeTab === id;
              return (
                <button
                  key={id}
                  onClick={() => setActiveTab(id)}
                  aria-selected={isActive}
                  role="tab"
                  className={`
                    relative flex items-center justify-center gap-1.5 px-3 py-3.5
                    text-xs font-semibold whitespace-nowrap flex-1
                    transition-colors duration-150
                    ${
                      isActive
                        ? "text-secundary bg-blue-50/70"
                        : "text-gray-400 hover:text-gray-600 hover:bg-gray-50"
                    }
                  `}
                >
                  <Icon
                    size={16}
                    className={isActive ? "text-secundary" : "text-gray-400"}
                    strokeWidth={isActive ? 2.5 : 2}
                  />
                  {/* Label: hidden on very small, shown on sm+ */}
                  <span className="hidden sm:inline">{label}</span>

                  {/* Active indicator bar — bottom of button */}
                  {isActive && (
                    <span
                      className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-secundary"
                      aria-hidden="true"
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Tab content ── */}
        <div
          role="tabpanel"
          aria-label={TABS.find((t) => t.id === activeTab)?.label}
          className="bg-white rounded-xl shadow-sm p-5 sm:p-6"
        >
          {activeTab === "overview" && (
            <OverviewSection stats={stats} goToTab={setActiveTab} />
          )}
          {activeTab === "listings" && <ListingsSection />}
          {activeTab === "sales" && <SalesSection />}
          {activeTab === "purchases" && <PurchasesSection />}
          {activeTab === "reviews" && <ReviewsSection stats={reviewStats} />}
        </div>
      </div>
    </div>
  );
}
