import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { AlertCircle } from "lucide-react";
import { socialAuthService } from "@/services/socialAuthService";
import { useAuth } from "@/contexts/AuthContext";

const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  access_denied: "Você cancelou a autorização do Google.",
  invalid_request: "Requisição OAuth inválida.",
  unauthorized_client: "Cliente não autorizado.",
  server_error: "Erro no servidor do Google. Tente novamente.",
};

export function GoogleCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const oauthError = searchParams.get("error");
    const errorDescription = searchParams.get("error_description");

    if (oauthError) {
      setError(
        OAUTH_ERROR_MESSAGES[oauthError] ||
          errorDescription ||
          "Erro na autenticação com Google.",
      );
      return;
    }

    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const storedState = sessionStorage.getItem("oauth_state");

    // State validation: reject when states mismatch OR when we expected a state
    // (storedState exists) but Google did not return one, or vice-versa.
    // This guards against CSRF and against a callback arriving in a different
    // browser session where sessionStorage was already cleared.
    const stateMismatch =
      state !== storedState ||
      (storedState !== null && state === null) ||
      (storedState === null && state !== null);
    if (stateMismatch) {
      setError("Falha na validação de segurança. Tente novamente.");
      sessionStorage.removeItem("oauth_state");
      return;
    }

    sessionStorage.removeItem("oauth_state");

    if (!code) {
      setError("Código de autenticação não encontrado.");
      return;
    }

    let cancelled = false;

    async function handleGoogleLogin(authCode: string) {
      try {
        const response = await socialAuthService.googleLogin({ code: authCode });
        if (!cancelled) {
          setUser(response.user);
          navigate("/", { replace: true });
        }
      } catch (err: any) {
        console.error("Erro no login com Google:", err);
        if (!cancelled) {
          setError(
            err.response?.data?.detail ||
              err.message ||
              "Erro ao autenticar com Google. Tente novamente.",
          );
        }
      }
    }

    handleGoogleLogin(code);
    return () => {
      cancelled = true;
    };
  }, [searchParams, navigate, setUser]);

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-8 text-center">
          <AlertCircle size={48} className="mx-auto mb-4 text-red-500" />
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Erro na autenticação
          </h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <button
            onClick={() => navigate("/login", { replace: true })}
            className="px-6 py-2.5 bg-blue-900 text-white rounded-lg font-semibold hover:bg-blue-800 transition cursor-pointer"
          >
            Voltar para o login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4" />
        <p className="text-white text-lg">Autenticando com Google...</p>
      </div>
    </div>
  );
}
