import { useEffect, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2, AlertCircle } from "lucide-react";
import { authService } from "@/services/authService";
import { AuthLogo } from "@/components/ui/AuthLogo";

type VerificationStatus = "loading" | "success" | "error" | "invalid";

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

const REDIRECT_DELAY_SECONDS = 5;

export default function ConfirmEmail() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [status, setStatus] = useState<VerificationStatus>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [countdown, setCountdown] = useState(REDIRECT_DELAY_SECONDS);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const verifyEmail = async () => {
      const key = searchParams.get("key") || searchParams.get("token");

      if (!key) {
        if (cancelled) return;
        setStatus("invalid");
        setErrorMessage("Link de verificação inválido. Token não encontrado.");
        return;
      }

      try {
        await authService.verifyEmail({ key });
        if (cancelled) return;
        setStatus("success");

        // Countdown to login
        let timeLeft = REDIRECT_DELAY_SECONDS;
        timer = setInterval(() => {
          timeLeft -= 1;
          if (cancelled) return;
          setCountdown(timeLeft);
          if (timeLeft === 0 && timer) {
            clearInterval(timer);
            navigate("/login", {
              state: {
                message:
                  "E-mail verificado com sucesso! Faça login para continuar.",
              },
            });
          }
        }, 1000);
      } catch (err: unknown) {
        if (cancelled) return;
        setStatus("error");
        setErrorMessage(
          getAxiosErrorMessage(
            err,
            "Não foi possível verificar seu e-mail. O link pode estar expirado ou já foi usado.",
          ),
        );
      }
    };

    verifyEmail();

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4 py-8 relative">
      <AuthLogo />

      {/* Card */}
      <div className="w-full max-w-md">
        <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
          {/* ──────────────── LOADING ──────────────── */}
          {status === "loading" && (
            <>
              <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
                <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <Loader2
                    size={28}
                    className="animate-spin text-gold"
                    aria-hidden="true"
                  />
                </div>
                <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
                  Verificando e-mail...
                </h1>
                <p className="text-ink-2 text-sm leading-relaxed">
                  Aguarde um momento
                </p>
              </div>

              <div
                className="p-6 md:p-8 text-center"
                role="status"
                aria-live="polite"
              >
                <p className="text-ink-2 text-sm leading-relaxed">
                  Estamos confirmando seu e-mail. Isso pode levar alguns
                  segundos.
                </p>
                <div
                  className="mt-6 flex justify-center gap-2"
                  aria-hidden="true"
                >
                  <div className="w-2 h-2 bg-gold rounded-full animate-pulse" />
                  <div
                    className="w-2 h-2 bg-gold rounded-full animate-pulse"
                    style={{ animationDelay: "150ms" }}
                  />
                  <div
                    className="w-2 h-2 bg-gold rounded-full animate-pulse"
                    style={{ animationDelay: "300ms" }}
                  />
                </div>
              </div>
            </>
          )}

          {/* ──────────────── SUCCESS ──────────────── */}
          {status === "success" && (
            <>
              <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
                <div className="w-16 h-16 bg-green-500/10 border border-green-500/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <CheckCircle2
                    size={28}
                    className="text-green-400"
                    aria-hidden="true"
                  />
                </div>
                <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
                  E-mail verificado!
                </h1>
                <p className="text-ink-2 text-sm leading-relaxed">
                  Sua conta foi confirmada com sucesso
                </p>
              </div>

              <div className="p-6 md:p-8 space-y-5" role="status">
                <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-xl flex items-start gap-3">
                  <CheckCircle2
                    className="text-green-400 shrink-0 mt-0.5"
                    size={18}
                    aria-hidden="true"
                  />
                  <div className="text-sm text-ink-1">
                    <p className="font-semibold mb-1">Tudo pronto!</p>
                    <p className="text-ink-2 leading-relaxed">
                      Sua conta está ativa e você já pode fazer login.
                    </p>
                  </div>
                </div>

                <p className="text-center text-ink-2 text-sm">
                  Redirecionando em{" "}
                  <span className="font-semibold text-gold">{countdown}</span>{" "}
                  {countdown === 1 ? "segundo" : "segundos"}...
                </p>

                <button
                  type="button"
                  onClick={() =>
                    navigate("/login", {
                      state: {
                        message:
                          "E-mail verificado com sucesso! Faça login para continuar.",
                      },
                    })
                  }
                  className="w-full bg-gold text-gold-deep py-3 rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
                >
                  Ir para login agora
                </button>
              </div>
            </>
          )}

          {/* ──────────────── ERROR ──────────────── */}
          {status === "error" && (
            <>
              <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
                <div className="w-16 h-16 bg-red-500/10 border border-red-500/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <XCircle
                    size={28}
                    className="text-red-400"
                    aria-hidden="true"
                  />
                </div>
                <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
                  Erro na verificação
                </h1>
                <p className="text-ink-2 text-sm leading-relaxed">
                  Não foi possível confirmar seu e-mail
                </p>
              </div>

              <div className="p-6 md:p-8 space-y-5">
                <div
                  role="alert"
                  className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-3"
                >
                  <AlertCircle
                    className="text-red-400 shrink-0 mt-0.5"
                    size={18}
                    aria-hidden="true"
                  />
                  <div className="text-sm text-red-400">
                    <p className="font-semibold mb-1">
                      Erro ao verificar e-mail
                    </p>
                    <p className="text-red-400/80 leading-relaxed">
                      {errorMessage}
                    </p>
                  </div>
                </div>

                <div className="bg-bg-2 border border-white/10 rounded-xl p-4">
                  <p className="text-sm font-semibold text-ink-1 mb-2">
                    O que fazer?
                  </p>
                  <ul className="text-sm text-ink-2 space-y-1.5">
                    <li className="flex items-start gap-2">
                      <span
                        className="mt-1 shrink-0 text-gold"
                        aria-hidden="true"
                      >
                        •
                      </span>
                      Verifique se o link está completo
                    </li>
                    <li className="flex items-start gap-2">
                      <span
                        className="mt-1 shrink-0 text-gold"
                        aria-hidden="true"
                      >
                        •
                      </span>
                      Certifique-se de que não foi usado antes
                    </li>
                    <li className="flex items-start gap-2">
                      <span
                        className="mt-1 shrink-0 text-gold"
                        aria-hidden="true"
                      >
                        •
                      </span>
                      Solicite um novo link de verificação
                    </li>
                    <li className="flex items-start gap-2">
                      <span
                        className="mt-1 shrink-0 text-gold"
                        aria-hidden="true"
                      >
                        •
                      </span>
                      Entre em contato com o suporte se o problema persistir
                    </li>
                  </ul>
                </div>

                <div className="space-y-3">
                  <button
                    type="button"
                    onClick={() => navigate("/register")}
                    className="w-full bg-gold text-gold-deep py-3 rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
                  >
                    Fazer novo cadastro
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate("/login")}
                    className="w-full bg-bg-2 border border-white/10 text-ink-1 py-3 rounded-xl font-semibold text-sm hover:bg-bg-3 hover:border-white/20 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
                  >
                    Voltar ao login
                  </button>
                </div>
              </div>
            </>
          )}

          {/* ──────────────── INVALID ──────────────── */}
          {status === "invalid" && (
            <>
              <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
                <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <AlertCircle
                    size={28}
                    className="text-gold"
                    aria-hidden="true"
                  />
                </div>
                <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
                  Link inválido
                </h1>
                <p className="text-ink-2 text-sm leading-relaxed">
                  Este link de verificação não é válido
                </p>
              </div>

              <div className="p-6 md:p-8 space-y-5">
                <div
                  role="alert"
                  className="p-4 bg-bg-2 border border-white/10 rounded-xl"
                >
                  <p className="text-sm text-ink-2">{errorMessage}</p>
                </div>

                <p className="text-center text-ink-2 text-sm leading-relaxed">
                  Certifique-se de estar usando o link completo enviado para seu
                  e-mail.
                </p>

                <button
                  type="button"
                  onClick={() => navigate("/register")}
                  className="w-full bg-gold text-gold-deep py-3 rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
                >
                  Fazer novo cadastro
                </button>
              </div>
            </>
          )}
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
