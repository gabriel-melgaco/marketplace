import React, { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Eye,
  EyeOff,
  Mail,
  Lock,
  User,
  CreditCard,
  AlertCircle,
  CheckCircle,
  X,
  Calendar,
} from "lucide-react";
import { authService } from "@/services/authService";
import { AuthLogo } from "@/components/ui/AuthLogo";
import {
  validateCPF,
  formatCPF,
  validatePasswordRequirements,
  isPasswordValid,
  validateEmail,
} from "@/utils/validators";

export function Register() {
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    fullName: "",
    cpf: "",
    birthday: "",
    email: "",
    password1: "",
    password2: "",
    picture: "",
  });

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  // Validação em tempo real da senha
  const passwordReqs = validatePasswordRequirements(formData.password1);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;

    // Formatar CPF automaticamente
    if (name === "cpf") {
      const formatted = formatCPF(value);
      setFormData((prev) => ({ ...prev, [name]: formatted }));
    } else {
      setFormData((prev) => ({ ...prev, [name]: value }));
    }

    // Limpar erro do campo
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: "" }));
    }
  };

  const handleBlur = (field: string) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    validateField(field);
  };

  const validateField = (field: string): boolean => {
    const newErrors: Record<string, string> = {};

    switch (field) {
      case "fullName":
        if (!formData.fullName.trim()) {
          newErrors.fullName = "Nome completo é obrigatório";
        } else if (formData.fullName.length < 3) {
          newErrors.fullName = "Nome deve ter pelo menos 3 caracteres";
        }
        break;

      case "cpf":
        if (!formData.cpf) {
          newErrors.cpf = "CPF é obrigatório";
        } else if (!validateCPF(formData.cpf)) {
          newErrors.cpf = "CPF inválido";
        }
        break;

      case "birthday":
        if (!formData.birthday) {
          newErrors.birthday = "Data de nascimento é obrigatória";
        }
        break;

      case "email":
        if (!formData.email) {
          newErrors.email = "Email é obrigatório";
        } else if (!validateEmail(formData.email)) {
          newErrors.email = "Email inválido";
        }
        break;

      case "password1":
        if (!formData.password1) {
          newErrors.password1 = "Senha é obrigatória";
        } else if (!isPasswordValid(formData.password1)) {
          newErrors.password1 = "A senha não atende todos os requisitos";
        }
        break;

      case "password2":
        if (!formData.password2) {
          newErrors.password2 = "Confirmação de senha é obrigatória";
        } else if (formData.password1 !== formData.password2) {
          newErrors.password2 = "As senhas não coincidem";
        }
        break;
    }

    setErrors((prev) => ({ ...prev, ...newErrors }));
    return Object.keys(newErrors).length === 0;
  };

  const validateForm = (): boolean => {
    const fields = [
      "fullName",
      "cpf",
      "birthday",
      "email",
      "password1",
      "password2",
    ];
    const validations = fields.map((field) => validateField(field));
    return validations.every((v) => v === true);
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    // Marcar todos os campos como touched
    setTouched({
      fullName: true,
      cpf: true,
      birthday: true,
      email: true,
      password1: true,
      password2: true,
    });

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);

    try {
      // Chamar API de registro
      await authService.register({
        email: formData.email,
        password1: formData.password1,
        password2: formData.password2,
        full_name: formData.fullName,
        cpf: formData.cpf.replace(/[^\d]/g, ""), // Remove formatação
        birthday: formData.birthday,
        picture: formData.picture || "",
      });

      // Redirecionar para login com mensagem de sucesso
      navigate("/email-sent", {
        state: {
          email: formData.email, // ← ADICIONAR ISSO
        },
      });
    } catch (error: any) {
      setErrors({ submit: error.message || "Erro ao realizar cadastro" });
      console.log(error);
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
      className={`flex items-center gap-2 text-xs md:text-sm ${met ? "text-green-600" : "text-gray-500"}`}
    >
      {met ? (
        <CheckCircle size={14} className="md:w-4 md:h-4" />
      ) : (
        <X size={14} className="md:w-4 md:h-4" />
      )}
      <span>{text}</span>
    </div>
  );

  return (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-900 to-blue-600 flex items-center justify-center p-4 py-8">
      <AuthLogo />
      {/* Card de Cadastro */}
      <div className="w-full max-w-md lg:max-w-2xl my-10 md:my-15">
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="bg-linear-to-r from-blue-900 to-gray-900 p-6 md:p-8 text-white text-center">
            <div className="w-16 h-16 md:w-20 md:h-20 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-3 md:mb-4 backdrop-blur-sm">
              <User size={32} className="md:w-10 md:h-10" />
            </div>
            <h1 className="text-2xl md:text-3xl font-bold mb-2">Criar Conta</h1>
            <p className="text-sm md:text-base text-blue-100">
              Preencha seus dados para começar
            </p>
          </div>

          {/* Formulário */}
          <form
            onSubmit={handleSubmit}
            className="p-6 md:p-8 space-y-4 md:space-y-6"
          >
            {/* Mensagem de Erro */}
            {errors.submit && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
                <AlertCircle
                  className="text-red-600 shrink-0 mt-0.5"
                  size={20}
                />
                <p className="text-sm text-red-800">{errors.submit}</p>
              </div>
            )}

            {/* Nome Completo */}
            <div>
              <label className="block text-gray-700 font-semibold mb-1.5 text-sm md:text-base">
                Nome Completo
              </label>
              <div className="relative">
                <User
                  className="absolute left-3 top-3.5 text-gray-400"
                  size={20}
                />
                <input
                  type="text"
                  name="fullName"
                  value={formData.fullName}
                  onChange={handleChange}
                  onBlur={() => handleBlur("fullName")}
                  placeholder="João Silva"
                  className={`w-full pl-11 pr-4 py-2.5 border-2 rounded-lg focus:outline-none transition text-sm md:text-base ${
                    touched.fullName && errors.fullName
                      ? "border-red-500 focus:border-red-500"
                      : "border-gray-300 focus:border-blue-500"
                  }`}
                  disabled={isLoading}
                />
              </div>
              {touched.fullName && errors.fullName && (
                <p className="mt-1 text-sm text-red-600">{errors.fullName}</p>
              )}
            </div>

            {/* CPF e Data de Nascimento */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4">
              {/* CPF */}
              <div>
                <label className="block text-gray-700 font-semibold mb-1.5 text-sm md:text-base">
                  CPF
                </label>
                <div className="relative">
                  <CreditCard
                    className="absolute left-3 top-3.5 text-gray-400"
                    size={20}
                  />
                  <input
                    type="text"
                    name="cpf"
                    value={formData.cpf}
                    onChange={handleChange}
                    onBlur={() => handleBlur("cpf")}
                    placeholder="000.000.000-00"
                    maxLength={14}
                    className={`w-full pl-11 pr-4 py-2.5 border-2 rounded-lg focus:outline-none transition text-sm md:text-base ${
                      touched.cpf && errors.cpf
                        ? "border-red-500 focus:border-red-500"
                        : touched.cpf && validateCPF(formData.cpf)
                          ? "border-green-500 focus:border-green-500"
                          : "border-gray-300 focus:border-blue-500"
                    }`}
                    disabled={isLoading}
                  />
                </div>
                {touched.cpf && errors.cpf && (
                  <p className="mt-1 text-sm text-red-600">{errors.cpf}</p>
                )}
              </div>

              {/* Data de Nascimento */}
              <div>
                <label className="block text-gray-700 font-semibold mb-1.5 text-sm md:text-base">
                  Data de Nascimento
                </label>
                <div className="relative">
                  <Calendar
                    className="absolute left-3 top-3.5 text-gray-400"
                    size={20}
                  />
                  <input
                    type="date"
                    name="birthday"
                    value={formData.birthday}
                    onChange={handleChange}
                    onBlur={() => handleBlur("birthday")}
                    className={`w-full pl-11 pr-4 py-2.5 border-2 rounded-lg focus:outline-none transition text-sm md:text-base ${
                      touched.birthday && errors.birthday
                        ? "border-red-500 focus:border-red-500"
                        : "border-gray-300 focus:border-blue-500"
                    }`}
                    disabled={isLoading}
                  />
                </div>
                {touched.birthday && errors.birthday && (
                  <p className="mt-1 text-sm text-red-600">{errors.birthday}</p>
                )}
              </div>
            </div>

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
                  value={formData.email}
                  onChange={handleChange}
                  onBlur={() => handleBlur("email")}
                  placeholder="seu@email.com"
                  className={`w-full pl-11 pr-4 py-2.5 border-2 rounded-lg focus:outline-none transition text-sm md:text-base ${
                    touched.email && errors.email
                      ? "border-red-500 focus:border-red-500"
                      : "border-gray-300 focus:border-blue-500"
                  }`}
                  disabled={isLoading}
                />
              </div>
              {touched.email && errors.email && (
                <p className="mt-1 text-sm text-red-600">{errors.email}</p>
              )}
            </div>

            {/* Senha */}
            <div>
              <label className="block text-gray-700 font-semibold mb-1.5 text-sm md:text-base">
                Senha
              </label>
              <div className="relative">
                <Lock
                  className="absolute left-3 top-3.5 text-gray-400"
                  size={20}
                />
                <input
                  type={showPassword ? "text" : "password"}
                  name="password1"
                  value={formData.password1}
                  onChange={handleChange}
                  onBlur={() => handleBlur("password1")}
                  placeholder="••••••••"
                  className={`w-full pl-11 pr-12 py-2.5 border-2 rounded-lg focus:outline-none transition text-sm md:text-base ${
                    touched.password1 && errors.password1
                      ? "border-red-500 focus:border-red-500"
                      : "border-gray-300 focus:border-blue-500"
                  }`}
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

              {/* Requisitos da Senha */}
              {formData.password1 && (
                <div className="mt-2 p-3 bg-gray-50 rounded-lg space-y-1.5">
                  <p className="text-xs md:text-sm font-semibold text-gray-700 mb-1.5">
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

            {/* Confirmar Senha */}
            <div>
              <label className="block text-gray-700 font-semibold mb-1.5 text-sm md:text-base">
                Confirmar Senha
              </label>
              <div className="relative">
                <Lock
                  className="absolute left-3 top-3.5 text-gray-400"
                  size={20}
                />
                <input
                  type={showConfirmPassword ? "text" : "password"}
                  name="password2"
                  value={formData.password2}
                  onChange={handleChange}
                  onBlur={() => handleBlur("password2")}
                  placeholder="••••••••"
                  className={`w-full pl-11 pr-12 py-2.5 border-2 rounded-lg focus:outline-none transition text-sm md:text-base ${
                    touched.password2 && errors.password2
                      ? "border-red-500 focus:border-red-500"
                      : touched.password2 &&
                          formData.password1 === formData.password2 &&
                          formData.password2
                        ? "border-green-500 focus:border-green-500"
                        : "border-gray-300 focus:border-blue-500"
                  }`}
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-3.5 text-gray-400 hover:text-gray-600 transition"
                  disabled={isLoading}
                >
                  {showConfirmPassword ? (
                    <EyeOff size={20} />
                  ) : (
                    <Eye size={20} />
                  )}
                </button>
              </div>
              {touched.password2 && errors.password2 && (
                <p className="mt-1 text-sm text-red-600">{errors.password2}</p>
              )}
              {touched.password2 &&
                !errors.password2 &&
                formData.password1 === formData.password2 &&
                formData.password2 && (
                  <p className="mt-1 text-sm text-green-600">
                    Senhas coincidem ✓
                  </p>
                )}
            </div>

            {/* Botão de Cadastro */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-linear-to-r from-blue-900 to-blue-700 text-white py-2.5 md:py-3 rounded-lg font-bold hover:from-blue-600 hover:to-blue-500 transition shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none text-sm md:text-base cursor-pointer"
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                  Cadastrando...
                </span>
              ) : (
                "Criar Conta"
              )}
            </button>

            {/* Link para Login */}
            <div className="mt-4 md:mt-6 text-center">
              <p className="text-sm md:text-base text-gray-600">
                Já tem uma conta?{" "}
                <a
                  href="/login"
                  className="text-blue-900 hover:text-blue-700 font-bold"
                >
                  Faça login
                </a>
              </p>
            </div>
          </form>
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
