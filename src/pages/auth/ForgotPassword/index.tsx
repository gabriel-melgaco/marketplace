import { useState, type FormEvent } from "react";
import { RectangleEllipsis, Mail } from "lucide-react";
import { authService } from "@/services/authService";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sendLinkSuccess, setSendLinkSuccess] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    try {
      await authService.requestPasswordReset({ email });
    } catch (error: any) {
      console.log(error.message);
    } finally {
      setSendLinkSuccess(true);
    }
  }

  return (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-900 to-blue-600 flex items-center justify-center p-4 py-8">
      {/* Logo */}
      <div className="absolute top-4 left-4 md:top-8 md:left-8 flex items-center gap-2 text-white">
        <div className="w-8 h-8 md:w-10 md:h-10 bg-secundary rounded-full flex items-center justify-center">
          <span className="text-xs md:text-sm font-bold">CS</span>
        </div>
        <span className="font-bold text-lg md:text-2xl">MARKETPLACE</span>
      </div>

      {/* Card de Recuperação de Senha */}
      <div className="w-full max-w-md lg:max-w-2xl -mt-20 md:mt-15">
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="bg-linear-to-r from-blue-900 to-gray-900 p-6 md:p-8 text-white text-center">
            <div className="w-16 h-16 md:w-20 md:h-20 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-3 md:mb-4 backdrop-blur-sm">
              <RectangleEllipsis size={32} className="md:w-10 md:h-10" />
            </div>
            <h1 className="text-2xl md:text-3xl font-bold mb-2">
              Esqueceu sua senha?
            </h1>
            <p className="text-sm md:text-base text-blue-100">
              Para redefinir sua senhra, informe o e-mail cadastrado na sua
              conta que nós enviaremos um link de alteração de senha.
            </p>
          </div>

          {/* Formulário */}
          <form
            onSubmit={handleSubmit}
            className="p-6 md:p-8 space-y-4 md:space-y-6"
          >
            {/* Email */}
            <div>
              <label className="block text-gray-700 font-semibold mb-1.5 text-sm md:text-base">
                Email
              </label>
              <div className="relative">
                <Mail
                  className="absolute left-3 top-3.5 text-gray-400"
                  size={20}
                />
                <input
                  type="email"
                  name="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="seu@email.com"
                  className={
                    "w-full pl-11 pr-4 py-2.5 border-2 rounded-lg focus:outline-none transition text-sm md:text-base"
                  }
                />
              </div>
            </div>

            {/* Botão de Cadastro */}
            <button
              type="submit"
              className="w-full bg-linear-to-r from-blue-900 to-blue-700 text-white py-2.5 md:py-3 rounded-lg font-bold hover:from-blue-600 hover:to-blue-500 transition shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none text-sm md:text-base cursor-pointer"
            >
              Enviar Link
            </button>
          </form>

          {/* Mensagem de Sucesso */}
          <div>
            {sendLinkSuccess && (
              <div
                className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded-b mb-4 mx-6 md:mx-8"
                role="alert"
              >
                <strong className="font-bold">Sucesso!</strong>
                <span className="block sm:inline">
                  {" "}
                  Se o e-mail informado estiver cadastrado, você receberá um
                  link para redefinir sua senha.
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="mt-4 md:mt-8 text-center text-white text-xs md:text-sm">
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
