import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { authService } from "@/services/authService";
import { AuthLogo } from "@/components/ui/AuthLogo";
import type { ResendEmailRequest } from "@/types/auth";
import { Mail, CheckCircle, ArrowLeft, Check } from "lucide-react";

export default function EmailSent() {
  const navigate = useNavigate();
  const location = useLocation();

  const [isResending, setIsResending] = useState(false);

  // Pega o email do state (se vier do cadastro)
  const email = location.state?.email || "seu e-mail";

  async function handleResendVerificationEmail(data: ResendEmailRequest) {
    const response = await authService.resendVerificationEmail(data);
    console.log(response);
    setIsResending(true);
  }

  return (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-700 to-blue-900 flex items-center justify-center p-4">
      <AuthLogo />

      {/* Card Principal */}
      <div className="w-full max-w-md lg:max-w-2xl my-12 md:my-8">
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
          {/* Header com Ícone */}
          <div className="bg-linear-to-r from-blue-900 to-black p-8 md:p-10 text-white text-center">
            {/* Ícone de Email com Animação */}
            <div className="w-20 h-20 md:w-24 md:h-24 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm animate-pulse">
              <Mail size={48} className="md:w-14 md:h-14" />
            </div>

            <h1 className="text-2xl md:text-3xl font-bold mb-2">
              Verifique seu E-mail! 📧
            </h1>
            <p className="text-sm md:text-base text-blue-100">
              Estamos quase lá!
            </p>
          </div>

          {/* Conteúdo */}
          <div className="p-6 md:p-8 space-y-6">
            {/* Mensagem Principal */}
            <div className="text-center space-y-3">
              <div className="flex justify-center">
                <CheckCircle className="text-green-500" size={48} />
              </div>

              <p className="text-gray-700 text-sm md:text-base leading-relaxed">
                Enviamos um link de confirmação para:
              </p>

              <p className="text-blue-900 font-bold text-base md:text-lg break-all px-4">
                {email}
              </p>
            </div>

            {/* Instruções */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-2">
              <p className="text-sm text-gray-700 font-semibold">
                📌 Próximos passos:
              </p>
              <ol className="text-xs md:text-sm text-gray-600 space-y-2 list-decimal list-inside">
                <li>Abra seu e-mail</li>
                <li>Procure por "Confirmação de Cadastro"</li>
                <li>Clique no link de verificação</li>
                <li>Faça login no Marketplace!</li>
              </ol>
            </div>

            {/* Dica */}
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <p className="text-xs md:text-sm text-yellow-800">
                <strong>💡 Dica:</strong> Não encontrou? Verifique sua caixa de
                spam ou lixo eletrônico.
              </p>
            </div>

            {/* Botões de Ação */}
            <div className="space-y-3">
              {/* Botão Voltar para Login */}
              <button
                onClick={() => navigate("/login")}
                className="w-full flex items-center justify-center gap-2 bg-blue-800 text-white hover:bg-white hover:text-blue-800 py-3 rounded-lg font-semibold border-2 border-blue-90 transition cursor-pointer"
              >
                <ArrowLeft size={20} />
                Voltar para Login
              </button>

              {/* Botão Reenviar Email */}
              <button
                onClick={() => {
                  handleResendVerificationEmail({
                    email: email,
                  });
                }}
                className="w-full bg-white text-blue-900 hover:bg-blue-800 hover:text-white py-3 rounded-lg font-semibold border-2 border-blue-90 transition cursor-pointer"
              >
                Reenviar E-mail
              </button>

              {isResending && (
                <p className="text-blue-600 text-center text-lg mt-2">
                  E-mail reenviado com sucesso!{" "}
                  <Check
                    size={30}
                    className="inline-block ml-1 text-green-500 text-bold"
                  />
                </p>
              )}
            </div>

            {/* Link de Ajuda */}
            <div className="text-center pt-4 border-t border-gray-200">
              <p className="text-xs md:text-sm text-gray-600">
                Problemas com a verificação?{" "}
                <a
                  href="/help"
                  className="text-blue-900 hover:text-blue-700 font-bold underline cursor-pointer"
                >
                  Fale conosco
                </a>
              </p>
            </div>
          </div>
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
