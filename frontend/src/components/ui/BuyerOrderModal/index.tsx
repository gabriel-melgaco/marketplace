import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  X,
  Package,
  MapPin,
  Truck,
  ExternalLink,
} from "lucide-react";
import Swal from "sweetalert2";
import { orderService } from "@/services/orderService";
import { shippingService } from "@/services/shippingService";
import { inPersonService } from "@/services/inPersonService";
import type { InPersonDelivery } from "@/services/inPersonService";
import { InPersonDeliveryPanel } from "@/components/ui/InPersonDeliveryPanel";
import { toPublicUrl } from "@/services/storageService";
import type { Order } from "@/services/orderService";
import type { SellerShipment } from "@/types/orders";

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

const SHIPMENT_STATUS_LABELS: Record<string, string> = {
  created: "Criado",
  pending: "Pendente",
  released: "Liberado",
  generated: "Etiqueta gerada",
  posted: "Postado",
  in_transit: "Em trânsito",
  out_for_delivery: "Saiu para entrega",
  delivered: "Entregue",
  cancelled: "Cancelado",
  returned: "Devolvido",
};

const SHIPMENT_STATUS_COLORS: Record<string, string> = {
  created: "bg-gray-100 text-gray-700",
  pending: "bg-yellow-100 text-yellow-800",
  released: "bg-yellow-100 text-yellow-800",
  generated: "bg-blue-100 text-blue-800",
  posted: "bg-purple-100 text-purple-800",
  in_transit: "bg-purple-100 text-purple-800",
  out_for_delivery: "bg-indigo-100 text-indigo-800",
  delivered: "bg-green-100 text-green-800",
  cancelled: "bg-red-100 text-red-800",
  returned: "bg-red-100 text-red-800",
};

const PAYMENT_METHOD_LABELS: Record<string, string> = {
  credit_card: "Cartão de Crédito",
  debit_card: "Cartão de Débito",
  pix: "PIX",
  boleto: "Boleto Bancário",
  boleto_bancario: "Boleto Bancário",
};

const SWAL_TOAST_CONFIG = {
  toast: true as const,
  position: "top-end" as const,
  showConfirmButton: false,
  timer: 3000,
};

// ─── Props ────────────────────────────────────────────────────────────────────

interface BuyerOrderModalProps {
  orderId: string;
  onClose: () => void;
  onOrderCancelled?: () => void;
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function ModalSkeleton() {
  return (
    <div className="p-5 space-y-5 animate-pulse">
      {/* Header row skeleton */}
      <div className="flex items-center justify-between">
        <div className="h-4 bg-gray-100 rounded-md w-28" />
        <div className="h-5 bg-gray-100 rounded-full w-20" />
      </div>
      {/* Info block */}
      <div className="h-24 bg-gray-100 rounded-xl w-full" />
      {/* Items block */}
      <div className="h-32 bg-gray-100 rounded-xl w-full" />
      {/* Address block */}
      <div className="h-20 bg-gray-100 rounded-xl w-full" />
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function BuyerOrderModal({
  orderId,
  onClose,
  onOrderCancelled,
}: BuyerOrderModalProps) {
  const [order, setOrder] = useState<Order | null>(null);
  const [shipments, setShipments] = useState<SellerShipment[]>([]);
  const [inPersonDeliveries, setInPersonDeliveries] = useState<InPersonDelivery[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState(false);

  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const isCancellingRef = useRef(false);

  // Focus into modal on open
  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  // Lock body scroll
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  // Close on Escape
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const fetchShipments = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const result = await shippingService.getOrderShipments(orderId);
        if (signal?.aborted) return;
        setShipments(result.shipments);
      } catch (err: unknown) {
        if ((err as { name?: string })?.name === "AbortError") return;
        if ((err as { name?: string })?.name === "CanceledError") return;
        // Non-critical: shipments may not exist yet — fail silently
      }
    },
    [orderId],
  );

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    async function fetchAll() {
      setLoading(true);
      setError("");
      try {
        // Fetch order (critical) and shipments (non-critical) in parallel
        const [orderRes] = await Promise.all([
          orderService.getOrder(orderId),
          fetchShipments(signal),
        ]);
        if (signal.aborted) return;
        setOrder(orderRes);

        // Fetch in-person deliveries (non-critical)
        try {
          const ipRes = await inPersonService.list({ role: "buyer" });
          if (!signal.aborted) {
            const filtered = ipRes.deliveries.filter(
              (d) => !d.order || d.order === orderId,
            );
            setInPersonDeliveries(filtered);
          }
        } catch {
          // non-critical — fail silently
        }
      } catch (err: unknown) {
        if ((err as { name?: string })?.name === "AbortError") return;
        if ((err as { name?: string })?.name === "CanceledError") return;
        setError(getAxiosErrorMessage(err, "Erro ao carregar pedido."));
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    }

    fetchAll();
    return () => controller.abort();
  }, [orderId, fetchShipments]);

  // ─── Cancel Action ──────────────────────────────────────────────────────────

  async function handleCancelOrder() {
    if (isCancellingRef.current) return;

    const result = await Swal.fire({
      title: "Cancelar pedido?",
      text: "Esta ação não pode ser desfeita.",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, cancelar",
      cancelButtonText: "Voltar",
      confirmButtonColor: "#dc2626",
    });

    if (!result.isConfirmed) return;

    isCancellingRef.current = true;
    setCancelling(true);

    try {
      await orderService.cancelOrder(orderId);
      Swal.fire({
        ...SWAL_TOAST_CONFIG,
        icon: "success",
        title: "Pedido cancelado com sucesso!",
      });
      onOrderCancelled?.();
      onClose();
    } catch (err: unknown) {
      Swal.fire({
        ...SWAL_TOAST_CONFIG,
        icon: "error",
        title: getAxiosErrorMessage(err, "Erro ao cancelar pedido."),
      });
    } finally {
      isCancellingRef.current = false;
      setCancelling(false);
    }
  }

  // ─── Render ─────────────────────────────────────────────────────────────────

  const canCancel =
    order?.status === "pending_payment" || order?.status === "processing";

  const shippingAddress = order?.shipping_address as
    | {
        recipient_name?: string;
        recipient_phone?: string;
        street: string;
        number: string;
        complement?: string;
        neighborhood: string;
        city: string;
        state: string;
        zipcode: string;
      }
    | null
    | undefined;

  const content = (
    <div
      className="fixed inset-0 z-50 flex"
      role="dialog"
      aria-modal="true"
      aria-labelledby="buyer-order-modal-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer — full screen on mobile, right panel on desktop */}
      <div className="relative ml-auto flex flex-col bg-white w-full lg:max-w-xl h-full shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 shrink-0">
          <h2
            id="buyer-order-modal-title"
            className="text-base font-bold text-gray-900"
          >
            {order ? `Pedido #${order.order_number}` : "Carregando pedido…"}
          </h2>
          <button
            ref={closeButtonRef}
            onClick={onClose}
            className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            aria-label="Fechar"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {loading && <ModalSkeleton />}

          {!loading && error && (
            <div className="p-5">
              <div className="bg-red-50 border border-red-100 rounded-xl p-4 text-sm text-red-700">
                {error}
              </div>
            </div>
          )}

          {!loading && !error && order && (
            <div className="p-5 space-y-6">
              {/* Section: Order Info */}
              <section>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
                  Informações do Pedido
                </h3>
                <div className="bg-gray-50 rounded-xl p-4 space-y-3">
                  {/* Order number + date + status */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">Status</span>
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                        ORDER_STATUS_COLORS[order.status] ??
                        "bg-gray-100 text-gray-700"
                      }`}
                    >
                      {ORDER_STATUS_LABELS[order.status] ?? order.status}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">Data do pedido</span>
                    <span className="text-sm font-medium text-gray-800">
                      {new Date(order.created_at).toLocaleDateString("pt-BR", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">
                      Método de pagamento
                    </span>
                    <span className="text-sm font-medium text-gray-800">
                      {PAYMENT_METHOD_LABELS[order.payment_method] ??
                        order.payment_method}
                    </span>
                  </div>
                  {order.buyer_notes && (
                    <div className="pt-2 border-t border-gray-200">
                      <p className="text-xs text-gray-500 mb-1">
                        Suas anotações
                      </p>
                      <p className="text-sm text-gray-700 bg-white rounded-lg px-3 py-2 border border-gray-100">
                        {order.buyer_notes}
                      </p>
                    </div>
                  )}
                </div>
              </section>

              {/* Section: Order Items */}
              <section>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
                  Itens do Pedido
                </h3>
                <div className="space-y-3">
                  {order.items.map((item) => {
                    const listing = item.listing as {
                      title?: string;
                      primary_image?: string | null;
                      images?: Array<{ image_url: string }>;
                      product?: { name: string };
                    };

                    const imgSrc = listing.primary_image
                      ? toPublicUrl(listing.primary_image)
                      : listing.images?.[0]?.image_url
                        ? toPublicUrl(listing.images[0].image_url)
                        : null;

                    const title =
                      listing.title ?? listing.product?.name ?? "Produto";

                    return (
                      <div
                        key={item.id}
                        className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl"
                      >
                        <div className="w-14 h-14 rounded-xl overflow-hidden bg-gray-200 shrink-0 flex items-center justify-center border border-gray-100">
                          {imgSrc ? (
                            <img
                              src={imgSrc}
                              alt={title}
                              className="w-full h-full object-cover"
                              loading="lazy"
                            />
                          ) : (
                            <Package size={20} className="text-gray-300" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-gray-800 truncate">
                            {title}
                          </p>
                          <p className="text-xs text-gray-500 mt-0.5">
                            {item.quantity}x R${" "}
                            {Number(item.unit_price).toLocaleString("pt-BR", {
                              minimumFractionDigits: 2,
                            })}
                          </p>
                        </div>
                        <p className="text-sm font-bold text-gray-800 shrink-0">
                          R${" "}
                          {Number(item.subtotal).toLocaleString("pt-BR", {
                            minimumFractionDigits: 2,
                          })}
                        </p>
                      </div>
                    );
                  })}

                  {/* Total row */}
                  <div className="flex items-center justify-between px-3 py-2 border-t border-gray-100 mt-1">
                    <span className="text-sm font-semibold text-gray-600">
                      Total
                    </span>
                    <span className="text-base font-extrabold text-blue-800">
                      R${" "}
                      {Number(order.total).toLocaleString("pt-BR", {
                        minimumFractionDigits: 2,
                      })}
                    </span>
                  </div>
                </div>
              </section>

              {/* Section: Shipping Address */}
              {shippingAddress && (
                <section>
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
                    Endereço de Entrega
                  </h3>
                  <div className="bg-gray-50 rounded-xl p-4 flex gap-3">
                    <MapPin
                      size={16}
                      className="text-gray-400 shrink-0 mt-0.5"
                    />
                    <div className="text-sm text-gray-700 space-y-0.5">
                      {shippingAddress.recipient_name && (
                        <p className="font-semibold text-gray-800">
                          {shippingAddress.recipient_name}
                        </p>
                      )}
                      <p>
                        {shippingAddress.street}, {shippingAddress.number}
                        {shippingAddress.complement
                          ? ` — ${shippingAddress.complement}`
                          : ""}
                      </p>
                      <p>
                        {shippingAddress.neighborhood} —{" "}
                        {shippingAddress.city}/{shippingAddress.state}
                      </p>
                      <p>CEP: {shippingAddress.zipcode}</p>
                      {shippingAddress.recipient_phone && (
                        <p className="text-gray-500">
                          Tel: {shippingAddress.recipient_phone}
                        </p>
                      )}
                    </div>
                  </div>
                </section>
              )}

              {/* Section: Tracking */}
              {shipments.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
                    Rastreamento
                  </h3>
                  <div className="space-y-3">
                    {shipments.map((shipment) => (
                      <div
                        key={shipment.id}
                        className="border border-gray-100 rounded-xl overflow-hidden"
                      >
                        {/* Shipment header */}
                        <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-100">
                          <p className="text-sm font-semibold text-gray-800">
                            <Truck
                              size={13}
                              className="inline mr-1.5 text-gray-400"
                            />
                            {shipment.carrier_name} — {shipment.service_name}
                          </p>
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                              SHIPMENT_STATUS_COLORS[shipment.status] ??
                              "bg-gray-100 text-gray-700"
                            }`}
                          >
                            {SHIPMENT_STATUS_LABELS[shipment.status] ??
                              shipment.status}
                          </span>
                        </div>

                        {/* Shipment body */}
                        <div className="p-4 space-y-2">
                          {shipment.tracking_code && (
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-gray-500">
                                Código de rastreamento
                              </span>
                              <span className="font-mono font-semibold text-gray-800">
                                {shipment.tracking_code}
                              </span>
                            </div>
                          )}
                          {shipment.estimated_delivery_date && (
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-gray-500">
                                Previsão de entrega
                              </span>
                              <span className="font-medium text-gray-800">
                                {new Date(
                                  shipment.estimated_delivery_date,
                                ).toLocaleDateString("pt-BR")}
                              </span>
                            </div>
                          )}
                          {shipment.tracking_url && (
                            <button
                              onClick={() =>
                                window.open(
                                  shipment.tracking_url,
                                  "_blank",
                                  "noopener,noreferrer",
                                )
                              }
                              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 border border-blue-900 text-blue-900 rounded-xl text-sm font-semibold hover:bg-blue-50 transition-colors mt-1"
                            >
                              <ExternalLink size={15} />
                              Rastrear envio
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Section: In-Person Deliveries */}
              {inPersonDeliveries.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
                    Entrega Presencial
                  </h3>
                  <div className="space-y-4">
                    {inPersonDeliveries.map((d) => (
                      <InPersonDeliveryPanel
                        key={d.id}
                        deliveryId={d.id}
                        role="buyer"
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Section: Cancel */}
              {canCancel && (
                <section>
                  <div className="border border-red-100 rounded-xl p-4 bg-red-50/40">
                    <p className="text-xs text-gray-500 mb-3">
                      Você pode cancelar este pedido enquanto ele ainda não foi
                      processado para envio.
                    </p>
                    <button
                      onClick={handleCancelOrder}
                      disabled={cancelling}
                      className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-red-600 text-white rounded-xl text-sm font-semibold hover:bg-red-700 transition-colors disabled:opacity-60"
                    >
                      {cancelling ? "Cancelando…" : "Cancelar pedido"}
                    </button>
                  </div>
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(content, document.body);
}
