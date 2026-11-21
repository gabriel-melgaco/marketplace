import { useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { authService } from "@/services/authService";
import { AuthLogo } from "@/components/ui/AuthLogo";
import {
  Mail,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Lightbulb,
  ListOrdered,
} from "lucide-react";

// Local fallback while the shared `getAxiosErrorMessage` helper is not centralized.
function getAxiosErrorMessage(err: unknown, fallback: string): string {
  const responseData = (err as { response?: { data?: unknown } })?.response
    ?.data;
  if (responseData && typeof responseData === "object") {
    return (
      (Object.values(responseData).flat() as string[]).join(" ") || fallback
    );
  }
  if (typeof responseData === "string" && responseData) return responseData;
  if (err instanceof Error) return err.message;
  return fallback;
}

// Rate-limit the resend button (seconds). Prevents spamming the backend
// and matches the behavior of most OTP/email-verification flows.
const RESEND_COOLDOWN_SECONDS = 60;

export default function EmailSent() {
  const navigate = useNavigate();
  const location = useLocation();

  // State
  const [isLoading, setIsLoading] = useState(false);
  const [feedback, setFeedback] = useState<
    | { type: "success"; message: string }
    | { type: "error"; message: string }
    | null
  >(null);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);

  // Email comes from the state (if coming from register)
  const email = (location.state as { email?: string } | null)?.email ?? "";
  const emailDisplay = email || "seu e-mail";

  const startCooldown = () => {
    setCooldownSeconds(RESEND_COOLDOWN_SECONDS);
    const tick = () => {
      setCooldownSeconds((s) => {
        if (s <= 1) return 0;
        window.setTimeout(tick, 1000);
        return s - 1;
      });
    };
    window.setTimeout(tick, 1000);
  };

  const handleResend = async () => {
    if (isLoading || cooldownSeconds > 0 || !email) return;

    setIsLoading(true);
    setFeedback(null);

    try {
      await authService.resendVerificationEmail({ email });
      setFeedback({
        type: "success",
        message: "E-mail reenviado com sucesso!",
      });
      startCooldown();
    } catch (err: unknown) {
      setFeedback({
        type: "error",
        message: getAxiosErrorMessage(
          err,
          "Não foi possível reenviar o e-mail. Tente novamente.",
        ),
      });
    } finally {
      setIsLoading(false);
    }
  };

  const resendDisabled = isLoading || cooldownSeconds > 0 || !email;

  return (
    <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4 py-8 relative">
      <AuthLogo />

      {/* Card */}
      <div className="w-full max-w-md">
        <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
          {/* Header */}
          <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
            <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Mail size={28} className="text-gold" aria-hidden="true" />
            </div>
            <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
              Verifique seu e-mail
            </h1>
            <p className="text-ink-2 text-sm leading-relaxed">
              Estamos quase lá! Confirme seu e-mail para ativar sua conta.
            </p>
          </div>

          {/* Body */}
          <div className="p-6 md:p-8 space-y-5">
            {/* Mensagem de destinatário */}
            <div className="text-center space-y-2">
              <p className="text-ink-2 text-sm">
                Enviamos um link de confirmação para:
              </p>
              <p className="font-semibold text-gold text-base break-all">
                {emailDisplay}
              </p>
            </div>

            {/* Próximos passos */}
            <div className="bg-bg-2 border border-white/10 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <ListOrdered
                  size={16}
                  className="text-gold"
                  aria-hidden="true"
                />
                <p className="text-sm font-semibold text-ink-1">
                  Próximos passos
                </p>
              </div>
              <ol className="text-sm text-ink-2 space-y-1.5 list-decimal list-inside marker:text-gold">
                <li>Abra seu e-mail</li>
                <li>
                  Procure por{" "}
                  <span className="text-ink-1">"Confirmação de Cadastro"</span>
                </li>
                <li>Clique no link de verificação</li>
                <li>Faça login no Marketplace</li>
              </ol>
            </div>

            {/* Dica — verificar spam */}
            <div className="bg-gold/10 border border-gold/30 rounded-xl p-4 flex items-start gap-3">
              <Lightbulb
                size={18}
                className="text-gold shrink-0 mt-0.5"
                aria-hidden="true"
              />
              <p className="text-sm text-ink-1 leading-relaxed">
                <span className="font-semibold">Dica:</span>{" "}
                <span className="text-ink-2">
                  não encontrou? Verifique sua caixa de spam ou lixo eletrônico.
                </span>
              </p>
            </div>

            {/* Feedback (success / error) do reenvio */}
            {feedback && (
              <div
                role={feedback.type === "error" ? "alert" : "status"}
                className={
                  feedback.type === "success"
                    ? "p-3 bg-green-500/10 border border-green-500/30 rounded-xl flex items-start gap-3"
                    : "p-3 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-3"
                }
              >
                {feedback.type === "success" ? (
                  <CheckCircle2
                    size={16}
                    className="text-green-400 shrink-0 mt-0.5"
                    aria-hidden="true"
                  />
                ) : (
                  <AlertCircle
                    size={16}
                    className="text-red-400 shrink-0 mt-0.5"
                    aria-hidden="true"
                  />
                )}
                <p
                  className={
                    feedback.type === "success"
                      ? "text-sm text-green-400"
                      : "text-sm text-red-400"
                  }
                >
                  {feedback.message}
                </p>
              </div>
            )}

            {/* Botões */}
            <div className="space-y-3 pt-1">
              {/* Reenviar (secundário) */}
              <button
                type="button"
                onClick={() => void handleResend()}
                disabled={resendDisabled}
                className="w-full bg-bg-2 border border-white/10 text-ink-1 py-3 rounded-xl text-sm font-medium hover:bg-bg-3 hover:border-white/15 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 rounded-full border-2 border-ink-3/30 border-t-ink-1 animate-spin" />
                    Reenviando...
                  </span>
                ) : cooldownSeconds > 0 ? (
                  `Aguarde ${cooldownSeconds}s para reenviar`
                ) : (
                  "Reenviar e-mail"
                )}
              </button>

              {/* Voltar ao login (primário) */}
              <button
                type="button"
                onClick={() => navigate("/login")}
                className="w-full flex items-center justify-center gap-2 bg-gold text-gold-deep py-3 rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
              >
                <ArrowLeft size={16} aria-hidden="true" />
                Voltar ao login
              </button>
            </div>

            {/* Link de Ajuda */}
            <div className="text-center pt-4 border-t border-white/10">
              <p className="text-sm text-ink-2">
                Problemas com a verificação?{" "}
                <Link
                  to="/help"
                  className="text-gold hover:text-gold/80 font-semibold transition-colors"
                >
                  Fale conosco
                </Link>
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-6 text-center text-ink-3 text-xs space-y-1">
          <p>© 2026 megdev. Todos os direitos reservados.</p>
          <div className="flex justify-center gap-4">
            <Link
              to="/politica-de-cookies"
              className="hover:text-ink-2 transition-colors"
            >
              Termos de Uso
            </Link>
            <span>•</span>
            <Link
              to="/politica-de-cookies"
              className="hover:text-ink-2 transition-colors"
            >
              Política de Privacidade
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
