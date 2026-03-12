import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { logisticsService } from "@/services/logisticsService";

const CLOSE_DELAY_MS = 2000;

// Map common OAuth error codes to friendlier Portuguese hints.
const ERROR_HINT: Record<string, string> = {
  access_denied: "Você cancelou a autorização no Melhor Envio.",
  server_error: "O servidor do Melhor Envio retornou um erro. Tente mais tarde.",
  temporarily_unavailable:
    "O serviço está temporariamente indisponível. Tente novamente em alguns minutos.",
};

// Derive the initial page scenario from URL params — computed once on mount.
type PageScenario =
  | { type: "success"; meEmail: string | null; environment: string | null }
  | { type: "error"; errorCode: string; errorMessage: string }
  | { type: "exchange"; code: string; state: string }
  | { type: "processing" };

function deriveScenario(): PageScenario {
  const params = new URLSearchParams(window.location.search);

  if (params.has("error")) {
    const errorCode = params.get("error") ?? "";
    const errorMessage =
      ERROR_HINT[errorCode] ?? "Ocorreu um erro durante a autorização. Tente novamente.";
    return { type: "error", errorCode, errorMessage };
  }

  if (params.get("status") === "connected") {
    return {
      type: "success",
      meEmail: params.get("me_email"),
      environment: params.get("environment"),
    };
  }

  const code = params.get("code");
  const state = params.get("state");
  if (code) {
    return { type: "exchange", code, state: state ?? "" };
  }

  return { type: "processing" };
}

type ViewState =
  | { kind: "loading" }
  | { kind: "success"; meEmail: string | null }
  | { kind: "error"; message: string }
  | { kind: "processing" };

export function MelhorEnvioCallback() {
  // Computed once on mount via lazy initializer — stable across renders.
  const [isPopup] = useState(
    () => window.opener != null && window.name === "melhorenvio_oauth",
  );
  const [scenario] = useState<PageScenario>(deriveScenario);

  // ViewState drives what is rendered. Starts resolved for non-exchange scenarios.
  const [view, setView] = useState<ViewState>(() => {
    switch (scenario.type) {
      case "success":
        return { kind: "success", meEmail: scenario.meEmail };
      case "error":
        return { kind: "error", message: scenario.errorMessage };
      case "exchange":
        return { kind: "loading" };
      case "processing":
        return { kind: "processing" };
    }
  });

  const [progress, setProgress] = useState(0); // 0–100

  // When redirect_uri points directly at the frontend, exchange the code via API.
  useEffect(() => {
    if (scenario.type !== "exchange") return;

    let cancelled = false;
    logisticsService
      .exchangeMelhorEnvioCode(scenario.code, scenario.state)
      .then((data) => {
        if (cancelled) return;
        setView({ kind: "success", meEmail: data.me_email ?? null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof Error
            ? err.message
            : "Ocorreu um erro durante a autorização. Tente novamente.";
        setView({ kind: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [scenario]);

  // Progress bar + auto-close: only runs after a confirmed success in a popup.
  useEffect(() => {
    if (!isPopup || view.kind !== "success") return;

    const start = Date.now();
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
  }, [isPopup, view.kind]);

  // --- Loading state (exchange in flight) ---
  if (view.kind === "loading") {
    return (
      <div className="min-h-screen bg-linear-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-auto overflow-hidden">
          <div
            role="status"
            aria-live="polite"
            className="bg-linear-to-r from-blue-900 to-gray-900 p-8 text-white text-center"
          >
            <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
              <Loader2 size={36} className="text-white animate-spin" aria-hidden="true" />
            </div>
            <h2 className="text-xl font-bold mb-1">Processando autorização…</h2>
            <p className="text-blue-100 text-sm">Aguarde enquanto conectamos sua conta</p>
          </div>
          <div className="p-8 text-center">
            <p className="text-gray-600 text-sm">
              Estamos verificando sua autorização com o Melhor Envio.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // --- Error state ---
  if (view.kind === "error") {
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
            <p className="text-gray-600 text-sm">{view.message}</p>
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

  // --- Processing state (no recognized params) ---
  if (view.kind === "processing") {
    return (
      <div className="min-h-screen bg-linear-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-auto overflow-hidden">
          <div
            role="status"
            aria-live="polite"
            className="bg-linear-to-r from-blue-900 to-gray-900 p-8 text-white text-center"
          >
            <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
              <Loader2 size={36} className="text-white animate-spin" aria-hidden="true" />
            </div>
            <h2 className="text-xl font-bold mb-1">Processando…</h2>
            <p className="text-blue-100 text-sm">Verificando autorização</p>
          </div>
          <div className="p-8 text-center">
            <p className="text-gray-600 text-sm">
              Esta janela será fechada em instantes.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // --- Success state ---
  const meEmail = view.meEmail;
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
          <p className="text-blue-100 text-sm">
            {meEmail ? `Conta ${meEmail} conectada!` : "Conta autorizada com sucesso"}
          </p>
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
