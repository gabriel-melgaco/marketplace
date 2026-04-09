// src/pages/auth/VerifyEmail/index.tsx

import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { CheckCircle, XCircle, Loader2, AlertCircle } from "lucide-react";
import { authService } from "@/services/authService";

type VerificationStatus = "loading" | "success" | "error" | "invalid";

export default function ConfirmEmail() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [status, setStatus] = useState<VerificationStatus>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [countdown, setCountdown] = useState(5);

  useEffect(() => {
    const verifyEmail = async () => {
      // Pega o token da URL (key no caso da sua API)
      const key = searchParams.get("key") || searchParams.get("token");

      // Se não tem token, mostra erro
      if (!key) {
        setStatus("invalid");
        setErrorMessage("Link de verificação inválido. Token não encontrado.");
        return;
      }

      try {
        // Chama a API de verificação
        await authService.verifyEmail({ key });

        // Sucesso!
        setStatus("success");

        // Inicia contagem regressiva para redirecionar
        let timeLeft = 5;
        const timer = setInterval(() => {
          timeLeft -= 1;
          setCountdown(timeLeft);

          if (timeLeft === 0) {
            clearInterval(timer);
            navigate("/login", {
              state: {
                message:
                  "E-mail verificado com sucesso! Faça login para continuar.",
              },
            });
          }
        }, 1000);
      } catch (error: any) {
        // Erro na verificação
        setStatus("error");
        setErrorMessage(
          error.message ||
            "Não foi possível verificar seu e-mail. O link pode estar expirado ou já foi usado.",
        );
      }
    };

    verifyEmail();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-700 to-blue-900 flex items-center justify-center p-4">
      {/* Logo */}
      <div className="absolute top-4 left-4 md:top-8 md:left-8 flex items-center gap-2 text-white">
        <div className="w-8 h-8 md:w-10 md:h-10 bg-blue-800 rounded-full flex items-center justify-center">
          <span className="text-xs md:text-sm font-bold">CS</span>
        </div>
        <span className="font-bold text-lg md:text-2xl">MARKETPLACE</span>
      </div>

      {/* Card Principal */}
      <div className="w-full max-w-md lg:max-w-2xl my-12 md:my-8">
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
          {/* STATUS: LOADING (Verificando) */}
          {status === "loading" && (
            <>
              <div className="bg-linear-to-r from-blue-600 to-blue-500 p-8 md:p-10 text-white text-center">
                <div className="w-20 h-20 md:w-24 md:h-24 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
                  <Loader2 size={48} className="animate-spin" />
                </div>
                <h1 className="text-2xl md:text-3xl font-bold mb-2">
                  Verificando E-mail...
                </h1>
                <p className="text-sm md:text-base text-blue-100">
                  Aguarde um momento
                </p>
              </div>

              <div className="p-6 md:p-8 text-center">
                <p className="text-gray-700">
                  Estamos confirmando seu e-mail. Isso pode levar alguns
                  segundos.
                </p>
                <div className="mt-6 flex justify-center">
                  <div className="animate-pulse flex space-x-2">
                    <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                    <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                    <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* STATUS: SUCCESS (Verificado com sucesso) */}
          {status === "success" && (
            <>
              <div className="bg-linear-to-r from-green-600 to-green-500 p-8 md:p-10 text-white text-center">
                <div className="w-20 h-20 md:w-24 md:h-24 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
                  <CheckCircle size={48} />
                </div>
                <h1 className="text-2xl md:text-3xl font-bold mb-2">
                  E-mail Verificado! 🎉
                </h1>
                <p className="text-sm md:text-base text-green-100">
                  Sua conta foi confirmada com sucesso
                </p>
              </div>

              <div className="p-6 md:p-8 text-center space-y-6">
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <CheckCircle
                    className="text-green-500 mx-auto mb-2"
                    size={32}
                  />
                  <p className="text-gray-700 font-semibold mb-1">
                    Tudo pronto!
                  </p>
                  <p className="text-sm text-gray-600">
                    Sua conta está ativa e você já pode fazer login.
                  </p>
                </div>

                <div className="flex flex-col items-center gap-2">
                  <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                  <p className="text-gray-600 text-sm">
                    Redirecionando em{" "}
                    <span className="font-bold text-blue-900">{countdown}</span>{" "}
                    segundos...
                  </p>
                </div>

                <button
                  onClick={() =>
                    navigate("/login", {
                      state: {
                        message:
                          "E-mail verificado com sucesso! Faça login para continuar.",
                      },
                    })
                  }
                  className="w-full bg-linear-to-r from-blue-600 to-blue-500 text-white py-3 rounded-lg font-bold hover:from-blue-700 hover:to-blue-600 transition shadow-lg hover:shadow-xl transform hover:-translate-y-0.5"
                >
                  Ir para Login Agora
                </button>
              </div>
            </>
          )}

          {/* STATUS: ERROR (Erro na verificação) */}
          {status === "error" && (
            <>
              <div className="bg-linear-to-r from-red-600 to-red-500 p-8 md:p-10 text-white text-center">
                <div className="w-20 h-20 md:w-24 md:h-24 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
                  <XCircle size={48} />
                </div>
                <h1 className="text-2xl md:text-3xl font-bold mb-2">
                  Erro na Verificação
                </h1>
                <p className="text-sm md:text-base text-red-100">
                  Não foi possível confirmar seu e-mail
                </p>
              </div>

              <div className="p-6 md:p-8 space-y-6">
                <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
                  <AlertCircle
                    className="text-red-600 shrink-0 mt-0.5"
                    size={20}
                  />
                  <div className="text-left">
                    <p className="text-sm font-semibold text-red-800 mb-1">
                      Erro ao verificar e-mail
                    </p>
                    <p className="text-xs text-red-700">{errorMessage}</p>
                  </div>
                </div>

                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-left">
                  <p className="text-sm text-gray-700 font-semibold mb-2">
                    O que fazer?
                  </p>
                  <ul className="text-xs md:text-sm text-gray-600 space-y-1 list-disc list-inside">
                    <li>Verifique se o link está completo</li>
                    <li>Certifique-se de que não foi usado antes</li>
                    <li>Solicite um novo link de verificação</li>
                    <li>
                      Entre em contato com o suporte se o problema persistir
                    </li>
                  </ul>
                </div>

                <div className="space-y-3">
                  <button
                    onClick={() => navigate("/register")}
                    className="w-full bg-linear-to-r from-blue-600 to-blue-500 text-white py-3 rounded-lg font-bold hover:from-blue-700 hover:to-blue-600 transition"
                  >
                    Fazer Novo Cadastro
                  </button>

                  <button
                    onClick={() => navigate("/login")}
                    className="w-full bg-white text-blue-900 py-3 rounded-lg font-semibold border-2 border-blue-900 hover:bg-blue-50 transition"
                  >
                    Voltar para Login
                  </button>
                </div>
              </div>
            </>
          )}

          {/* STATUS: INVALID (Link inválido) */}
          {status === "invalid" && (
            <>
              <div className="bg-linear-to-r from-orange-600 to-orange-500 p-8 md:p-10 text-white text-center">
                <div className="w-20 h-20 md:w-24 md:h-24 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
                  <AlertCircle size={48} />
                </div>
                <h1 className="text-2xl md:text-3xl font-bold mb-2">
                  Link Inválido
                </h1>
                <p className="text-sm md:text-base text-orange-100">
                  Este link de verificação não é válido
                </p>
              </div>

              <div className="p-6 md:p-8 space-y-6">
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                  <p className="text-sm text-gray-700">{errorMessage}</p>
                </div>

                <p className="text-gray-600 text-sm text-center">
                  Por favor, certifique-se de estar usando o link completo
                  enviado para seu e-mail.
                </p>

                <button
                  onClick={() => navigate("/register")}
                  className="w-full bg-linear-to-r from-blue-600 to-blue-500 text-white py-3 rounded-lg font-bold hover:from-blue-700 hover:to-blue-600 transition"
                >
                  Fazer Novo Cadastro
                </button>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="mt-6 md:mt-8 text-center text-white text-xs">
          <p className="mb-2">
            © 2025 Marketplace. Todos os direitos reservados.
          </p>
          <div className="flex justify-center gap-3 md:gap-4">
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
