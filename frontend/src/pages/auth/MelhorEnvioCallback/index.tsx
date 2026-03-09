import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, XCircle } from "lucide-react";

const CLOSE_DELAY_MS = 2000;

// Map common OAuth error codes to friendlier Portuguese hints.
const ERROR_HINT: Record<string, string> = {
  access_denied: "Você cancelou a autorização no Melhor Envio.",
  server_error: "O servidor do Melhor Envio retornou um erro. Tente mais tarde.",
  temporarily_unavailable:
    "O serviço está temporariamente indisponível. Tente novamente em alguns minutos.",
};

export function MelhorEnvioCallback() {
  // Computed once on mount via lazy initializer — stable across RAF ticks.
  // A window opened via window.open() with a specific name is safer to detect
  // than checking window.opener alone, which can be truthy in other scenarios.
  const [isPopup] = useState(
    () => window.opener != null && window.name === "melhorenvio_oauth",
  );
  const [hasError] = useState(() =>
    new URLSearchParams(window.location.search).has("error"),
  );
  const [errorCode] = useState(
    () => new URLSearchParams(window.location.search).get("error") ?? "",
  );

  const [progress, setProgress] = useState(0); // 0–100

  useEffect(() => {
    if (!isPopup || hasError) return;

    const start = Date.now();
    // Animate the progress bar in small increments, then close.
    const rafId = { current: 0 };
    const tick = () => {
      const elapsed = Date.now() - start;
      const pct = Math.min((elapsed / CLOSE_DELAY_MS) * 100, 100);
      setProgress(pct);
      if (elapsed < CLOSE_DELAY_MS) {
        rafId.current = requestAnimationFrame(tick);
      } else {
        window.close();
      }
    };
    rafId.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId.current);
  }, [isPopup, hasError]);

  const errorMessage =
    ERROR_HINT[errorCode] ?? "Ocorreu um erro durante a autorização. Tente novamente.";

  if (hasError) {
    return (
      <div className="min-h-screen bg-linear-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-auto overflow-hidden">
          <div
            role="alert"
            className="bg-linear-to-r from-red-700 to-red-900 p-8 text-white text-center"
          >
            <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
              <XCircle size={36} className="text-white" aria-hidden="true" />
            </div>
            <h2 className="text-xl font-bold mb-1">Falha na conexão</h2>
            <p className="text-red-100 text-sm">
              Não foi possível conectar o Melhor Envio
            </p>
          </div>
          <div className="p-8 text-center space-y-4">
            <p className="text-gray-600 text-sm">{errorMessage}</p>
            {isPopup ? (
              <button
                onClick={() => window.close()}
                className="w-full py-2.5 bg-gray-800 text-white rounded-xl text-sm font-semibold hover:bg-gray-700 focus-visible:ring-2 focus-visible:ring-gray-500 focus-visible:ring-offset-2 transition cursor-pointer"
              >
                Fechar janela
              </button>
            ) : (
              <Link
                to="/"
                className="block w-full py-2.5 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 focus-visible:ring-2 focus-visible:ring-blue-700 focus-visible:ring-offset-2 transition text-center"
              >
                Voltar ao início
              </Link>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-auto overflow-hidden">
        <div
          role="status"
          className="bg-linear-to-r from-blue-900 to-gray-900 p-8 text-white text-center"
        >
          <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
            <CheckCircle2 size={36} className="text-white" aria-hidden="true" />
          </div>
          <h2 className="text-xl font-bold mb-1">Melhor Envio conectado!</h2>
          <p className="text-blue-100 text-sm">Conta autorizada com sucesso</p>
        </div>
        <div className="p-8 text-center space-y-4">
          <p className="text-gray-600 text-sm">
            Sua conta do Melhor Envio foi conectada. Agora você pode calcular
            fretes e processar envios nos seus anúncios.
          </p>
          {isPopup ? (
            <div className="space-y-2">
              {/* Progress bar communicates the remaining auto-close time */}
              <div
                className="w-full h-1 bg-gray-100 rounded-full overflow-hidden"
                aria-hidden="true"
              >
                <div
                  className="h-full bg-blue-900 rounded-full transition-[width] ease-linear"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="text-xs text-gray-400">
                Esta janela será fechada automaticamente…
              </p>
            </div>
          ) : (
            <Link
              to="/"
              className="block w-full py-2.5 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 focus-visible:ring-2 focus-visible:ring-blue-700 focus-visible:ring-offset-2 transition text-center"
            >
              Ir para o início
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
