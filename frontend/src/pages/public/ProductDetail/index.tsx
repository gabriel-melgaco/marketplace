import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  ChevronLeft,
  ChevronRight,
  Package,
  MessageCircle,
  MapPin,
  Eye,
  Calendar,
  Tag,
  Box,
  User,
  Weight,
  Ruler,
  ShoppingCart,
  ShoppingBag,
  Loader2,
  AlertCircle,
  Truck,
} from "lucide-react";
import { productService } from "@/services/productService";
import { toPublicUrl } from "@/services/storageService";
import { useAuth } from "@/contexts/AuthContext";
import { useCart } from "@/contexts/CartContext";
import { Footer } from "@/components/layout/Footer";
import { ProductDetailSkeleton } from "@/components/skeletons/ProductDetailSkeleton";
import { ProductCard, formatListingDate } from "@/components/ui/ProductCard";
import type {
  MarketplaceListingDetail,
  MarketplaceListing,
  ListingFreightQuoteResponse,
  ShippingMethod,
} from "@/types/product";
import { logisticsService } from "@/services/logisticsService";

function FreightCalculator({ listingId }: { listingId: number }) {
  const [cep, setCep] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ListingFreightQuoteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleCepChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value.replace(/\D/g, "").slice(0, 8);
    const formatted =
      raw.length > 5 ? `${raw.slice(0, 5)}-${raw.slice(5)}` : raw;
    setCep(formatted);
    if (result) setResult(null);
    if (error) setError(null);
  };

  const handleCalculate = async () => {
    const rawCep = cep.replace(/\D/g, "");
    if (rawCep.length !== 8) return;

    // Cancel any in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const data = await logisticsService.getFreightQuote(listingId, rawCep);
      setResult(data);
    } catch (err: unknown) {
      const e = err as { name?: string };
      if (e.name !== "AbortError" && e.name !== "CanceledError") {
        setError("Não foi possível calcular o frete. Tente novamente.");
      }
    } finally {
      setLoading(false);
    }
  };

  const rawCep = cep.replace(/\D/g, "");

  return (
    <div className="bg-bg-1 border border-white/10 rounded-xl p-5">
      <h3 className="text-ink-1 font-semibold text-sm mb-3 flex items-center gap-2">
        <Truck size={16} className="text-gold" />
        Calcular Frete
      </h3>
      <div className="flex gap-2">
        <input
          type="text"
          inputMode="numeric"
          placeholder="00000-000"
          value={cep}
          onChange={handleCepChange}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleCalculate();
          }}
          maxLength={9}
          className="flex-1 px-3 py-2 bg-bg-2 border border-white/10 rounded-lg text-sm text-ink-1 placeholder:text-ink-3 focus:outline-none focus:ring-2 focus:ring-gold/20 focus:border-gold/50 transition"
        />
        <button
          onClick={handleCalculate}
          disabled={rawCep.length !== 8 || loading}
          className="px-4 py-2 bg-gold text-gold-deep rounded-lg text-sm font-semibold hover:bg-gold/90 transition disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
        >
          {loading ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            "Calcular"
          )}
        </button>
      </div>

      {error && (
        <div className="mt-3 flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2.5">
          <AlertCircle size={15} className="text-red-400 shrink-0 mt-0.5" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {result && !result.available && (
        <div className="mt-3 flex items-start gap-2 bg-gold/10 border border-gold/30 rounded-lg px-3 py-2.5">
          <AlertCircle size={15} className="text-gold shrink-0 mt-0.5" />
          <p className="text-sm text-gold">
            {result.message || "Frete não disponível para este CEP."}
          </p>
        </div>
      )}

      {result?.available && result.options && result.options.length > 0 && (
        <div className="mt-3 divide-y divide-white/10">
          {result.options.map((option) => (
            <div
              key={option.service_id}
              className="flex items-center justify-between py-2.5"
            >
              <div className="flex items-center gap-2">
                {option.company_picture && (
                  <img
                    src={option.company_picture}
                    alt={option.company}
                    className="h-5 max-w-16 object-contain bg-ink-1/5 rounded px-1 py-0.5 filter brightness-90 contrast-110"
                  />
                )}
                <div>
                  <p className="text-sm font-medium text-ink-1">
                    {option.name}
                  </p>
                  <p className="text-xs text-ink-3">
                    Prazo: {option.delivery_days}{" "}
                    {option.delivery_days === 1
                      ? "dia útil"
                      : "dias úteis"}
                  </p>
                </div>
              </div>
              <p className="text-sm font-semibold text-gold">
                R${" "}
                {Number(option.price).toLocaleString("pt-BR", {
                  minimumFractionDigits: 2,
                })}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const SHIPPING_METHOD_LABELS: Record<
  NonNullable<ShippingMethod>,
  { label: string; icon: "truck" | "mappin" | "both" }
> = {
  in_person: { label: "Somente retirada presencial", icon: "mappin" },
  melhor_envio: { label: "Somente envio via transportadora", icon: "truck" },
  both: { label: "Envio via transportadora ou retirada presencial", icon: "both" },
};

function ShippingMethodInfo({ method }: { method: ShippingMethod | undefined }) {
  if (!method) return null;
  const { label, icon } = SHIPPING_METHOD_LABELS[method];
  return (
    <div className="bg-bg-1 border border-white/10 rounded-xl p-4 flex items-center gap-3">
      {icon === "mappin" ? (
        <MapPin size={16} className="text-gold shrink-0" />
      ) : (
        <Truck size={16} className="text-gold shrink-0" />
      )}
      <div>
        <p className="text-xs text-ink-3">Método de entrega</p>
        <p className="text-sm font-medium text-ink-1">{label}</p>
      </div>
    </div>
  );
}

function formatPrice(price: string): string {
  const num = Number(price);
  if (isNaN(num)) return price;
  return num.toLocaleString("pt-BR", { minimumFractionDigits: 2 });
}

function getLocation(listing: MarketplaceListingDetail): string {
  const addr = listing.shipping_address;
  if (!addr) return "";
  const parts: string[] = [];
  if (addr.city) parts.push(addr.city);
  if (addr.state) parts.push(addr.state);
  return parts.join(" - ");
}

function ImageCarousel({
  images,
  productName,
}: {
  images: MarketplaceListingDetail["images"];
  productName: string;
}) {
  const [currentIndex, setCurrentIndex] = useState(0);

  const sortedImages = useMemo(() => {
    return [...images].sort((a, b) => {
      if (a.is_primary) return -1;
      if (b.is_primary) return 1;
      return a.order - b.order;
    });
  }, [images]);

  // Reset carousel index when images change (e.g., navigating to different product)
  useEffect(() => {
    setCurrentIndex(0);
  }, [images]);

  const goToPrevious = useCallback(() => {
    setCurrentIndex((prev) =>
      prev === 0 ? sortedImages.length - 1 : prev - 1,
    );
  }, [sortedImages.length]);

  const goToNext = useCallback(() => {
    setCurrentIndex((prev) =>
      prev === sortedImages.length - 1 ? 0 : prev + 1,
    );
  }, [sortedImages.length]);

  if (sortedImages.length === 0) {
    return (
      <div className="aspect-4/3 bg-bg-2 border border-white/10 rounded-xl flex items-center justify-center">
        <div className="text-ink-3 text-center p-4">
          <Package size={60} className="mx-auto mb-2" />
          <p>Sem imagem</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Main image */}
      <div className="relative">
        <div
          className="aspect-4/3 rounded-xl overflow-hidden max-h-150 mx-auto"
          style={{ background: 'radial-gradient(circle at 50% 40%, #25252d 0%, #141418 100%)' }}
        >
          <img
            src={toPublicUrl(sortedImages[currentIndex].image_url)}
            alt={`${productName} - Imagem ${currentIndex + 1} de ${sortedImages.length}`}
            className="w-full h-full object-contain [image-rendering:auto]"
            loading="eager"
            decoding="async"
            fetchPriority="high"
            onError={(e) => {
              e.currentTarget.src =
                "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100'%3E%3Crect width='100' height='100' fill='%23e5e7eb'/%3E%3Ctext x='50' y='50' font-size='14' text-anchor='middle' dy='.3em' fill='%239ca3af'%3EImagem não disponível%3C/text%3E%3C/svg%3E";
            }}
          />
        </div>

        {sortedImages.length > 1 && (
          <>
            <button
              onClick={goToPrevious}
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-bg-0/80 backdrop-blur hover:bg-bg-0 border border-white/10 text-ink-1 rounded-full p-3 transition-all hover:scale-110 focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
              aria-label="Imagem anterior"
            >
              <ChevronLeft size={24} />
            </button>
            <button
              onClick={goToNext}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-bg-0/80 backdrop-blur hover:bg-bg-0 border border-white/10 text-ink-1 rounded-full p-3 transition-all hover:scale-110 focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
              aria-label="Próxima imagem"
            >
              <ChevronRight size={24} />
            </button>

            {/* Counter badge */}
            <div className="absolute bottom-3 right-3 bg-bg-0/80 backdrop-blur text-ink-1 border border-white/10 text-xs px-3 py-1 rounded-full font-medium">
              {currentIndex + 1} / {sortedImages.length}
            </div>
          </>
        )}
      </div>

      {/* Thumbnail strip */}
      {sortedImages.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent">
          {sortedImages.map((img, idx) => (
            <button
              key={img.id}
              onClick={() => setCurrentIndex(idx)}
              className={`shrink-0 w-20 h-20 rounded-lg overflow-hidden border-2 transition-all focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1 ${
                idx === currentIndex
                  ? "border-gold ring-1 ring-gold/50"
                  : "border-white/10 opacity-60 hover:opacity-100 hover:border-white/20"
              }`}
              aria-label={`Ver imagem ${idx + 1}`}
            >
              <img
                src={toPublicUrl(img.image_url)}
                alt={`${productName} - Miniatura ${idx + 1}`}
                className="w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function ProductDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const { addToCart } = useCart();

  const [listing, setListing] = useState<MarketplaceListingDetail | null>(null);
  const [suggestedListings, setSuggestedListings] = useState<
    MarketplaceListing[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;

    const numericId = Number(id);
    if (isNaN(numericId)) {
      setError("ID de produto inválido.");
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function fetchData() {
      try {
        setLoading(true);
        setError(null);

        const [listingData, allListings] = await Promise.all([
          productService.getListingById(numericId),
          productService.getListings(),
        ]);

        if (!cancelled) {
          setListing(listingData);
          setSuggestedListings(
            allListings.results.filter((l) => l.id !== numericId).slice(0, 8),
          );
        }

        productService.incrementListingView(numericId).catch((err) => {
          console.warn("Falha ao incrementar visualização:", err);
        });
      } catch (err) {
        console.error("Erro ao buscar detalhes do anúncio:", err);
        if (!cancelled) {
          setError("Erro ao carregar detalhes do produto. Tente novamente.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchData();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleBuyClick = () => {
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    if (!listing || listing.quantity <= 0) return;
    addToCart(listing);
    navigate("/checkout");
  };

  const handleAddToCartClick = () => {
    if (!listing) return;
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    if (listing.quantity <= 0) return;
    addToCart(listing);
    import("sweetalert2").then(({ default: Swal }) => {
      Swal.fire({
        icon: "success",
        title: "Adicionado ao carrinho!",
        toast: true,
        position: "top-end",
        showConfirmButton: false,
        timer: 2000,
        timerProgressBar: true,
      });
    });
  };

  const handleChatClick = () => {
    if (isAuthenticated) {
      navigate(`/chat/${listing?.id ?? id}`);
    } else {
      navigate("/login");
    }
  };

  if (loading) {
    return <ProductDetailSkeleton />;
  }

  if (error || !listing) {
    return (
      <div className="min-h-screen bg-bg-0">
        <div className="text-center py-20">
          <p className="text-ink-1 text-lg mb-4">
            {error || "Produto não encontrado."}
          </p>
          <Link
            to="/"
            className="px-4 py-2 bg-gold text-gold-deep rounded-lg font-semibold hover:bg-gold/90 transition focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-0"
          >
            Voltar para o início
          </Link>
        </div>
      </div>
    );
  }

  const firstPackage = listing.packages?.[0];
  const hasDimensions =
    listing.weight_kg ||
    listing.height_cm ||
    listing.width_cm ||
    listing.length_cm ||
    (listing.packages?.length ?? 0) > 0;

  return (
    <div className="min-h-screen bg-bg-0">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 pb-24">
        {/* Main content grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Image + Info */}
          <div className="lg:col-span-2 space-y-5">
            {/* Image Carousel */}
            <div className="bg-bg-1 border border-white/10 rounded-xl p-4 sm:p-6">
              <ImageCarousel
                images={listing.images}
                productName={listing.product.name}
              />
            </div>

            {/* Mobile: Price/Chat + Seller (after image on mobile, hidden on desktop) */}
            <div className="lg:hidden space-y-4">
              {/* Price + Buy buttons */}
              <div className="bg-bg-1 border border-white/10 rounded-xl p-5">
                <p className="font-display text-3xl font-bold text-ink-1 tabular-nums tracking-[-0.02em] mb-4">
                  R$ {formatPrice(listing.price)}
                </p>
                <div className="space-y-3">
                  <button
                    onClick={handleBuyClick}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gold text-gold-deep rounded-lg font-semibold hover:bg-gold/90 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
                  >
                    <ShoppingBag size={20} />
                    Comprar
                  </button>
                  <button
                    onClick={handleAddToCartClick}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-ink-1 text-bg-0 rounded-lg font-semibold hover:bg-ink-2 transition-colors focus:outline-none focus:ring-2 focus:ring-ink-1/40 focus:ring-offset-2 focus:ring-offset-bg-1"
                  >
                    <ShoppingCart size={20} />
                    Adicionar ao Carrinho
                  </button>
                </div>
              </div>

              {/* Seller info */}
              <div className="bg-bg-1 border border-white/10 rounded-xl p-5">
                <h3 className="text-xs font-semibold text-ink-3 uppercase tracking-wide mb-3">
                  Vendedor
                </h3>
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-gold/15 rounded-full flex items-center justify-center shrink-0">
                    <User size={22} className="text-gold" />
                  </div>
                  <div>
                    <p className="font-semibold text-ink-1">
                      {listing.seller_name}
                    </p>
                    {listing.shipping_address && (
                      <p className="text-sm text-ink-3">
                        {listing.shipping_address.state}
                      </p>
                    )}
                  </div>
                </div>
                <button
                  onClick={handleChatClick}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 mt-4 bg-bg-2 border border-white/10 text-ink-1 rounded-lg font-semibold hover:bg-bg-3 hover:border-white/15 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
                >
                  <MessageCircle size={20} />
                  Chat com vendedor
                </button>
              </div>

              <ShippingMethodInfo method={listing.shipping_method} />
              {listing.shipping_method !== "in_person" && (
                <FreightCalculator listingId={listing.id} />
              )}
            </div>

            {/* Title */}
            <div className="bg-bg-1 border border-white/10 rounded-xl p-5 sm:p-6">
              <h1 className="font-display font-bold text-2xl sm:text-3xl text-ink-1 leading-tight tracking-[-0.02em]">
                {listing.product.name}
              </h1>
              <div className="flex flex-wrap items-center gap-3 sm:gap-4 mt-3 text-sm text-ink-3">
                <span className="flex items-center gap-1.5">
                  <Calendar size={16} className="text-ink-3" />
                  Publicado em {formatListingDate(listing.created_at)}
                </span>
                <span className="flex items-center gap-1.5">
                  <Eye size={16} className="text-ink-3" />
                  {listing.views_count} visualizações
                </span>
              </div>
            </div>

            {/* Description */}
            <div className="bg-bg-1 border border-white/10 rounded-xl p-5 sm:p-6">
              <h2 className="text-lg font-semibold text-ink-1 mb-4">
                Descrição
              </h2>
              <p className="text-ink-2 whitespace-pre-line leading-relaxed text-sm sm:text-base">
                {listing.description}
              </p>
            </div>

            {/* Location */}
            <div className="bg-bg-1 border border-white/10 rounded-xl p-5 sm:p-6">
              <h2 className="text-lg font-semibold text-ink-1 mb-4">
                Localização do anúncio
              </h2>
              <div className="flex items-start gap-3">
                <MapPin size={20} className="text-gold shrink-0 mt-0.5" />
                <p className="text-ink-1 font-medium">
                  {getLocation(listing) || "Não informada"}
                </p>
              </div>
            </div>

            {/* Other details */}
            <div className="bg-bg-1 border border-white/10 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-ink-1 mb-4">
                Detalhes do anúncio
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex items-center gap-3">
                  <Tag size={18} className="text-ink-3" />
                  <div>
                    <p className="text-xs text-ink-3">Condição</p>
                    <p className="text-sm font-medium text-ink-1">
                      {listing.condition.name}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Box size={18} className="text-ink-3" />
                  <div>
                    <p className="text-xs text-ink-3">Marca</p>
                    <p className="text-sm font-medium text-ink-1">
                      {listing.brand.name}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Package size={18} className="text-ink-3" />
                  <div>
                    <p className="text-xs text-ink-3">
                      Quantidade disponível
                    </p>
                    <p className="text-sm font-medium text-ink-1">
                      {listing.quantity} un.
                    </p>
                  </div>
                </div>

                {listing.product.category && (
                  <div className="flex items-center gap-3">
                    <Tag size={18} className="text-ink-3" />
                    <div>
                      <p className="text-xs text-ink-3">Categoria</p>
                      <p className="text-sm font-medium text-ink-1">
                        {listing.product.category.name}
                      </p>
                    </div>
                  </div>
                )}

                {listing.product.series && (
                  <div className="flex items-center gap-3">
                    <Tag size={18} className="text-ink-3" />
                    <div>
                      <p className="text-xs text-ink-3">Série</p>
                      <p className="text-sm font-medium text-ink-1">
                        {listing.product.series.name}
                      </p>
                    </div>
                  </div>
                )}

                {listing.product.code && (
                  <div className="flex items-center gap-3">
                    <Tag size={18} className="text-ink-3" />
                    <div>
                      <p className="text-xs text-ink-3">Código do produto</p>
                      <p className="text-sm font-medium text-ink-1">
                        {listing.product.code}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {hasDimensions && (
                <div className="mt-6 pt-4 border-t border-white/10">
                  <h3 className="text-sm font-semibold text-ink-2 mb-3">
                    Dimensões e peso
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {(listing.weight_kg || firstPackage?.weight_kg) && (
                      <div className="flex items-center gap-2">
                        <Weight size={16} className="text-ink-3" />
                        <div>
                          <p className="text-xs text-ink-3">Peso</p>
                          <p className="text-sm text-ink-1">
                            {listing.weight_kg || firstPackage?.weight_kg} kg
                          </p>
                        </div>
                      </div>
                    )}
                    {(listing.height_cm || firstPackage?.height_cm) && (
                      <div className="flex items-center gap-2">
                        <Ruler size={16} className="text-ink-3" />
                        <div>
                          <p className="text-xs text-ink-3">Altura</p>
                          <p className="text-sm text-ink-1">
                            {listing.height_cm || firstPackage?.height_cm} cm
                          </p>
                        </div>
                      </div>
                    )}
                    {(listing.width_cm || firstPackage?.width_cm) && (
                      <div className="flex items-center gap-2">
                        <Ruler size={16} className="text-ink-3" />
                        <div>
                          <p className="text-xs text-ink-3">Largura</p>
                          <p className="text-sm text-ink-1">
                            {listing.width_cm || firstPackage?.width_cm} cm
                          </p>
                        </div>
                      </div>
                    )}
                    {(listing.length_cm || firstPackage?.length_cm) && (
                      <div className="flex items-center gap-2">
                        <Ruler size={16} className="text-ink-3" />
                        <div>
                          <p className="text-xs text-ink-3">Comprimento</p>
                          <p className="text-sm text-ink-1">
                            {listing.length_cm || firstPackage?.length_cm} cm
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right sidebar: Price + Buy + Seller - Desktop only */}
          <div className="hidden lg:block">
            <div className="space-y-4">
              {/* Price + Buy buttons */}
              <div className="bg-bg-1 border border-white/10 rounded-xl p-6">
                <p className="font-display text-3xl font-bold text-ink-1 tabular-nums tracking-[-0.02em] mb-4">
                  R$ {formatPrice(listing.price)}
                </p>
                <div className="space-y-3">
                  <button
                    onClick={handleBuyClick}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gold text-gold-deep rounded-lg font-semibold hover:bg-gold/90 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
                  >
                    <ShoppingBag size={20} />
                    Comprar
                  </button>
                  <button
                    onClick={handleAddToCartClick}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-ink-1 text-bg-0 rounded-lg font-semibold hover:bg-ink-2 transition-colors focus:outline-none focus:ring-2 focus:ring-ink-1/40 focus:ring-offset-2 focus:ring-offset-bg-1"
                  >
                    <ShoppingCart size={20} />
                    Adicionar ao Carrinho
                  </button>
                </div>
              </div>

              {/* Seller info */}
              <div className="bg-bg-1 border border-white/10 rounded-xl p-6">
                <h3 className="text-xs font-semibold text-ink-3 uppercase tracking-wide mb-3">
                  Vendedor
                </h3>
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-gold/15 rounded-full flex items-center justify-center shrink-0">
                    <User size={22} className="text-gold" />
                  </div>
                  <div>
                    <p className="font-semibold text-ink-1">
                      {listing.seller_name}
                    </p>
                    {listing.shipping_address && (
                      <p className="text-sm text-ink-3">
                        {listing.shipping_address.state}
                      </p>
                    )}
                  </div>
                </div>
                <button
                  onClick={handleChatClick}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 mt-4 bg-bg-2 border border-white/10 text-ink-1 rounded-lg font-semibold hover:bg-bg-3 hover:border-white/15 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
                >
                  <MessageCircle size={20} />
                  Chat com vendedor
                </button>
              </div>

              <ShippingMethodInfo method={listing.shipping_method} />
              {listing.shipping_method !== "in_person" && (
                <FreightCalculator listingId={listing.id} />
              )}
            </div>
          </div>
        </div>

        {/* Suggested products */}
        {suggestedListings.length > 0 && (
          <div className="mt-10">
            <h2 className="font-display font-bold text-xl md:text-2xl text-ink-1 tracking-[-0.02em] mb-6">
              Também podem te interessar
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
              {suggestedListings.map((l) => (
                <ProductCard key={l.id} listing={l} />
              ))}
            </div>
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
