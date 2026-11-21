import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Eye,
  EyeOff,
  Mail,
  Lock,
  User,
  CreditCard,
  AlertCircle,
  CheckCircle2,
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
import { toISODate } from "@/utils/formatters";

// Local fallback while the shared `getAxiosErrorMessage` helper
// is not centralized. Mirrors the pattern used in Login/index.tsx.
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

  // Real-time password validation
  const passwordReqs = validatePasswordRequirements(formData.password1);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;

    if (name === "cpf") {
      const formatted = formatCPF(value);
      setFormData((prev) => ({ ...prev, [name]: formatted }));
    } else {
      setFormData((prev) => ({ ...prev, [name]: value }));
    }

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

  const handleRegister = async () => {
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
      await authService.register({
        email: formData.email,
        password1: formData.password1,
        password2: formData.password2,
        full_name: formData.fullName,
        cpf: formData.cpf.replace(/[^\d]/g, ""),
        birthday: toISODate(formData.birthday),
        picture: formData.picture || "",
      });

      navigate("/email-sent", {
        state: {
          email: formData.email,
        },
      });
    } catch (err: unknown) {
      setErrors({
        submit: getAxiosErrorMessage(err, "Erro ao realizar cadastro"),
      });
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

  // Helper: input className with dark V1 tokens and validation states
  const inputClass = (hasError: boolean, hasSuccess = false) => {
    const base =
      "w-full pl-10 pr-4 py-2.5 bg-bg-2 rounded-xl text-ink-1 placeholder:text-ink-3 text-sm focus:ring-2 focus:outline-none transition-colors disabled:opacity-50";
    if (hasError) {
      return `${base} border border-red-500/50 focus:border-red-500 focus:ring-red-500/20`;
    }
    if (hasSuccess) {
      return `${base} border border-green-500/50 focus:border-green-500 focus:ring-green-500/20`;
    }
    return `${base} border border-white/10 focus:border-gold/50 focus:ring-gold/20`;
  };

  return (
    <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4 py-8 relative">
      {/* AuthLogo is hidden on lg+ by its own lg:hidden class (shared across auth pages). */}
      <AuthLogo />

      {/* Card */}
      <div className="w-full max-w-xl my-10 md:my-12">
        <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
          {/* Header */}
          <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
            <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <User size={28} className="text-gold" aria-hidden="true" />
            </div>
            <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-1">
              Criar Conta
            </h1>
            <p className="text-ink-2 text-sm">
              Preencha seus dados para começar
            </p>
          </div>

          {/* Body */}
          <div className="p-6 md:p-8 space-y-5">
            {/* Submit error */}
            {errors.submit && (
              <div
                role="alert"
                className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-3"
              >
                <AlertCircle
                  className="text-red-400 shrink-0 mt-0.5"
                  size={18}
                  aria-hidden="true"
                />
                <p className="text-sm text-red-400">{errors.submit}</p>
              </div>
            )}

            {/* Nome Completo */}
            <div>
              <label
                htmlFor="reg-fullName"
                className="block text-sm font-semibold text-ink-1 mb-2"
              >
                Nome Completo
              </label>
              <div className="relative">
                <User
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
                  size={18}
                  aria-hidden="true"
                />
                <input
                  id="reg-fullName"
                  type="text"
                  name="fullName"
                  value={formData.fullName}
                  onChange={handleChange}
                  onBlur={() => handleBlur("fullName")}
                  placeholder="João Silva"
                  className={inputClass(
                    !!(touched.fullName && errors.fullName),
                  )}
                  disabled={isLoading}
                />
              </div>
              {touched.fullName && errors.fullName && (
                <p className="mt-1.5 text-xs text-red-400">{errors.fullName}</p>
              )}
            </div>

            {/* CPF + Data de Nascimento */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* CPF */}
              <div>
                <label
                  htmlFor="reg-cpf"
                  className="block text-sm font-semibold text-ink-1 mb-2"
                >
                  CPF
                </label>
                <div className="relative">
                  <CreditCard
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
                    size={18}
                    aria-hidden="true"
                  />
                  <input
                    id="reg-cpf"
                    type="text"
                    name="cpf"
                    value={formData.cpf}
                    onChange={handleChange}
                    onBlur={() => handleBlur("cpf")}
                    placeholder="000.000.000-00"
                    maxLength={14}
                    className={inputClass(
                      !!(touched.cpf && errors.cpf),
                      !!(
                        touched.cpf &&
                        !errors.cpf &&
                        validateCPF(formData.cpf)
                      ),
                    )}
                    disabled={isLoading}
                  />
                </div>
                {touched.cpf && errors.cpf && (
                  <p className="mt-1.5 text-xs text-red-400">{errors.cpf}</p>
                )}
              </div>

              {/* Data de Nascimento */}
              <div>
                <label
                  htmlFor="reg-birthday"
                  className="block text-sm font-semibold text-ink-1 mb-2"
                >
                  Data de Nascimento
                </label>
                <div className="relative">
                  <Calendar
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
                    size={18}
                    aria-hidden="true"
                  />
                  <input
                    id="reg-birthday"
                    type="text"
                    name="birthday"
                    inputMode="numeric"
                    maxLength={10}
                    placeholder="DD/MM/AAAA"
                    value={formData.birthday}
                    onChange={(e) => {
                      const numbers = e.target.value.replace(/\D/g, "");

                      let formatted = numbers;

                      if (numbers.length > 2 && numbers.length <= 4) {
                        formatted = `${numbers.slice(0, 2)}/${numbers.slice(2)}`;
                      } else if (numbers.length > 4) {
                        formatted = `${numbers.slice(0, 2)}/${numbers.slice(2, 4)}/${numbers.slice(4, 8)}`;
                      }

                      handleChange({
                        ...e,
                        target: {
                          ...e.target,
                          name: "birthday",
                          value: formatted,
                        },
                      });
                    }}
                    onBlur={() => handleBlur("birthday")}
                    className={inputClass(
                      !!(touched.birthday && errors.birthday),
                    )}
                    disabled={isLoading}
                  />
                </div>
                {touched.birthday && errors.birthday && (
                  <p className="mt-1.5 text-xs text-red-400">
                    {errors.birthday}
                  </p>
                )}
              </div>
            </div>

            {/* Email */}
            <div>
              <label
                htmlFor="reg-email"
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
                  id="reg-email"
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  onBlur={() => handleBlur("email")}
                  placeholder="seu@email.com"
                  className={inputClass(!!(touched.email && errors.email))}
                  disabled={isLoading}
                />
              </div>
              {touched.email && errors.email && (
                <p className="mt-1.5 text-xs text-red-400">{errors.email}</p>
              )}
            </div>

            {/* Senha */}
            <div>
              <label
                htmlFor="reg-password1"
                className="block text-sm font-semibold text-ink-1 mb-2"
              >
                Senha
              </label>
              <div className="relative">
                <Lock
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
                  size={18}
                  aria-hidden="true"
                />
                <input
                  id="reg-password1"
                  type={showPassword ? "text" : "password"}
                  name="password1"
                  value={formData.password1}
                  onChange={handleChange}
                  onBlur={() => handleBlur("password1")}
                  placeholder="••••••••"
                  className={`${inputClass(
                    !!(touched.password1 && errors.password1),
                  )} pr-12`}
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

              {/* Requisitos da Senha */}
              {formData.password1 && (
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

            {/* Confirmar Senha */}
            <div>
              <label
                htmlFor="reg-password2"
                className="block text-sm font-semibold text-ink-1 mb-2"
              >
                Confirmar Senha
              </label>
              <div className="relative">
                <Lock
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none"
                  size={18}
                  aria-hidden="true"
                />
                <input
                  id="reg-password2"
                  type={showConfirmPassword ? "text" : "password"}
                  name="password2"
                  value={formData.password2}
                  onChange={handleChange}
                  onBlur={() => handleBlur("password2")}
                  placeholder="••••••••"
                  className={`${inputClass(
                    !!(touched.password2 && errors.password2),
                    !!(
                      touched.password2 &&
                      !errors.password2 &&
                      formData.password1 === formData.password2 &&
                      formData.password2
                    ),
                  )} pr-12`}
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
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
              {touched.password2 && errors.password2 && (
                <p className="mt-1.5 text-xs text-red-400">
                  {errors.password2}
                </p>
              )}
              {touched.password2 &&
                !errors.password2 &&
                formData.password1 === formData.password2 &&
                formData.password2 && (
                  <p className="mt-1.5 text-xs text-green-400 flex items-center gap-1">
                    <CheckCircle2 size={14} aria-hidden="true" />
                    Senhas coincidem
                  </p>
                )}
            </div>

            {/* Botão de Cadastro */}
            <button
              type="button"
              onClick={() => void handleRegister()}
              disabled={isLoading}
              className="w-full bg-gold text-gold-deep py-3 rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 rounded-full border-2 border-gold-deep/30 border-t-gold-deep animate-spin" />
                  Cadastrando...
                </span>
              ) : (
                "Criar Conta"
              )}
            </button>

            {/* Link para Login */}
            <p className="text-center text-sm text-ink-2 pt-1">
              Já tem uma conta?{" "}
              <Link
                to="/login"
                className="text-gold hover:text-gold/80 font-semibold transition-colors"
              >
                Faça login
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
