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
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-10">
      <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center">

        {/* Amber icon */}
        <div className="w-20 h-20 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-6">
          <Clock size={42} className="text-amber-500" aria-hidden="true" />
        </div>

        <h1 className="text-2xl font-bold text-gray-900 mb-2">Pagamento em análise</h1>
        <p className="text-gray-500 mb-2 leading-relaxed">
          Seu pagamento está sendo processado pelo banco emissor.
        </p>
        {orderId && (
          <p className="text-xs text-gray-400 mb-8">
            Pedido <span className="font-semibold text-gray-600">#{orderId}</span>
          </p>
        )}
        {!orderId && <div className="mb-8" />}

        {/* Context note */}
        <div className="bg-amber-50 border border-amber-100 rounded-xl px-4 py-3 mb-8 text-left">
          <p className="text-xs font-semibold text-amber-800 mb-2 uppercase tracking-wide">
            O que esperar?
          </p>
          <ul className="space-y-1 text-xs text-amber-700">
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">&#x2022;</span>
              A confirmação pode levar alguns minutos.
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">&#x2022;</span>
              Você receberá um e-mail assim que o pagamento for concluído.
            </li>
            <li className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">&#x2022;</span>
              Nenhuma ação adicional é necessária por enquanto.
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          {orderId && (
            <button
              onClick={() => navigate(`/orders/${orderId}`)}
              className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-blue-900 text-white font-semibold rounded-xl hover:bg-blue-800 active:bg-blue-950 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
            >
              <Package size={16} aria-hidden="true" />
              Acompanhar pedido
            </button>
          )}
          <button
            onClick={() => navigate("/")}
            className="w-full flex items-center justify-center gap-2 px-4 py-3.5 border border-gray-200 text-gray-700 font-semibold rounded-xl hover:bg-gray-50 active:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-300 focus:ring-offset-2"
          >
            <RefreshCw size={16} aria-hidden="true" />
            Ir para a loja
          </button>
        </div>
      </div>
    </div>
  );
}
