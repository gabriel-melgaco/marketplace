import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  ShoppingBag,
  ShoppingCart,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { orderService } from "@/services/orderService";
import { BuyerOrderModal } from "@/components/ui/BuyerOrderModal";
import type { OrderList } from "@/services/orderService";

// ─── Constants ───────────────────────────────────────────────────────────────

const ORDER_STATUS_COLORS: Record<string, string> = {
  pending_payment: "bg-amber-500/10 text-amber-400 border border-amber-500/30",
  paid: "bg-gold/10 text-gold border border-gold/30",
  processing: "bg-gold/10 text-gold border border-gold/30",
  shipped: "bg-purple-500/10 text-purple-400 border border-purple-500/30",
  delivered: "bg-green-500/10 text-green-400 border border-green-500/30",
  completed: "bg-green-500/10 text-green-400 border border-green-500/30",
  cancelled: "bg-red-500/10 text-red-400 border border-red-500/30",
  failed: "bg-red-500/10 text-red-400 border border-red-500/30",
};

const STATUS_FILTERS = [
  { value: "all", label: "Todos" },
  { value: "pending_payment", label: "Aguardando Pagamento" },
  { value: "paid", label: "Pagos" },
  { value: "processing", label: "Em Processamento" },
  { value: "shipped", label: "Enviados" },
  { value: "delivered", label: "Entregues" },
  { value: "cancelled", label: "Cancelados" },
];

const PAGE_SIZE = 10;

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBadge({
  status,
  statusDisplay,
}: {
  status: string;
  statusDisplay: string;
}) {
  const colorClass =
    ORDER_STATUS_COLORS[status] ?? "bg-bg-2 text-ink-2 border border-white/10";
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${colorClass}`}
    >
      {statusDisplay}
    </span>
  );
}

function OrderCardSkeleton() {
  return (
    <div className="bg-bg-1 border border-white/10 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] p-4 animate-pulse">
      <div className="flex items-center justify-between mb-3">
        <div className="h-4 bg-bg-2 rounded-md w-36" />
        <div className="h-3 bg-bg-2 rounded-md w-20" />
      </div>
      <div className="h-5 bg-bg-2 rounded-full w-28 mb-3" />
      <div className="flex items-center justify-between">
        <div className="h-4 bg-bg-2 rounded-md w-24" />
        <div className="h-8 bg-bg-2 rounded-lg w-24" />
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function MyPurchase() {
  const [orders, setOrders] = useState<OrderList[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);

  const loadOrders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await orderService.listOrders();
      setOrders(data);
    } catch {
      setError("Não foi possível carregar seus pedidos. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOrders();
  }, [loadOrders]);

  // Reset page when filter changes
  useEffect(() => {
    setPage(1);
  }, [statusFilter]);

  // ─── Derived state ──────────────────────────────────────────────────────────

  const filtered =
    statusFilter === "all"
      ? orders
      : orders.filter((o) => o.status === statusFilter);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-bg-0 pb-16">
      {/* Page header */}
      <div className="bg-bg-1 border-b border-white/10">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center shrink-0">
              <ShoppingCart
                size={22}
                className="text-gold"
                aria-hidden="true"
              />
            </div>
            <div>
              <h1 className="font-display text-2xl sm:text-3xl font-bold text-ink-1 tracking-[-0.02em]">
                Minhas Compras
              </h1>
              {!loading && !error && (
                <p className="text-sm text-ink-2 mt-0.5">
                  {orders.length} pedido{orders.length !== 1 ? "s" : ""}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 sm:px-6 mt-6 space-y-4">
        {/* Status filter tabs */}
        <div className="overflow-x-auto no-scrollbar">
          <div
            className="flex gap-2 pb-1"
            role="tablist"
            aria-label="Filtrar por status"
          >
            {STATUS_FILTERS.map((filter) => {
              const isActive = statusFilter === filter.value;
              return (
                <button
                  key={filter.value}
                  type="button"
                  onClick={() => setStatusFilter(filter.value)}
                  role="tab"
                  aria-selected={isActive}
                  className={`
                    whitespace-nowrap px-3.5 py-2 rounded-xl text-xs font-semibold transition-colors shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-0
                    ${
                      isActive
                        ? "bg-gold text-gold-deep"
                        : "bg-bg-1 border border-white/10 text-ink-2 hover:bg-bg-2 hover:border-white/20 hover:text-ink-1"
                    }
                  `}
                >
                  {filter.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Content area */}
        {loading && (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <OrderCardSkeleton key={i} />
            ))}
          </div>
        )}
        {!loading && error && (
          <div
            role="alert"
            className="flex flex-col items-center justify-center py-14 text-center gap-3 bg-bg-1 rounded-2xl border border-red-500/30 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]"
          >
            <AlertCircle
              size={32}
              className="text-red-400"
              aria-hidden="true"
            />
            <p className="text-ink-2 text-sm">{error}</p>
            <button
              type="button"
              onClick={loadOrders}
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:text-gold/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-0 rounded-md px-1"
            >
              <RefreshCw size={13} aria-hidden="true" />
              Tentar novamente
            </button>
          </div>
        )}
        {!loading && !error && orders.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center gap-3 bg-bg-1 rounded-2xl border border-white/10 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
            <div className="w-16 h-16 rounded-2xl bg-bg-2 border border-white/10 flex items-center justify-center">
              <ShoppingCart
                size={28}
                className="text-ink-3"
                aria-hidden="true"
              />
            </div>
            <p className="text-ink-1 font-semibold text-sm">
              Você ainda não fez nenhuma compra
            </p>
            <p className="text-ink-3 text-xs max-w-xs leading-relaxed">
              Explore o marketplace e encontre produtos incríveis.
            </p>
            <Link
              to="/"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-gold text-gold-deep rounded-xl text-sm font-semibold hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-0 mt-1"
            >
              <ShoppingBag size={14} aria-hidden="true" />
              Explorar produtos
            </Link>
          </div>
        )}
        {!loading && !error && orders.length > 0 && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-14 text-center gap-3 bg-bg-1 rounded-2xl border border-white/10 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
            <div className="w-16 h-16 rounded-2xl bg-bg-2 border border-white/10 flex items-center justify-center">
              <ShoppingCart
                size={28}
                className="text-ink-3"
                aria-hidden="true"
              />
            </div>
            <p className="text-ink-1 font-semibold text-sm">
              Nenhum pedido com este status
            </p>
            <button
              type="button"
              onClick={() => setStatusFilter("all")}
              className="text-sm font-semibold text-gold hover:text-gold/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-0 rounded-md px-1"
            >
              Ver todos os pedidos
            </button>
          </div>
        )}

        {!loading && !error && paginated.length > 0 && (
          <div className="space-y-3">
            {paginated.map((order) => (
              <div
                key={order.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedOrderId(order.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelectedOrderId(order.id);
                  }
                }}
                className="bg-bg-1 rounded-2xl border border-white/10 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] p-4 cursor-pointer hover:border-white/20 hover:bg-bg-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-0"
              >
                {/* Row 1: order number + date */}
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-bold text-ink-1">
                    Pedido #{order.order_number}
                  </p>
                  <p className="text-xs text-ink-3">
                    {new Date(order.created_at).toLocaleDateString("pt-BR", {
                      day: "2-digit",
                      month: "2-digit",
                      year: "numeric",
                    })}
                  </p>
                </div>

                {/* Row 2: status badge */}
                <div className="mb-3">
                  <StatusBadge
                    status={order.status}
                    statusDisplay={order.status_display}
                  />
                </div>

                {/* Row 3: total + contextual button */}
                <div className="flex items-center justify-between">
                  <p className="text-sm font-extrabold text-ink-1">
                    R${" "}
                    {Number(order.total).toLocaleString("pt-BR", {
                      minimumFractionDigits: 2,
                    })}
                  </p>

                  {order.status === "shipped" ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedOrderId(order.id);
                      }}
                      className="px-3 py-1.5 bg-purple-500/10 text-purple-400 border border-purple-500/30 rounded-xl text-xs font-semibold hover:bg-purple-500/20 transition-colors"
                    >
                      Rastrear
                    </button>
                  ) : order.status !== "pending_payment" ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedOrderId(order.id);
                      }}
                      className="px-3 py-1.5 bg-bg-2 text-ink-1 border border-white/10 rounded-xl text-xs font-semibold hover:bg-bg-3 hover:border-white/20 transition-colors"
                    >
                      Ver detalhes
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {!loading && !error && totalPages > 1 && (
          <div className="flex items-center justify-between mt-4 bg-bg-1 border border-white/10 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] px-4 py-3">
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-4 py-2 text-sm font-semibold text-ink-1 bg-bg-2 border border-white/10 rounded-xl hover:bg-bg-3 hover:border-white/20 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-bg-2 disabled:hover:border-white/10"
            >
              Anterior
            </button>
            <span className="text-sm text-ink-2 font-medium">
              Página <span className="text-ink-1 font-semibold">{page}</span> de{" "}
              <span className="text-ink-1 font-semibold">{totalPages}</span>
            </span>
            <button
              type="button"
              disabled={page === totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="px-4 py-2 text-sm font-semibold text-ink-1 bg-bg-2 border border-white/10 rounded-xl hover:bg-bg-3 hover:border-white/20 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-bg-2 disabled:hover:border-white/10"
            >
              Próxima
            </button>
          </div>
        )}
      </div>

      {/* Order detail modal */}
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
