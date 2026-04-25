import { useState } from "react";
import { Link } from "react-router-dom";
import { RectangleEllipsis, Mail, CheckCircle2, ArrowLeft } from "lucide-react";
import { authService } from "@/services/authService";
import { AuthLogo } from "@/components/ui/AuthLogo";

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

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sendLinkSuccess, setSendLinkSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!email.trim()) {
      setError("Informe seu e-mail para continuar.");
      return;
    }

    setIsLoading(true);
    setError("");

    try {
      await authService.requestPasswordReset({ email });
    } catch (err: unknown) {
      // Intentionally silent to the user: to avoid email enumeration, we always
      // show the same success message regardless of whether the email exists.
      // Only log so devs can still debug via the console.
      console.log(getAxiosErrorMessage(err, "Erro ao solicitar redefinição"));
    } finally {
      setSendLinkSuccess(true);
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4 py-8 relative">
      <AuthLogo />

      {/* Card */}
      <div className="w-full max-w-md">
        <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
          {/* Header */}
          <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
            <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <RectangleEllipsis
                size={28}
                className="text-gold"
                aria-hidden="true"
              />
            </div>
            <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
              Esqueceu sua senha?
            </h1>
            <p className="text-ink-2 text-sm leading-relaxed">
              Informe o e-mail cadastrado e enviaremos um link para redefinir
              sua senha.
            </p>
          </div>

          {/* Body */}
          <div className="p-6 md:p-8 space-y-5">
            {/* Mensagem de Sucesso */}
            {sendLinkSuccess ? (
              <div
                role="alert"
                className="p-4 bg-gold/10 border border-gold/30 rounded-xl flex items-start gap-3"
              >
                <CheckCircle2
                  className="text-gold shrink-0 mt-0.5"
                  size={18}
                  aria-hidden="true"
                />
                <div className="text-sm text-ink-1">
                  <p className="font-semibold mb-1">Link enviado!</p>
                  <p className="text-ink-2 leading-relaxed">
                    Se o e-mail informado estiver cadastrado, você receberá um
                    link para redefinir sua senha em instantes.
                  </p>
                </div>
              </div>
            ) : (
              <>
                {/* Erro de validação */}
                {error && (
                  <div
                    role="alert"
                    className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-3"
                  >
                    <p className="text-sm text-red-400">{error}</p>
                  </div>
                )}

                {/* Email */}
                <div>
                  <label
                    htmlFor="forgot-email"
                    className="block text-sm font-semibold text-ink-1 mb-2"
                  >
                    Email
                  </label>
                  <div className="relative">
                    <Mail
                      className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
                      size={18}
                      aria-hidden="true"
                    />
                    <input
                      id="forgot-email"
                      type="email"
                      name="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        if (error) setError("");
                      }}
                      onKeyDown={(e) =>
                        e.key === "Enter" && !isLoading && void handleSubmit()
                      }
                      placeholder="seu@email.com"
                      className="w-full pl-10 pr-4 py-2.5 bg-bg-2 border border-white/10 rounded-xl text-ink-1 placeholder:text-ink-3 text-sm focus:border-gold/50 focus:ring-2 focus:ring-gold/20 focus:outline-none transition-colors disabled:opacity-50"
                      disabled={isLoading}
                      autoFocus
                    />
                  </div>
                </div>

                {/* Botão */}
                <button
                  type="button"
                  onClick={() => void handleSubmit()}
                  disabled={isLoading}
                  className="w-full bg-gold text-gold-deep py-3 rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-4 h-4 rounded-full border-2 border-gold-deep/30 border-t-gold-deep animate-spin" />
                      Enviando...
                    </span>
                  ) : (
                    "Enviar Link"
                  )}
                </button>
              </>
            )}

            {/* Link voltar ao login */}
            <p className="text-center text-sm text-ink-2 pt-1">
              <Link
                to="/login"
                className="inline-flex items-center gap-1.5 text-gold hover:text-gold/80 font-medium transition-colors"
              >
                <ArrowLeft size={14} aria-hidden="true" />
                Voltar ao login
              </Link>
            </p>
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
