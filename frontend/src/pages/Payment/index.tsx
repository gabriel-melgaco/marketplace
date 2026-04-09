import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from "@stripe/react-stripe-js";
import {
  CreditCard,
  CheckCircle2,
  Loader2,
  AlertCircle,
  ArrowLeft,
  Lock,
  ShieldCheck,
} from "lucide-react";
import { paymentService } from "@/services/paymentService";
import api from "@/api/axios";
import axios from "axios";
import Swal from "sweetalert2";

// ─── Stripe init (module-level — never recreated) ────────────────────────────

const STRIPE_PUBLIC_KEY = import.meta.env.VITE_STRIPE_PUBLIC_KEY as string | undefined;
if (!STRIPE_PUBLIC_KEY) {
  throw new Error("VITE_STRIPE_PUBLIC_KEY is not defined. Check your .env file.");
}
const stripePromise = loadStripe(STRIPE_PUBLIC_KEY);

// ─── Types ────────────────────────────────────────────────────────────────────

type PaymentMethodType = "credit_card" | "debit_card";

interface QuoteSnapshot {
  melhor_envio_items: { listing_id: number }[];
  in_person_items: { listing_id: number }[];
  in_person_only: boolean;
}

export interface CheckoutNavigationState {
  shippingAddressId: number;
  selectedServices: Record<string, number>;
  inPersonSellers: string[];
  sellerDeliveryMethods: Record<string, "melhor_envio" | "vendor" | "both">;
  quotesSnapshot: Record<string, QuoteSnapshot>;
}

interface ItemDelivery {
  listing_id: number;
  delivery_method: "melhor_envio" | "in_person";
  service_id?: number;
}

interface OrderCreatePayload {
  shipping_address_id: number;
  payment_method: PaymentMethodType;
  items_delivery: ItemDelivery[];
}

// Backend returns Order[] (array), even for single-seller carts.
// For multi-seller carts the array will contain one entry per seller.
interface OrderCreateResponse {
  id: number;
}

type OrderCreateApiResponse = OrderCreateResponse | OrderCreateResponse[];

interface PaymentIntentResponseData {
  payment_id: number;
  client_secret: string;
  amount: number;
  currency: string;
  payment_method: string;
  reused?: boolean;
}

interface PaymentIntentState {
  clientSecret: string;
  stripePaymentIntentId: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getAxiosErrorMessage(err: unknown, fallback: string): string {
  const responseData = (err as { response?: { data?: unknown } })?.response?.data;
  if (responseData && typeof responseData === "object") {
    const messages = (Object.values(responseData).flat() as unknown[]).filter(
      (v): v is string => typeof v === "string",
    );
    return messages.join(" ") || fallback;
  }
  if (typeof responseData === "string" && responseData) return responseData;
  if (err instanceof Error) return err.message;
  return fallback;
}

// ─── Poll payment status ──────────────────────────────────────────────────────

async function pollPaymentStatus(
  paymentIntentId: string,
  signal: AbortSignal,
): Promise<'succeeded' | 'failed' | 'cancelled' | 'timeout'> {
  const MAX_ATTEMPTS = 12;
  const INTERVAL_MS = 2500;

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    if (signal.aborted) return 'timeout';

    try {
      const response = await api.get<{ status: string }>(
        `/payments/status/${paymentIntentId}/`,
        { signal },
      );

      if (response.data.status === 'succeeded') return 'succeeded';
      if (response.data.status === 'failed' || response.data.status === 'cancelled') {
        return response.data.status as 'failed' | 'cancelled';
      }
    } catch (err: unknown) {
      if (axios.isCancel(err)) return 'timeout';
      console.error('[polling] erro:', getAxiosErrorMessage(err, 'Erro desconhecido'));
    }

    if (attempt < MAX_ATTEMPTS - 1) {
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, INTERVAL_MS);
        signal.addEventListener('abort', () => {
          clearTimeout(timer);
          resolve();
        });
      });
    }
  }

  return 'timeout';
}

// ─── Shared: Step header (matches checkout page visual language) ──────────────

function StepHeader({
  step,
  icon,
  title,
  complete,
}: {
  step: number;
  icon: React.ReactNode;
  title: string;
  complete?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <div
        className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold shrink-0 transition-colors ${
          complete ? "bg-green-100 text-green-700" : "bg-blue-900 text-white"
        }`}
        aria-hidden="true"
      >
        {complete ? <CheckCircle2 size={15} /> : step}
      </div>
      <h2 className="text-base font-semibold text-gray-900 flex items-center gap-2">
        {icon}
        {title}
      </h2>
    </div>
  );
}

// ─── Stripe Card Form (inner component — must be inside <Elements>) ───────────

interface StripeCardFormProps {
  clientSecret: string;
  stripePaymentIntentId: string;
  orderId: number;
}

function StripeCardForm({ clientSecret: _clientSecret, stripePaymentIntentId, orderId }: StripeCardFormProps) {
  const stripe = useStripe();
  const elements = useElements();
  const navigate = useNavigate();

  const [confirming, setConfirming] = useState(false);
  const [stripeError, setStripeError] = useState("");
  const [polling, setPolling] = useState(false);

  const confirmingRef = useRef(false);
  const pollingAbortRef = useRef<AbortController | null>(null);

  // Abort polling on unmount
  useEffect(() => {
    return () => {
      pollingAbortRef.current?.abort();
    };
  }, []);

  const handleConfirmPayment = useCallback(async () => {
    if (!stripe || !elements || confirmingRef.current) return;

    confirmingRef.current = true;
    setConfirming(true);
    setStripeError("");

    const { error } = await stripe.confirmPayment({
      elements,
      redirect: 'if_required',
    });

    if (error) {
      setStripeError(error.message ?? "Erro ao processar pagamento.");
      confirmingRef.current = false;
      setConfirming(false);
      return;
    }

    // Start polling — release guard early so double-click window is minimal (Issue 1.4)
    pollingAbortRef.current?.abort();
    const controller = new AbortController();
    pollingAbortRef.current = controller;

    setPolling(true);
    confirmingRef.current = false;
    setConfirming(false);

    const result = await pollPaymentStatus(stripePaymentIntentId, controller.signal);

    if (result === 'succeeded') {
      // Fire-and-forget shipment creation (Issue 1.3)
      api.post('/logistics/shipments/create/', { order_id: orderId })
        .catch((err: unknown) =>
          console.error('shipments/create error:', getAxiosErrorMessage(err, 'Erro desconhecido')),
        );
      navigate('/payment/success', { state: { orderId } });
    } else if (result === 'failed' || result === 'cancelled') {
      navigate('/payment/failed');
    } else {
      navigate('/payment/processing', { state: { orderId } });
    }
  }, [stripe, elements, stripePaymentIntentId, orderId, navigate]);

  if (polling) {
    return (
      <div
        className="flex flex-col items-center gap-4 py-12"
        role="status"
        aria-live="polite"
        aria-label="Processando pagamento"
      >
        <div className="w-16 h-16 rounded-full bg-blue-50 flex items-center justify-center">
          <Loader2 size={32} className="animate-spin text-blue-800" aria-hidden="true" />
        </div>
        <div className="text-center space-y-1">
          <p className="text-base font-semibold text-gray-800">Processando pagamento...</p>
          <p className="text-sm text-gray-500">Aguarde enquanto confirmamos sua transação.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Dados do pagamento
        </label>
        <PaymentElement />
      </div>

      {stripeError && (
        <div
          role="alert"
          className="flex items-start gap-2.5 text-red-700 text-sm bg-red-50 border border-red-200 rounded-xl p-3.5"
        >
          <AlertCircle size={16} className="shrink-0 mt-0.5" aria-hidden="true" />
          <span>{stripeError}</span>
        </div>
      )}

      <button
        onClick={handleConfirmPayment}
        disabled={confirming || !stripe}
        aria-disabled={confirming || !stripe}
        className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-blue-900 text-white font-semibold rounded-xl hover:bg-blue-800 active:bg-blue-950 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
      >
        {confirming ? (
          <>
            <Loader2 size={18} className="animate-spin" aria-hidden="true" />
            Processando...
          </>
        ) : (
          <>
            <Lock size={18} aria-hidden="true" />
            Confirmar Pagamento
          </>
        )}
      </button>

      <p className="text-center text-xs text-gray-400 flex items-center justify-center gap-1.5 pt-1">
        <ShieldCheck size={12} aria-hidden="true" />
        Seus dados são criptografados e nunca armazenados neste site
      </p>
    </div>
  );
}

// ─── Main Payment Component ───────────────────────────────────────────────────

// Extended location state — may carry an existingOrderId when the user is
// redirected back from the pending-payment recovery flow (BUG 3).
interface PaymentLocationState extends CheckoutNavigationState {
  existingOrderId?: number;
}

export function Payment() {
  const navigate = useNavigate();
  const location = useLocation();

  const checkoutState = location.state as PaymentLocationState | null;

  // Redirect if arrived without checkout state (e.g. direct navigation or refresh)
  useEffect(() => {
    if (!checkoutState) navigate("/checkout", { replace: true });
  }, [checkoutState, navigate]);

  // ── State ──
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethodType>("credit_card");
  const paymentMethodRef = useRef(paymentMethod);

  const [orderId, setOrderId] = useState<number | null>(null);
  const [orderLoading, setOrderLoading] = useState(true);
  const [orderError, setOrderError] = useState("");

  const [paymentIntent, setPaymentIntent] = useState<PaymentIntentState | null>(null);
  const [intentLoading, setIntentLoading] = useState(false);
  const [intentError, setIntentError] = useState("");

  // ── Create order automatically on mount ──
  useEffect(() => {
    if (!checkoutState) return;

    // BUG 3 — if the user was redirected back with an existing pending order,
    // skip creation entirely and use that order id directly.
    if (checkoutState.existingOrderId != null) {
      setOrderId(checkoutState.existingOrderId);
      setOrderLoading(false);
      return;
    }

    const controller = new AbortController();
    const { shippingAddressId, selectedServices, sellerDeliveryMethods, quotesSnapshot } = checkoutState;

    // Build items_delivery from quotesSnapshot (per-listing arrays from shipping calc)
    const itemsDelivery: ItemDelivery[] = [];
    for (const [sellerId, snapshot] of Object.entries(quotesSnapshot)) {
      const method = sellerDeliveryMethods?.[sellerId] ?? "melhor_envio";
      const serviceId = selectedServices[sellerId];

      if (method === "vendor") {
        for (const item of [...snapshot.in_person_items, ...snapshot.melhor_envio_items]) {
          itemsDelivery.push({ listing_id: item.listing_id, delivery_method: "in_person" });
        }
      } else if (method === "melhor_envio") {
        for (const item of snapshot.melhor_envio_items) {
          itemsDelivery.push({
            listing_id: item.listing_id,
            delivery_method: "melhor_envio",
            ...(serviceId != null ? { service_id: serviceId } : {}),
          });
        }
        for (const item of snapshot.in_person_items) {
          itemsDelivery.push({ listing_id: item.listing_id, delivery_method: "in_person" });
        }
      } else {
        // both
        for (const item of snapshot.melhor_envio_items) {
          itemsDelivery.push({
            listing_id: item.listing_id,
            delivery_method: "melhor_envio",
            ...(serviceId != null ? { service_id: serviceId } : {}),
          });
        }
        for (const item of snapshot.in_person_items) {
          itemsDelivery.push({ listing_id: item.listing_id, delivery_method: "in_person" });
        }
      }
    }

    // Guard: if quotesSnapshot is missing, send user back to checkout
    if (itemsDelivery.length === 0) {
      navigate("/checkout", {
        state: { error: "Informações de entrega incompletas. Por favor, recalcule o frete." },
      });
      return;
    }

    async function createOrder() {
      try {
        const payload: OrderCreatePayload = {
          shipping_address_id: shippingAddressId,
          payment_method: paymentMethodRef.current,
          items_delivery: itemsDelivery,
        };

        // BUG 2 — The backend returns Order[] (an array), not a single object.
        // Typing it as the union and normalising to a single entry here.
        const response = await api.post<OrderCreateApiResponse>("/orders/create/", payload, {
          signal: controller.signal,
        });

        // Normalise: accept both array (backend) and plain object (future-proof)
        const firstOrder = Array.isArray(response.data)
          ? response.data[0]
          : response.data;

        if (!firstOrder?.id) {
          throw new Error("Resposta inválida do servidor ao criar pedido.");
        }

        setOrderId(firstOrder.id);
        setOrderLoading(false);
      } catch (err: unknown) {
        // Axios throws a CanceledError when the AbortController signal fires;
        // treat that as a silent cancellation, not a user-visible error.
        if (controller.signal.aborted) return;

        if (axios.isAxiosError(err) && err.response?.status === 422) {
          const data = err.response.data as { error?: string };
          if (data.error === "insufficient_me_balance") {
            await Swal.fire({
              icon: "error",
              title: "Envio indisponível",
              text: "Este vendedor não pode processar o envio no momento. Tente novamente mais tarde ou contate o vendedor diretamente.",
            });
            setOrderLoading(false);
            return;
          }
        }

        if (axios.isAxiosError(err) && err.response?.status === 400) {
          const data = err.response.data as { error?: string; detail?: string };
          const msg = (data?.error ?? data?.detail ?? "").toLowerCase();

          // Expired quote — redirect back to checkout
          if (msg.includes("cotação") || msg.includes("expirada")) {
            navigate("/checkout", {
              state: { error: "Sua cotação de frete expirou. Por favor, recalcule o frete." },
            });
            return;
          }

          // BUG 3 — Existing pending_payment order blocks new order creation
          if (msg.includes("aguardando pagamento") || msg.includes("pending_payment")) {
            const orderMatch = msg.match(/ord-\d{4}-\d+/i);
            const orderNumber = orderMatch ? orderMatch[0].toUpperCase() : null;

            const result = await Swal.fire({
              icon: "warning",
              title: "Pedido pendente",
              html: `Você já possui um pedido aguardando pagamento${orderNumber ? ` (${orderNumber})` : ""}.<br><br>Deseja continuar pagando esse pedido ou cancelá-lo para criar um novo?`,
              showDenyButton: true,
              showCancelButton: true,
              confirmButtonText: "Continuar pagando",
              denyButtonText: "Cancelar pedido antigo",
              cancelButtonText: "Voltar",
            });

            if (result.isConfirmed) {
              // Resume payment on the existing pending order
              const ordersRes = await api.get<{ results?: OrderCreateResponse[] }>("/orders/?status=pending_payment");
              const pendingOrder = ordersRes.data.results?.[0];
              if (pendingOrder) {
                navigate("/payment", {
                  state: { ...checkoutState, existingOrderId: pendingOrder.id },
                });
              }
            } else if (result.isDenied) {
              // Cancel the old order then retry creation
              const ordersRes = await api.get<{ results?: OrderCreateResponse[] }>("/orders/?status=pending_payment");
              const pendingOrder = ordersRes.data.results?.[0];
              if (pendingOrder) {
                await api.post(`/orders/${pendingOrder.id}/cancel/`);
                // Restart the whole page so the useEffect re-runs cleanly
                navigate("/payment", { state: checkoutState });
              }
            }

            setOrderLoading(false);
            return;
          }
        }

        setOrderError(getAxiosErrorMessage(err, "Erro ao criar o pedido."));
        setOrderLoading(false);
      }
    }

    createOrder();
    return () => controller.abort();
  }, []);

  // ── Create payment intent when user confirms method ──
  // intentLoadingRef prevents double-submission without adding intentLoading to deps,
  // which would cause the callback to be recreated on every loading state flip.
  const intentLoadingRef = useRef(false);

  const handleConfirmMethod = useCallback(async () => {
    if (!orderId || intentLoadingRef.current) return;

    intentLoadingRef.current = true;
    setIntentLoading(true);
    setIntentError("");

    try {
      const response = await api.post<PaymentIntentResponseData>("/payments/create-intent/", {
        order_id: orderId,
        payment_method: paymentMethod,
      });

      setPaymentIntent({
        clientSecret: response.data.client_secret,
        stripePaymentIntentId: response.data.client_secret.split("_secret_")[0],
      });
    } catch (err: unknown) {
      setIntentError(getAxiosErrorMessage(err, "Erro ao inicializar pagamento."));
    } finally {
      intentLoadingRef.current = false;
      setIntentLoading(false);
    }
  }, [orderId, paymentMethod]);

  // Guard — null while redirecting
  if (!checkoutState) return null;

  const cardFormReady = paymentIntent !== null && orderId !== null;

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-lg mx-auto px-4 py-8 sm:py-10">

        {/* Back navigation */}
        <button
          onClick={() => navigate("/checkout")}
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 mb-6 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 rounded-md px-1 -ml-1"
          aria-label="Voltar ao checkout"
        >
          <ArrowLeft size={16} aria-hidden="true" />
          Voltar ao checkout
        </button>

        {/* Page heading */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Pagamento</h1>
          <p className="text-sm text-gray-500 mt-1">
            {cardFormReady
              ? "Informe os dados do seu cartão para concluir a compra."
              : "Selecione o método de pagamento e prossiga."}
          </p>
        </div>

        {/* ── Order creation loading banner ── */}
        {orderLoading && (
          <div
            role="status"
            aria-live="polite"
            aria-label="Criando pedido"
            className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 mb-6 flex items-center gap-3"
          >
            <Loader2 size={18} className="animate-spin text-blue-800 shrink-0" aria-hidden="true" />
            <div>
              <p className="text-sm font-medium text-gray-700">Criando seu pedido...</p>
              <p className="text-xs text-gray-400 mt-0.5">Isso levará apenas alguns segundos.</p>
            </div>
          </div>
        )}

        {/* ── Order created confirmation (shown while method selector is visible) ── */}
        {!orderLoading && orderId !== null && !cardFormReady && (
          <div
            role="status"
            aria-live="polite"
            className="bg-green-50 border border-green-200 rounded-xl p-3.5 mb-6 flex items-center gap-3"
          >
            <CheckCircle2 size={18} className="text-green-600 shrink-0" aria-hidden="true" />
            <p className="text-sm text-green-700 font-medium">Pedido criado. Escolha como pagar.</p>
          </div>
        )}

        {/* ── Order error ── */}
        {orderError && (
          <div
            role="alert"
            className="bg-white rounded-xl border border-gray-100 shadow-sm p-6 mb-6"
          >
            <div className="flex items-start gap-2.5 text-red-700 mb-4">
              <AlertCircle size={18} className="shrink-0 mt-0.5" aria-hidden="true" />
              <p className="text-sm font-medium leading-snug">{orderError}</p>
            </div>
            <button
              onClick={() => navigate("/checkout")}
              className="text-sm font-medium text-blue-800 hover:text-blue-900 hover:underline focus:outline-none focus:underline"
            >
              Voltar ao checkout
            </button>
          </div>
        )}

        {/* ── STEP 1: Payment method selector (hidden after card form appears) ── */}
        {!cardFormReady && !orderError && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
            <StepHeader
              step={1}
              complete={false}
              icon={<CreditCard size={18} className="text-blue-800" aria-hidden="true" />}
              title="Método de pagamento"
            />

            {/* Radio cards — consistent with checkout shipping selector */}
            <div
              className="space-y-3 mb-6"
              role="radiogroup"
              aria-label="Selecione o método de pagamento"
            >
              {(
                [
                  {
                    value: "credit_card" as const,
                    label: "Cartão de Crédito",
                    description: "Pague parcelado ou à vista",
                  },
                  {
                    value: "debit_card" as const,
                    label: "Cartão de Débito",
                    description: "Débito direto na conta",
                  },
                ] as const
              ).map((option) => {
                const isSelected = paymentMethod === option.value;
                return (
                  <div
                    key={option.value}
                    role="radio"
                    aria-checked={isSelected}
                    tabIndex={0}
                    onClick={() => setPaymentMethod(option.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setPaymentMethod(option.value);
                      }
                    }}
                    className={`flex items-center gap-3.5 p-4 rounded-xl border-2 cursor-pointer transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 ${
                      isSelected
                        ? "border-blue-800 bg-blue-50"
                        : "border-gray-200 bg-white hover:border-blue-300 hover:bg-gray-50"
                    }`}
                  >
                    {/* Custom radio dot */}
                    <div
                      aria-hidden="true"
                      className={`w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center transition-colors ${
                        isSelected ? "border-blue-800" : "border-gray-300"
                      }`}
                    >
                      {isSelected && <div className="w-2 h-2 rounded-full bg-blue-800" />}
                    </div>

                    {/* Card icon */}
                    <CreditCard
                      size={18}
                      className={`shrink-0 transition-colors ${isSelected ? "text-blue-800" : "text-gray-400"}`}
                      aria-hidden="true"
                    />

                    {/* Labels */}
                    <div className="flex-1 min-w-0">
                      <p
                        className={`text-sm font-semibold leading-tight ${
                          isSelected ? "text-blue-900" : "text-gray-800"
                        }`}
                      >
                        {option.label}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5">{option.description}</p>
                    </div>

                    {/* Selected indicator */}
                    {isSelected && (
                      <CheckCircle2
                        size={16}
                        className="text-blue-800 shrink-0"
                        aria-hidden="true"
                      />
                    )}
                  </div>
                );
              })}
            </div>

            {intentError && (
              <div
                role="alert"
                className="flex items-start gap-2.5 text-red-700 text-sm bg-red-50 border border-red-200 rounded-xl p-3.5 mb-4"
              >
                <AlertCircle size={16} className="shrink-0 mt-0.5" aria-hidden="true" />
                <span>{intentError}</span>
              </div>
            )}

            <button
              onClick={handleConfirmMethod}
              disabled={!orderId || orderLoading || intentLoading}
              aria-disabled={!orderId || orderLoading || intentLoading}
              className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-blue-900 text-white font-semibold rounded-xl hover:bg-blue-800 active:bg-blue-950 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
            >
              {intentLoading ? (
                <>
                  <Loader2 size={18} className="animate-spin" aria-hidden="true" />
                  Aguarde...
                </>
              ) : (
                "Continuar para pagamento"
              )}
            </button>

            {orderLoading && (
              <p className="mt-3 text-xs text-center text-gray-400" aria-live="polite">
                Aguardando a criação do pedido para prosseguir...
              </p>
            )}
          </div>
        )}

        {/* ── STEP 2: Stripe card form (inside Elements) ── */}
        {cardFormReady && paymentIntent && orderId !== null && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <StepHeader
              step={2}
              complete={false}
              icon={<Lock size={18} className="text-blue-800" aria-hidden="true" />}
              title="Dados do cartão"
            />

            {/* Security context row */}
            <div className="flex items-center gap-2 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2.5 mb-5">
              <ShieldCheck size={15} className="text-blue-700 shrink-0" aria-hidden="true" />
              <p className="text-xs text-blue-700 leading-snug">
                Conexão segura — seus dados de cartão são processados diretamente pelo{" "}
                <span className="font-semibold">Stripe</span> e nunca passam pelos nossos servidores.
              </p>
            </div>

            <Elements
              stripe={stripePromise}
              options={{
                clientSecret: paymentIntent.clientSecret,
                appearance: {
                  theme: 'stripe',
                  variables: {
                    colorPrimary: '#1e3a5f',
                  },
                },
              }}
            >
              <StripeCardForm
                clientSecret={paymentIntent.clientSecret}
                stripePaymentIntentId={paymentIntent.stripePaymentIntentId}
                orderId={orderId}
              />
            </Elements>
          </div>
        )}

        {/* ── Trust footer ── */}
        <div className="mt-6 flex items-center justify-center gap-4 text-xs text-gray-400">
          <span className="flex items-center gap-1.5">
            <Lock size={11} aria-hidden="true" />
            Pagamento seguro
          </span>
          <span aria-hidden="true" className="text-gray-300">|</span>
          <span className="flex items-center gap-1.5">
            <ShieldCheck size={11} aria-hidden="true" />
            Processado pelo Stripe
          </span>
        </div>
      </div>
    </div>
  );
}
