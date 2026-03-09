import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Clock, XCircle, Loader2 } from "lucide-react";
import {
  stripeConnectService,
  type SyncAccountStatusResponse,
} from "@/services/stripeConnectService";
import { ROUTES } from "@/routes/routePaths";
import Swal from "sweetalert2";

type SyncState = "loading" | "success" | "pending" | "error";

export function StripeOnboardingComplete() {
  const navigate = useNavigate();

  // Computed once on mount — stable across renders
  const [urlStatus] = useState(
    () => new URLSearchParams(window.location.search).get("status"),
  );

  const [syncState, setSyncState] = useState<SyncState>("loading");
  const [syncResult, setSyncResult] = useState<SyncAccountStatusResponse | null>(null);
  const [onboardingLoading, setOnboardingLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    stripeConnectService
      .syncAccountStatus()
      .then((result) => {
        if (cancelled) return;
        setSyncResult(result);
        const isVerified =
          result.seller_verified === true ||
          result.ready_to_receive_payments === true;
        if (urlStatus === "active" && isVerified) {
          setSyncState("success");
        } else {
          setSyncState("pending");
        }
      })
      .catch(() => {
        if (!cancelled) setSyncState("error");
      });

    return () => {
      cancelled = true;
    };
  }, [urlStatus]);

  const handleContinueOnboarding = useCallback(async () => {
    if (onboardingLoading) return;
    setOnboardingLoading(true);
    try {
      try {
        await stripeConnectService.createConnectedAccount();
      } catch {
        // Account may already exist — this is expected
      }
      const link = await stripeConnectService.getOnboardingLink();
      window.location.href = link.url;
    } catch (err: unknown) {
      Swal.fire({
        icon: "error",
        title: "Erro",
        text: "Não foi possível iniciar o cadastro Stripe. Tente novamente.",
        confirmButtonColor: "#1e3a5f",
      });
    } finally {
      setOnboardingLoading(false);
    }
  }, [onboardingLoading]);

  // ── Shared layout wrapper ───────────────────────────────────────────────────

  const PageShell = ({ children }: { children: React.ReactNode }) => (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
      {children}
    </div>
  );

  // ── Loading state ──────────────────────────────────────────────────────────
  // Kept as a flat card — a gradient header during loading would imply a
  // resolved state before the result is known. Flat is cleaner and honest.
  // The icon shape is aligned with all other states (rounded-full circle).

  if (syncState === "loading") {
    return (
      <PageShell>
        <div
          role="status"
          aria-live="polite"
          aria-label="Sincronizando conta Stripe"
          className="bg-white rounded-2xl shadow-2xl p-10 max-w-sm w-full text-center"
        >
          <div className="w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center mx-auto mb-5">
            <Loader2 className="h-8 w-8 animate-spin text-blue-900" aria-hidden="true" />
          </div>
          <h2 className="text-xl font-bold text-gray-900 mb-1">
            Finalizando cadastro...
          </h2>
          <p className="text-sm text-gray-500">
            Aguarde enquanto sincronizamos sua conta com a Stripe.
          </p>
        </div>
      </PageShell>
    );
  }

  // ── Success state ──────────────────────────────────────────────────────────
  // Dashboard is the primary CTA (filled) — it's the most productive next
  // action after a successful onboarding. "Minha Conta" is secondary (outline).

  if (syncState === "success") {
    return (
      <PageShell>
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-auto overflow-hidden">
          <div
            role="status"
            aria-live="polite"
            className="bg-linear-to-r from-blue-900 to-gray-900 p-8 text-white text-center"
          >
            <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
              <CheckCircle2 size={36} className="text-white" aria-hidden="true" />
            </div>
            <h2 className="text-xl font-bold mb-1">Cadastro concluído!</h2>
            <p className="text-blue-100 text-sm">Conta Stripe ativa</p>
          </div>
          <div className="p-8 text-center space-y-4">
            <p className="text-gray-600 text-sm">
              Sua conta Stripe está ativa e você já pode receber pagamentos
              pelos seus anúncios no marketplace.
            </p>
            {/* Primary: Dashboard — most productive next step */}
            <button
              onClick={() => navigate(ROUTES.DASHBOARD)}
              className="w-full py-3 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-700 focus-visible:ring-offset-2 transition cursor-pointer"
            >
              Ir para o Dashboard
            </button>
            {/* Secondary: Account — lower-priority alternative */}
            <button
              onClick={() => navigate(ROUTES.ACCOUNT)}
              className="w-full py-3 border border-gray-200 text-gray-600 rounded-xl text-sm font-semibold hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 focus-visible:ring-offset-2 transition cursor-pointer"
            >
              Ir para Minha Conta
            </button>
          </div>
        </div>
      </PageShell>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────

  if (syncState === "error") {
    return (
      <PageShell>
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-auto overflow-hidden">
          <div
            role="alert"
            className="bg-linear-to-r from-red-700 to-red-900 p-8 text-white text-center"
          >
            <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
              <XCircle size={36} className="text-white" aria-hidden="true" />
            </div>
            <h2 className="text-xl font-bold mb-1">Erro ao finalizar</h2>
            <p className="text-red-100 text-sm">Não foi possível sincronizar o cadastro</p>
          </div>
          <div className="p-8 text-center space-y-4">
            <p className="text-gray-600 text-sm">
              Ocorreu um erro ao sincronizar sua conta Stripe. Isso pode ser
              temporário. Tente acessar sua conta para verificar o status.
            </p>
            <button
              onClick={() => navigate(ROUTES.ACCOUNT)}
              className="w-full py-3 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-700 focus-visible:ring-offset-2 transition cursor-pointer"
            >
              Ir para Minha Conta
            </button>
          </div>
        </div>
      </PageShell>
    );
  }

  // ── Pending state (status=inactive or sync returned not verified) ──────────
  // role="alert" is appropriate here: the user must take action to proceed.
  // This is not a passive informational status — it demands a response.
  //
  // Contextual info box logic:
  //   - details_submitted=false → user hasn't even started the Stripe form yet
  //   - pending_verification=true → user submitted, Stripe is reviewing
  //   - neither → generic "complete your registration" message

  const detailsNotSubmitted =
    syncResult !== null && syncResult.details_submitted === false;
  const pendingVerification = syncResult?.pending_verification === true;

  return (
    <PageShell>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-auto overflow-hidden">
        <div
          role="alert"
          className="bg-linear-to-r from-amber-600 to-amber-800 p-8 text-white text-center"
        >
          <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
            <Clock size={36} className="text-white" aria-hidden="true" />
          </div>
          <h2 className="text-xl font-bold mb-1">Cadastro incompleto</h2>
          <p className="text-amber-100 text-sm">Ação necessária para continuar</p>
        </div>
        <div className="p-8 text-center space-y-4">
          <p className="text-gray-600 text-sm">
            Seu cadastro Stripe ainda não está completo. Você precisa concluir
            todas as etapas de verificação exigidas pela Stripe para poder
            receber pagamentos.
          </p>

          {/* Contextual guidance depending on where the user is in the flow */}
          {detailsNotSubmitted && !pendingVerification && (
            <p className="text-xs text-blue-800 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-left">
              Você ainda não enviou suas informações à Stripe. Clique em
              "Completar cadastro" para iniciar o processo.
            </p>
          )}
          {pendingVerification && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-left">
              Suas informações foram enviadas e estão sendo analisadas pela
              Stripe. Isso pode levar alguns minutos.
            </p>
          )}

          {/* Primary CTA: blue-900 keeps this consistent with all other primary
              actions in the project. The amber gradient header already
              communicates the warning context. */}
          <button
            onClick={handleContinueOnboarding}
            disabled={onboardingLoading}
            className="w-full py-3 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-700 focus-visible:ring-offset-2 transition disabled:opacity-50 cursor-pointer"
          >
            {onboardingLoading ? (
              <span className="flex items-center justify-center gap-2">
                <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                Aguarde...
              </span>
            ) : (
              "Completar cadastro"
            )}
          </button>
          <button
            onClick={() => navigate(ROUTES.ACCOUNT)}
            className="w-full py-3 border border-gray-200 text-gray-600 rounded-xl text-sm font-semibold hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 focus-visible:ring-offset-2 transition cursor-pointer"
          >
            Ir para Minha Conta
          </button>
        </div>
      </div>
    </PageShell>
  );
}
