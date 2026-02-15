import { useState, useEffect, useCallback, useMemo } from "react";
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
} from "lucide-react";
import { productService } from "@/services/productService";
import { useAuth } from "@/contexts/AuthContext";
import { Footer } from "@/components/layout/Footer";
import { ProductDetailSkeleton } from "@/components/skeletons/ProductDetailSkeleton";
import type {
  MarketplaceListingDetail,
  MarketplaceListing,
} from "@/types/product";

function formatPrice(price: string): string {
  const num = Number(price);
  if (isNaN(num)) return price;
  return num.toLocaleString("pt-BR", { minimumFractionDigits: 2 });
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) {
    return "Data inválida";
  }
  return date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

function getLocation(listing: MarketplaceListingDetail): string {
  const addr = listing.seller_shipping_address;
  if (!addr) return "Brasil";
  return `${addr.city} - ${addr.state}`;
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
      <div className="aspect-4/3 bg-gray-200 rounded-xl flex items-center justify-center">
        <div className="text-gray-400 text-center p-4">
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
        <div className="aspect-4/3 bg-gray-100 rounded-xl overflow-hidden">
          <img
            src={sortedImages[currentIndex].image_url}
            alt={`${productName} - Imagem ${currentIndex + 1} de ${sortedImages.length}`}
            className="w-full h-full object-contain"
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
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white rounded-full p-3 shadow-lg transition-all hover:scale-110 focus:outline-none focus:ring-2 focus:ring-blue-800 focus:ring-offset-2"
              aria-label="Imagem anterior"
            >
              <ChevronLeft size={24} className="text-gray-800" />
            </button>
            <button
              onClick={goToNext}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white rounded-full p-3 shadow-lg transition-all hover:scale-110 focus:outline-none focus:ring-2 focus:ring-blue-800 focus:ring-offset-2"
              aria-label="Próxima imagem"
            >
              <ChevronRight size={24} className="text-gray-800" />
            </button>

            {/* Counter badge */}
            <div className="absolute bottom-3 right-3 bg-black/70 text-white text-xs px-3 py-1 rounded-full">
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
              className={`shrink-0 w-20 h-20 rounded-lg overflow-hidden border-2 transition-all focus:outline-none focus:ring-2 focus:ring-blue-800 focus:ring-offset-2 ${
                idx === currentIndex
                  ? "border-blue-800 ring-2 ring-blue-800"
                  : "border-gray-300 hover:border-blue-800 opacity-60 hover:opacity-100"
              }`}
              aria-label={`Ver imagem ${idx + 1}`}
            >
              <img
                src={img.image_url}
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

function SuggestedProductCard({ listing }: { listing: MarketplaceListing }) {
  return (
    <Link
      to={`/productdetail/${listing.id}`}
      className="block bg-white rounded-xl shadow-md overflow-hidden hover:shadow-lg transition-shadow focus:outline-none focus:ring-2 focus:ring-blue-800 focus:ring-offset-2"
    >
      <div className="aspect-4/3 bg-gray-200 flex items-center justify-center">
        {listing.primary_image ? (
          <img
            src={listing.primary_image}
            alt={listing.product.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="text-gray-400 text-center p-4">
            <Package size={40} className="mx-auto mb-2" />
            <p className="text-sm">Sem imagem</p>
          </div>
        )}
      </div>
      <div className="p-3">
        <h3 className="font-semibold text-gray-800 text-sm truncate">
          {listing.product.name}
        </h3>
        <p className="text-lg font-bold text-blue-800 mt-1">
          R$ {formatPrice(listing.price)}
        </p>
      </div>
    </Link>
  );
}

export function ProductDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

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
            allListings.filter((l) => l.id !== numericId).slice(0, 8),
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
    // TODO: implement checkout flow
  };

  const handleAddToCartClick = () => {
    // TODO: implement cart
  };

  const handleChatClick = () => {
    if (isAuthenticated) {
      navigate(`/chat/${id}`);
    } else {
      navigate("/login");
    }
  };

  if (loading) {
    return <ProductDetailSkeleton />;
  }

  if (error || !listing) {
    return (
      <div className="min-h-screen bg-blue-900">
        <div className="text-center py-20">
          <p className="text-white text-lg mb-4">
            {error || "Produto não encontrado."}
          </p>
          <Link
            to="/"
            className="px-4 py-2 bg-white text-blue-900 rounded-lg font-medium hover:bg-gray-100 transition focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-900"
          >
            Voltar para o início
          </Link>
        </div>
      </div>
    );
  }

  const hasDimensions =
    listing.weight_kg ||
    listing.height_cm ||
    listing.width_cm ||
    listing.length_cm;

  return (
    <div className="min-h-screen bg-blue-900">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 pb-24">
        {/* Main content grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Image + Info */}
          <div className="lg:col-span-2 space-y-5">
            {/* Image Carousel */}
            <div className="bg-white rounded-xl p-4 sm:p-6 shadow-md">
              <ImageCarousel
                images={listing.images}
                productName={listing.product.name}
              />
            </div>

            {/* Mobile: Price/Chat + Seller (after image on mobile, hidden on desktop) */}
            <div className="lg:hidden space-y-4">
              {/* Price + Buy buttons */}
              <div className="bg-white rounded-xl p-5 shadow-md">
                <p className="text-3xl font-bold text-blue-800 mb-4">
                  R$ {formatPrice(listing.price)}
                </p>
                <div className="space-y-3">
                  <button
                    onClick={handleBuyClick}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-900 text-white rounded-lg font-semibold hover:bg-blue-950 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  >
                    <ShoppingBag size={20} />
                    Comprar
                  </button>
                  <button
                    onClick={handleAddToCartClick}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-white text-blue-800 border border-blue-800 rounded-lg font-semibold hover:bg-blue-50 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  >
                    <ShoppingCart size={20} />
                    Adicionar ao Carrinho
                  </button>
                </div>
              </div>

              {/* Seller info */}
              <div className="bg-white rounded-xl p-5 shadow-md">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  Vendedor
                </h3>
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center shrink-0">
                    <User size={22} className="text-blue-800" />
                  </div>
                  <div>
                    <p className="font-semibold text-gray-900">
                      {listing.seller_name}
                    </p>
                    {listing.seller_shipping_address && (
                      <p className="text-sm text-gray-500">
                        {listing.seller_shipping_address.state}
                      </p>
                    )}
                  </div>
                </div>
                <button
                  onClick={handleChatClick}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 mt-4 bg-blue-800 text-white rounded-lg font-semibold hover:bg-blue-900 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                >
                  <MessageCircle size={20} />
                  Chat com vendedor
                </button>
              </div>
            </div>

            {/* Title */}
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md">
              <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 leading-tight">
                {listing.product.name}
              </h1>
              <div className="flex flex-wrap items-center gap-3 sm:gap-4 mt-3 text-sm text-gray-500">
                <span className="flex items-center gap-1.5">
                  <Calendar size={16} />
                  Publicado em {formatDate(listing.created_at)}
                </span>
                <span className="flex items-center gap-1.5">
                  <Eye size={16} />
                  {listing.views_count} visualizações
                </span>
              </div>
            </div>

            {/* Description */}
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Descrição
              </h2>
              <p className="text-gray-700 whitespace-pre-line leading-relaxed text-sm sm:text-base">
                {listing.description}
              </p>
            </div>

            {/* Location */}
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Localização do anúncio
              </h2>
              <div className="flex items-start gap-3 text-gray-700">
                <MapPin size={20} className="text-blue-800 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium">{getLocation(listing)}</p>
                  {listing.seller_shipping_address && (
                    <p className="text-sm text-gray-500 mt-1">
                      {listing.seller_shipping_address.neighborhood},{" "}
                      {listing.seller_shipping_address.city} -{" "}
                      {listing.seller_shipping_address.state}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Other details */}
            <div className="bg-white rounded-xl p-6 shadow-md">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Detalhes do anúncio
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex items-center gap-3">
                  <Tag size={18} className="text-blue-800" />
                  <div>
                    <p className="text-xs text-gray-500">Condição</p>
                    <p className="text-sm font-medium text-gray-800">
                      {listing.condition.name}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Box size={18} className="text-blue-800" />
                  <div>
                    <p className="text-xs text-gray-500">Marca</p>
                    <p className="text-sm font-medium text-gray-800">
                      {listing.brand.name}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Package size={18} className="text-blue-800" />
                  <div>
                    <p className="text-xs text-gray-500">
                      Quantidade disponível
                    </p>
                    <p className="text-sm font-medium text-gray-800">
                      {listing.quantity} un.
                    </p>
                  </div>
                </div>

                {listing.product.category && (
                  <div className="flex items-center gap-3">
                    <Tag size={18} className="text-blue-800" />
                    <div>
                      <p className="text-xs text-gray-500">Categoria</p>
                      <p className="text-sm font-medium text-gray-800">
                        {listing.product.category.name}
                      </p>
                    </div>
                  </div>
                )}

                {listing.product.series && (
                  <div className="flex items-center gap-3">
                    <Tag size={18} className="text-blue-800" />
                    <div>
                      <p className="text-xs text-gray-500">Série</p>
                      <p className="text-sm font-medium text-gray-800">
                        {listing.product.series.name}
                      </p>
                    </div>
                  </div>
                )}

                {listing.product.code && (
                  <div className="flex items-center gap-3">
                    <Tag size={18} className="text-blue-800" />
                    <div>
                      <p className="text-xs text-gray-500">Código do produto</p>
                      <p className="text-sm font-medium text-gray-800">
                        {listing.product.code}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {hasDimensions && (
                <div className="mt-6 pt-4 border-t border-gray-100">
                  <h3 className="text-sm font-semibold text-gray-700 mb-3">
                    Dimensões e peso
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {listing.weight_kg && (
                      <div className="flex items-center gap-2">
                        <Weight size={16} className="text-gray-500" />
                        <div>
                          <p className="text-xs text-gray-500">Peso</p>
                          <p className="text-sm text-gray-800">
                            {listing.weight_kg} kg
                          </p>
                        </div>
                      </div>
                    )}
                    {listing.height_cm && (
                      <div className="flex items-center gap-2">
                        <Ruler size={16} className="text-gray-500" />
                        <div>
                          <p className="text-xs text-gray-500">Altura</p>
                          <p className="text-sm text-gray-800">
                            {listing.height_cm} cm
                          </p>
                        </div>
                      </div>
                    )}
                    {listing.width_cm && (
                      <div className="flex items-center gap-2">
                        <Ruler size={16} className="text-gray-500" />
                        <div>
                          <p className="text-xs text-gray-500">Largura</p>
                          <p className="text-sm text-gray-800">
                            {listing.width_cm} cm
                          </p>
                        </div>
                      </div>
                    )}
                    {listing.length_cm && (
                      <div className="flex items-center gap-2">
                        <Ruler size={16} className="text-gray-500" />
                        <div>
                          <p className="text-xs text-gray-500">Comprimento</p>
                          <p className="text-sm text-gray-800">
                            {listing.length_cm} cm
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
              <div className="bg-white rounded-xl p-6 shadow-md">
                <p className="text-3xl font-bold text-blue-800 mb-4">
                  R$ {formatPrice(listing.price)}
                </p>
                <div className="space-y-3">
                  <button
                    onClick={handleBuyClick}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-900 text-white rounded-lg font-semibold hover:bg-blue-950 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  >
                    <ShoppingBag size={20} />
                    Comprar
                  </button>
                  <button
                    onClick={handleAddToCartClick}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-white text-blue-800 border border-blue-800 rounded-lg font-semibold hover:bg-blue-50 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  >
                    <ShoppingCart size={20} />
                    Adicionar ao Carrinho
                  </button>
                </div>
              </div>

              {/* Seller info */}
              <div className="bg-white rounded-xl p-6 shadow-md">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  Vendedor
                </h3>
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center shrink-0">
                    <User size={22} className="text-blue-800" />
                  </div>
                  <div>
                    <p className="font-semibold text-gray-900">
                      {listing.seller_name}
                    </p>
                    {listing.seller_shipping_address && (
                      <p className="text-sm text-gray-500">
                        {listing.seller_shipping_address.state}
                      </p>
                    )}
                  </div>
                </div>
                <button
                  onClick={handleChatClick}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 mt-4 bg-blue-800 text-white rounded-lg font-semibold hover:bg-blue-900 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                >
                  <MessageCircle size={20} />
                  Chat com vendedor
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Suggested products */}
        {suggestedListings.length > 0 && (
          <div className="mt-10">
            <h2 className="text-xl font-bold text-white mb-6">
              Também podem te interessar
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
              {suggestedListings.map((l) => (
                <SuggestedProductCard key={l.id} listing={l} />
              ))}
            </div>
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
