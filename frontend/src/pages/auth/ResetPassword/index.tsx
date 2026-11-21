import { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Lock, Eye, EyeOff, AlertCircle, CheckCircle2, X } from "lucide-react";
import { authService } from "@/services/authService";
import { AuthLogo } from "@/components/ui/AuthLogo";
import {
  validatePasswordRequirements,
  isPasswordValid,
} from "@/utils/validators";

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

export default function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const uid = searchParams.get("uid");
  const token = searchParams.get("token");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Real-time password validation (matches Register)
  const passwordReqs = validatePasswordRequirements(password);

  const handleResetPassword = async () => {
    setError("");

    if (!uid || !token) {
      setError("Link inválido ou expirado.");
      return;
    }

    if (!password || !confirmPassword) {
      setError("Preencha todos os campos.");
      return;
    }

    if (!isPasswordValid(password)) {
      setError("A senha não atende todos os requisitos.");
      return;
    }

    if (password !== confirmPassword) {
      setError("As senhas não coincidem.");
      return;
    }

    try {
      setIsLoading(true);
      await authService.confirmPasswordReset({
        new_password1: password,
        new_password2: confirmPassword,
        uid,
        token,
      });
      setSuccess(true);
      setTimeout(() => navigate("/login"), 2500);
    } catch (err: unknown) {
      setError(getAxiosErrorMessage(err, "Erro ao redefinir senha."));
    } finally {
      setIsLoading(false);
    }
  };

  const PasswordRequirement = ({
    met,
    text,
  }: {
    met: boolean;
    text: string;
  }) => (
    <div
      className={`flex items-center gap-2 text-xs ${
        met ? "text-gold" : "text-ink-3"
      }`}
    >
      {met ? (
        <CheckCircle2 size={14} aria-hidden="true" />
      ) : (
        <X size={14} aria-hidden="true" />
      )}
      <span>{text}</span>
    </div>
  );

  return (
    <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4 py-8 relative">
      <AuthLogo />

      {/* Card */}
      <div className="w-full max-w-md">
        <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
          {/* Header */}
          <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
            <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Lock size={28} className="text-gold" aria-hidden="true" />
            </div>
            <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
              Redefinir senha
            </h1>
            <p className="text-ink-2 text-sm leading-relaxed">
              Crie uma nova senha para sua conta
            </p>
          </div>

          {/* Body */}
          <div className="p-6 md:p-8 space-y-5">
            {/* Success state replaces form */}
            {success ? (
              <div
                role="status"
                className="p-4 bg-green-500/10 border border-green-500/30 rounded-xl flex items-start gap-3"
              >
                <CheckCircle2
                  className="text-green-400 shrink-0 mt-0.5"
                  size={18}
                  aria-hidden="true"
                />
                <div className="text-sm text-ink-1">
                  <p className="font-semibold mb-1">Senha redefinida!</p>
                  <p className="text-ink-2 leading-relaxed">
                    Redirecionando para o login em instantes…
                  </p>
                </div>
              </div>
            ) : (
              <>
                {/* Error */}
                {error && (
                  <div
                    role="alert"
                    className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-3"
                  >
                    <AlertCircle
                      className="text-red-400 shrink-0 mt-0.5"
                      size={18}
                      aria-hidden="true"
                    />
                    <p className="text-sm text-red-400">{error}</p>
                  </div>
                )}

                {/* Nova senha */}
                <div>
                  <label
                    htmlFor="reset-password"
                    className="block text-sm font-semibold text-ink-1 mb-2"
                  >
                    Nova senha
                  </label>
                  <div className="relative">
                    <Lock
                      className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
                      size={18}
                      aria-hidden="true"
                    />
                    <input
                      id="reset-password"
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => {
                        setPassword(e.target.value);
                        if (error) setError("");
                      }}
                      placeholder="••••••••"
                      className="w-full pl-10 pr-12 py-2.5 bg-bg-2 border border-white/10 rounded-xl text-ink-1 placeholder:text-ink-3 text-sm focus:border-gold/50 focus:ring-2 focus:ring-gold/20 focus:outline-none transition-colors disabled:opacity-50"
                      disabled={isLoading}
                      autoFocus
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-ink-3 hover:text-ink-1 transition-colors"
                      disabled={isLoading}
                      aria-label={
                        showPassword ? "Ocultar senha" : "Mostrar senha"
                      }
                    >
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>

                  {/* Requisitos da senha */}
                  {password && (
                    <div className="mt-3 p-3 bg-bg-2 border border-white/10 rounded-xl space-y-1.5">
                      <p className="text-xs font-semibold text-ink-2 mb-1.5">
                        Requisitos da senha:
                      </p>
                      <PasswordRequirement
                        met={passwordReqs.minLength}
                        text="Mínimo de 8 caracteres"
                      />
                      <PasswordRequirement
                        met={passwordReqs.hasUpperCase}
                        text="Letra maiúscula"
                      />
                      <PasswordRequirement
                        met={passwordReqs.hasLowerCase}
                        text="Letra minúscula"
                      />
                      <PasswordRequirement
                        met={passwordReqs.hasNumber}
                        text="Número"
                      />
                      <PasswordRequirement
                        met={passwordReqs.hasSpecialChar}
                        text="Caractere especial"
                      />
                    </div>
                  )}
                </div>

                {/* Confirmar senha */}
                <div>
                  <label
                    htmlFor="reset-confirm"
                    className="block text-sm font-semibold text-ink-1 mb-2"
                  >
                    Confirmar nova senha
                  </label>
                  <div className="relative">
                    <Lock
                      className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
                      size={18}
                      aria-hidden="true"
                    />
                    <input
                      id="reset-confirm"
                      type={showConfirmPassword ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => {
                        setConfirmPassword(e.target.value);
                        if (error) setError("");
                      }}
                      onKeyDown={(e) =>
                        e.key === "Enter" &&
                        !isLoading &&
                        void handleResetPassword()
                      }
                      placeholder="••••••••"
                      className="w-full pl-10 pr-12 py-2.5 bg-bg-2 border border-white/10 rounded-xl text-ink-1 placeholder:text-ink-3 text-sm focus:border-gold/50 focus:ring-2 focus:ring-gold/20 focus:outline-none transition-colors disabled:opacity-50"
                      disabled={isLoading}
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setShowConfirmPassword(!showConfirmPassword)
                      }
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-ink-3 hover:text-ink-1 transition-colors"
                      disabled={isLoading}
                      aria-label={
                        showConfirmPassword ? "Ocultar senha" : "Mostrar senha"
                      }
                    >
                      {showConfirmPassword ? (
                        <EyeOff size={18} />
                      ) : (
                        <Eye size={18} />
                      )}
                    </button>
                  </div>
                  {confirmPassword &&
                    password === confirmPassword &&
                    isPasswordValid(password) && (
                      <p className="mt-1.5 text-xs text-green-400 flex items-center gap-1">
                        <CheckCircle2 size={14} aria-hidden="true" />
                        Senhas coincidem
                      </p>
                    )}
                </div>

                {/* Botão */}
                <button
                  type="button"
                  onClick={() => void handleResetPassword()}
                  disabled={isLoading}
                  className="w-full bg-gold text-gold-deep py-3 rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-4 h-4 rounded-full border-2 border-gold-deep/30 border-t-gold-deep animate-spin" />
                      Redefinindo...
                    </span>
                  ) : (
                    "Redefinir senha"
                  )}
                </button>
              </>
            )}

            {/* Voltar ao login */}
            <p className="text-center text-sm text-ink-2 pt-1">
              <Link
                to="/login"
                className="text-gold hover:text-gold/80 font-medium transition-colors"
              >
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
