import { useState, type FormEvent } from "react";
import { CreditCard, Calendar, AlertCircle } from "lucide-react";
import { validateCPF, formatCPF } from "@/utils/validators";
import { toISODate } from "@/utils/formatters";
import { userService } from "@/services/userService";
import { tokenStorage } from "@/utils/tokenStorage";
import type { User } from "@/types/auth";

interface CompleteProfileModalProps {
  user: User;
  onComplete: (updatedUser: User) => void;
}

export function CompleteProfileModal({
  user,
  onComplete,
}: CompleteProfileModalProps) {
  const [cpf, setCpf] = useState("");
  const [birthday, setBirthday] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(false);

  const handleCpfChange = (value: string) => {
    setCpf(formatCPF(value));
    if (errors.cpf) setErrors((prev) => ({ ...prev, cpf: "" }));
  };

  const handleBirthdayChange = (value: string) => {
    const numbers = value.replace(/\D/g, "");
    let formatted = numbers;
    if (numbers.length > 2 && numbers.length <= 4) {
      formatted = `${numbers.slice(0, 2)}/${numbers.slice(2)}`;
    } else if (numbers.length > 4) {
      formatted = `${numbers.slice(0, 2)}/${numbers.slice(2, 4)}/${numbers.slice(4, 8)}`;
    }
    setBirthday(formatted);
    if (errors.birthday) setErrors((prev) => ({ ...prev, birthday: "" }));
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!cpf) {
      newErrors.cpf = "CPF é obrigatório";
    } else if (!validateCPF(cpf)) {
      newErrors.cpf = "CPF inválido";
    }

    if (!birthday) {
      newErrors.birthday = "Data de nascimento é obrigatória";
    } else if (birthday.length !== 10) {
      newErrors.birthday = "Data incompleta";
    } else {
      const [day, month, year] = birthday.split("/").map(Number);
      const date = new Date(year, month - 1, day);
      if (
        date.getDate() !== day ||
        date.getMonth() !== month - 1 ||
        date.getFullYear() !== year
      ) {
        newErrors.birthday = "Data inválida";
      } else if (date > new Date()) {
        newErrors.birthday = "Data não pode ser no futuro";
      } else {
        const age = Math.floor(
          (Date.now() - date.getTime()) / (365.25 * 24 * 60 * 60 * 1000),
        );
        if (age < 18) {
          newErrors.birthday = "Você deve ter pelo menos 18 anos";
        }
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched({ cpf: true, birthday: true });

    if (!validate()) return;

    setIsLoading(true);
    try {
      const updatedUser = await userService.updateCurrentUser({
        cpf: cpf.replace(/[^\d]/g, ""),
        birthday: toISODate(birthday),
      });

      const newUser: User = {
        ...user,
        cpf: updatedUser.cpf,
        birthday: updatedUser.birthday,
      };
      tokenStorage.saveUser(newUser);
      onComplete(newUser);
    } catch (error: any) {
      const data = error?.response?.data;
      let message = "Erro ao salvar dados. Tente novamente.";

      if (data && typeof data === "object") {
        const fieldErrors: string[] = [];
        for (const [field, value] of Object.entries(data)) {
          const msgs = Array.isArray(value) ? value : [String(value)];
          if (field === "non_field_errors" || field === "detail") {
            fieldErrors.unshift(...msgs);
          } else {
            fieldErrors.push(...msgs);
          }
        }
        if (fieldErrors.length > 0) message = fieldErrors[0];
      } else if (typeof data === "string" && data) {
        message = data;
      }

      setErrors({ submit: message });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-9999 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="bg-linear-to-r from-blue-900 to-gray-900 p-6 text-white text-center">
          <h2 className="text-xl font-bold mb-1">Complete seu cadastro</h2>
          <p className="text-blue-200 text-sm">
            Precisamos de mais algumas informações
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {errors.submit && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
              <AlertCircle className="text-red-600 shrink-0 mt-0.5" size={18} />
              <p className="text-sm text-red-800">{errors.submit}</p>
            </div>
          )}

          {/* CPF */}
          <div>
            <label className="block text-gray-700 font-semibold mb-1.5 text-sm">
              CPF
            </label>
            <div className="relative">
              <CreditCard
                className="absolute left-3 top-3 text-gray-400"
                size={20}
              />
              <input
                type="text"
                value={cpf}
                onChange={(e) => handleCpfChange(e.target.value)}
                onBlur={() => setTouched((prev) => ({ ...prev, cpf: true }))}
                placeholder="000.000.000-00"
                maxLength={14}
                className={`w-full pl-11 pr-4 py-2.5 border-2 rounded-lg focus:outline-none transition text-sm ${
                  touched.cpf && errors.cpf
                    ? "border-red-500 focus:border-red-500"
                    : touched.cpf && validateCPF(cpf)
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
            <label className="block text-gray-700 font-semibold mb-1.5 text-sm">
              Data de Nascimento
            </label>
            <div className="relative">
              <Calendar
                className="absolute left-3 top-3 text-gray-400"
                size={20}
              />
              <input
                type="text"
                inputMode="numeric"
                maxLength={10}
                placeholder="DD/MM/AAAA"
                value={birthday}
                onChange={(e) => handleBirthdayChange(e.target.value)}
                onBlur={() =>
                  setTouched((prev) => ({ ...prev, birthday: true }))
                }
                className={`w-full pl-11 pr-4 py-2.5 border-2 rounded-lg focus:outline-none transition text-sm ${
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

          {/* Submit */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-linear-to-r from-blue-900 to-blue-700 text-white py-2.5 rounded-lg font-bold hover:from-blue-600 hover:to-blue-500 transition shadow-lg disabled:opacity-50 disabled:cursor-not-allowed text-sm cursor-pointer"
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white" />
                Salvando...
              </span>
            ) : (
              "Salvar e continuar"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
