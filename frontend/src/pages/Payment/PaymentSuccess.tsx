import { useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { CheckCircle2, ShoppingBag, Package } from "lucide-react";
import { useCart } from "@/contexts/CartContext";

interface SuccessState {
  orderId?: number;
}

export function PaymentSuccess() {
  const navigate = useNavigate();
  const location = useLocation();
  const { clearCart } = useCart();

  const orderId = (location.state as SuccessState | null)?.orderId;

  // Clear cart exactly once when the success page mounts.
  // We intentionally omit clearCart from the dependency array because its identity
  // changes with every cart update (CartContext recreates it on each render), which
  // would cause the cart to be cleared on every re-render of this page.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    clearCart();
  }, []);

  return (
    <div className="min-h-screen bg-bg-0 flex items-center justify-center px-4 py-10">
      <div className="max-w-md w-full bg-bg-1 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] border border-white/10 p-8 text-center">
        {/* Green success icon */}
        <div className="relative mx-auto mb-6 w-fit">
          <div className="w-20 h-20 bg-green-500/10 border border-green-500/30 rounded-2xl flex items-center justify-center">
            <CheckCircle2
              size={42}
              className="text-green-400"
              aria-hidden="true"
            />
          </div>
        </div>

        <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
          Pedido confirmado!
        </h1>
        <p className="text-ink-2 mb-2 leading-relaxed">
          Seu pagamento foi processado com sucesso.
        </p>
        {orderId && (
          <p className="text-xs text-ink-3 mb-8">
            Pedido{" "}
            <span className="font-semibold text-ink-1">#{orderId}</span>
          </p>
        )}
        {!orderId && <div className="mb-8" />}

        {/* What happens next */}
        <div className="bg-bg-2 border border-white/10 rounded-xl px-4 py-3 mb-8 text-left">
          <p className="text-xs font-semibold text-ink-1 mb-2 uppercase tracking-wide">
            O que acontece agora?
          </p>
          <ul className="space-y-1 text-xs text-ink-2">
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0 text-ink-3">
                &#x2022;
              </span>
              Você receberá um e-mail de confirmação em instantes.
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0 text-ink-3">
                &#x2022;
              </span>
              O vendedor será notificado e preparará o envio.
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0 text-ink-3">
                &#x2022;
              </span>
              Você poderá acompanhar o status do pedido a qualquer momento.
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          {orderId && (
            <button
              type="button"
              onClick={() => navigate("/mypurchase")}
              className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-gold text-gold-deep font-semibold rounded-xl hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
            >
              <Package size={16} aria-hidden="true" />
              Ver meus pedidos
            </button>
          )}
          <button
            type="button"
            onClick={() => navigate("/")}
            className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-bg-2 border border-white/10 text-ink-1 font-semibold rounded-xl hover:bg-bg-3 hover:border-white/20 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
          >
            <ShoppingBag size={16} aria-hidden="true" />
            Continuar comprando
          </button>
        </div>
      </div>
    </div>
  );
}