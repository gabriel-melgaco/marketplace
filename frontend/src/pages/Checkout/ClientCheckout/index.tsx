import { useState, useEffect, useMemo, useCallback, useRef } from "react";
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
  MessageSquare,
  Trash2,
} from "lucide-react";
import { useCart, type CartItem } from "@/contexts/CartContext";
import { addressService, type Address, type AddressCreateRequest } from "@/services/addressService";
import { shippingService } from "@/services/shippingService";
import { logisticsService } from "@/services/logisticsService";
import { formatCurrency } from "@/utils/formatters";
import { BRAZILIAN_STATES } from "@/constants/brazilianStates";
import { toPublicUrl } from "@/services/storageService";
import api from "@/api/axios";
import axios from "axios";
import Swal from "sweetalert2";

// ─── Types ────────────────────────────────────────────────────────────────────

// BUG 5 — 'in_person' is the value emitted by the "Combinar com vendedor"
// radio card inside mixed-seller quote sections.
export type SellerDeliveryMethod = 'melhor_envio' | 'vendor' | 'both' | 'in_person';

interface ItemRef {
  listing_id: number;
  title: string;
  shipping_method: string;
}

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
  in_person_items: ItemRef[];
  melhor_envio_items: ItemRef[];
  quotes: ShippingOption[];
}

/**
 * Represents the raw shape returned by the API per seller inside
 * `quotes_by_listing` (SellerQuoteEntry schema).
 * The canonical field is `services`; `quotes`/`options` are kept as
 * fallbacks for backward compatibility with older API responses.
 */
interface RawSellerQuote {
  seller_name?: string;
  in_person_only?: boolean;
  in_person_items?: { listing_id?: number; title?: string; shipping_method?: string }[];
  melhor_envio_items?: { listing_id?: number; title?: string; shipping_method?: string }[];
  services?: RawShippingOption[];
  quotes?: RawShippingOption[];
  options?: RawShippingOption[];
  error?: string;
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

export interface QuoteSnapshot {
  melhor_envio_items: { listing_id: number }[];
  in_person_items: { listing_id: number }[];
  in_person_only: boolean;
}

export interface CheckoutNavigationState {
  shippingAddressId: number;
  selectedServices: Record<string, number>;
  inPersonSellers: string[];
  sellerDeliveryMethods: Record<string, SellerDeliveryMethod>;
  quotesSnapshot: Record<string, QuoteSnapshot>;
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

/**
 * Builds a SellerQuote from the cart items' listing.shipping_method.
 * Used as fallback when the Melhor Envio API does not return data for a seller.
 */
function buildQuoteFromItems(sellerName: string, cartItems: CartItem[]): SellerQuote {
  const inPersonItems: ItemRef[] = [];
  const melhorEnvioItems: ItemRef[] = [];

  for (const item of cartItems) {
    const method = (item.listing as { shipping_method?: string }).shipping_method;
    const title =
      (item.listing as { title?: string }).title ||
      (item.listing as { product?: { name?: string } }).product?.name ||
      '';
    const ref: ItemRef = { listing_id: item.listing.id, title, shipping_method: method ?? '' };
    if (method === 'in_person' || method === 'both') inPersonItems.push(ref);
    if (method === 'melhor_envio' || method === 'both') melhorEnvioItems.push(ref);
  }

  const allInPerson = cartItems.every(
    (i) => (i.listing as { shipping_method?: string }).shipping_method === 'in_person',
  );

  return {
    seller_name: sellerName,
    in_person_only: allInPerson,
    has_in_person: inPersonItems.length > 0,
    in_person_items: inPersonItems,
    melhor_envio_items: melhorEnvioItems,
    quotes: [],
  };
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
  const { items, removeFromCart } = useCart();
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
  const [deletingAddressId, setDeletingAddressId] = useState<number | null>(null);

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
  const [sellerDeliveryMethods, setSellerDeliveryMethods] = useState<Record<string, SellerDeliveryMethod>>({});
  const [syncingCart, setSyncingCart] = useState(false);
  const [perSellerLoading, setPerSellerLoading] = useState<Record<string, boolean>>({});

  // Refs for stale-closure-safe access inside async callbacks
  const addressesRef = useRef<Address[]>([]);
  useEffect(() => { addressesRef.current = addresses; }, [addresses]);
  const selectedAddressIdRef = useRef<number | null>(null);
  useEffect(() => { selectedAddressIdRef.current = selectedAddressId; }, [selectedAddressId]);
  const quotesMapRef = useRef<Record<string, SellerQuote>>({});
  useEffect(() => { quotesMapRef.current = quotesMap; }, [quotesMap]);

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

  // ── Sync cart then calculate shipping when address is selected ──
  // Dependency is ONLY selectedAddressId. Cart items are captured once from
  // the closure — they are already populated when the component mounts and
  // must not change during checkout. Including items/sellerGroups would cause
  // the effect to re-run mid-flow, restarting the sync before it finishes.
  useEffect(() => {
    if (!selectedAddressId || items.length === 0) return;

    let cancelled = false;

    // Capture stable snapshots so we read consistent values throughout the
    // async flow without adding them to the dependency array.
    const addressId = selectedAddressId;
    const cartItems = items;
    const groups = sellerGroups;

    async function syncAndCalculate() {
      try {
        // ── Step 1: sync backend cart (must complete before shipping call) ──
        setSellerDeliveryMethods({});
        setSyncingCart(true);
        setShippingLoading(true);
        setShippingError("");

        // 404 means the cart doesn't exist yet (first purchase or new session)
        // — treat it as already empty and continue adding items normally.
        try {
          await api.delete("/orders/cart/clear/");
        } catch (clearErr: unknown) {
          if (!axios.isAxiosError(clearErr) || clearErr.response?.status !== 404) {
            throw clearErr;
          }
        }

        let unavailableCount = 0;
        for (const item of cartItems) {
          if (cancelled) return;
          try {
            await api.post("/orders/cart/add/", {
              listing: item.listing.id,
              quantity: item.quantity,
            });
          } catch (addErr: unknown) {
            // 404 = listing no longer exists or is inactive — skip and continue
            if (axios.isAxiosError(addErr) && addErr.response?.status === 404) {
              unavailableCount++;
            } else {
              throw addErr;
            }
          }
        }
        if (unavailableCount > 0 && unavailableCount === cartItems.length) {
          // All items failed — build from listing data and abort sync
          const fallback: Record<string, SellerQuote> = {};
          for (const [sellerId, group] of groups.entries()) {
            fallback[sellerId] = buildQuoteFromItems(group.seller_name, group.items);
          }
          const fallbackMethods: Record<string, SellerDeliveryMethod> = {};
          for (const [sellerId, quote] of Object.entries(fallback)) {
            if (quote.in_person_only) fallbackMethods[sellerId] = 'vendor';
            else if (!quote.has_in_person) fallbackMethods[sellerId] = 'melhor_envio';
          }
          setQuotesMap(fallback);
          setSellerDeliveryMethods(fallbackMethods);
          setShippingError("Não foi possível verificar a disponibilidade dos itens. Confirme com o vendedor antes de prosseguir.");
          return;
        }

        if (cancelled) return;
        setSyncingCart(false);

        // ── Step 2: calculate shipping (cart is guaranteed populated) ──────
        const response = await shippingService.calculateShipping({ shipping_address_id: addressId });
        if (cancelled) return;

        const newQuotes: Record<string, SellerQuote> = {};
        const newInPerson: string[] = [];

        for (const [sellerId, raw] of Object.entries(response.quotes_by_seller ?? {})) {
          const rawData = raw as RawSellerQuote;
          const inPersonOnly = rawData.in_person_only === true;

          if (inPersonOnly) newInPerson.push(sellerId);

          // `services` is the canonical field per SellerQuoteEntry schema;
          // `quotes`/`options` kept as fallbacks for older API responses.
          const rawOptions = rawData.services ?? rawData.quotes ?? rawData.options ?? [];
          const quotes = rawOptions.map(parseRawShippingOption);

          const inPersonItems: ItemRef[] = (rawData.in_person_items ?? []).map((item) => ({
            listing_id: item.listing_id ?? 0,
            title: item.title ?? "",
            shipping_method: item.shipping_method ?? "",
          }));

          const melhorEnvioItems: ItemRef[] = (rawData.melhor_envio_items ?? []).map((item) => ({
            listing_id: item.listing_id ?? 0,
            title: item.title ?? "",
            shipping_method: item.shipping_method ?? "",
          }));

          // Also derive has_in_person from cart listings' shipping_method so that
          // sellers with shipping_method 'both' always show the delivery method
          // selector even when the API returns an empty in_person_items array.
          const cartGroup = groups.get(sellerId);
          const hasInPersonFromCart = cartGroup?.items.some((i) => {
            const m = (i.listing as { shipping_method?: string }).shipping_method;
            return m === 'in_person' || m === 'both';
          }) ?? false;

          newQuotes[sellerId] = {
            seller_name: rawData.seller_name ?? groups.get(sellerId)?.seller_name ?? sellerId,
            in_person_only: inPersonOnly,
            has_in_person: inPersonItems.length > 0 || hasInPersonFromCart,
            in_person_items: inPersonItems,
            melhor_envio_items: melhorEnvioItems,
            quotes,
          };
        }

        // Fallback: sellers absent from the API response → build from listing.shipping_method
        for (const [sellerId, group] of groups.entries()) {
          if (!newQuotes[sellerId]) {
            newQuotes[sellerId] = buildQuoteFromItems(group.seller_name, group.items);
          }
        }

        const autoMethods: Record<string, SellerDeliveryMethod> = {};
        const autoServices: Record<string, number> = {};

        for (const [sellerId, quote] of Object.entries(newQuotes)) {
          if (quote.in_person_only) {
            autoMethods[sellerId] = 'vendor';
          } else if (!quote.has_in_person) {
            autoMethods[sellerId] = 'melhor_envio';
            // Auto-seleciona o mais barato (API já retorna ordenado por preço)
            if (quote.quotes.length > 0) {
              autoServices[sellerId] = quote.quotes[0].service_id;
            }
          }
          // mixed sellers: sem auto-seleção, usuário escolhe
        }
        setSellerDeliveryMethods(autoMethods);
        setSelectedServices(autoServices);

        setQuotesMap(newQuotes);
        setInPersonSellers(newInPerson);
      } catch (err: unknown) {
        if (cancelled) return;

        if (axios.isAxiosError(err) && err.response?.status === 422) {
          const errData = err.response.data as { error?: string };
          if (errData.error === "insufficient_me_balance") {
            await Swal.fire({
              icon: "error",
              title: "Envio indisponível",
              text: "Este vendedor não pode processar o envio no momento. Tente novamente mais tarde ou contate o vendedor diretamente.",
            });
            return;
          }
        }

        if (axios.isAxiosError(err) && err.response?.status === 400) {
          const msg = ((err.response.data as { error?: string })?.error ?? '').toLowerCase();
          if (msg.includes('cotação') || msg.includes('cotacao') || msg.includes('expirada')) {
            navigate('/checkout', {
              state: { error: 'Sua cotação de frete expirou. Por favor, recalcule o frete.' },
            });
            return;
          }
        }

        // Even when the API fails, show shipping options derived from listing.shipping_method
        const fallback: Record<string, SellerQuote> = {};
        for (const [sellerId, group] of groups.entries()) {
          fallback[sellerId] = buildQuoteFromItems(group.seller_name, group.items);
        }
        setQuotesMap(fallback);

        const fallbackMethods: Record<string, SellerDeliveryMethod> = {};
        for (const [sellerId, quote] of Object.entries(fallback)) {
          if (quote.in_person_only) fallbackMethods[sellerId] = 'vendor';
          else if (!quote.has_in_person) fallbackMethods[sellerId] = 'melhor_envio';
        }
        setSellerDeliveryMethods(fallbackMethods);

        setShippingError(getAxiosErrorMessage(err, "Erro ao calcular o frete."));
      } finally {
        if (!cancelled) {
          setSyncingCart(false);
          setShippingLoading(false);
        }
      }
    }

    syncAndCalculate();
    return () => { cancelled = true; };
  }, [selectedAddressId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Delete address ──
  const handleDeleteAddress = useCallback(async (id: number) => {
    const { isConfirmed } = await Swal.fire({
      icon: "warning",
      title: "Excluir endereço?",
      text: "Esta ação não pode ser desfeita.",
      showCancelButton: true,
      confirmButtonText: "Excluir",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#dc2626",
    });
    if (!isConfirmed) return;

    try {
      setDeletingAddressId(id);
      await addressService.deleteAddress(id);
      setAddresses((prev) => {
        const remaining = prev.filter((a) => a.id !== id);
        if (selectedAddressId === id) {
          setSelectedAddressId(remaining[0]?.id ?? null);
        }
        return remaining;
      });
    } catch (err: unknown) {
      await Swal.fire({
        icon: "error",
        title: "Erro ao excluir",
        text: getAxiosErrorMessage(err, "Não foi possível excluir o endereço."),
      });
    } finally {
      setDeletingAddressId(null);
    }
  }, [selectedAddressId]);

  // ── CEP auto-fill: dispara assim que 8 dígitos são digitados ──
  useEffect(() => {
    const clean = newAddress.zipcode.replace(/\D/g, "");
    if (clean.length !== 8) return;

    let cancelled = false;
    setCepLoading(true);

    addressService
      .lookupCEP({ zipcode: clean })
      .then((result) => {
        if (cancelled) return;
        setNewAddress((prev) => ({
          ...prev,
          street: result.street || prev.street,
          neighborhood: result.neighborhood || prev.neighborhood,
          city: result.city || prev.city,
          state: result.state || prev.state,
        }));
      })
      .catch(() => {
        // falha silenciosa — usuário preenche manualmente
      })
      .finally(() => {
        if (!cancelled) setCepLoading(false);
      });

    return () => {
      cancelled = true;
    };
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

      // ── Validar se o CEP confere com a cidade/estado preenchidos ──
      const cleanZip = newAddress.zipcode.replace(/\D/g, "");
      try {
        const cepResult = await addressService.lookupCEP({ zipcode: cleanZip });
        const normalize = (s: string) =>
          s.trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        const cityOk = normalize(cepResult.city) === normalize(newAddress.city);
        const stateOk = cepResult.state.toUpperCase() === newAddress.state.toUpperCase();
        if (!cityOk || !stateOk) {
          setFormError(
            `O CEP ${newAddress.zipcode} corresponde a ${cepResult.city}/${cepResult.state}, ` +
            `mas o endereço preenchido é ${newAddress.city}/${newAddress.state}. ` +
            `Corrija o CEP ou os campos Cidade e Estado.`
          );
          return;
        }
      } catch {
        // Lookup falhou — prosseguir sem bloquear o salvamento
      }

      const created = await addressService.createAddress({
        ...newAddress,
        zipcode: cleanZip,
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

  // ── Delivery method selection ──
  const handleSelectDeliveryMethod = useCallback(async (sellerId: string, method: SellerDeliveryMethod) => {
    setSellerDeliveryMethods(prev => ({ ...prev, [sellerId]: method }));
    if (method === 'vendor' || method === 'in_person') {
      setSelectedServices(prev => {
        const next = { ...prev };
        delete next[sellerId];
        return next;
      });
    }

    // When Melhor Envio is selected and quotes are not yet loaded, fetch them
    // using the same freight-quote endpoint used in ProductDetail.
    if (method === 'melhor_envio' || method === 'both') {
      const currentQuote = quotesMapRef.current[sellerId];
      if (!currentQuote || currentQuote.quotes.length > 0) return;
      if (currentQuote.melhor_envio_items.length === 0) return;

      const address = addressesRef.current.find(a => a.id === selectedAddressIdRef.current);
      if (!address) return;

      const cep = address.zipcode.replace(/\D/g, '');
      if (cep.length !== 8) return;

      const firstItem = currentQuote.melhor_envio_items[0];
      setPerSellerLoading(prev => ({ ...prev, [sellerId]: true }));
      try {
        const result = await logisticsService.getFreightQuote(firstItem.listing_id, cep);
        if (result.available && result.options && result.options.length > 0) {
          const parsedOptions: ShippingOption[] = result.options.map(o => ({
            service_id: o.service_id,
            name: o.name,
            company: o.company,
            company_picture: toSafeImageUrl(o.company_picture),
            price: Number(o.price),
            delivery_time: o.delivery_days,
          }));
          setQuotesMap(prev => ({
            ...prev,
            [sellerId]: { ...prev[sellerId], quotes: parsedOptions },
          }));
        }
      } catch {
        // fail silently — user sees empty-state message
      } finally {
        setPerSellerLoading(prev => ({ ...prev, [sellerId]: false }));
      }
    }
  }, []);

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
      if (!quote) return false;
      if (quote.in_person_only) return true;
      const method = sellerDeliveryMethods[sid];
      if (!method) return false;
      // BUG 5 — 'in_person' (Combinar com vendedor) and 'vendor' need no service_id
      if (method === 'vendor' || method === 'in_person') return true;
      if (quote.quotes.length === 0) return true;
      return selectedServices[sid] !== undefined;
    });
  }, [selectedAddressId, shippingLoading, sellerGroups, quotesMap, sellerDeliveryMethods, selectedServices]);

  const handleProceedToPayment = useCallback(() => {
    if (!allServicesSelected || !selectedAddressId) return;
    navigate("/payment", {
      state: {
        shippingAddressId: selectedAddressId,
        selectedServices,
        // BUG 5 — 'in_person' (Combinar com vendedor) must also appear in inPersonSellers
        inPersonSellers: Object.entries(sellerDeliveryMethods)
          .filter(([, m]) => m === 'vendor' || m === 'both' || m === 'in_person')
          .map(([id]) => id),
        sellerDeliveryMethods,
        quotesSnapshot: Object.fromEntries(
          Object.entries(quotesMap).map(([id, q]) => [
            id,
            {
              melhor_envio_items: q.melhor_envio_items.map((i) => ({ listing_id: i.listing_id })),
              in_person_items: q.in_person_items.map((i) => ({ listing_id: i.listing_id })),
              in_person_only: q.in_person_only,
            },
          ])
        ),
      } as CheckoutNavigationState,
    });
  }, [allServicesSelected, selectedAddressId, navigate, selectedServices, sellerDeliveryMethods, quotesMap]);

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

                            {/* Line total + remove */}
                            <div className="shrink-0 self-center text-right flex flex-col items-end gap-2">
                              <p className="text-sm font-bold text-blue-800">
                                {formatCurrency(unitPrice * item.quantity)}
                              </p>
                              <button
                                type="button"
                                onClick={() => removeFromCart(item.listing.id)}
                                aria-label={`Remover ${productName} do carrinho`}
                                className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-red-500 border border-red-200 hover:bg-red-50 hover:border-red-400 hover:text-red-600 active:bg-red-100 transition-colors"
                              >
                                <Trash2 size={11} aria-hidden="true" />
                                Remover
                              </button>
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

                            {/* Actions: check icon + delete button */}
                            <div className="flex items-start gap-1.5 shrink-0">
                              {isSelected && (
                                <CheckCircle2
                                  size={18}
                                  className="text-blue-800 mt-0.5"
                                  aria-hidden="true"
                                />
                              )}
                              <button
                                type="button"
                                aria-label={`Excluir endereço de ${addr.recipient_name}`}
                                disabled={deletingAddressId === addr.id}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteAddress(addr.id);
                                }}
                                className="p-1 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400/40 disabled:opacity-50 disabled:cursor-not-allowed"
                              >
                                {deletingAddressId === addr.id ? (
                                  <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                                ) : (
                                  <Trash2 size={15} aria-hidden="true" />
                                )}
                              </button>
                            </div>
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
                              placeholder="00000-000"
                              className={`${inputCls()} pr-9`}
                            />
                            {cepLoading && (
                              <Loader2
                                size={15}
                                className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-blue-800"
                                aria-label="Buscando endereço..."
                              />
                            )}
                          </div>
                          <p className="mt-1 text-xs text-gray-400">
                            {cepLoading
                              ? "Buscando endereço..."
                              : "Preenchido automaticamente ao digitar o CEP."}
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
              className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 sm:p-6"
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
                    <LoadingRow label={syncingCart ? "Preparando seu carrinho..." : "Calculando opções de frete..."} />
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
                              <p className="text-sm text-gray-400 italic pl-1">Aguardando cotações...</p>
                            ) : sellerQuote.in_person_only ? (
                              // Case 1: vendor-only delivery — BUG 5: amber info card, no selection needed
                              <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl">
                                <p className="text-sm font-medium text-amber-800">Entrega presencial</p>
                                <p className="text-sm text-amber-700 mt-1">
                                  Este vendedor realiza apenas entrega presencial.
                                  Após confirmar o pedido, combine os detalhes pelo chat.
                                </p>
                              </div>
                            ) : !sellerQuote.has_in_person ? (
                              // Case 2: ME-only — show quotes directly
                              <div role="radiogroup" aria-label={`Frete para ${sellerName}`} className="space-y-2">
                                {sellerQuote.quotes.length === 0 ? (
                                  <p className="text-sm text-gray-500 italic pl-1">Nenhuma opção de frete disponível.</p>
                                ) : (
                                  sellerQuote.quotes.map((option) => {
                                    const isSelected = selectedServices[sellerId] === option.service_id;
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
                                        <div
                                          aria-hidden="true"
                                          className={`w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center transition-colors ${
                                            isSelected ? "border-blue-800" : "border-gray-300"
                                          }`}
                                        >
                                          {isSelected && <div className="w-2 h-2 rounded-full bg-blue-800" />}
                                        </div>
                                        {option.company_picture && (
                                          <img
                                            src={option.company_picture}
                                            alt={option.company}
                                            className="h-6 w-auto object-contain shrink-0"
                                          />
                                        )}
                                        <div className="flex-1 min-w-0">
                                          <p className="text-sm font-semibold text-gray-800 leading-tight">{option.name}</p>
                                          <p className="text-xs text-gray-500 mt-0.5">
                                            {option.company} &middot;{" "}
                                            {option.delivery_time}{" "}
                                            {option.delivery_time === 1 ? "dia útil" : "dias úteis"}
                                          </p>
                                        </div>
                                        <span
                                          className={`text-sm font-bold shrink-0 ${
                                            isSelected ? "text-blue-800" : "text-gray-700"
                                          }`}
                                        >
                                          {formatCurrency(option.price)}
                                        </span>
                                      </div>
                                    );
                                  })
                                )}
                              </div>
                            ) : (
                              // Case 3: mixed seller — delivery method selector + conditional content
                              <>
                                {/* Delivery method buttons */}
                                <div
                                  className="flex flex-wrap gap-2 mb-4"
                                  role="radiogroup"
                                  aria-label={`Método de entrega para ${sellerName}`}
                                >
                                  {(
                                    [
                                      { value: 'melhor_envio' as SellerDeliveryMethod, label: 'Melhor Envio', icon: <Truck size={14} /> },
                                      { value: 'vendor' as SellerDeliveryMethod, label: 'Entrega pelo Vendedor', icon: <MessageSquare size={14} /> },
                                      { value: 'both' as SellerDeliveryMethod, label: 'Ambos', icon: <Package size={14} /> },
                                    ] as { value: SellerDeliveryMethod; label: string; icon: React.ReactNode }[]
                                  ).map(({ value, label, icon }) => {
                                    const sel = sellerDeliveryMethods[sellerId] === value;
                                    return (
                                      <button
                                        key={value}
                                        type="button"
                                        role="radio"
                                        aria-checked={sel}
                                        onClick={() => handleSelectDeliveryMethod(sellerId, value)}
                                        className={`flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border-2 font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-800/50 ${
                                          sel
                                            ? 'border-blue-800 bg-blue-50 text-blue-800'
                                            : 'border-gray-200 text-gray-600 hover:border-blue-300 hover:bg-gray-50'
                                        }`}
                                      >
                                        {icon}
                                        {label}
                                      </button>
                                    );
                                  })}
                                </div>

                                {/* ME quotes when melhor_envio or both selected */}
                                {(sellerDeliveryMethods[sellerId] === 'melhor_envio' || sellerDeliveryMethods[sellerId] === 'both') && (
                                  perSellerLoading[sellerId] ? (
                                    <LoadingRow label="Buscando opções de frete..." />
                                  ) : sellerQuote.quotes.length === 0 ? (
                                    <p className="text-sm text-gray-500 italic pl-1">Nenhuma opção de frete disponível.</p>
                                  ) : (
                                    <div role="radiogroup" aria-label={`Serviços Melhor Envio para ${sellerName}`} className="space-y-2 mb-3">
                                      {sellerQuote.quotes.map((option) => {
                                        const isSelected = selectedServices[sellerId] === option.service_id;
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
                                            <div
                                              aria-hidden="true"
                                              className={`w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center transition-colors ${
                                                isSelected ? "border-blue-800" : "border-gray-300"
                                              }`}
                                            >
                                              {isSelected && <div className="w-2 h-2 rounded-full bg-blue-800" />}
                                            </div>
                                            {option.company_picture && (
                                              <img
                                                src={option.company_picture}
                                                alt={option.company}
                                                className="h-6 w-auto object-contain shrink-0"
                                              />
                                            )}
                                            <div className="flex-1 min-w-0">
                                              <p className="text-sm font-semibold text-gray-800 leading-tight">{option.name}</p>
                                              <p className="text-xs text-gray-500 mt-0.5">
                                                {option.company} &middot;{" "}
                                                {option.delivery_time}{" "}
                                                {option.delivery_time === 1 ? "dia útil" : "dias úteis"}
                                              </p>
                                            </div>
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
                                  )
                                )}

                                {/* Contact note when vendor or both selected */}
                                {(sellerDeliveryMethods[sellerId] === 'vendor' || sellerDeliveryMethods[sellerId] === 'both') && (
                                  <AlertBanner variant="warning">
                                    Entre em contato com o vendedor para combinar a entrega dos itens a cargo dele.
                                  </AlertBanner>
                                )}

                                {/* No method selected yet */}
                                {!sellerDeliveryMethods[sellerId] && (
                                  <p className="text-sm text-gray-400 italic pl-1">Selecione o método de entrega acima.</p>
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
