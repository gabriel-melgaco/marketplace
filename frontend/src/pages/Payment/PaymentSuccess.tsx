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
  useEffect(() => { clearCart(); }, []);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-10">
      <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center">

        {/* Icon with layered ring for depth */}
        <div className="relative mx-auto mb-6 w-fit">
          <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center">
            <CheckCircle2 size={42} className="text-green-600" aria-hidden="true" />
          </div>
        </div>

        <h1 className="text-2xl font-bold text-gray-900 mb-2">Pedido confirmado!</h1>
        <p className="text-gray-500 mb-2 leading-relaxed">
          Seu pagamento foi processado com sucesso.
        </p>
        {orderId && (
          <p className="text-xs text-gray-400 mb-8">
            Pedido <span className="font-semibold text-gray-600">#{orderId}</span>
          </p>
        )}
        {!orderId && <div className="mb-8" />}

        {/* What happens next */}
        <div className="bg-green-50 border border-green-100 rounded-xl px-4 py-3 mb-8 text-left">
          <p className="text-xs font-semibold text-green-800 mb-2 uppercase tracking-wide">
            O que acontece agora?
          </p>
          <ul className="space-y-1 text-xs text-green-700">
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">&#x2022;</span>
              Você receberá um e-mail de confirmação em instantes.
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">&#x2022;</span>
              O vendedor será notificado e preparará o envio.
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">&#x2022;</span>
              Você poderá acompanhar o status do pedido a qualquer momento.
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          {orderId && (
            <button
              onClick={() => navigate("/mypurchase")}
              className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-blue-900 text-white font-semibold rounded-xl hover:bg-blue-800 active:bg-blue-950 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
            >
              <Package size={16} aria-hidden="true" />
              Ver meus pedidos
            </button>
          )}
          <button
            onClick={() => navigate("/")}
            className="w-full flex items-center justify-center gap-2 px-4 py-3.5 border border-gray-200 text-gray-700 font-semibold rounded-xl hover:bg-gray-50 active:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-300 focus:ring-offset-2"
          >
            <ShoppingBag size={16} aria-hidden="true" />
            Continuar comprando
          </button>
        </div>
      </div>
    </div>
  );
}
