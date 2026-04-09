import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { AuthLogo } from "@/components/ui/AuthLogo";
import { Eye, EyeOff, Mail, Lock, LogIn, AlertCircle } from "lucide-react";
import { startGoogleOAuth } from "@/hooks/useGoogleAuth";

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

  const handleLogin = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");

    try {
      await login({ email, password });
      navigate("/");
    } catch (err: any) {
      setError(err.message || "Erro ao efetuar login");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
      <AuthLogo />

      {/* Card de Cadastro - MARGEM CORRIGIDA */}
      <div className="w-full max-w-md lg:max-w-2xl mt-24 mb-8 md:my-8">
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
          {/* Header do Card */}
          <div className="bg-linear-to-r from-blue-900 to-gray-900 p-8 text-white text-center">
            <div className="w-20 h-20 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
              <LogIn size={40} />
            </div>
            <h1 className="text-3xl font-bold mb-2">Bem-vindo!</h1>
            <p className="text-blue-100">Entre para acessar sua conta</p>
          </div>

          {/* Formulário */}
          <form onSubmit={handleLogin} className="p-8">
            {/* Mensagem de Erro */}
            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
                <AlertCircle
                  className="text-red-600 shrink-0 mt-0.5"
                  size={20}
                />
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}

            {/* Campo de Email */}
            <div className="mb-6">
              <label className="block text-gray-700 font-semibold mb-2">
                Email
              </label>
              <div className="relative">
                <Mail
                  className="absolute left-3 top-3.5 text-gray-400"
                  size={20}
                />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="seu@email.com"
                  className="w-full pl-11 pr-4 py-3 border-2 border-gray-300 rounded-lg focus:border-blue-500 focus:outline-none transition"
                  required
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Campo de Senha */}
            <div className="mb-6">
              <label className="block text-gray-700 font-semibold mb-2">
                Senha
              </label>
              <div className="relative">
                <Lock
                  className="absolute left-3 top-3.5 text-gray-400"
                  size={20}
                />
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-11 pr-12 py-3 border-2 border-gray-300 rounded-lg focus:border-blue-500 focus:outline-none transition"
                  required
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-3.5 text-gray-400 hover:text-gray-600 transition"
                  disabled={isLoading}
                >
                  {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
            </div>

            {/* Lembrar-me e Esqueci a senha */}
            <div className="flex items-center justify-between mb-6">
              <label className="flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  disabled={isLoading}
                />
                <span className="ml-2 text-sm text-gray-600">Lembrar-me</span>
              </label>
              <Link
                to="/forgotpassword"
                className="text-sm text-blue-900 hover:text-blue-600 underline font-semibold transition-transform duration-200 hover:scale-105"
              >
                Esqueci minha senha
              </Link>
            </div>

            {/* Botão de Login */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-linear-to-r from-gray-800 to-blue-900 text-white py-3 rounded-lg font-bold hover:from-blue-700 hover:to-blue-600 transition shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none cursor-pointer"
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                  Entrando...
                </span>
              ) : (
                "Entrar"
              )}
            </button>

            {/* Divider */}
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-300"></div>
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-4 bg-white text-gray-500">ou</span>
              </div>
            </div>

            {/* Login Social */}
            <div className="space-y-3">
              <button
                type="button"
                onClick={handleGoogleLogin}
                className="w-full flex items-center justify-center gap-3 bg-white border-2 border-gray-300 text-gray-700 py-3 rounded-lg font-semibold hover:bg-gray-50 transition cursor-pointer"
                disabled={isLoading}
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24">
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
            </div>

            {/* Link para Cadastro */}
            <div className="mt-8 text-center">
              <p className="text-gray-600">
                Não tem uma conta?{" "}
                <Link
                  to="/register"
                  className="text-blue-800 hover:text-blue-700 font-bold"
                >
                  Cadastre-se agora
                </Link>
              </p>
            </div>
          </form>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-white text-sm">
          <p className="mb-2">
            © 2025 Marketplace. Todos os direitos reservados.
          </p>
          <div className="flex justify-center gap-4">
            <a href="#" className="hover:underline">
              Termos de Uso
            </a>
            <span>•</span>
            <a href="#" className="hover:underline">
              Política de Privacidade
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
