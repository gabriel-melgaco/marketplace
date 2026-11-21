import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { AuthLogo } from "@/components/ui/AuthLogo";
import {
  Eye,
  EyeOff,
  Mail,
  Lock,
  LogIn,
  AlertCircle,
  CheckCircle2,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { startGoogleOAuth } from "@/hooks/useGoogleAuth";

function getAxiosErrorMessage(err: unknown, fallback: string): string {
  const responseData = (err as { response?: { data?: unknown } })?.response
    ?.data;
  if (responseData && typeof responseData === "object") {
    return (Object.values(responseData).flat() as string[]).join(" ") || fallback;
  }
  if (typeof responseData === "string" && responseData) return responseData;
  if (err instanceof Error) return err.message;
  return fallback;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [rememberMe, setRememberMe] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const handleGoogleLogin = () => {
    startGoogleOAuth("login");
  };

  const handleLogin = async () => {
    setIsLoading(true);
    setError("");

    try {
      await login({ email, password });
      navigate("/");
    } catch (err: unknown) {
      setError(getAxiosErrorMessage(err, "Erro ao efetuar login"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-0 lg:grid lg:grid-cols-[2fr_3fr] relative">

      {/* ── Hero (apenas lg+) ─────────────────────────────────────────── */}
      <aside className="hidden lg:flex flex-col items-center justify-between p-12 bg-bg-1 border-r border-white/10 relative overflow-hidden">
        {/* Decorative glow */}
        <div
          aria-hidden="true"
          className="absolute -top-32 -left-32 w-[500px] h-[500px] rounded-full pointer-events-none"
          style={{
            background:
              "radial-gradient(circle, rgba(245,158,11,0.08) 0%, transparent 70%)",
          }}
        />

        {/* Brand */}
        <div className="relative z-10 w-full max-w-sm">
          <div className="flex items-center gap-3 mb-12">
            <div className="w-10 h-10 bg-gold rounded-full flex items-center justify-center shrink-0">
              <span className="text-gold-deep text-sm font-bold">CS</span>
            </div>
            <span className="font-display font-bold text-xl text-ink-1 tracking-tight">
              MARKETPLACE
            </span>
          </div>

          <h2 className="font-display text-4xl font-extrabold text-ink-1 tracking-[-0.03em] leading-tight mb-4">
            Equipamentos{" "}
            <span className="text-gold">profissionais.</span>
          </h2>
          <p className="text-ink-2 text-base leading-relaxed max-w-xs">
            A plataforma para comprar e vender equipamentos fitness com
            segurança e agilidade.
          </p>

          <ul className="mt-10 space-y-4">
            <li className="flex items-center gap-3 text-ink-2 text-sm">
              <CheckCircle2 size={18} className="text-gold shrink-0" />
              Pagamento seguro e protegido
            </li>
            <li className="flex items-center gap-3 text-ink-2 text-sm">
              <ShieldCheck size={18} className="text-gold shrink-0" />
              Vendedores verificados
            </li>
            <li className="flex items-center gap-3 text-ink-2 text-sm">
              <Zap size={18} className="text-gold shrink-0" />
              Entrega rápida para todo o Brasil
            </li>
          </ul>
        </div>

        {/* Footer hero */}
        <p className="relative z-10 text-ink-3 text-xs">
          © 2026 megdev. Todos os direitos reservados.
        </p>
      </aside>

      {/* ── Formulário ───────────────────────────────────────────────── */}
      <main className="flex items-center justify-center p-4 pt-24 lg:pt-4 min-h-screen lg:min-h-0">
        {/* AuthLogo — visível apenas em mobile (lg:hidden não existe aqui pois
            o hero já está hidden em mobile; o logo fixed cobre ambos) */}
        <AuthLogo />

        <div className="w-full max-w-md">
          {/* Card */}
          <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden">

            {/* Header do card */}
            <div className="bg-bg-2 p-8 border-b border-white/10 text-center">
              <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <LogIn size={32} className="text-gold" aria-hidden="true" />
              </div>
              <h1 className="font-display text-2xl font-bold text-ink-1 tracking-[-0.02em] mb-1">
                Bem-vindo!
              </h1>
              <p className="text-ink-2 text-sm">Entre para acessar sua conta</p>
            </div>

            {/* Body */}
            <div className="p-8 space-y-5">

              {/* Erro */}
              {error && (
                <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-3">
                  <AlertCircle
                    className="text-red-400 shrink-0 mt-0.5"
                    size={18}
                  />
                  <p className="text-sm text-red-400">{error}</p>
                </div>
              )}

              {/* Email */}
              <div>
                <label className="block text-sm font-semibold text-ink-1 mb-2">
                  Email
                </label>
                <div className="relative">
                  <Mail
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
                    size={18}
                    aria-hidden="true"
                  />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && void handleLogin()}
                    placeholder="seu@email.com"
                    className="w-full pl-10 pr-4 py-3 bg-bg-2 border border-white/10 rounded-xl text-ink-1 placeholder:text-ink-3 text-sm focus:border-gold/50 focus:ring-2 focus:ring-gold/20 focus:outline-none transition-colors disabled:opacity-50"
                    disabled={isLoading}
                  />
                </div>
              </div>

              {/* Senha */}
              <div>
                <label className="block text-sm font-semibold text-ink-1 mb-2">
                  Senha
                </label>
                <div className="relative">
                  <Lock
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
                    size={18}
                    aria-hidden="true"
                  />
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && void handleLogin()}
                    placeholder="••••••••"
                    className="w-full pl-10 pr-12 py-3 bg-bg-2 border border-white/10 rounded-xl text-ink-1 placeholder:text-ink-3 text-sm focus:border-gold/50 focus:ring-2 focus:ring-gold/20 focus:outline-none transition-colors disabled:opacity-50"
                    disabled={isLoading}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-ink-3 hover:text-ink-1 transition-colors"
                    disabled={isLoading}
                    aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              {/* Lembrar-me + Esqueci a senha */}
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="w-4 h-4 rounded border-white/20 bg-bg-2 accent-gold"
                    disabled={isLoading}
                  />
                  <span className="text-sm text-ink-2">Lembrar-me</span>
                </label>
                <Link
                  to="/forgotpassword"
                  className="text-sm text-gold hover:text-gold/80 font-medium transition-colors"
                >
                  Esqueci minha senha
                </Link>
              </div>

              {/* Botão principal */}
              <button
                type="button"
                onClick={() => void handleLogin()}
                disabled={isLoading}
                className="w-full bg-gold text-gold-deep py-3 rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 rounded-full border-2 border-gold-deep/30 border-t-gold-deep animate-spin" />
                    Entrando...
                  </span>
                ) : (
                  "Entrar"
                )}
              </button>

              {/* Divider */}
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-white/10" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="px-3 bg-bg-1 text-ink-3">ou</span>
                </div>
              </div>

              {/* Google */}
              <button
                type="button"
                onClick={handleGoogleLogin}
                disabled={isLoading}
                className="w-full flex items-center justify-center gap-3 bg-bg-2 border border-white/10 text-ink-1 py-3 rounded-xl text-sm font-medium hover:bg-bg-3 hover:border-white/15 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  />
                </svg>
                Continuar com Google
              </button>

              {/* Cadastro */}
              <p className="text-center text-sm text-ink-2 pt-1">
                Não tem uma conta?{" "}
                <Link
                  to="/register"
                  className="text-gold hover:text-gold/80 font-semibold transition-colors"
                >
                  Cadastre-se agora
                </Link>
              </p>
            </div>
          </div>

          {/* Footer (mobile) */}
          <div className="mt-6 text-center text-ink-3 text-xs space-y-1 lg:hidden">
            <p>© 2026 megdev. Todos os direitos reservados.</p>
            <div className="flex justify-center gap-4">
              <Link to="/politica-de-cookies" className="hover:text-ink-2 transition-colors">
                Termos de Uso
              </Link>
              <span>•</span>
              <Link to="/politica-de-cookies" className="hover:text-ink-2 transition-colors">
                Política de Privacidade
              </Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
