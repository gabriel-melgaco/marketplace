import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2, Truck } from "lucide-react";
import { logisticsService } from "@/services/logisticsService";

const CLOSE_DELAY_MS = 2000;

// Map common OAuth error codes to friendlier Portuguese hints.
const ERROR_HINT: Record<string, string> = {
  access_denied: "Você cancelou a autorização no Melhor Envio.",
  server_error:
    "O servidor do Melhor Envio retornou um erro. Tente mais tarde.",
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
      ERROR_HINT[errorCode] ??
      "Ocorreu um erro durante a autorização. Tente novamente.";
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
      <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
        <div className="w-full max-w-sm">
          <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
            <div
              role="status"
              aria-live="polite"
              className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center"
            >
              <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <Loader2
                  size={28}
                  className="text-gold animate-spin"
                  aria-hidden="true"
                />
              </div>
              <h2 className="font-display text-xl md:text-2xl font-bold text-ink-1 tracking-[-0.02em] mb-1">
                Processando autorização…
              </h2>
              <p className="text-ink-2 text-sm leading-relaxed">
                Aguarde enquanto conectamos sua conta
              </p>
            </div>
            <div className="p-6 md:p-8 text-center">
              <p className="text-ink-2 text-sm leading-relaxed">
                Estamos verificando sua autorização com o Melhor Envio.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // --- Error state ---
  if (view.kind === "error") {
    return (
      <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
        <div className="w-full max-w-sm">
          <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
            <div
              role="alert"
              className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center"
            >
              <div className="w-16 h-16 bg-red-500/10 border border-red-500/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <XCircle
                  size={28}
                  className="text-red-400"
                  aria-hidden="true"
                />
              </div>
              <h2 className="font-display text-xl md:text-2xl font-bold text-ink-1 tracking-[-0.02em] mb-1">
                Falha na conexão
              </h2>
              <p className="text-ink-2 text-sm leading-relaxed">
                Não foi possível conectar o Melhor Envio
              </p>
            </div>
            <div className="p-6 md:p-8 text-center space-y-4">
              <p className="text-ink-2 text-sm leading-relaxed">
                {view.message}
              </p>
              {isPopup ? (
                <button
                  type="button"
                  onClick={() => window.close()}
                  className="w-full py-3 bg-bg-2 border border-white/10 text-ink-1 rounded-xl text-sm font-semibold hover:bg-bg-3 hover:border-white/20 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1"
                >
                  Fechar janela
                </button>
              ) : (
                <Link
                  to="/"
                  className="block w-full py-3 bg-gold text-gold-deep rounded-xl text-sm font-semibold hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1 text-center"
                >
                  Voltar ao início
                </Link>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // --- Processing state (no recognized params) ---
  if (view.kind === "processing") {
    return (
      <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
        <div className="w-full max-w-sm">
          <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
            <div
              role="status"
              aria-live="polite"
              className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center"
            >
              <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <Loader2
                  size={28}
                  className="text-gold animate-spin"
                  aria-hidden="true"
                />
              </div>
              <h2 className="font-display text-xl md:text-2xl font-bold text-ink-1 tracking-[-0.02em] mb-1">
                Processando…
              </h2>
              <p className="text-ink-2 text-sm leading-relaxed">
                Verificando autorização
              </p>
            </div>
            <div className="p-6 md:p-8 text-center">
              <p className="text-ink-2 text-sm leading-relaxed">
                Esta janela será fechada em instantes.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // --- Success state ---
  const meEmail = view.meEmail;
  return (
    <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
          <div
            role="status"
            className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center"
          >
            <div className="w-16 h-16 bg-green-500/10 border border-green-500/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <CheckCircle2
                size={28}
                className="text-green-400"
                aria-hidden="true"
              />
            </div>
            <h2 className="font-display text-xl md:text-2xl font-bold text-ink-1 tracking-[-0.02em] mb-1">
              Melhor Envio conectado!
            </h2>
            <p className="text-ink-2 text-sm leading-relaxed">
              {meEmail
                ? `Conta ${meEmail} conectada`
                : "Conta autorizada com sucesso"}
            </p>
          </div>
          <div className="p-6 md:p-8 text-center space-y-4">
            <div className="bg-bg-2 border border-white/10 rounded-xl p-4 flex items-start gap-3 text-left">
              <Truck
                size={18}
                className="text-gold shrink-0 mt-0.5"
                aria-hidden="true"
              />
              <p className="text-sm text-ink-2 leading-relaxed">
                Sua conta foi conectada. Agora você pode calcular fretes e
                processar envios nos seus anúncios.
              </p>
            </div>
            {isPopup ? (
              <div className="space-y-2">
                {/* Progress bar communicates the remaining auto-close time */}
                <div
                  className="w-full h-1 bg-bg-2 rounded-full overflow-hidden"
                  aria-hidden="true"
                >
                  <div
                    className="h-full bg-gold rounded-full transition-[width] ease-linear"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="text-xs text-ink-3">
                  Esta janela será fechada automaticamente…
                </p>
              </div>
            ) : (
              <Link
                to="/"
                className="block w-full py-3 bg-gold text-gold-deep rounded-xl text-sm font-semibold hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1 text-center"
              >
                Ir para o início
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
