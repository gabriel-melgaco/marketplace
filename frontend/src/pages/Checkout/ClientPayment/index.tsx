import { useState, useEffect, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  CreditCard,
  Smartphone,
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ShoppingBag,
  ChevronRight,
} from "lucide-react";
import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from "@stripe/react-stripe-js";
import { useCart } from "@/contexts/CartContext";
import { orderService } from "@/services/orderService";
import type { ItemDelivery } from "@/services/orderService";
import { paymentService } from "@/services/paymentService";
import type { PaymentMethodType } from "@/services/paymentService";
import type { CheckoutNavigationState } from "@/pages/Checkout/ClientCheckout";
import { formatCurrency } from "@/utils/formatters";

// ─── Stripe setup ─────────────────────────────────────────────────────────────

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLIC_KEY as string);

// ─── Types ────────────────────────────────────────────────────────────────────

type PayStep = "select" | "form" | "polling" | "success" | "error";

interface PaymentInfo {
  orderId: string;
  paymentIntentId: string;
  clientSecret: string;
  amount: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getAxiosErrorMessage(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (data && typeof data === "object") {
    const msgs = (Object.values(data).flat() as unknown[]).filter(
      (v): v is string => typeof v === "string"
    );
    if (msgs.length) return msgs.join(" ");
    const errField = (data as Record<string, unknown>).error;
    if (typeof errField === "string") return errField;
  }
  return fallback;
}

function buildItemsDelivery(
  quotesSnapshot: CheckoutNavigationState["quotesSnapshot"],
  sellerDeliveryMethods: CheckoutNavigationState["sellerDeliveryMethods"],
  selectedServices: Record<string, number>
): ItemDelivery[] {
  const items: ItemDelivery[] = [];

  for (const [sellerId, snapshot] of Object.entries(quotesSnapshot)) {
    const method = sellerDeliveryMethods[sellerId] ?? "melhor_envio";

    if (method === "vendor") {
      // All items from this seller go as in_person
      for (const item of [
        ...snapshot.in_person_items,
        ...snapshot.melhor_envio_items,
      ]) {
        items.push({ listing_id: item.listing_id, delivery_method: "in_person" });
      }
    } else if (method === "melhor_envio") {
      const serviceId = selectedServices[sellerId];
      for (const item of snapshot.melhor_envio_items) {
        items.push({
          listing_id: item.listing_id,
          delivery_method: "melhor_envio",
          ...(serviceId != null ? { service_id: serviceId } : {}),
        });
      }
      // in_person items for a ME seller (in_person_only=false but has both)
      for (const item of snapshot.in_person_items) {
        items.push({ listing_id: item.listing_id, delivery_method: "in_person" });
      }
    } else {
      // both: ME items with service, in_person items without
      const serviceId = selectedServices[sellerId];
      for (const item of snapshot.melhor_envio_items) {
        items.push({
          listing_id: item.listing_id,
          delivery_method: "melhor_envio",
          ...(serviceId != null ? { service_id: serviceId } : {}),
        });
      }
      for (const item of snapshot.in_person_items) {
        items.push({ listing_id: item.listing_id, delivery_method: "in_person" });
      }
    }
  }

  return items;
}

async function pollPaymentStatus(
  paymentIntentId: string
): Promise<{ succeeded: boolean; failureMessage?: string }> {
  const MAX_ATTEMPTS = 14;
  const INTERVAL_MS = 2500;

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    const payment = await paymentService.getPaymentStatus(paymentIntentId);
    if (payment.status === "succeeded") return { succeeded: true };
    if (payment.status === "failed") {
      return { succeeded: false, failureMessage: payment.failure_message || "Pagamento recusado." };
    }
    if (attempt < MAX_ATTEMPTS - 1) {
      await new Promise((r) => setTimeout(r, INTERVAL_MS));
    }
  }

  throw new Error("Tempo esgotado aguardando confirmação do pagamento.");
}

// ─── Payment method config ────────────────────────────────────────────────────

const PAYMENT_METHODS: {
  id: PaymentMethodType;
  label: string;
  icon: React.ElementType;
  description: string;
}[] = [
  {
    id: "credit_card",
    label: "Cartão de Crédito",
    icon: CreditCard,
    description: "Pague parcelado ou à vista",
  },
  {
    id: "debit_card",
    label: "Cartão de Débito",
    icon: CreditCard,
    description: "Débito direto na conta",
  },
  {
    id: "pix",
    label: "Pix",
    icon: Smartphone,
    description: "Pagamento instantâneo",
  },
  {
    id: "boleto",
    label: "Boleto",
    icon: FileText,
    description: "Vencimento em 3 dias úteis",
  },
];

// ─── Stripe card form ─────────────────────────────────────────────────────────

function StripePaymentForm({
  onSuccess,
  onError,
  amount,
}: {
  onSuccess: () => void;
  onError: (msg: string) => void;
  amount: number;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!stripe || !elements) return;

    setSubmitting(true);
    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: `${window.location.origin}/payment/return`,
      },
      redirect: "if_required",
    });

    if (error) {
      onError(error.message ?? "Erro ao processar pagamento.");
      setSubmitting(false);
      return;
    }

    onSuccess();
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <PaymentElement />
      <button
        type="submit"
        disabled={submitting || !stripe}
        className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-blue-900 text-white text-sm font-semibold rounded-xl hover:bg-blue-800 active:bg-blue-950 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {submitting ? (
          <>
            <Loader2 size={16} className="animate-spin" />
            Processando...
          </>
        ) : (
          <>
            <CreditCard size={16} />
            Pagar {formatCurrency(amount)}
          </>
        )}
      </button>
    </form>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function Payment() {
  const location = useLocation();
  const navigate = useNavigate();
  const { clearCart } = useCart();

  const state = location.state as CheckoutNavigationState | null;

  const [step, setStep] = useState<PayStep>("select");
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethodType>("credit_card");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [paymentInfo, setPaymentInfo] = useState<PaymentInfo | null>(null);
  const [orderNumber, setOrderNumber] = useState("");

  // Redirect back if no state
  useEffect(() => {
    if (!state?.quotesSnapshot || !state?.shippingAddressId) {
      navigate("/checkout", { replace: true });
    }
  }, [state, navigate]);

  const handleCreateOrderAndIntent = useCallback(async () => {
    if (!state) return;
    setCreating(true);
    setError("");

    try {
      const itemsDelivery = buildItemsDelivery(
        state.quotesSnapshot,
        state.sellerDeliveryMethods,
        state.selectedServices
      );

      const order = await orderService.createOrder({
        shipping_address_id: state.shippingAddressId,
        items_delivery: itemsDelivery,
        payment_method: selectedMethod,
      });

      const intent = await paymentService.createPaymentIntent({
        order_id: order.id,
        payment_method: selectedMethod,
      });

      setOrderNumber(order.order_number);
      setPaymentInfo({
        orderId: order.id,
        paymentIntentId: intent.client_secret.split("_secret_")[0],
        clientSecret: intent.client_secret,
        amount: intent.amount,
      });
      setStep("form");
    } catch (err) {
      setError(getAxiosErrorMessage(err, "Erro ao criar pedido. Tente novamente."));
    } finally {
      setCreating(false);
    }
  }, [state, selectedMethod]);

  const handlePaymentSuccess = useCallback(async () => {
    if (!paymentInfo) return;
    setStep("polling");
    setError("");

    try {
      const result = await pollPaymentStatus(paymentInfo.paymentIntentId);
      if (result.succeeded) {
        clearCart();
        setStep("success");
      } else {
        setError(result.failureMessage ?? "Pagamento recusado.");
        setStep("error");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao confirmar pagamento.");
      setStep("error");
    }
  }, [paymentInfo, clearCart]);

  const handlePaymentError = useCallback((msg: string) => {
    setError(msg);
    setStep("error");
  }, []);

  if (!state) return null;

  // ── Success ──
  if (step === "success") {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="bg-white rounded-2xl shadow-sm p-8 max-w-md w-full text-center">
          <div className="flex justify-center mb-4">
            <div className="p-4 bg-green-50 rounded-full">
              <CheckCircle2 size={48} className="text-green-500" />
            </div>
          </div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Pagamento confirmado!</h1>
          {orderNumber && (
            <p className="text-sm text-gray-500 mb-1">Pedido #{orderNumber}</p>
          )}
          <p className="text-sm text-gray-500 mb-6">
            Seu pedido foi realizado com sucesso. Você receberá uma confirmação por e-mail.
          </p>
          <button
            onClick={() => navigate("/dashboard")}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-900 text-white text-sm font-semibold rounded-xl hover:bg-blue-800 transition-colors"
          >
            <ShoppingBag size={16} />
            Ver meus pedidos
          </button>
        </div>
      </div>
    );
  }

  // ── Error ──
  if (step === "error") {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="bg-white rounded-2xl shadow-sm p-8 max-w-md w-full text-center">
          <div className="flex justify-center mb-4">
            <div className="p-4 bg-red-50 rounded-full">
              <XCircle size={48} className="text-red-500" />
            </div>
          </div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Pagamento não processado</h1>
          <p className="text-sm text-gray-500 mb-6">{error}</p>
          <div className="space-y-3">
            <button
              onClick={() => {
                setStep("select");
                setPaymentInfo(null);
                setError("");
              }}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-900 text-white text-sm font-semibold rounded-xl hover:bg-blue-800 transition-colors"
            >
              Tentar novamente
            </button>
            <button
              onClick={() => navigate("/checkout")}
              className="w-full px-4 py-3 text-sm font-semibold text-gray-600 hover:text-gray-800 transition-colors"
            >
              Voltar ao carrinho
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Polling ──
  if (step === "polling") {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="bg-white rounded-2xl shadow-sm p-8 max-w-md w-full text-center">
          <div className="flex justify-center mb-4">
            <Loader2 size={48} className="animate-spin text-blue-600" />
          </div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Confirmando pagamento...</h1>
          <p className="text-sm text-gray-500">
            Aguarde enquanto confirmamos seu pagamento com segurança.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-6 sm:py-8">

        {/* Header */}
        <div className="mb-6">
          <h1 className="text-xl font-bold text-gray-900">Pagamento</h1>
          <p className="text-sm text-gray-500 mt-1">Escolha a forma de pagamento</p>
        </div>

        {/* Error banner */}
        {error && step === "select" && (
          <div className="mb-4 flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
            <AlertCircle size={16} className="shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {step === "select" && (
          <div className="space-y-4">
            {/* Method selector */}
            <div className="bg-white rounded-xl shadow-sm p-5">
              <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">
                Forma de pagamento
              </h2>
              <div className="space-y-2">
                {PAYMENT_METHODS.map(({ id, label, icon: Icon, description }) => (
                  <button
                    key={id}
                    onClick={() => setSelectedMethod(id)}
                    className={`w-full flex items-center gap-4 p-4 rounded-xl border-2 transition-all text-left ${
                      selectedMethod === id
                        ? "border-blue-600 bg-blue-50"
                        : "border-gray-100 bg-gray-50 hover:border-gray-200 hover:bg-white"
                    }`}
                  >
                    <div
                      className={`p-2 rounded-lg ${
                        selectedMethod === id ? "bg-blue-600" : "bg-gray-200"
                      }`}
                    >
                      <Icon
                        size={18}
                        className={selectedMethod === id ? "text-white" : "text-gray-500"}
                      />
                    </div>
                    <div className="flex-1">
                      <p
                        className={`text-sm font-semibold ${
                          selectedMethod === id ? "text-blue-900" : "text-gray-700"
                        }`}
                      >
                        {label}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">{description}</p>
                    </div>
                    <div
                      className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                        selectedMethod === id
                          ? "border-blue-600 bg-blue-600"
                          : "border-gray-300"
                      }`}
                    >
                      {selectedMethod === id && (
                        <div className="w-2 h-2 rounded-full bg-white" />
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* CTA */}
            <button
              onClick={handleCreateOrderAndIntent}
              disabled={creating}
              className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-blue-900 text-white text-sm font-semibold rounded-xl hover:bg-blue-800 active:bg-blue-950 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {creating ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Criando pedido...
                </>
              ) : (
                <>
                  Continuar para pagamento
                  <ChevronRight size={16} />
                </>
              )}
            </button>
          </div>
        )}

        {step === "form" && paymentInfo && (
          <div className="bg-white rounded-xl shadow-sm p-5">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">
              Dados do pagamento
            </h2>
            {orderNumber && (
              <p className="text-sm text-gray-500 mb-4">Pedido #{orderNumber}</p>
            )}
            <Elements
              stripe={stripePromise}
              options={{
                clientSecret: paymentInfo.clientSecret,
                appearance: { theme: "stripe" },
                locale: "pt-BR",
              }}
            >
              <StripePaymentForm
                onSuccess={handlePaymentSuccess}
                onError={handlePaymentError}
                amount={paymentInfo.amount}
              />
            </Elements>
          </div>
        )}
      </div>
    </div>
  );
}
