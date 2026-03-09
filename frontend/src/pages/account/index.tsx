import { useState, useEffect, useRef, useCallback, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  User as UserIcon,
  MapPin,
  Shield,
  Bell,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  X,
  AlertTriangle,
  Loader2,
  Camera,
  ExternalLink,
  CheckCircle2,
  Link2,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { userService, type CustomUser } from "@/services/userService";
import { authService } from "@/services/authService";
import {
  socialAuthService,
  type SocialAccount,
} from "@/services/socialAuthService";
import {
  logisticsService,
  type AddressData,
  type CreateAddressRequest,
} from "@/services/logisticsService";
import { tokenStorage } from "@/utils/tokenStorage";
import { toISODate } from "@/utils/formatters";
import { startGoogleOAuth } from "@/hooks/useGoogleAuth";
import Swal from "sweetalert2";
import type { User } from "@/types/auth";
import { storageService, toPublicUrl } from "@/services/storageService";

// ─── Types ────────────────────────────────────────────────────────────────────

type Section = "personal" | "addresses" | "security" | "notifications";

const SECTIONS: {
  id: Section;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}[] = [
  { id: "personal", label: "Dados Pessoais", icon: UserIcon },
  { id: "addresses", label: "Endereços", icon: MapPin },
  { id: "security", label: "Segurança", icon: Shield },
  { id: "notifications", label: "Notificações", icon: Bell },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

// Notification defaults (UI only — no backend yet; toggles are purely decorative)
const NOTIFICATION_DEFAULTS = {
  newListings: false,
  messages: false,
  orders: true,
  promotions: false,
} as const;

function isoToDisplay(iso: string | undefined): string {
  if (!iso || !iso.includes("-")) return iso ?? "";
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function formatCpfDisplay(cpf: string): string {
  const clean = cpf.replace(/\D/g, "");
  if (clean.length !== 11) return cpf;
  return `${clean.slice(0, 3)}.${clean.slice(3, 6)}.${clean.slice(6, 9)}-${clean.slice(9)}`;
}

function formatPhone(value: string): string {
  const n = value.replace(/\D/g, "").slice(0, 11);
  if (n.length <= 2) return n;
  if (n.length <= 7) return `(${n.slice(0, 2)}) ${n.slice(2)}`;
  return `(${n.slice(0, 2)}) ${n.slice(2, 7)}-${n.slice(7)}`;
}

function formatZipcode(value: string): string {
  const n = value.replace(/\D/g, "").slice(0, 8);
  if (n.length <= 5) return n;
  return `${n.slice(0, 5)}-${n.slice(5)}`;
}

/** Maps a CustomUser API response to the AuthContext User shape. */
function mapToUser(updated: CustomUser, fallbackIsActive?: boolean): User {
  return {
    id: updated.id,
    email: updated.email,
    full_name: updated.full_name,
    birthday: updated.birthday ?? "",
    cpf: updated.cpf,
    picture: updated.picture ?? "",
    is_active: updated.is_active ?? fallbackIsActive ?? true,
  };
}

/** Extracts a human-readable message from an unknown catch value.
 *  Axios errors are checked first because AxiosError extends Error —
 *  checking instanceof Error first would return the generic Axios message
 *  (e.g. "Request failed with status code 422") instead of the API body.
 */
function getAxiosErrorMessage(err: unknown, fallback: string): string {
  const responseData = (err as { response?: { data?: unknown } })?.response?.data;
  if (responseData && typeof responseData === "object") {
    return (Object.values(responseData).flat() as string[]).join(" ") || fallback;
  }
  if (typeof responseData === "string" && responseData) return responseData;
  if (err instanceof Error) return err.message;
  return fallback;
}

// ─── Address Modal ────────────────────────────────────────────────────────────

interface AddressModalProps {
  onClose: () => void;
  onSaved: (address: AddressData) => void;
}

function AddressModal({ onClose, onSaved }: AddressModalProps) {
  const [form, setForm] = useState<Omit<CreateAddressRequest, "country">>({
    address_type: "Residencial",
    nickname: "",
    recipient_name: "",
    recipient_phone: "",
    zipcode: "",
    street: "",
    number: "",
    complement: "",
    neighborhood: "",
    city: "",
    state: "",
    is_default: false,
    is_shipping_address: true,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [cepLoading, setCepLoading] = useState(false);
  const [cepError, setCepError] = useState("");

  const set = (key: keyof typeof form, value: string | boolean) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const handleZipcodeBlur = async () => {
    const clean = form.zipcode.replace(/\D/g, "");
    if (clean.length !== 8) return;
    setCepLoading(true);
    setCepError("");
    try {
      const data = await logisticsService.lookupCep(clean);
      setForm((prev) => ({
        ...prev,
        street: data.street || prev.street,
        neighborhood: data.neighborhood || prev.neighborhood,
        city: data.city || prev.city,
        state: data.state || prev.state,
        complement: data.complement || prev.complement,
      }));
    } catch {
      setCepError("CEP não encontrado. Preencha os campos manualmente.");
    } finally {
      setCepLoading(false);
    }
  };

  const validate = (): boolean => {
    const e: Record<string, string> = {};
    if (!form.nickname.trim()) e.nickname = "Campo obrigatório";
    if (!form.recipient_name.trim()) e.recipient_name = "Campo obrigatório";
    if (!form.recipient_phone.trim()) e.recipient_phone = "Campo obrigatório";
    if (form.zipcode.replace(/\D/g, "").length !== 8)
      e.zipcode = "CEP inválido";
    if (!form.street.trim()) e.street = "Campo obrigatório";
    if (!form.number.trim()) e.number = "Campo obrigatório";
    if (!form.neighborhood.trim()) e.neighborhood = "Campo obrigatório";
    if (!form.city.trim()) e.city = "Campo obrigatório";
    if (!form.state.trim()) e.state = "Campo obrigatório";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setIsLoading(true);
    try {
      const saved = await logisticsService.createAddress({
        ...form,
        zipcode: form.zipcode.replace(/\D/g, ""),
        recipient_phone: form.recipient_phone.replace(/\D/g, ""),
        country: "BR",
      });
      onSaved(saved);
    } catch (err: unknown) {
      const data = (err as { response?: { data?: unknown } })?.response?.data;
      if (data && typeof data === "object") {
        // Map per-field API validation errors to inline field messages
        const msgs: Record<string, string> = {};
        for (const [k, v] of Object.entries(data as Record<string, unknown>)) {
          msgs[k] = Array.isArray(v) ? (v as string[])[0] : String(v);
        }
        setErrors(msgs);
      } else {
        setErrors({
          submit: getAxiosErrorMessage(err, "Erro ao salvar endereço. Tente novamente."),
        });
      }
    } finally {
      setIsLoading(false);
    }
  };

  const inputCls = (key?: string) =>
    `w-full px-3 py-2.5 border-2 rounded-lg text-sm focus:outline-none transition ${
      key && errors[key]
        ? "border-red-500 focus:border-red-500"
        : "border-gray-300 focus:border-blue-500"
    }`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="address-modal-title"
        className="w-full max-w-lg bg-white rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-linear-to-r from-blue-900 to-gray-900 p-5 text-white flex items-center justify-between shrink-0">
          <h2 id="address-modal-title" className="text-lg font-bold">
            Novo Endereço
          </h2>
          <button
            onClick={onClose}
            aria-label="Fechar modal"
            className="hover:text-gray-300 transition cursor-pointer"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="overflow-y-auto p-5 space-y-3">
          {errors.submit && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
              {errors.submit}
            </p>
          )}

          {/* Apelido + Tipo */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                Apelido
              </label>
              <input
                type="text"
                value={form.nickname}
                onChange={(e) => set("nickname", e.target.value)}
                placeholder="Ex: Casa, Trabalho"
                className={inputCls("nickname")}
              />
              {errors.nickname && (
                <p className="mt-1 text-xs text-red-600">{errors.nickname}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                Tipo
              </label>
              <select
                value={form.address_type}
                onChange={(e) => set("address_type", e.target.value)}
                className="w-full px-3 py-2.5 border-2 border-gray-300 rounded-lg text-sm focus:outline-none focus:border-blue-500 transition"
              >
                <option>Residencial</option>
                <option>Comercial</option>
                <option>Outro</option>
              </select>
            </div>
          </div>

          {/* Destinatário */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              Nome do destinatário
            </label>
            <input
              type="text"
              value={form.recipient_name}
              onChange={(e) => set("recipient_name", e.target.value)}
              placeholder="Nome completo"
              className={inputCls("recipient_name")}
            />
            {errors.recipient_name && (
              <p className="mt-1 text-xs text-red-600">
                {errors.recipient_name}
              </p>
            )}
          </div>

          {/* Telefone */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              Telefone
            </label>
            <input
              type="text"
              value={form.recipient_phone}
              onChange={(e) =>
                set("recipient_phone", formatPhone(e.target.value))
              }
              placeholder="(00) 00000-0000"
              maxLength={15}
              className={inputCls("recipient_phone")}
            />
            {errors.recipient_phone && (
              <p className="mt-1 text-xs text-red-600">
                {errors.recipient_phone}
              </p>
            )}
          </div>

          {/* CEP */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              CEP
            </label>
            <div className="relative">
              <input
                type="text"
                value={form.zipcode}
                onChange={(e) => set("zipcode", formatZipcode(e.target.value))}
                onBlur={handleZipcodeBlur}
                placeholder="00000-000"
                maxLength={9}
                className={inputCls("zipcode")}
              />
              {cepLoading && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600" />
                </div>
              )}
            </div>
            {cepLoading && (
              <p className="mt-1 text-xs text-gray-500">Buscando endereço...</p>
            )}
            {cepError && (
              <p className="mt-1 text-xs text-amber-600">{cepError}</p>
            )}
            {errors.zipcode && (
              <p className="mt-1 text-xs text-red-600">{errors.zipcode}</p>
            )}
          </div>

          {/* Rua */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              Rua
            </label>
            <input
              type="text"
              value={form.street}
              onChange={(e) => set("street", e.target.value)}
              readOnly={cepLoading}
              placeholder="Nome da rua"
              className={`${inputCls("street")} ${cepLoading ? "bg-gray-50" : ""}`}
            />
            {errors.street && (
              <p className="mt-1 text-xs text-red-600">{errors.street}</p>
            )}
          </div>

          {/* Número + Complemento */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                Número
              </label>
              <input
                type="text"
                value={form.number}
                onChange={(e) => set("number", e.target.value)}
                placeholder="Nº"
                className={inputCls("number")}
              />
              {errors.number && (
                <p className="mt-1 text-xs text-red-600">{errors.number}</p>
              )}
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                Complemento
              </label>
              <input
                type="text"
                value={form.complement}
                onChange={(e) => set("complement", e.target.value)}
                placeholder="Apto, bloco... (opcional)"
                className={inputCls()}
              />
            </div>
          </div>

          {/* Bairro */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              Bairro
            </label>
            <input
              type="text"
              value={form.neighborhood}
              onChange={(e) => set("neighborhood", e.target.value)}
              readOnly={cepLoading}
              className={`${inputCls("neighborhood")} ${cepLoading ? "bg-gray-50" : ""}`}
            />
            {errors.neighborhood && (
              <p className="mt-1 text-xs text-red-600">{errors.neighborhood}</p>
            )}
          </div>

          {/* Cidade + Estado */}
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                Cidade
              </label>
              <input
                type="text"
                value={form.city}
                onChange={(e) => set("city", e.target.value)}
                readOnly={cepLoading}
                className={`${inputCls("city")} ${cepLoading ? "bg-gray-50" : ""}`}
              />
              {errors.city && (
                <p className="mt-1 text-xs text-red-600">{errors.city}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                Estado
              </label>
              <input
                type="text"
                value={form.state}
                onChange={(e) => set("state", e.target.value.toUpperCase())}
                readOnly={cepLoading}
                maxLength={2}
                placeholder="UF"
                className={`${inputCls("state")} ${cepLoading ? "bg-gray-50" : ""}`}
              />
              {errors.state && (
                <p className="mt-1 text-xs text-red-600">{errors.state}</p>
              )}
            </div>
          </div>

          {/* Padrão */}
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => set("is_default", e.target.checked)}
              className="w-5 h-5 accent-blue-900"
            />
            <span className="text-sm text-gray-700">
              Definir como endereço padrão
            </span>
          </label>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 border-2 border-gray-300 text-gray-700 rounded-lg font-semibold text-sm hover:bg-gray-50 transition cursor-pointer"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="flex-1 py-2.5 bg-blue-900 text-white rounded-lg font-semibold text-sm hover:bg-blue-800 transition disabled:opacity-50 cursor-pointer"
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                  Salvando...
                </span>
              ) : (
                "Salvar endereço"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function AccountPage() {
  const { user, setUser, logout } = useAuth();
  const navigate = useNavigate();

  const [activeSection, setActiveSection] = useState<Section>("personal");

  // Personal data
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [birthday, setBirthday] = useState(isoToDisplay(user?.birthday));
  const [personalLoading, setPersonalLoading] = useState(false);
  const [personalSuccess, setPersonalSuccess] = useState(false);
  const [personalError, setPersonalError] = useState("");
  const [pictureUploading, setPictureUploading] = useState(false);
  const pictureInputRef = useRef<HTMLInputElement>(null);

  // Addresses
  const [addresses, setAddresses] = useState<AddressData[]>([]);
  const [addressesLoading, setAddressesLoading] = useState(false);
  const [showAddressModal, setShowAddressModal] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  // Melhor Envio connection
  const [meConnected, setMeConnected] = useState(false);
  const [meCheckLoading, setMeCheckLoading] = useState(false);
  const [meConnectUrl, setMeConnectUrl] = useState<string | null>(null);
  const [mePolling, setMePolling] = useState(false);
  const mePopupRef = useRef<Window | null>(null);
  const mePollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Security — password
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);
  const [showConfirmPw, setShowConfirmPw] = useState(false);
  const [pwLoading, setPwLoading] = useState(false);
  const [pwSuccess, setPwSuccess] = useState(false);
  const [pwError, setPwError] = useState("");

  // Security — Google
  const [socialAccounts, setSocialAccounts] = useState<SocialAccount[]>([]);
  const [socialLoading, setSocialLoading] = useState(false);

  // Notifications state is intentionally omitted — toggles are UI-only decorators.

  const loadAddresses = useCallback(async () => {
    setAddressesLoading(true);
    try {
      const data = await logisticsService.getAddresses();
      setAddresses(data);
    } catch {
      Swal.fire({
        icon: "error",
        title: "Erro",
        text: "Não foi possível carregar os endereços. Tente novamente.",
        confirmButtonColor: "#1e3a5f",
      });
    } finally {
      setAddressesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeSection !== "addresses") return;

    let cancelled = false;
    loadAddresses();

    setMeCheckLoading(true);
    logisticsService
      .getMelhorEnvioStatus()
      .then((status) => {
        if (cancelled) return;
        if (status.connected && !status.is_expired) {
          setMeConnected(true);
        } else {
          setMeConnected(false);
          return logisticsService.getMelhorEnvioConnectUrl().then((data) => {
            if (!cancelled) setMeConnectUrl(data.authorization_url);
          });
        }
      })
      .catch(() => {
        // Non-fatal: button simply won't appear if URL fetch fails
      })
      .finally(() => {
        if (!cancelled) setMeCheckLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeSection, loadAddresses]);

  // Cleanup ME popup and polling on unmount
  useEffect(() => {
    return () => {
      if (mePollingIntervalRef.current) clearInterval(mePollingIntervalRef.current);
      if (mePopupRef.current && !mePopupRef.current.closed) mePopupRef.current.close();
    };
  }, []);

  useEffect(() => {
    if (activeSection === "security") {
      setSocialLoading(true);
      socialAuthService
        .listSocialAccounts()
        .then(setSocialAccounts)
        .catch(() => {})
        .finally(() => setSocialLoading(false));
    }
  }, [activeSection]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const startMeConnection = useCallback(() => {
    // Prevent double-click from starting a second interval
    if (!meConnectUrl || mePollingIntervalRef.current) return;

    const popup = window.open(
      meConnectUrl,
      "melhorenvio_oauth",
      "width=640,height=720,left=200,top=100,toolbar=no,menubar=no,scrollbars=yes",
    );

    if (!popup) {
      Swal.fire({
        icon: "warning",
        title: "Pop-up bloqueado",
        text: "Habilite pop-ups no navegador para conectar o Melhor Envio e tente novamente.",
        confirmButtonColor: "#1e3a5f",
      });
      return;
    }

    mePopupRef.current = popup;
    setMePolling(true);

    const MAX_POLLS = 20; // 60 s total
    let pollCount = 0;

    mePollingIntervalRef.current = setInterval(async () => {
      pollCount += 1;
      try {
        const status = await logisticsService.getMelhorEnvioStatus();
        if (status.connected && !status.is_expired) {
          clearInterval(mePollingIntervalRef.current!);
          mePollingIntervalRef.current = null;
          if (mePopupRef.current && !mePopupRef.current.closed) mePopupRef.current.close();
          setMePolling(false);
          setMeConnected(true);
          return;
        }
      } catch {
        // Ignore transient errors during polling
      }
      if (mePopupRef.current?.closed) {
        clearInterval(mePollingIntervalRef.current!);
        mePollingIntervalRef.current = null;
        setMePolling(false);
        return;
      }
      if (pollCount >= MAX_POLLS) {
        clearInterval(mePollingIntervalRef.current!);
        mePollingIntervalRef.current = null;
        if (mePopupRef.current && !mePopupRef.current.closed) mePopupRef.current.close();
        setMePolling(false);
      }
    }, 3000);
  }, [meConnectUrl]);

  const handleBirthdayChange = (value: string) => {
    const numbers = value.replace(/\D/g, "");
    let formatted = numbers;
    if (numbers.length > 2 && numbers.length <= 4) {
      formatted = `${numbers.slice(0, 2)}/${numbers.slice(2)}`;
    } else if (numbers.length > 4) {
      formatted = `${numbers.slice(0, 2)}/${numbers.slice(2, 4)}/${numbers.slice(4, 8)}`;
    }
    setBirthday(formatted);
  };

  const handlePictureUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // Reset input before early returns so the same file can be re-selected if needed
    e.target.value = "";
    if (!file) return;

    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      Swal.fire({
        icon: "error",
        title: "Arquivo inválido",
        text: "Selecione apenas imagens JPG, PNG ou WebP.",
      });
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      Swal.fire({
        icon: "error",
        title: "Arquivo muito grande",
        text: "O tamanho máximo permitido é 5 MB.",
      });
      return;
    }

    setPictureUploading(true);
    try {
      // Use getPresignedUrl + uploadToS3 to upload; save file_url (full public URL)
      // to the backend — consistent with how product images are stored in the system.
      // object_name is a bare storage key (e.g. "products/abc.jpg") and cannot be
      // passed to toPublicUrl, which expects a full URL.
      const { upload_url, file_url } = await storageService.getPresignedUrl(
        file.name,
        file.type,
      );
      await storageService.uploadToS3(upload_url, file);
      const updated = await userService.updateCurrentUser({ picture: file_url });
      const newUser = mapToUser(updated, user?.is_active);
      tokenStorage.saveUser(newUser);
      setUser(newUser);
      Swal.fire({
        icon: "success",
        title: "Foto atualizada!",
        toast: true,
        position: "top-end",
        showConfirmButton: false,
        timer: 2000,
        timerProgressBar: true,
      });
    } catch (err: unknown) {
      Swal.fire({
        icon: "error",
        title: "Erro",
        text: getAxiosErrorMessage(err, "Não foi possível atualizar a foto. Tente novamente."),
      });
    } finally {
      setPictureUploading(false);
    }
  };

  const handleSavePersonal = async (e: FormEvent) => {
    e.preventDefault();
    setPersonalError("");
    setPersonalSuccess(false);
    if (!fullName.trim()) {
      setPersonalError("Nome completo é obrigatório.");
      return;
    }
    setPersonalLoading(true);
    try {
      const updated = await userService.updateCurrentUser({
        full_name: fullName.trim(),
        ...(birthday.length === 10 && { birthday: toISODate(birthday) }),
      });
      const newUser = mapToUser(updated, user?.is_active);
      tokenStorage.saveUser(newUser);
      setUser(newUser);
      setPersonalSuccess(true);
      setTimeout(() => setPersonalSuccess(false), 3000);
    } catch (err: unknown) {
      setPersonalError(getAxiosErrorMessage(err, "Erro ao salvar. Tente novamente."));
    } finally {
      setPersonalLoading(false);
    }
  };

  const handleDeleteAddress = async (id: number) => {
    const result = await Swal.fire({
      title: "Remover endereço?",
      text: "Esta ação não pode ser desfeita.",
      icon: "warning",
      showCancelButton: true,
      confirmButtonColor: "#1e3a5f",
      cancelButtonColor: "#6b7280",
      confirmButtonText: "Remover",
      cancelButtonText: "Cancelar",
    });
    if (!result.isConfirmed) return;
    setDeletingId(id);
    try {
      await logisticsService.deleteAddress(id);
      setAddresses((prev) => prev.filter((a) => a.id !== id));
    } catch {
      Swal.fire("Erro", "Não foi possível remover o endereço.", "error");
    } finally {
      setDeletingId(null);
    }
  };

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault();
    setPwError("");
    setPwSuccess(false);
    if (!currentPw || !newPw || !confirmPw) {
      setPwError("Preencha todos os campos.");
      return;
    }
    if (newPw !== confirmPw) {
      setPwError("As senhas não coincidem.");
      return;
    }
    if (newPw.length < 8) {
      setPwError("A nova senha deve ter pelo menos 8 caracteres.");
      return;
    }
    setPwLoading(true);
    try {
      await authService.changePassword({
        old_password: currentPw,
        new_password1: newPw,
        new_password2: confirmPw,
      });
      setPwSuccess(true);
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      setTimeout(() => setPwSuccess(false), 4000);
    } catch (err: unknown) {
      setPwError(getAxiosErrorMessage(err, "Erro ao alterar senha. Tente novamente."));
    } finally {
      setPwLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    const result = await Swal.fire({
      title: "Excluir conta",
      html: "Esta ação é <strong>permanente</strong> e não pode ser desfeita.<br/><br/>Digite <strong>EXCLUIR</strong> para confirmar.",
      input: "text",
      inputPlaceholder: "EXCLUIR",
      showCancelButton: true,
      confirmButtonColor: "#dc2626",
      cancelButtonColor: "#6b7280",
      confirmButtonText: "Excluir minha conta",
      cancelButtonText: "Cancelar",
      inputValidator: (value) => {
        if (value !== "EXCLUIR")
          return 'Digite exatamente "EXCLUIR" para confirmar.';
      },
    });
    if (!result.isConfirmed) return;
    try {
      await userService.deleteCurrentUser();
      logout();
      navigate("/", { replace: true });
    } catch (err: unknown) {
      const responseData = (err as { response?: { data?: unknown; status?: number } })?.response;
      const status = responseData?.status;
      if (status === 404 || status === 405) {
        Swal.fire(
          "Funcionalidade em implementação",
          "Esta funcionalidade está sendo implementada. Entre em contato com o suporte.",
          "info",
        );
      } else {
        Swal.fire(
          "Erro",
          getAxiosErrorMessage(err, "Não foi possível excluir a conta. Tente novamente."),
          "error",
        );
      }
    }
  };

  // ── Shared styles ────────────────────────────────────────────────────────────

  const inputCls = (hasError?: boolean) =>
    `w-full px-3 py-2.5 border-2 rounded-lg text-sm focus:outline-none transition ${
      hasError
        ? "border-red-500 focus:border-red-500"
        : "border-gray-300 focus:border-blue-500"
    }`;

  const googleAccount = socialAccounts.find((a) => a.provider === "google");
  const googleEmail = googleAccount?.extra_data?.email as string | undefined;

  // ── Section: Dados Pessoais ──────────────────────────────────────────────────

  const renderPersonal = () => (
    <div className="bg-white rounded-2xl shadow p-6">
      <h2 className="text-lg font-bold text-gray-900 mb-5">Dados Pessoais</h2>
      <form onSubmit={handleSavePersonal} className="space-y-4">
        {personalError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {personalError}
          </div>
        )}
        {personalSuccess && (
          <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
            Dados salvos com sucesso!
          </div>
        )}

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            Nome completo
          </label>
          <input
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Seu nome completo"
            className={inputCls()}
          />
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            Email
          </label>
          <input
            type="email"
            value={user?.email ?? ""}
            readOnly
            className={`${inputCls()} bg-gray-50 cursor-not-allowed text-gray-600`}
          />
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            CPF
          </label>
          <input
            type="text"
            value={user?.cpf ? formatCpfDisplay(user.cpf) : ""}
            readOnly
            className={`${inputCls()} bg-gray-50 cursor-not-allowed text-gray-600`}
          />
          <p className="mt-1 text-xs text-gray-500">
            O CPF não pode ser alterado após o cadastro.
          </p>
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            Data de nascimento
          </label>
          <input
            type="text"
            value={birthday}
            onChange={(e) => handleBirthdayChange(e.target.value)}
            placeholder="DD/MM/AAAA"
            maxLength={10}
            inputMode="numeric"
            className={inputCls()}
          />
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-3">
            Foto de perfil
          </label>
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full overflow-hidden bg-blue-100 flex items-center justify-center shrink-0">
              {pictureUploading ? (
                <Loader2 size={24} className="animate-spin text-blue-900" />
              ) : user?.picture ? (
                <img
                  src={toPublicUrl(user.picture)}
                  alt="Foto de perfil"
                  className="w-full h-full object-cover"
                />
              ) : (
                <UserIcon size={32} className="text-blue-400" />
              )}
            </div>
            <div>
              <button
                type="button"
                disabled={pictureUploading}
                onClick={() => pictureInputRef.current?.click()}
                className="flex items-center gap-2 px-4 py-2 border-2 border-blue-900 text-blue-900 rounded-lg text-sm font-semibold hover:bg-blue-50 transition disabled:opacity-50 cursor-pointer"
              >
                <Camera size={16} />
                {pictureUploading ? "Enviando..." : "Alterar foto"}
              </button>
              <p className="mt-1.5 text-xs text-gray-400">
                JPG, PNG ou WebP · Máx. 5 MB
              </p>
            </div>
          </div>
          <input
            ref={pictureInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            onChange={handlePictureUpload}
          />
        </div>

        <div className="flex justify-end pt-1">
          <button
            type="submit"
            disabled={personalLoading}
            className="px-6 py-2.5 bg-blue-900 text-white rounded-lg font-semibold text-sm hover:bg-blue-800 transition disabled:opacity-50 cursor-pointer"
          >
            {personalLoading ? (
              <span className="flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                Salvando...
              </span>
            ) : (
              "Salvar alterações"
            )}
          </button>
        </div>
      </form>
    </div>
  );

  // ── Section: Endereços ───────────────────────────────────────────────────────

  const renderAddresses = () => (
    <div className="bg-white rounded-2xl shadow p-6">
      {/* Header row: title + primary action */}
      <div className="flex items-center justify-between mb-3 gap-2">
        <h2 className="text-lg font-bold text-gray-900 min-w-0">
          Meus Endereços
        </h2>
        <button
          onClick={() => setShowAddressModal(true)}
          className="flex items-center gap-1.5 px-4 py-2 bg-blue-900 text-white rounded-lg text-sm font-semibold hover:bg-blue-800 focus-visible:ring-2 focus-visible:ring-blue-700 focus-visible:ring-offset-2 transition cursor-pointer shrink-0"
        >
          <Plus size={15} aria-hidden="true" />
          Novo endereço
        </button>
      </div>

      {/* Melhor Envio integration status — secondary row, visually distinct */}
      <div className="mb-5">
        {meCheckLoading ? (
          <div
            aria-live="polite"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-gray-200 rounded-lg text-xs text-gray-400"
          >
            <Loader2 size={12} className="animate-spin" aria-hidden="true" />
            Verificando Melhor Envio…
          </div>
        ) : meConnected ? (
          <div
            role="status"
            aria-label="Melhor Envio conectado com sucesso"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-50 border border-green-200 rounded-lg text-xs font-semibold text-green-700"
          >
            <CheckCircle2 size={12} aria-hidden="true" />
            Melhor Envio conectado
          </div>
        ) : mePolling ? (
          <div
            aria-live="polite"
            className="inline-flex items-center gap-2 px-3 py-1.5 border border-blue-200 bg-blue-50 rounded-lg text-xs text-blue-700"
          >
            <Loader2 size={12} className="animate-spin" aria-hidden="true" />
            <span>Aguardando autorização… <span className="text-blue-400">(até 60&nbsp;s)</span></span>
            <button
              onClick={() => {
                if (mePollingIntervalRef.current) {
                  clearInterval(mePollingIntervalRef.current);
                  mePollingIntervalRef.current = null;
                }
                if (mePopupRef.current && !mePopupRef.current.closed) {
                  mePopupRef.current.close();
                }
                setMePolling(false);
              }}
              aria-label="Cancelar conexão com Melhor Envio"
              className="ml-1 p-0.5 rounded hover:bg-blue-100 focus-visible:ring-2 focus-visible:ring-blue-500 transition cursor-pointer"
            >
              <X size={12} aria-hidden="true" />
            </button>
          </div>
        ) : meConnectUrl ? (
          <button
            onClick={startMeConnection}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-blue-900 text-blue-900 rounded-lg text-xs font-semibold hover:bg-blue-50 focus-visible:ring-2 focus-visible:ring-blue-700 focus-visible:ring-offset-2 transition cursor-pointer"
          >
            <Link2 size={13} aria-hidden="true" />
            Conectar Melhor Envio
            <ExternalLink size={11} className="text-blue-400" aria-hidden="true" />
          </button>
        ) : null}
      </div>


      {addressesLoading ? (
        <div className="flex justify-center py-10">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-900" />
        </div>
      ) : addresses.length === 0 ? (
        <div className="text-center py-10 text-gray-400">
          <MapPin size={40} className="mx-auto mb-3 opacity-40" />
          <p className="text-sm">Nenhum endereço cadastrado.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {addresses.map((addr) => (
            <div
              key={addr.id}
              className="flex items-start justify-between p-4 border border-gray-200 rounded-xl hover:border-blue-200 transition"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="font-semibold text-gray-900 text-sm">
                    {addr.nickname || addr.address_type}
                  </span>
                  {addr.is_default && (
                    <span className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full">
                      Padrão
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-600 truncate">
                  {addr.street}, {addr.number}
                  {addr.complement ? ` — ${addr.complement}` : ""}
                </p>
                <p className="text-sm text-gray-500">
                  {addr.city}/{addr.state} &bull; CEP {addr.zipcode}
                </p>
              </div>
              <button
                onClick={() => handleDeleteAddress(addr.id)}
                disabled={deletingId === addr.id}
                title="Remover endereço"
                className="ml-3 p-2 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition disabled:opacity-40 cursor-pointer shrink-0"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // ── Section: Segurança ───────────────────────────────────────────────────────

  const renderSecurity = () => (
    <div className="space-y-5">
      {/* Alterar senha */}
      <div className="bg-white rounded-2xl shadow p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-5">Alterar Senha</h2>
        <form onSubmit={handleChangePassword} className="space-y-4">
          {pwError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              {pwError}
            </div>
          )}
          {pwSuccess && (
            <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
              Senha alterada com sucesso!
            </div>
          )}

          {(
            [
              {
                label: "Senha atual",
                value: currentPw,
                setter: setCurrentPw,
                show: showCurrentPw,
                toggle: () => setShowCurrentPw((v) => !v),
              },
              {
                label: "Nova senha",
                value: newPw,
                setter: setNewPw,
                show: showNewPw,
                toggle: () => setShowNewPw((v) => !v),
              },
              {
                label: "Confirmar nova senha",
                value: confirmPw,
                setter: setConfirmPw,
                show: showConfirmPw,
                toggle: () => setShowConfirmPw((v) => !v),
              },
            ] as const
          ).map(({ label, value, setter, show, toggle }) => (
            <div key={label}>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                {label}
              </label>
              <div className="relative">
                <input
                  type={show ? "text" : "password"}
                  value={value}
                  onChange={(e) => setter(e.target.value)}
                  className={`${inputCls()} pr-10`}
                />
                <button
                  type="button"
                  onClick={toggle}
                  aria-label={show ? "Ocultar senha" : "Mostrar senha"}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 cursor-pointer"
                >
                  {show ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>
          ))}

          <div className="flex justify-end pt-1">
            <button
              type="submit"
              disabled={pwLoading}
              className="px-6 py-2.5 bg-blue-900 text-white rounded-lg font-semibold text-sm hover:bg-blue-800 transition disabled:opacity-50 cursor-pointer"
            >
              {pwLoading ? (
                <span className="flex items-center gap-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                  Alterando...
                </span>
              ) : (
                "Alterar senha"
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Conta Google */}
      <div className="bg-white rounded-2xl shadow p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Conta Google</h2>
        {socialLoading ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-400" />
            Verificando...
          </div>
        ) : googleAccount ? (
          <div className="flex items-center gap-3 p-3 bg-green-50 border border-green-200 rounded-xl">
            <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center shrink-0 shadow-sm">
              <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none">
                <path
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  fill="#4285F4"
                />
                <path
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  fill="#34A853"
                />
                <path
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
                  fill="#FBBC05"
                />
                <path
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  fill="#EA4335"
                />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-green-800">
                Google conectado
              </p>
              {googleEmail && (
                <p className="text-xs text-green-700 truncate">{googleEmail}</p>
              )}
            </div>
            <span className="px-2.5 py-1 bg-green-100 text-green-800 text-xs font-bold rounded-full shrink-0">
              Conectado
            </span>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-3 p-3 bg-gray-50 border border-gray-200 rounded-xl">
            <p className="text-sm text-gray-600">
              Nenhuma conta Google vinculada.
            </p>
            <button
              onClick={() => startGoogleOAuth("connect")}
              className="px-4 py-2 bg-blue-900 text-white rounded-lg text-sm font-semibold hover:bg-blue-800 transition cursor-pointer shrink-0"
            >
              Vincular conta Google
            </button>
          </div>
        )}
      </div>

      {/* Zona de perigo */}
      <div className="bg-red-50 border border-red-200 rounded-2xl p-6">
        <h2 className="flex items-center gap-2 text-lg font-bold text-red-800 mb-1">
          <AlertTriangle size={20} />
          Zona de perigo
        </h2>
        <p className="text-sm text-red-600 mb-4">
          A exclusão da conta é permanente e não pode ser desfeita. Todos os
          seus dados e anúncios serão removidos.
        </p>
        <button
          onClick={handleDeleteAccount}
          className="px-5 py-2.5 border-2 border-red-600 text-red-600 rounded-lg font-semibold text-sm hover:bg-red-600 hover:text-white transition cursor-pointer"
        >
          Excluir minha conta
        </button>
      </div>
    </div>
  );

  // ── Section: Notificações ────────────────────────────────────────────────────

  const renderNotifications = () => (
    <div className="bg-white rounded-2xl shadow p-6">
      <h2 className="text-lg font-bold text-gray-900 mb-5">Notificações</h2>
      <div className="divide-y divide-gray-100">
        {(
          [
            { key: "newListings", label: "Novos anúncios na sua busca" },
            { key: "messages", label: "Mensagens recebidas" },
            { key: "orders", label: "Atualizações de pedidos" },
            { key: "promotions", label: "Promoções e novidades" },
          ] as const
        ).map(({ key, label }) => (
          <div
            key={key}
            className="flex items-center justify-between py-4 opacity-60"
          >
            <div>
              <p className="text-sm font-medium text-gray-800">{label}</p>
              <p className="text-xs text-gray-500 mt-0.5">Em breve</p>
            </div>
            {/* Visual-only toggle — notifications backend not yet available */}
            <div
              aria-hidden="true"
              className={`relative w-11 h-6 rounded-full shrink-0 ${
                NOTIFICATION_DEFAULTS[key] ? "bg-blue-900" : "bg-gray-300"
              }`}
            >
              <span
                className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full shadow transition-transform duration-200 ${
                  NOTIFICATION_DEFAULTS[key] ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs text-gray-500 text-center">
        As configurações de notificação serão ativadas em breve.
      </p>
    </div>
  );

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      {/* Page header */}
      <div className="bg-linear-to-r from-black via-gray-800 to-blue-900 px-4 py-6">
        <div className="max-w-5xl mx-auto">
          <h1 className="text-2xl font-bold text-white">Minha Conta</h1>
          <p className="text-blue-200 text-sm mt-1">
            Gerencie suas informações pessoais
          </p>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-6">
        {/* Mobile nav — horizontal scroll */}
        <nav className="flex md:hidden overflow-x-auto gap-2 mb-6 pb-1 -mx-4 px-4 scrollbar-none">
          {SECTIONS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveSection(id)}
              aria-current={activeSection === id ? "page" : undefined}
              className={`flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-semibold whitespace-nowrap transition cursor-pointer shrink-0 ${
                activeSection === id
                  ? "bg-blue-900 text-white"
                  : "bg-white text-gray-600 border border-gray-200 hover:border-blue-300"
              }`}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </nav>

        <div className="flex gap-5">
          {/* Desktop sidebar */}
          <aside className="hidden md:flex flex-col w-52 shrink-0 gap-1">
            {SECTIONS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActiveSection(id)}
                aria-current={activeSection === id ? "page" : undefined}
                className={`flex items-center gap-2.5 px-4 py-3 rounded-xl text-sm font-semibold text-left transition cursor-pointer ${
                  activeSection === id
                    ? "bg-blue-900 text-white"
                    : "text-gray-600 hover:bg-white hover:text-gray-900"
                }`}
              >
                <Icon size={17} />
                {label}
              </button>
            ))}
          </aside>

          {/* Content — only the active section is rendered to avoid wasted computation */}
          <main className="flex-1 min-w-0">
            {activeSection === "personal" && renderPersonal()}
            {activeSection === "addresses" && renderAddresses()}
            {activeSection === "security" && renderSecurity()}
            {activeSection === "notifications" && renderNotifications()}
          </main>
        </div>
      </div>

      {showAddressModal && (
        <AddressModal
          onClose={() => setShowAddressModal(false)}
          onSaved={(addr) => {
            setAddresses((prev) => [...prev, addr]);
            setShowAddressModal(false);
          }}
        />
      )}
    </div>
  );
}
