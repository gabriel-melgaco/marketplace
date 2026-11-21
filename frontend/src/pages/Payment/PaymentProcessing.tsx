import { useNavigate, useLocation } from "react-router-dom";
import { Clock, Package, RefreshCw } from "lucide-react";

interface ProcessingState {
  orderId?: number;
}

export function PaymentProcessing() {
  const navigate = useNavigate();
  const location = useLocation();

  const orderId = (location.state as ProcessingState | null)?.orderId;

  return (
    <div className="min-h-screen bg-bg-0 flex items-center justify-center px-4 py-10">
      <div className="max-w-md w-full bg-bg-1 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] border border-white/10 p-8 text-center">
        {/* Gold icon (in-progress state) */}
        <div className="w-20 h-20 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-6">
          <Clock size={42} className="text-gold" aria-hidden="true" />
        </div>

        <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
          Pagamento em análise
        </h1>
        <p className="text-ink-2 mb-2 leading-relaxed">
          Seu pagamento está sendo processado pelo banco emissor.
        </p>
        {orderId && (
          <p className="text-xs text-ink-3 mb-8">
            Pedido{" "}
            <span className="font-semibold text-ink-1">#{orderId}</span>
          </p>
        )}
        {!orderId && <div className="mb-8" />}

        {/* Context note */}
        <div className="bg-bg-2 border border-white/10 rounded-xl px-4 py-3 mb-8 text-left">
          <p className="text-xs font-semibold text-ink-1 mb-2 uppercase tracking-wide">
            O que esperar?
          </p>
          <ul className="space-y-1 text-xs text-ink-2">
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0 text-ink-3">
                &#x2022;
              </span>
              A confirmação pode levar alguns minutos.
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0 text-ink-3">
                &#x2022;
              </span>
              Você receberá um e-mail assim que o pagamento for concluído.
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0 text-ink-3">
                &#x2022;
              </span>
              Nenhuma ação adicional é necessária por enquanto.
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
            <RefreshCw size={16} aria-hidden="true" />
            Ir para a loja
          </button>
        </div>
      </div>
    </div>
  );
}