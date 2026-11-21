import { useNavigate } from "react-router-dom";
import { XCircle, ShoppingBag, RotateCcw, AlertCircle } from "lucide-react";

export function PaymentFailed() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-bg-0 flex items-center justify-center px-4 py-10">
      <div className="max-w-md w-full bg-bg-1 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] border border-white/10 p-8 text-center">
        {/* Red icon */}
        <div className="w-20 h-20 bg-red-500/10 border border-red-500/30 rounded-2xl flex items-center justify-center mx-auto mb-6">
          <XCircle size={42} className="text-red-400" aria-hidden="true" />
        </div>

        <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
          Pagamento recusado
        </h1>
        <p className="text-ink-2 mb-8 leading-relaxed">
          Não conseguimos processar o pagamento desta vez. Isso pode acontecer
          por saldo insuficiente, dados incorretos ou uma recusa temporária do
          banco.
        </p>

        {/* Possible reasons */}
        <div className="bg-bg-2 border border-white/10 rounded-xl px-4 py-3 mb-8 text-left">
          <div className="flex items-center gap-1.5 mb-2">
            <AlertCircle
              size={13}
              className="text-red-400 shrink-0"
              aria-hidden="true"
            />
            <p className="text-xs font-semibold text-ink-1 uppercase tracking-wide">
              Possíveis causas
            </p>
          </div>
          <ul className="space-y-1 text-xs text-ink-2">
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0 text-ink-3">
                &#x2022;
              </span>
              Dados do cartão incorretos (número, validade ou CVV).
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0 text-ink-3">
                &#x2022;
              </span>
              Limite insuficiente ou cartão bloqueado.
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0 text-ink-3">
                &#x2022;
              </span>
              Recusa temporária do banco emissor.
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          <button
            type="button"
            onClick={() => navigate("/checkout")}
            className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-gold text-gold-deep font-semibold rounded-xl hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
          >
            <RotateCcw size={16} aria-hidden="true" />
            Tentar novamente
          </button>
          <button
            type="button"
            onClick={() => navigate("/")}
            className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-bg-2 border border-white/10 text-ink-1 font-semibold rounded-xl hover:bg-bg-3 hover:border-white/20 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
          >
            <ShoppingBag size={16} aria-hidden="true" />
            Voltar às compras
          </button>
        </div>
      </div>
    </div>
  );
}