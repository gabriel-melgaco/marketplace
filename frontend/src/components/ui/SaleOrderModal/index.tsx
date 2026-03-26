import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  X,
  Loader2,
  Package,
  MapPin,
  Truck,
  ExternalLink,
  Send,
  User,
} from "lucide-react";
import Swal from "sweetalert2";
import api from "@/api/axios";
import { shippingService } from "@/services/shippingService";
import { toPublicUrl } from "@/services/storageService";
import type {
  SellerOrderDetail,
  SellerShipment,
} from "@/types/orders";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getAxiosErrorMessage(err: unknown, fallback: string): string {
  const responseData = (err as { response?: { data?: unknown } })?.response?.data;
  if (responseData && typeof responseData === "object") {
    const messages = (Object.values(responseData as Record<string, unknown>).flat() as unknown[]).filter(
      (v): v is string => typeof v === "string",
    );
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

// ─── Shipment Phase ───────────────────────────────────────────────────────────

type ShipmentPhase = "needs_label" | "needs_post" | "in_transit";

function getShipmentPhase(s: SellerShipment): ShipmentPhase {
  if (["posted", "in_transit", "out_for_delivery", "delivered"].includes(s.status)) {
    return "in_transit";
  }
  if (s.status === "generated" || s.label_url) {
    return "needs_post";
  }
  return "needs_label";
}

const PHASE_BORDER: Record<ShipmentPhase, string> = {
  needs_label: "border-l-4 border-l-amber-400",
  needs_post: "border-l-4 border-l-blue-500",
  in_transit: "border-l-4 border-l-emerald-500",
};

// ─── Props ────────────────────────────────────────────────────────────────────

interface SaleOrderModalProps {
  orderId: string;
  onClose: () => void;
  onOrderUpdated?: () => void;
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
      {/* Shipping block */}
      <div className="h-20 bg-gray-100 rounded-xl w-full" />
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function SaleOrderModal({ orderId, onClose, onOrderUpdated }: SaleOrderModalProps) {
  const [order, setOrder] = useState<SellerOrderDetail | null>(null);
  const [shipments, setShipments] = useState<SellerShipment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generatingTickets, setGeneratingTickets] = useState(false);
  const [labelLoading, setLabelLoading] = useState<Record<number, boolean>>({});
  const [markingShipped, setMarkingShipped] = useState<Record<number, boolean>>({});
  const [trackingInputs, setTrackingInputs] = useState<Record<number, string>>({});
  const [showTrackingInput, setShowTrackingInput] = useState<Record<number, boolean>>({});
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Move focus into modal on open
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
        // Non-critical: shipments might not exist yet
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
        const [orderRes] = await Promise.all([
          api.get<SellerOrderDetail>(`/orders/sales/${orderId}/`, { signal }),
          fetchShipments(signal),
        ]);
        if (signal.aborted) return;
        setOrder(orderRes.data);
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

  // ─── Actions ────────────────────────────────────────────────────────────────

  async function handleGenerateTickets() {
    setGeneratingTickets(true);
    try {
      const result = await shippingService.createShipments({ order_id: orderId });
      await fetchShipments();
      if (result.created_count > 0) {
        Swal.fire({
          ...SWAL_TOAST_CONFIG,
          icon: "success",
          title: "Tickets de envio gerados com sucesso!",
        });
      }
      onOrderUpdated?.();
    } catch (err: unknown) {
      Swal.fire({
        ...SWAL_TOAST_CONFIG,
        icon: "error",
        title: getAxiosErrorMessage(err, "Erro ao gerar tickets de envio."),
      });
    } finally {
      setGeneratingTickets(false);
    }
  }

  async function handleGenerateLabel(shipmentId: number) {
    setLabelLoading((prev) => ({ ...prev, [shipmentId]: true }));
    try {
      const result = await shippingService.generateLabel(shipmentId);
      if (result.label_url) {
        window.open(result.label_url, "_blank", "noopener,noreferrer");
      }
      await fetchShipments();
      Swal.fire({
        ...SWAL_TOAST_CONFIG,
        icon: "success",
        title: "Etiqueta gerada com sucesso!",
      });
    } catch (err: unknown) {
      Swal.fire({
        ...SWAL_TOAST_CONFIG,
        icon: "error",
        title: getAxiosErrorMessage(err, "Erro ao gerar etiqueta."),
      });
    } finally {
      setLabelLoading((prev) => ({ ...prev, [shipmentId]: false }));
    }
  }

  async function handleMarkAsShipped(shipmentId: number) {
    const trackingCode = trackingInputs[shipmentId]?.trim() ?? "";
    if (!trackingCode) {
      Swal.fire({
        ...SWAL_TOAST_CONFIG,
        icon: "warning",
        title: "Informe o código de rastreamento.",
      });
      return;
    }
    setMarkingShipped((prev) => ({ ...prev, [shipmentId]: true }));
    try {
      await shippingService.markAsShipped(shipmentId, trackingCode);
      await fetchShipments();
      setShowTrackingInput((prev) => ({ ...prev, [shipmentId]: false }));
      setTrackingInputs((prev) => ({ ...prev, [shipmentId]: "" }));
      Swal.fire({
        ...SWAL_TOAST_CONFIG,
        icon: "success",
        title: "Envio confirmado com sucesso!",
      });
    } catch (err: unknown) {
      Swal.fire({
        ...SWAL_TOAST_CONFIG,
        icon: "error",
        title: getAxiosErrorMessage(err, "Erro ao marcar como postado."),
      });
    } finally {
      setMarkingShipped((prev) => ({ ...prev, [shipmentId]: false }));
    }
  }

  // ─── Render ─────────────────────────────────────────────────────────────────

  const canGenerateTickets =
    order && (order.status === "paid" || order.status === "processing");

  const content = (
    <div
      className="fixed inset-0 z-50 flex"
      aria-modal="true"
      role="dialog"
      aria-labelledby="sale-order-modal-title"
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
          <h2 id="sale-order-modal-title" className="text-base font-bold text-gray-900">
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
                  {/* Buyer */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500 flex items-center gap-1.5">
                      <User size={13} className="text-gray-400" />
                      Comprador
                    </span>
                    <span className="text-sm font-medium text-gray-800">
                      {order.buyer.full_name}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">Status</span>
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${ORDER_STATUS_COLORS[order.status] ?? "bg-gray-100 text-gray-700"}`}
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
                    <span className="text-sm text-gray-500">Método de pagamento</span>
                    <span className="text-sm font-medium text-gray-800">
                      {PAYMENT_METHOD_LABELS[order.payment_method] ?? order.payment_method}
                    </span>
                  </div>
                  {order.buyer_notes && (
                    <div className="pt-2 border-t border-gray-200">
                      <p className="text-xs text-gray-500 mb-1">Notas do comprador</p>
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
                    const imgSrc =
                      item.listing.primary_image
                        ? toPublicUrl(item.listing.primary_image)
                        : item.listing.images?.[0]?.image_url
                          ? toPublicUrl(item.listing.images[0].image_url)
                          : null;

                    return (
                      <div
                        key={item.id}
                        className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl"
                      >
                        <div className="w-14 h-14 rounded-xl overflow-hidden bg-gray-200 shrink-0 flex items-center justify-center border border-gray-100">
                          {imgSrc ? (
                            <img
                              src={imgSrc}
                              alt={item.listing.title}
                              className="w-full h-full object-cover"
                              loading="lazy"
                            />
                          ) : (
                            <Package size={20} className="text-gray-300" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-gray-800 truncate">
                            {item.listing.title}
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
                    <span className="text-sm font-semibold text-gray-600">Total</span>
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
              {order.shipping_address && (
                <section>
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
                    Endereço de Entrega
                  </h3>
                  <div className="bg-gray-50 rounded-xl p-4 flex gap-3">
                    <MapPin size={16} className="text-gray-400 shrink-0 mt-0.5" />
                    <div className="text-sm text-gray-700 space-y-0.5">
                      {order.shipping_address.recipient_name && (
                        <p className="font-semibold text-gray-800">
                          {order.shipping_address.recipient_name}
                        </p>
                      )}
                      <p>
                        {order.shipping_address.street}, {order.shipping_address.number}
                        {order.shipping_address.complement
                          ? ` — ${order.shipping_address.complement}`
                          : ""}
                      </p>
                      <p>
                        {order.shipping_address.neighborhood} — {order.shipping_address.city}/
                        {order.shipping_address.state}
                      </p>
                      <p>CEP: {order.shipping_address.zipcode}</p>
                      {order.shipping_address.recipient_phone && (
                        <p className="text-gray-500">
                          Tel: {order.shipping_address.recipient_phone}
                        </p>
                      )}
                    </div>
                  </div>
                </section>
              )}

              {/* Section: Shipping */}
              <section>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
                  Envio
                </h3>

                {/* No shipments + can generate */}
                {shipments.length === 0 && canGenerateTickets && (
                  <div className="space-y-3">
                    <button
                      onClick={handleGenerateTickets}
                      disabled={generatingTickets}
                      className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 transition-colors disabled:opacity-60"
                    >
                      {generatingTickets ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Truck size={16} />
                      )}
                      {generatingTickets ? "Gerando tickets…" : "Gerar Tickets de Envio"}
                    </button>
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800">
                      Itens com entrega presencial serão exibidos após a geração.
                    </div>
                  </div>
                )}

                {/* Shipments list */}
                {shipments.length > 0 && (
                  <div className="space-y-4">
                    {shipments.map((shipment) => {
                      const phase = getShipmentPhase(shipment);
                      const isLabelLoading = labelLoading[shipment.id] ?? false;
                      const isMarkingShipped = markingShipped[shipment.id] ?? false;
                      const showInput = showTrackingInput[shipment.id] ?? false;
                      const trackingValue = trackingInputs[shipment.id] ?? "";

                      return (
                        <div
                          key={shipment.id}
                          className={`border border-gray-100 rounded-xl overflow-hidden ${PHASE_BORDER[phase]}`}
                        >
                          {/* Shipment header */}
                          <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-100">
                            <div>
                              <p className="text-sm font-semibold text-gray-800">
                                {shipment.carrier_name} — {shipment.service_name}
                              </p>
                              <p className="text-xs text-gray-500 mt-0.5">
                                Frete: R${" "}
                                {Number(shipment.shipping_cost).toLocaleString("pt-BR", {
                                  minimumFractionDigits: 2,
                                })}
                              </p>
                            </div>
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${SHIPMENT_STATUS_COLORS[shipment.status] ?? "bg-gray-100 text-gray-700"}`}
                            >
                              {SHIPMENT_STATUS_LABELS[shipment.status] ?? shipment.status}
                            </span>
                          </div>

                          {/* Shipment body */}
                          <div className="p-4 space-y-3">
                            {/* Phase: needs_label */}
                            {phase === "needs_label" && (
                              <button
                                onClick={() => handleGenerateLabel(shipment.id)}
                                disabled={isLabelLoading}
                                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 transition-colors disabled:opacity-60"
                              >
                                {isLabelLoading ? (
                                  <Loader2 size={15} className="animate-spin" />
                                ) : (
                                  <ExternalLink size={15} />
                                )}
                                {isLabelLoading ? "Gerando etiqueta…" : "Gerar Etiqueta"}
                              </button>
                            )}

                            {/* Phase: needs_post */}
                            {phase === "needs_post" && (
                              <div className="space-y-3">
                                {shipment.label_url && (
                                  <a
                                    href={shipment.label_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 border border-blue-900 text-blue-900 rounded-xl text-sm font-semibold hover:bg-blue-50 transition-colors"
                                  >
                                    <ExternalLink size={15} />
                                    Abrir Etiqueta
                                  </a>
                                )}

                                {showInput ? (
                                  <div className="space-y-2">
                                    <input
                                      type="text"
                                      value={trackingValue}
                                      onChange={(e) =>
                                        setTrackingInputs((prev) => ({
                                          ...prev,
                                          [shipment.id]: e.target.value,
                                        }))
                                      }
                                      placeholder="Código de rastreamento"
                                      className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/30 focus:border-blue-900"
                                    />
                                    <div className="flex gap-2">
                                      <button
                                        onClick={() => handleMarkAsShipped(shipment.id)}
                                        disabled={isMarkingShipped}
                                        className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 transition-colors disabled:opacity-60"
                                      >
                                        {isMarkingShipped ? (
                                          <Loader2 size={15} className="animate-spin" />
                                        ) : null}
                                        {isMarkingShipped ? "Confirmando…" : "Confirmar Envio"}
                                      </button>
                                      <button
                                        onClick={() =>
                                          setShowTrackingInput((prev) => ({
                                            ...prev,
                                            [shipment.id]: false,
                                          }))
                                        }
                                        className="px-4 py-2.5 border border-gray-200 text-gray-600 rounded-xl text-sm font-semibold hover:bg-gray-50 transition-colors"
                                      >
                                        Cancelar
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <button
                                    onClick={() =>
                                      setShowTrackingInput((prev) => ({
                                        ...prev,
                                        [shipment.id]: true,
                                      }))
                                    }
                                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 transition-colors"
                                  >
                                    <Send size={15} />
                                    Marcar como Postado
                                  </button>
                                )}
                              </div>
                            )}

                            {/* Phase: in_transit */}
                            {phase === "in_transit" && (
                              <div className="space-y-2">
                                {shipment.tracking_code && (
                                  <div className="flex items-center justify-between text-sm">
                                    <span className="text-gray-500">Rastreamento</span>
                                    <span className="font-mono font-semibold text-gray-800">
                                      {shipment.tracking_code}
                                    </span>
                                  </div>
                                )}
                                {shipment.estimated_delivery_date && (
                                  <div className="flex items-center justify-between text-sm">
                                    <span className="text-gray-500">Previsão de entrega</span>
                                    <span className="font-medium text-gray-800">
                                      {new Date(shipment.estimated_delivery_date).toLocaleDateString(
                                        "pt-BR",
                                      )}
                                    </span>
                                  </div>
                                )}
                                {shipment.tracking_url && (
                                  <button
                                    onClick={() =>
                                      window.open(shipment.tracking_url, "_blank", "noopener,noreferrer")
                                    }
                                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 border border-blue-900 text-blue-900 rounded-xl text-sm font-semibold hover:bg-blue-50 transition-colors mt-2"
                                  >
                                    <ExternalLink size={15} />
                                    Ver Rastreamento
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* No shipments + cannot generate */}
                {shipments.length === 0 && !canGenerateTickets && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
                    {order.status === "shipped" || order.status === "delivered"
                      ? "Envio processado externamente."
                      : "Aguardando pagamento para processar envio."}
                  </div>
                )}
              </section>

            </div>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(content, document.body);
}
