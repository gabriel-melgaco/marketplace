import { useState, useEffect, useRef, useCallback } from "react";
import {
  Package,
  Loader2,
  AlertCircle,
  RefreshCw,
  TrendingUp,
  ShoppingBag,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import Swal from "sweetalert2";
import api from "@/api/axios";
import { shippingService } from "@/services/shippingService";
import { toPublicUrl } from "@/services/storageService";
import { SaleOrderModal } from "@/components/ui/SaleOrderModal";
import type { PaginatedSaleList, PaginatedSaleListItem } from "@/types/orders";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getAxiosErrorMessage(err: unknown, fallback: string): string {
  const responseData = (err as { response?: { data?: unknown } })?.response?.data;
  if (responseData && typeof responseData === "object") {
    const messages = (
      Object.values(responseData as Record<string, unknown>).flat() as unknown[]
    ).filter((v): v is string => typeof v === "string");
    return messages.join(" ") || fallback;
  }
  if (typeof responseData === "string" && responseData) return responseData;
  if (err instanceof Error) return err.message;
  return fallback;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const PAGE_SIZE = 10;

const SWAL_TOAST_CONFIG = {
  toast: true as const,
  position: "top-end" as const,
  showConfirmButton: false,
  timer: 3000,
};

const ORDER_STATUS_LABELS: Record<string, string> = {
  pending_payment: "Aguardando Pagamento",
  paid: "Pago",
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
  processing: "bg-blue-100 text-blue-800",
  shipped: "bg-purple-100 text-purple-800",
  delivered: "bg-green-100 text-green-800",
  completed: "bg-green-100 text-green-800",
  cancelled: "bg-red-100 text-red-800",
  failed: "bg-red-100 text-red-800",
};

// ─── Types ────────────────────────────────────────────────────────────────────

type StatusFilter =
  | "all"
  | "pending_payment"
  | "paid"
  | "processing"
  | "shipped"
  | "delivered"
  | "cancelled";

const FILTER_TABS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "pending_payment", label: "Aguardando Pagamento" },
  { value: "paid", label: "Pago" },
  { value: "processing", label: "Em Processamento" },
  { value: "shipped", label: "Enviado" },
  { value: "delivered", label: "Entregue" },
  { value: "cancelled", label: "Cancelado" },
];

// ─── Card Action Logic ────────────────────────────────────────────────────────

function getCardAction(sale: PaginatedSaleListItem): "generate_tickets" | "view_details" {
  if (sale.status === "paid" || sale.status === "processing") return "generate_tickets";
  return "view_details";
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function CardSkeleton() {
  return (
    <div className="animate-pulse bg-white rounded-xl shadow-sm p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="h-4 bg-gray-100 rounded-md w-32" />
        <div className="h-5 bg-gray-100 rounded-full w-20" />
      </div>
      <div className="flex gap-2">
        <div className="w-10 h-10 bg-gray-100 rounded-full" />
        <div className="w-10 h-10 bg-gray-100 rounded-full" />
        <div className="w-10 h-10 bg-gray-100 rounded-full" />
      </div>
      <div className="flex items-center justify-between pt-2 border-t border-gray-50">
        <div className="h-5 bg-gray-100 rounded-md w-24" />
        <div className="flex gap-2">
          <div className="h-9 bg-gray-100 rounded-xl w-28" />
        </div>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function MySales() {
  const navigate = useNavigate();
  const [sales, setSales] = useState<PaginatedSaleListItem[]>([]);
  const [count, setCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generatingForOrder, setGeneratingForOrder] = useState<string | null>(null);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);

  const isGeneratingRef = useRef(false);

  const loadSales = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError("");
      try {
        const response = await api.get<PaginatedSaleList>("/orders/sales/", {
          signal,
          params: {
            page: currentPage,
            ...(filter !== "all" && { status: filter }),
          },
        });
        if (signal?.aborted) return;
        const data = response.data;
        setSales(data.results);
        setCount(data.count);
        setHasNext(data.next !== null);
        setHasPrev(data.previous !== null);
      } catch (err: unknown) {
        if ((err as { name?: string })?.name === "AbortError") return;
        if ((err as { name?: string })?.name === "CanceledError") return;
        setError(getAxiosErrorMessage(err, "Erro ao carregar suas vendas."));
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [currentPage, filter],
  );

  // Reset to page 1 when filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [filter]);

  useEffect(() => {
    const controller = new AbortController();
    loadSales(controller.signal);
    return () => controller.abort();
  }, [loadSales]);

  async function handleGenerateTickets(saleId: string) {
    if (isGeneratingRef.current) return;
    isGeneratingRef.current = true;
    setGeneratingForOrder(saleId);
    try {
      await shippingService.createShipments({ order_id: saleId });
      Swal.fire({
        ...SWAL_TOAST_CONFIG,
        icon: "success",
        title: "Tickets de envio gerados com sucesso!",
      });
      const controller = new AbortController();
      await loadSales(controller.signal);
    } catch (err: unknown) {
      Swal.fire({
        ...SWAL_TOAST_CONFIG,
        icon: "error",
        title: getAxiosErrorMessage(err, "Erro ao gerar tickets de envio."),
      });
    } finally {
      isGeneratingRef.current = false;
      setGeneratingForOrder(null);
    }
  }

  // ─── Render ─────────────────────────────────────────────────────────────────

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        {/* Page header */}
        <div className="flex items-center gap-3 mb-6">
          <TrendingUp size={24} className="text-blue-900" />
          <h1 className="text-2xl font-bold text-gray-900">Minhas Vendas</h1>
          {!loading && (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
              {count} {count === 1 ? "venda" : "vendas"}
            </span>
          )}
        </div>

        {/* Filter tabs with scroll affordance */}
        <div className="relative mb-6">
          <div className="flex items-center gap-2 overflow-x-auto no-scrollbar pb-2">
            {FILTER_TABS.map((tab) => {
              const isActive = filter === tab.value;
              return (
                <button
                  key={tab.value}
                  onClick={() => setFilter(tab.value)}
                  className={`
                    flex-shrink-0 px-4 py-2 rounded-xl text-sm font-semibold transition-colors whitespace-nowrap
                    ${
                      isActive
                        ? "bg-blue-900 text-white shadow-sm"
                        : "bg-white border border-gray-200 text-gray-600 hover:border-blue-900/40 hover:text-blue-900"
                    }
                  `}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
          {/* Right fade affordance */}
          <div className="pointer-events-none absolute right-0 top-0 bottom-2 w-10 bg-gradient-to-l from-gray-50 to-transparent" />
        </div>

        {/* Error state */}
        {error && !loading && (
          <div className="flex flex-col items-center justify-center py-12 text-center gap-3 bg-red-50/50 rounded-xl border border-red-100">
            <AlertCircle size={32} className="text-red-400" />
            <p className="text-gray-600 text-sm">{error}</p>
            <button
              onClick={() => loadSales()}
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-blue-900 hover:text-blue-800 transition-colors"
            >
              <RefreshCw size={13} />
              Tentar novamente
            </button>
          </div>
        )}

        {/* Loading skeletons */}
        {loading && (
          <div className="space-y-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && sales.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
            <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center">
              <TrendingUp size={30} className="text-gray-400" />
            </div>
            <p className="text-gray-700 font-semibold text-sm">
              {filter === "all"
                ? "Nenhuma venda realizada ainda"
                : "Nenhuma venda com este status"}
            </p>
            <p className="text-gray-400 text-xs max-w-xs">
              {filter === "all"
                ? "Suas vendas aparecerão aqui quando alguém comprar seus anúncios."
                : "Tente outro filtro para ver suas vendas."}
            </p>
            {filter === "all" && (
              <button
                onClick={() => navigate("/dashboard?tab=listings")}
                className="mt-1 inline-flex items-center gap-1.5 px-4 py-2 border border-blue-900 text-blue-900 rounded-xl text-sm font-semibold hover:bg-blue-50 transition-colors"
              >
                <ShoppingBag size={14} />
                Gerenciar Anúncios
              </button>
            )}
          </div>
        )}

        {/* Sales cards */}
        {!loading && !error && sales.length > 0 && (
          <div className="space-y-4">
            {sales.map((sale) => {
              const action = getCardAction(sale);
              const isGenerating = generatingForOrder === sale.id;
              const items = sale.items ?? [];
              const visibleItems = items.slice(0, 3);
              const extraCount = items.length - 3;

              return (
                <div
                  key={sale.id}
                  className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden"
                >
                  {/* Card header */}
                  <div className="flex items-center justify-between px-4 py-3 border-b border-gray-50">
                    <div>
                      <p className="text-sm font-bold text-gray-900">
                        Pedido #{sale.order_number}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {new Date(sale.created_at).toLocaleDateString("pt-BR", {
                          day: "2-digit",
                          month: "2-digit",
                          year: "numeric",
                        })}
                      </p>
                    </div>
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${ORDER_STATUS_COLORS[sale.status] ?? "bg-gray-100 text-gray-700"}`}
                    >
                      {ORDER_STATUS_LABELS[sale.status] ?? sale.status}
                    </span>
                  </div>

                  {/* Card body */}
                  <div className="px-4 py-3">
                    {/* Item thumbnails */}
                    {items.length > 0 ? (
                      <div className="flex items-center gap-2 mb-4">
                        {visibleItems.map((item) => {
                          const imgSrc =
                            item.listing.primary_image
                              ? toPublicUrl(item.listing.primary_image)
                              : item.listing.images?.[0]?.image_url
                                ? toPublicUrl(item.listing.images[0].image_url)
                                : null;

                          return (
                            <div
                              key={item.id}
                              className="w-10 h-10 rounded-full overflow-hidden bg-gray-100 border-2 border-white shadow-sm flex items-center justify-center shrink-0"
                              title={item.listing.title}
                            >
                              {imgSrc ? (
                                <img
                                  src={imgSrc}
                                  alt={item.listing.title}
                                  className="w-full h-full object-cover"
                                  loading="lazy"
                                />
                              ) : (
                                <Package size={14} className="text-gray-300" />
                              )}
                            </div>
                          );
                        })}
                        {extraCount > 0 && (
                          <div
                            className="w-10 h-10 rounded-full bg-gray-100 border-2 border-white shadow-sm flex items-center justify-center shrink-0"
                            title={`+ ${extraCount} ${extraCount === 1 ? "item" : "itens"} — clique em Ver Detalhes`}
                            aria-label={`e mais ${extraCount} ${extraCount === 1 ? "item" : "itens"}`}
                          >
                            <span className="text-xs font-bold text-gray-500">
                              +{extraCount}
                            </span>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="mb-4" />
                    )}

                    {/* Bottom row: total + actions */}
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                      <p className="text-base font-extrabold text-blue-800">
                        R${" "}
                        {Number(sale.total).toLocaleString("pt-BR", {
                          minimumFractionDigits: 2,
                        })}
                      </p>

                      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                        {action === "generate_tickets" && (
                          <button
                            onClick={() => handleGenerateTickets(sale.id)}
                            disabled={isGenerating}
                            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-blue-900 text-white rounded-xl text-xs font-semibold hover:bg-blue-800 transition-colors disabled:opacity-60"
                          >
                            {isGenerating ? (
                              <Loader2 size={13} className="animate-spin" />
                            ) : null}
                            {isGenerating ? "Gerando…" : "Gerar Tickets"}
                          </button>
                        )}

                        <button
                          onClick={() => setSelectedOrderId(sale.id)}
                          className="flex items-center justify-center gap-1.5 px-3 py-2 border border-gray-200 text-gray-600 rounded-xl text-xs font-semibold hover:border-blue-900/40 hover:text-blue-900 transition-colors"
                        >
                          Ver Detalhes
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination */}
        {(hasPrev || hasNext) && (
          <div className="flex justify-center items-center gap-4 mt-6">
            <button
              onClick={() => setCurrentPage((p) => p - 1)}
              disabled={!hasPrev}
              className="px-4 py-2 border border-gray-200 rounded-xl text-sm font-semibold text-gray-600 hover:border-blue-900/40 hover:text-blue-900 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ← Anterior
            </button>
            <span className="text-sm text-gray-500 font-medium">
              Página {currentPage} de {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage((p) => p + 1)}
              disabled={!hasNext}
              className="px-4 py-2 border border-gray-200 rounded-xl text-sm font-semibold text-gray-600 hover:border-blue-900/40 hover:text-blue-900 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Próxima →
            </button>
          </div>
        )}
      </div>

      {/* Order detail modal */}
      {selectedOrderId && (
        <SaleOrderModal
          orderId={selectedOrderId}
          onClose={() => setSelectedOrderId(null)}
          onOrderUpdated={() => loadSales()}
        />
      )}
    </div>
  );
}
