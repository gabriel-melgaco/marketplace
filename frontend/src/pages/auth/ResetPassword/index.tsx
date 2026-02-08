import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { AuthLogo } from "@/components/ui/AuthLogo";
import { Lock, Eye, EyeOff, AlertCircle, CheckCircle } from "lucide-react";
import { authService } from "@/services/authService";

export default function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const uid = searchParams.get("uid");
  const token = searchParams.get("token");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleResetPassword = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (!uid || !token) {
      setError("Link inválido ou expirado.");
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

      setSuccess("Senha redefinida com sucesso! Redirecionando...");
      setTimeout(() => navigate("/login"), 2500);
    } catch (err: any) {
      setError(err.message || "Erro ao redefinir senha.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
      <AuthLogo />

      <div className="w-full max-w-md lg:max-w-2xl mt-24 mb-8 md:my-18">
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="bg-linear-to-r from-blue-900 to-gray-900 p-8 text-white text-center">
            <div className="w-20 h-20 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
              <Lock size={40} />
            </div>
            <h1 className="text-3xl font-bold mb-2">Redefinir senha</h1>
            <p className="text-blue-100">Crie uma nova senha para sua conta</p>
          </div>

          {/* Form */}
          <form onSubmit={handleResetPassword} className="p-8">
            {/* Error */}
            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
                <AlertCircle className="text-red-600 mt-0.5" size={20} />
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}

            {/* Success */}
            {success && (
              <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg flex items-start gap-3">
                <CheckCircle className="text-green-600 mt-0.5" size={20} />
                <p className="text-sm text-green-800">{success}</p>
              </div>
            )}

            {/* Nova senha */}
            <div className="mb-6">
              <label className="block text-gray-700 font-semibold mb-2">
                Nova senha
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
                  className="absolute right-3 top-3.5 text-gray-400 hover:text-gray-600"
                >
                  {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
            </div>

            {/* Confirmar senha */}
            <div className="mb-6">
              <label className="block text-gray-700 font-semibold mb-2">
                Confirmar nova senha
              </label>
              <div className="relative">
                <Lock
                  className="absolute left-3 top-3.5 text-gray-400"
                  size={20}
                />
                <input
                  type={showPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-11 pr-4 py-3 border-2 border-gray-300 rounded-lg focus:border-blue-500 focus:outline-none transition"
                  required
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-linear-to-r from-gray-800 to-blue-900 text-white py-3 rounded-lg font-bold hover:from-blue-700 hover:to-blue-600 transition shadow-lg disabled:opacity-50"
            >
              {isLoading ? "Redefinindo..." : "Redefinir senha"}
            </button>

            {/* Voltar */}
            <div className="mt-6 text-center">
              <Link
                to="/login"
                className="text-blue-800 hover:text-blue-700 font-semibold"
              >
                Voltar para o login
              </Link>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
