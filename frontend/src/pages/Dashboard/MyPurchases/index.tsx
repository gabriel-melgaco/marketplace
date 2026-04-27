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
  pending_payment: "bg-yellow-100 text-yellow-800",
  paid: "bg-blue-100 text-blue-800",
  processing: "bg-blue-100 text-blue-800",
  shipped: "bg-purple-100 text-purple-800",
  delivered: "bg-green-100 text-green-800",
  completed: "bg-green-100 text-green-800",
  cancelled: "bg-red-100 text-red-800",
  failed: "bg-red-100 text-red-800",
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
  const colorClass = ORDER_STATUS_COLORS[status] ?? "bg-gray-100 text-gray-700";
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
    <div className="bg-white rounded-xl shadow-sm p-4 animate-pulse">
      <div className="flex items-center justify-between mb-3">
        <div className="h-4 bg-gray-100 rounded-md w-36" />
        <div className="h-3 bg-gray-100 rounded-md w-20" />
      </div>
      <div className="h-5 bg-gray-100 rounded-full w-28 mb-3" />
      <div className="flex items-center justify-between">
        <div className="h-4 bg-gray-100 rounded-md w-24" />
        <div className="h-8 bg-gray-100 rounded-lg w-24" />
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
    <div className="min-h-screen bg-gray-50 pb-16">
      {/* Page header */}
      <div className="bg-white border-b border-gray-100 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-secundary rounded-xl">
              <ShoppingCart size={20} className="text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">
                Minhas Compras
              </h1>
              {!loading && !error && (
                <p className="text-sm text-gray-500 mt-0.5">
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
                  onClick={() => setStatusFilter(filter.value)}
                  role="tab"
                  aria-selected={isActive}
                  className={`
                    whitespace-nowrap px-3.5 py-2 rounded-lg text-xs font-semibold transition-colors shrink-0
                    ${
                      isActive
                        ? "bg-secundary text-white shadow-sm"
                        : "bg-white text-gray-500 hover:bg-gray-100 border border-gray-200"
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
          <div className="flex flex-col items-center justify-center py-14 text-center gap-3 bg-white rounded-xl shadow-sm border border-red-100">
            <AlertCircle size={32} className="text-red-400" />
            <p className="text-gray-600 text-sm">{error}</p>
            <button
              onClick={loadOrders}
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-secundary hover:text-secundary/80 transition-colors"
            >
              <RefreshCw size={13} />
              Tentar novamente
            </button>
          </div>
        )}

        {!loading && !error && orders.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center gap-3 bg-white rounded-xl shadow-sm">
            <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center">
              <ShoppingCart size={30} className="text-gray-400" />
            </div>
            <p className="text-gray-700 font-semibold text-sm">
              Você ainda não fez nenhuma compra
            </p>
            <p className="text-gray-400 text-xs max-w-xs">
              Explore o marketplace e encontre produtos incríveis.
            </p>
            <Link
              to="/"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-secundary text-white rounded-lg text-sm font-semibold hover:bg-secundary/90 transition-colors shadow-sm mt-1"
            >
              <ShoppingBag size={14} />
              Explorar produtos
            </Link>
          </div>
        )}

        {!loading && !error && orders.length > 0 && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-14 text-center gap-3 bg-white rounded-xl shadow-sm">
            <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center">
              <ShoppingCart size={30} className="text-gray-400" />
            </div>
            <p className="text-gray-700 font-semibold text-sm">
              Nenhum pedido com este status
            </p>
            <button
              onClick={() => setStatusFilter("all")}
              className="text-sm font-semibold text-secundary hover:text-secundary/80 transition-colors"
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
                onClick={() => setSelectedOrderId(order.id)}
                className="bg-white rounded-xl shadow-sm p-4 cursor-pointer hover:shadow-md transition-shadow"
              >
                {/* Row 1: order number + date */}
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-bold text-gray-800">
                    Pedido #{order.order_number}
                  </p>
                  <p className="text-xs text-gray-400">
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
                  <p className="text-sm font-extrabold text-gray-900">
                    R${" "}
                    {Number(order.total).toLocaleString("pt-BR", {
                      minimumFractionDigits: 2,
                    })}
                  </p>

                  {order.status === "shipped" ? (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedOrderId(order.id);
                      }}
                      className="px-3 py-1.5 bg-purple-100 text-purple-800 rounded-lg text-xs font-semibold hover:bg-purple-200 transition-colors"
                    >
                      Rastrear
                    </button>
                  ) : order.status !== "pending_payment" ? (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedOrderId(order.id);
                      }}
                      className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-xs font-semibold hover:bg-gray-200 transition-colors"
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
          <div className="flex items-center justify-between mt-4 bg-white rounded-xl shadow-sm px-4 py-3">
            <button
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-4 py-2 text-sm font-semibold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Anterior
            </button>
            <span className="text-sm text-gray-500 font-medium">
              Página {page} de {totalPages}
            </span>
            <button
              disabled={page === totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="px-4 py-2 text-sm font-semibold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
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
