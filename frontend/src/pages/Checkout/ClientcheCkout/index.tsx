import { useState, useEffect, useMemo, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  MapPin,
  Plus,
  X,
  Package,
  Truck,
  User,
  ChevronRight,
  Loader2,
  AlertCircle,
  CheckCircle2,
  ShoppingBag,
} from "lucide-react";
import { useCart, type CartItem } from "@/contexts/CartContext";
import { addressService, type Address, type AddressCreateRequest } from "@/services/addressService";
import { shippingService } from "@/services/shippingService";
import { formatCurrency } from "@/utils/formatters";
import { BRAZILIAN_STATES } from "@/constants/brazilianStates";
import { toPublicUrl } from "@/services/storageService";
import api from "@/api/axios";
import axios from "axios";
import Swal from "sweetalert2";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ShippingOption {
  service_id: number;
  name: string;
  company: string;
  company_picture?: string;
  price: number;
  delivery_time: number;
}

interface SellerQuote {
  seller_name: string;
  in_person_only: boolean;
  has_in_person: boolean;
  quotes: ShippingOption[];
}

/**
 * Represents the raw shape returned by the API per seller inside
 * `quotes_by_seller`. The API contract is intentionally loose, so both
 * `quotes` and `options` are accepted as the array field name.
 */
interface RawSellerQuote {
  seller_name?: string;
  in_person_only?: boolean;
  in_person_items?: unknown[];
  quotes?: RawShippingOption[];
  options?: RawShippingOption[];
}

interface RawShippingOption {
  service_id?: number;
  id?: number;
  name?: string;
  service_name?: string;
  company?: string;
  carrier_name?: string;
  company_picture?: string;
  price?: number | string;
  delivery_time?: number;
  delivery_days?: number;
}

export interface CheckoutNavigationState {
  shippingAddressId: number;
  selectedServices: Record<string, number>;
  inPersonSellers: string[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getAxiosErrorMessage(err: unknown, fallback: string): string {
  const responseData = (err as { response?: { data?: unknown } })?.response?.data;
  if (responseData && typeof responseData === "object") {
    const messages = (Object.values(responseData).flat() as unknown[])
      .filter((v): v is string => typeof v === "string");
    return messages.join(" ") || fallback;
  }
  if (typeof responseData === "string" && responseData) return responseData;
  if (err instanceof Error) return err.message;
  return fallback;
}

function applyZipcodeMask(value: string): string {
  const n = value.replace(/\D/g, "").slice(0, 8);
  if (n.length <= 5) return n;
  return `${n.slice(0, 5)}-${n.slice(5)}`;
}

function applyPhoneMask(value: string): string {
  const n = value.replace(/\D/g, "").slice(0, 11);
  if (n.length <= 2) return n;
  if (n.length <= 7) return `(${n.slice(0, 2)}) ${n.slice(2)}`;
  return `(${n.slice(0, 2)}) ${n.slice(2, 7)}-${n.slice(7)}`;
}

function groupBySeller(items: CartItem[]): Map<string, { seller_name: string; items: CartItem[] }> {
  const map = new Map<string, { seller_name: string; items: CartItem[] }>();
  for (const item of items) {
    const sellerId = String(item.listing.seller);
    if (!map.has(sellerId)) {
      map.set(sellerId, { seller_name: item.listing.seller_name, items: [] });
    }
    map.get(sellerId)!.items.push(item);
  }
  return map;
}

function sellerSubtotal(sellerItems: CartItem[]): number {
  return sellerItems.reduce((sum, item) => sum + Number(item.listing.price) * item.quantity, 0);
}

/** Rejects URLs that are not http/https to guard against unexpected schemes. */
function toSafeImageUrl(url: string | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const { protocol } = new URL(url);
    return protocol === "https:" || protocol === "http:" ? url : undefined;
  } catch {
    return undefined;
  }
}

function parseRawShippingOption(q: RawShippingOption): ShippingOption {
  const rawPrice = q.price;
  const price =
    typeof rawPrice === "number" ? rawPrice : parseFloat(String(rawPrice ?? "0"));
  return {
    service_id: q.service_id ?? q.id ?? 0,
    name: q.name ?? q.service_name ?? "",
    company: q.company ?? q.carrier_name ?? "",
    company_picture: toSafeImageUrl(q.company_picture),
    price: isNaN(price) ? 0 : price,
    delivery_time: q.delivery_time ?? q.delivery_days ?? 0,
  };
}

// ─── Blank address form ────────────────────────────────────────────────────────

const BLANK_ADDRESS: AddressCreateRequest = {
  recipient_name: "",
  recipient_phone: "",
  zipcode: "",
  street: "",
  number: "",
  complement: "",
  neighborhood: "",
  city: "",
  state: "",
  address_type: "shipping",
  is_shipping_address: true,
};

// ─── Shared UI primitives ─────────────────────────────────────────────────────

/**
 * Step header with a numbered badge that turns into a check when complete.
 * Keeps visual hierarchy consistent across all three sections.
 */
function StepHeader({
  step,
  icon,
  title,
  complete,
}: {
  step: number;
  icon: React.ReactNode;
  title: string;
  complete?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <div
        className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold shrink-0 transition-colors ${
          complete ? "bg-green-100 text-green-700" : "bg-blue-900 text-white"
        }`}
        aria-hidden="true"
      >
        {complete ? <CheckCircle2 size={15} /> : step}
      </div>
      <h2 className="text-base font-semibold text-gray-900 flex items-center gap-2">
        {icon}
        {title}
      </h2>
    </div>
  );
}

/** Label with optional required asterisk and proper htmlFor wiring. */
function FieldLabel({
  htmlFor,
  required,
  optional,
  children,
}: {
  htmlFor: string;
  required?: boolean;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label htmlFor={htmlFor} className="block text-sm font-medium text-gray-700 mb-1">
      {children}
      {required && (
        <span className="ml-0.5 text-red-500" aria-hidden="true">
          {" "}*
        </span>
      )}
      {optional && (
        <span className="ml-1 text-xs font-normal text-gray-400">(opcional)</span>
      )}
    </label>
  );
}

/** Unified input class string — adds red tint on error. */
function inputCls(error = false) {
  return [
    "w-full px-3 py-2.5 text-sm border rounded-lg transition-colors",
    "focus:outline-none focus:ring-2 focus:ring-blue-800/30 focus:border-blue-800",
    error
      ? "border-red-400 bg-red-50 focus:border-red-500 focus:ring-red-400/20"
      : "border-gray-300 bg-white hover:border-gray-400",
  ].join(" ");
}

/** Inline alert banner for errors and notices. */
function AlertBanner({
  children,
  variant = "error",
}: {
  children: React.ReactNode;
  variant?: "error" | "warning";
}) {
  const styles =
    variant === "warning"
      ? "bg-amber-50 border-amber-200 text-amber-800"
      : "bg-red-50 border-red-200 text-red-700";
  return (
    <div
      role="alert"
      className={`flex items-start gap-2 text-sm border rounded-lg p-3 ${styles}`}
    >
      <AlertCircle size={15} className="shrink-0 mt-0.5" aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

/** Spinner row used in loading states — min-h prevents layout collapse. */
function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5 text-gray-500 py-6 min-h-[72px]">
      <Loader2 size={18} className="animate-spin shrink-0 text-blue-800" aria-hidden="true" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────────

export function Checkout() {
  const { items } = useCart();
  const navigate = useNavigate();
  const location = useLocation();

  // Redirect if cart is empty
  useEffect(() => {
    if (items.length === 0) navigate("/", { replace: true });
  }, [items.length, navigate]);

  // ── Sellers groups (memoised) ──
  const sellerGroups = useMemo(() => groupBySeller(items), [items]);

  // ── Address state ──
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [addressesLoading, setAddressesLoading] = useState(true);
  const [addressError, setAddressError] = useState("");
  const [selectedAddressId, setSelectedAddressId] = useState<number | null>(null);
  const [showAddressForm, setShowAddressForm] = useState(false);

  // ── New address form ──
  const [newAddress, setNewAddress] = useState<AddressCreateRequest>(BLANK_ADDRESS);
  const [cepLoading, setCepLoading] = useState(false);
  const [savingAddress, setSavingAddress] = useState(false);
  const [formError, setFormError] = useState("");

  // ── Shipping state ──
  const [quotesMap, setQuotesMap] = useState<Record<string, SellerQuote>>({});
  const [shippingLoading, setShippingLoading] = useState(false);
  const [shippingError, setShippingError] = useState("");
  const [selectedServices, setSelectedServices] = useState<Record<string, number>>({});
  const [inPersonSellers, setInPersonSellers] = useState<string[]>([]);
  const [syncingCart, setSyncingCart] = useState(false);

  // ── Load addresses ──
  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        setAddressesLoading(true);
        const data = await addressService.listAddresses();
        if (controller.signal.aborted) return;
        setAddresses(data);
        if (data.length === 0) {
          setShowAddressForm(true);
        } else {
          const defaultAddr = data.find((a) => a.is_default) ?? data[0];
          setSelectedAddressId(defaultAddr.id);
        }
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        setAddressError(getAxiosErrorMessage(err, "Erro ao carregar endereços."));
      } finally {
        if (!controller.signal.aborted) setAddressesLoading(false);
      }
    }

    load();
    return () => controller.abort();
  }, []);

  // ── Auto-calculate shipping when address changes ──
  useEffect(() => {
    if (!selectedAddressId) return;

    const controller = new AbortController();
    const addressId = selectedAddressId;

    async function calculate() {
      try {
        setShippingLoading(true);
        setSyncingCart(true);
        setShippingError("");

        // Sincronizar carrinho do backend
        await api.delete("/orders/cart/clear/", { signal: controller.signal });
        for (const item of items) {
          if (controller.signal.aborted) return;
          await api.post("/orders/cart/add/", {
            listing: item.listing.id,
            quantity: item.quantity,
          }, { signal: controller.signal });
        }
        setSyncingCart(false);

        const response = await shippingService.calculateShipping({ shipping_address_id: addressId });
        if (controller.signal.aborted) return;

        const newQuotes: Record<string, SellerQuote> = {};
        const newInPerson: string[] = [];

        for (const [sellerId, raw] of Object.entries(response.quotes_by_seller)) {
          const data = raw as RawSellerQuote;
          const inPersonOnly = data.in_person_only === true;

          if (inPersonOnly) newInPerson.push(sellerId);

          const rawOptions = data.quotes ?? data.options ?? [];
          const quotes = rawOptions.map(parseRawShippingOption);

          newQuotes[sellerId] = {
            seller_name: data.seller_name ?? sellerGroups.get(sellerId)?.seller_name ?? sellerId,
            in_person_only: inPersonOnly,
            has_in_person: (data.in_person_items ?? []).length > 0,
            quotes,
          };
        }

        setQuotesMap(newQuotes);
        setInPersonSellers(newInPerson);
        setSelectedServices({});
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        setSyncingCart(false);

        if (axios.isAxiosError(err) && err.response?.status === 422) {
          const data = err.response.data as { error?: string };
          if (data.error === "insufficient_me_balance") {
            await Swal.fire({
              icon: "error",
              title: "Envio indisponível",
              text: "Este vendedor não pode processar o envio no momento. Tente novamente mais tarde ou contate o vendedor diretamente.",
            });
            setShippingLoading(false);
            return;
          }
        }

        setShippingError(getAxiosErrorMessage(err, "Erro ao calcular o frete."));
      } finally {
        if (!controller.signal.aborted) setShippingLoading(false);
      }
    }

    calculate();
    return () => controller.abort();
  }, [selectedAddressId, sellerGroups, items]);

  // ── CEP lookup ──
  const handleCepBlur = useCallback(async () => {
    const clean = newAddress.zipcode.replace(/\D/g, "");
    if (clean.length !== 8) return;
    try {
      setCepLoading(true);
      const result = await addressService.lookupCEP({ zipcode: clean });
      setNewAddress((prev) => ({
        ...prev,
        street: result.street || prev.street,
        neighborhood: result.neighborhood || prev.neighborhood,
        city: result.city || prev.city,
        state: result.state || prev.state,
      }));
    } catch {
      // fail silently — user fills in manually
    } finally {
      setCepLoading(false);
    }
  }, [newAddress.zipcode]);

  // ── Save new address ──
  const handleSaveAddress = useCallback(async () => {
    if (savingAddress) return;

    const { recipient_name, recipient_phone, zipcode, street, number, neighborhood, city, state } =
      newAddress;
    if (
      !recipient_name ||
      !recipient_phone ||
      !zipcode ||
      !street ||
      !number ||
      !neighborhood ||
      !city ||
      !state
    ) {
      setFormError("Preencha todos os campos obrigatórios.");
      return;
    }

    try {
      setSavingAddress(true);
      setFormError("");
      const created = await addressService.createAddress({
        ...newAddress,
        zipcode: newAddress.zipcode.replace(/\D/g, ""),
        recipient_phone: newAddress.recipient_phone.replace(/\D/g, ""),
      });
      setAddresses((prev) => [...prev, created]);
      setSelectedAddressId(created.id);
      setShowAddressForm(false);
      setNewAddress(BLANK_ADDRESS);
    } catch (err: unknown) {
      setFormError(getAxiosErrorMessage(err, "Erro ao salvar endereço."));
    } finally {
      setSavingAddress(false);
    }
  }, [savingAddress, newAddress]);

  // ── Totals ──
  const productSubtotal = useMemo(
    () => items.reduce((sum, item) => sum + Number(item.listing.price) * item.quantity, 0),
    [items],
  );

  const shippingTotal = useMemo(() => {
    return Object.entries(selectedServices).reduce((sum, [sellerId, serviceId]) => {
      const option = quotesMap[sellerId]?.quotes.find((q) => q.service_id === serviceId);
      return sum + (option?.price ?? 0);
    }, 0);
  }, [selectedServices, quotesMap]);

  // ── Can proceed ──
  const allServicesSelected = useMemo(() => {
    if (!selectedAddressId || shippingLoading) return false;
    return Array.from(sellerGroups.keys()).every((sid) => {
      const quote = quotesMap[sid];
      // In-person only or no quotes → no selection needed
      if (!quote || quote.in_person_only || quote.quotes.length === 0) return true;
      return selectedServices[sid] !== undefined;
    });
  }, [selectedAddressId, shippingLoading, sellerGroups, quotesMap, selectedServices]);

  const handleProceedToPayment = useCallback(() => {
    if (!allServicesSelected || !selectedAddressId) return;
    navigate("/payment", {
      state: {
        shippingAddressId: selectedAddressId,
        selectedServices,
        inPersonSellers,
      } as CheckoutNavigationState,
    });
  }, [allServicesSelected, selectedAddressId, navigate, selectedServices, inPersonSellers]);

  // ── Early return while redirecting ──
  if (items.length === 0) return null;

  const selectedAddress = addresses.find((a) => a.id === selectedAddressId);

  // Step completion flags drive the numbered badges
  const step2Complete = !!selectedAddressId && !showAddressForm;
  const step3Complete = step2Complete && allServicesSelected;

  // ─── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-6 sm:py-8">

        {/* ── Page heading ── */}
        <div className="mb-6 sm:mb-8">
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Finalizar Compra</h1>
          <p className="text-sm text-gray-500 mt-1">
            Revise seus itens, escolha o endereço e selecione o frete para continuar.
          </p>
        </div>

        {location.state?.error && (
          <div className="mb-5">
            <AlertBanner variant="warning">{location.state.error as string}</AlertBanner>
          </div>
        )}

        <div className="flex flex-col lg:flex-row gap-5 lg:gap-8 items-start">

          {/* ════════════════════════════════════════
              Main column
          ════════════════════════════════════════ */}
          <div className="flex-1 min-w-0 space-y-4 sm:space-y-5">

            {/* ── STEP 1: Itens do carrinho ── */}
            <section className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 sm:p-6">
              <StepHeader
                step={1}
                icon={<ShoppingBag size={17} className="text-blue-800" />}
                title="Itens do pedido"
                complete
              />

              <div className="space-y-5">
                {Array.from(sellerGroups.entries()).map(([sellerId, group]) => (
                  <div key={sellerId}>

                    {/* Seller identifier row */}
                    <div className="flex items-center gap-1.5 mb-3 pb-2 border-b border-gray-100">
                      <User size={13} className="text-gray-400 shrink-0" aria-hidden="true" />
                      <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                        Vendedor
                      </span>
                      <span className="text-sm font-semibold text-gray-700">{group.seller_name}</span>
                    </div>

                    {/* Item list */}
                    <ul className="divide-y divide-gray-50" aria-label={`Itens de ${group.seller_name}`}>
                      {group.items.map((item) => {
                        const primaryImg =
                          item.listing.images?.find((i) => i.is_primary) ?? item.listing.images?.[0];
                        const imgSrc = primaryImg ? toPublicUrl(primaryImg.image_url) : null;
                        const productName = item.listing.title || item.listing.product.name;
                        const unitPrice = Number(item.listing.price);

                        return (
                          <li key={item.listing.id} className="flex gap-3 sm:gap-4 py-3">
                            {/* Thumbnail */}
                            <div className="w-14 h-14 sm:w-16 sm:h-16 bg-gray-100 rounded-lg overflow-hidden shrink-0">
                              {imgSrc ? (
                                <img
                                  src={imgSrc}
                                  alt={productName}
                                  className="w-full h-full object-cover"
                                  loading="lazy"
                                />
                              ) : (
                                <div className="w-full h-full flex items-center justify-center" aria-hidden="true">
                                  <Package size={20} className="text-gray-300" />
                                </div>
                              )}
                            </div>

                            {/* Info */}
                            <div className="flex-1 min-w-0 self-center">
                              <p className="text-sm font-semibold text-gray-800 leading-snug line-clamp-2">
                                {productName}
                              </p>
                              <p className="text-xs text-gray-500 mt-1">
                                {item.quantity} × {formatCurrency(unitPrice)}
                              </p>
                            </div>

                            {/* Line total */}
                            <div className="shrink-0 self-center text-right">
                              <p className="text-sm font-bold text-blue-800">
                                {formatCurrency(unitPrice * item.quantity)}
                              </p>
                            </div>
                          </li>
                        );
                      })}
                    </ul>

                    {/* Per-seller subtotal */}
                    <div className="flex justify-end pt-2 mt-1 border-t border-gray-100">
                      <p className="text-xs text-gray-500">
                        Subtotal:{" "}
                        <span className="font-semibold text-gray-700">
                          {formatCurrency(sellerSubtotal(group.items))}
                        </span>
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── STEP 2: Endereço de entrega ── */}
            <section className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 sm:p-6">
              <StepHeader
                step={2}
                icon={<MapPin size={17} className="text-blue-800" />}
                title="Endereço de entrega"
                complete={step2Complete}
              />

              {/* Address load error */}
              {addressError && (
                <div className="mb-4">
                  <AlertBanner>{addressError}</AlertBanner>
                </div>
              )}

              {addressesLoading ? (
                <LoadingRow label="Carregando endereços..." />
              ) : (
                <>
                  {/* Address selection cards */}
                  {addresses.length > 0 && (
                    <div
                      className="space-y-3 mb-4"
                      role="radiogroup"
                      aria-label="Selecionar endereço de entrega"
                    >
                      {addresses.map((addr) => {
                        const isSelected = selectedAddressId === addr.id;
                        return (
                          <div
                            key={addr.id}
                            role="radio"
                            aria-checked={isSelected}
                            tabIndex={0}
                            onClick={() => {
                              setSelectedAddressId(addr.id);
                              setShowAddressForm(false);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                setSelectedAddressId(addr.id);
                                setShowAddressForm(false);
                              }
                            }}
                            className={`flex items-start gap-3 p-4 rounded-xl border-2 cursor-pointer transition-colors min-h-[60px] focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-800/50 ${
                              isSelected
                                ? "border-blue-800 bg-blue-50"
                                : "border-gray-200 hover:border-blue-300 hover:bg-gray-50"
                            }`}
                          >
                            {/* Custom radio dot */}
                            <div
                              aria-hidden="true"
                              className={`mt-1 w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center transition-colors ${
                                isSelected ? "border-blue-800" : "border-gray-300"
                              }`}
                            >
                              {isSelected && <div className="w-2 h-2 rounded-full bg-blue-800" />}
                            </div>

                            {/* Address text */}
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-semibold text-gray-800">
                                {addr.recipient_name}
                                {addr.is_default && (
                                  <span className="ml-2 text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full font-medium">
                                    Padrão
                                  </span>
                                )}
                              </p>
                              <p className="text-sm text-gray-600 mt-0.5">
                                {addr.street}, {addr.number}
                                {addr.complement ? `, ${addr.complement}` : ""}
                              </p>
                              <p className="text-sm text-gray-600">
                                {addr.neighborhood} — {addr.city}/{addr.state}
                              </p>
                              <p className="text-xs text-gray-400 mt-0.5">{addr.zipcode}</p>
                            </div>

                            {isSelected && (
                              <CheckCircle2
                                size={18}
                                className="text-blue-800 shrink-0 mt-0.5"
                                aria-hidden="true"
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Toggle form button — icon swaps between Plus and X */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowAddressForm((prev) => !prev);
                      setFormError("");
                    }}
                    aria-expanded={showAddressForm}
                    className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-800 hover:text-blue-900 hover:underline underline-offset-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-800/40 rounded"
                  >
                    {showAddressForm ? (
                      <>
                        <X size={15} aria-hidden="true" />
                        Cancelar novo endereço
                      </>
                    ) : (
                      <>
                        <Plus size={15} aria-hidden="true" />
                        Adicionar novo endereço
                      </>
                    )}
                  </button>

                  {/* ── Inline address form ── */}
                  {showAddressForm && (
                    <div className="mt-5 pt-5 border-t border-gray-100 space-y-4">

                      {/* Section label + required field hint */}
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold text-gray-800">Novo endereço</p>
                        <p className="text-xs text-gray-400">
                          <span className="text-red-500" aria-hidden="true">*</span>
                          {" "}Campos obrigatórios
                        </p>
                      </div>

                      {/* Form error */}
                      {formError && <AlertBanner>{formError}</AlertBanner>}

                      {/* Row: Nome / Telefone */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                          <FieldLabel htmlFor="recipient_name" required>
                            Nome do destinatário
                          </FieldLabel>
                          <input
                            id="recipient_name"
                            type="text"
                            autoComplete="name"
                            value={newAddress.recipient_name}
                            onChange={(e) =>
                              setNewAddress((p) => ({ ...p, recipient_name: e.target.value }))
                            }
                            placeholder="Nome completo"
                            className={inputCls()}
                          />
                        </div>
                        <div>
                          <FieldLabel htmlFor="recipient_phone" required>
                            Telefone
                          </FieldLabel>
                          <input
                            id="recipient_phone"
                            type="tel"
                            autoComplete="tel"
                            inputMode="tel"
                            value={newAddress.recipient_phone}
                            onChange={(e) =>
                              setNewAddress((p) => ({
                                ...p,
                                recipient_phone: applyPhoneMask(e.target.value),
                              }))
                            }
                            placeholder="(00) 00000-0000"
                            className={inputCls()}
                          />
                        </div>
                      </div>

                      {/* Row: CEP / Número */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                          <FieldLabel htmlFor="zipcode" required>
                            CEP
                          </FieldLabel>
                          <div className="relative">
                            <input
                              id="zipcode"
                              type="text"
                              autoComplete="postal-code"
                              inputMode="numeric"
                              value={newAddress.zipcode}
                              onChange={(e) =>
                                setNewAddress((p) => ({
                                  ...p,
                                  zipcode: applyZipcodeMask(e.target.value),
                                }))
                              }
                              onBlur={handleCepBlur}
                              placeholder="00000-000"
                              className={`${inputCls()} pr-9`}
                            />
                            {cepLoading && (
                              <Loader2
                                size={15}
                                className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-blue-800"
                                aria-label="Buscando CEP..."
                              />
                            )}
                          </div>
                          <p className="mt-1 text-xs text-gray-400">
                            Preenchido automaticamente ao sair do campo.
                          </p>
                        </div>
                        <div>
                          <FieldLabel htmlFor="address_number" required>
                            Número
                          </FieldLabel>
                          <input
                            id="address_number"
                            type="text"
                            autoComplete="address-line2"
                            inputMode="numeric"
                            value={newAddress.number}
                            onChange={(e) =>
                              setNewAddress((p) => ({ ...p, number: e.target.value }))
                            }
                            placeholder="Ex: 123"
                            className={inputCls()}
                          />
                        </div>
                      </div>

                      {/* Rua */}
                      <div>
                        <FieldLabel htmlFor="street" required>
                          Rua / Logradouro
                        </FieldLabel>
                        <input
                          id="street"
                          type="text"
                          autoComplete="address-line1"
                          value={newAddress.street}
                          onChange={(e) =>
                            setNewAddress((p) => ({ ...p, street: e.target.value }))
                          }
                          placeholder="Nome da rua, avenida, etc."
                          className={inputCls()}
                        />
                      </div>

                      {/* Row: Complemento / Bairro */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                          <FieldLabel htmlFor="complement" optional>
                            Complemento
                          </FieldLabel>
                          <input
                            id="complement"
                            type="text"
                            autoComplete="address-level3"
                            value={newAddress.complement}
                            onChange={(e) =>
                              setNewAddress((p) => ({ ...p, complement: e.target.value }))
                            }
                            placeholder="Apto, bloco, sala, etc."
                            className={inputCls()}
                          />
                        </div>
                        <div>
                          <FieldLabel htmlFor="neighborhood" required>
                            Bairro
                          </FieldLabel>
                          <input
                            id="neighborhood"
                            type="text"
                            autoComplete="address-level3"
                            value={newAddress.neighborhood}
                            onChange={(e) =>
                              setNewAddress((p) => ({ ...p, neighborhood: e.target.value }))
                            }
                            placeholder="Bairro"
                            className={inputCls()}
                          />
                        </div>
                      </div>

                      {/* Row: Cidade / Estado */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <FieldLabel htmlFor="city" required>
                            Cidade
                          </FieldLabel>
                          <input
                            id="city"
                            type="text"
                            autoComplete="address-level2"
                            value={newAddress.city}
                            onChange={(e) =>
                              setNewAddress((p) => ({ ...p, city: e.target.value }))
                            }
                            placeholder="Cidade"
                            className={inputCls()}
                          />
                        </div>
                        <div>
                          <FieldLabel htmlFor="state" required>
                            Estado
                          </FieldLabel>
                          <select
                            id="state"
                            autoComplete="address-level1"
                            value={newAddress.state}
                            onChange={(e) =>
                              setNewAddress((p) => ({ ...p, state: e.target.value }))
                            }
                            className={`${inputCls()} appearance-none`}
                          >
                            <option value="" disabled>
                              Selecionar UF
                            </option>
                            {BRAZILIAN_STATES.map((s) => (
                              <option key={s.uf} value={s.uf}>
                                {s.uf}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>

                      {/* Form actions: stacked on mobile, inline on sm+ */}
                      <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-3 pt-3 border-t border-gray-100">
                        <button
                          type="button"
                          onClick={() => {
                            setShowAddressForm(false);
                            setFormError("");
                          }}
                          className="w-full sm:w-auto px-5 py-2.5 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 active:bg-gray-100 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-400/40"
                        >
                          Cancelar
                        </button>
                        <button
                          type="button"
                          onClick={handleSaveAddress}
                          disabled={savingAddress}
                          className="w-full sm:w-auto flex items-center justify-center gap-2 px-5 py-2.5 text-sm font-semibold text-white bg-blue-900 rounded-lg hover:bg-blue-800 active:bg-blue-950 disabled:opacity-60 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
                        >
                          {savingAddress && (
                            <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                          )}
                          {savingAddress ? "Salvando..." : "Salvar endereço"}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </section>

            {/* ── STEP 3: Frete por vendedor ──
                Always rendered so the layout does not jump; dimmed + pointer-
                events blocked until an address is selected.
            ── */}
            <section
              className={`bg-white rounded-xl border shadow-sm p-5 sm:p-6 transition-opacity duration-200 ${
                selectedAddressId
                  ? "border-gray-100 opacity-100"
                  : "border-dashed border-gray-200 opacity-50 pointer-events-none select-none"
              }`}
              aria-disabled={!selectedAddressId}
            >
              <StepHeader
                step={3}
                icon={<Truck size={17} className="text-blue-800" />}
                title="Opções de frete"
                complete={step3Complete}
              />

              {/* Locked state hint */}
              {!selectedAddressId && (
                <p className="text-sm text-gray-400 italic">
                  Selecione um endereço acima para calcular o frete.
                </p>
              )}

              {selectedAddressId && (
                <>
                  {shippingError && (
                    <div className="mb-4">
                      <AlertBanner>{shippingError}</AlertBanner>
                    </div>
                  )}

                  {shippingLoading ? (
                    <LoadingRow label={syncingCart ? "Sincronizando carrinho..." : "Calculando frete..."} />
                  ) : (
                    <div className="space-y-6">
                      {Array.from(sellerGroups.keys()).map((sellerId) => {
                        const sellerQuote = quotesMap[sellerId];
                        const sellerName = sellerGroups.get(sellerId)?.seller_name ?? sellerId;

                        return (
                          <div key={sellerId}>
                            {/* Seller label inside shipping section */}
                            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2.5 flex items-center gap-1.5">
                              <User size={12} className="text-gray-400 shrink-0" aria-hidden="true" />
                              {sellerName}
                            </p>

                            {!sellerQuote ? (
                              <p className="text-sm text-gray-400 italic pl-1">
                                Aguardando cotações...
                              </p>
                            ) : sellerQuote.in_person_only ? (
                              <AlertBanner variant="warning">
                                Este vendedor realiza entrega presencial. Entre em contato após a compra.
                              </AlertBanner>
                            ) : (
                              <>
                                {sellerQuote.quotes.length === 0 ? (
                                  <p className="text-sm text-gray-500 italic pl-1">
                                    Nenhuma opção de frete disponível para este vendedor.
                                  </p>
                                ) : (
                                  <div
                                    className="space-y-2"
                                    role="radiogroup"
                                    aria-label={`Frete para ${sellerName}`}
                                  >
                                    {sellerQuote.quotes.map((option) => {
                                      const isSelected =
                                        selectedServices[sellerId] === option.service_id;
                                      return (
                                        <div
                                          key={option.service_id}
                                          role="radio"
                                          aria-checked={isSelected}
                                          tabIndex={0}
                                          onClick={() =>
                                            setSelectedServices((prev) => ({
                                              ...prev,
                                              [sellerId]: option.service_id,
                                            }))
                                          }
                                          onKeyDown={(e) => {
                                            if (e.key === "Enter" || e.key === " ") {
                                              e.preventDefault();
                                              setSelectedServices((prev) => ({
                                                ...prev,
                                                [sellerId]: option.service_id,
                                              }));
                                            }
                                          }}
                                          className={`flex items-center gap-3 p-3.5 rounded-xl border-2 cursor-pointer transition-colors min-h-[56px] focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-800/50 ${
                                            isSelected
                                              ? "border-blue-800 bg-blue-50"
                                              : "border-gray-200 hover:border-blue-300 hover:bg-gray-50"
                                          }`}
                                        >
                                          {/* Radio dot */}
                                          <div
                                            aria-hidden="true"
                                            className={`w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center transition-colors ${
                                              isSelected ? "border-blue-800" : "border-gray-300"
                                            }`}
                                          >
                                            {isSelected && (
                                              <div className="w-2 h-2 rounded-full bg-blue-800" />
                                            )}
                                          </div>

                                          {/* Carrier logo */}
                                          {option.company_picture && (
                                            <img
                                              src={option.company_picture}
                                              alt={option.company}
                                              className="h-6 w-auto object-contain shrink-0"
                                            />
                                          )}

                                          {/* Service name and delivery time */}
                                          <div className="flex-1 min-w-0">
                                            <p className="text-sm font-semibold text-gray-800 leading-tight">
                                              {option.name}
                                            </p>
                                            <p className="text-xs text-gray-500 mt-0.5">
                                              {option.company} &middot;{" "}
                                              {option.delivery_time}{" "}
                                              {option.delivery_time === 1
                                                ? "dia útil"
                                                : "dias úteis"}
                                            </p>
                                          </div>

                                          {/* Price — inherits selected color */}
                                          <span
                                            className={`text-sm font-bold shrink-0 ${
                                              isSelected ? "text-blue-800" : "text-gray-700"
                                            }`}
                                          >
                                            {formatCurrency(option.price)}
                                          </span>
                                        </div>
                                      );
                                    })}
                                  </div>
                                )}

                                {/* In-person sub-notice */}
                                {sellerQuote.has_in_person && (
                                  <div className="mt-3">
                                    <AlertBanner variant="warning">
                                      Alguns itens deste vendedor são entregues presencialmente. Entre
                                      em contato após a compra.
                                    </AlertBanner>
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </>
              )}
            </section>
          </div>

          {/* ════════════════════════════════════════
              Sidebar — order summary
              Sticky on lg, stacked below on mobile
          ════════════════════════════════════════ */}
          <aside className="w-full lg:w-80 shrink-0">
            <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 sm:p-6 lg:sticky lg:top-6">

              <h2 className="text-base font-semibold text-gray-900 mb-4 pb-3 border-b border-gray-100">
                Resumo do pedido
              </h2>

              {/* Line items */}
              <div className="space-y-2.5 text-sm">
                <div className="flex justify-between text-gray-600">
                  <span>Produtos</span>
                  <span className="font-medium text-gray-800">{formatCurrency(productSubtotal)}</span>
                </div>

                <div className="flex justify-between text-gray-600">
                  <span>Frete</span>
                  <span
                    className={`font-medium ${
                      shippingLoading || shippingTotal === 0 ? "text-gray-400" : "text-gray-800"
                    }`}
                  >
                    {shippingLoading
                      ? "Calculando..."
                      : shippingTotal > 0
                      ? formatCurrency(shippingTotal)
                      : "—"}
                  </span>
                </div>

                {/* Total row */}
                <div className="flex justify-between items-baseline pt-3 mt-1 border-t border-gray-200">
                  <span className="font-semibold text-gray-900">Total</span>
                  <span className="font-bold text-lg text-blue-800">
                    {formatCurrency(productSubtotal + shippingTotal)}
                  </span>
                </div>
              </div>

              {/* Address preview chip */}
              {selectedAddress && (
                <div className="mt-4 pt-4 border-t border-gray-100">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">
                    Entregando em
                  </p>
                  <p className="text-sm text-gray-700 leading-relaxed">
                    {selectedAddress.street}, {selectedAddress.number}
                    {selectedAddress.complement ? `, ${selectedAddress.complement}` : ""} —{" "}
                    {selectedAddress.city}/{selectedAddress.state}
                  </p>
                </div>
              )}

              {/* Primary CTA */}
              <button
                type="button"
                onClick={handleProceedToPayment}
                disabled={!allServicesSelected}
                aria-disabled={!allServicesSelected}
                className="mt-5 w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-blue-900 text-white text-sm font-semibold rounded-xl hover:bg-blue-800 active:bg-blue-950 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
              >
                Ir para pagamento
                <ChevronRight size={17} aria-hidden="true" />
              </button>

              {/* Contextual guidance — improved contrast (text-gray-500 instead of 400) */}
              {!selectedAddressId && !addressesLoading && (
                <p className="mt-3 text-xs text-center text-gray-500">
                  Selecione um endereço de entrega para continuar.
                </p>
              )}
              {selectedAddressId && !allServicesSelected && !shippingLoading && (
                <p className="mt-3 text-xs text-center text-gray-500">
                  Selecione o frete de cada vendedor para continuar.
                </p>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
