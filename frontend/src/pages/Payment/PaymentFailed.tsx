import { useNavigate } from "react-router-dom";
import { XCircle, ShoppingBag, RotateCcw, AlertCircle } from "lucide-react";

export function PaymentFailed() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-10">
      <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center">

        {/* Red icon */}
        <div className="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-6">
          <XCircle size={42} className="text-red-500" aria-hidden="true" />
        </div>

        <h1 className="text-2xl font-bold text-gray-900 mb-2">Pagamento recusado</h1>
        <p className="text-gray-500 mb-8 leading-relaxed">
          Não conseguimos processar o pagamento desta vez. Isso pode acontecer por saldo
          insuficiente, dados incorretos ou uma recusa temporária do banco.
        </p>

        {/* Possible reasons */}
        <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 mb-8 text-left">
          <div className="flex items-center gap-1.5 mb-2">
            <AlertCircle size={13} className="text-red-600 shrink-0" aria-hidden="true" />
            <p className="text-xs font-semibold text-red-800 uppercase tracking-wide">
              Possíveis causas
            </p>
          </div>
          <ul className="space-y-1 text-xs text-red-700">
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">&#x2022;</span>
              Dados do cartão incorretos (número, validade ou CVV).
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">&#x2022;</span>
              Limite insuficiente ou cartão bloqueado.
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">&#x2022;</span>
              Recusa temporária do banco emissor.
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          <button
            onClick={() => navigate("/checkout")}
            className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-blue-900 text-white font-semibold rounded-xl hover:bg-blue-800 active:bg-blue-950 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
          >
            <RotateCcw size={16} aria-hidden="true" />
            Tentar novamente
          </button>
          <button
            onClick={() => navigate("/")}
            className="w-full flex items-center justify-center gap-2 px-4 py-3.5 border border-gray-200 text-gray-700 font-semibold rounded-xl hover:bg-gray-50 active:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-300 focus:ring-offset-2"
          >
            <ShoppingBag size={16} aria-hidden="true" />
            Voltar às compras
          </button>
        </div>
      </div>
    </div>
  );
}
