import { useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { Package, ChevronLeft, ChevronRight, MapPin } from "lucide-react";
import { toPublicUrl } from "@/services/storageService";
import type { MarketplaceListing } from "@/types/product";

function formatPrice(price: string): string {
  const num = Number(price);
  if (isNaN(num)) return price;
  return num.toLocaleString("pt-BR", { minimumFractionDigits: 2 });
}

export function formatListingDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "Data inválida";
  return date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function getListingLocation(listing: MarketplaceListing): string {
  const addr = listing.seller_shipping_address;
  if (!addr) return "";
  const parts: string[] = [];
  if (addr.city) parts.push(addr.city);
  if (addr.state) parts.push(addr.state);
  return parts.join(" - ");
}

export function getImageSrc(listing: MarketplaceListing): string | null {
  let url: string | null = null;
  if (listing.primary_image) {
    url = listing.primary_image;
  } else if (listing.images && listing.images.length > 0) {
    const primary = listing.images.find((img) => img.is_primary);
    url = primary ? primary.image_url : listing.images[0].image_url;
  }
  return url ? toPublicUrl(url) : null;
}

export function ProductCard({ listing }: { listing: MarketplaceListing }) {
  const [currentIndex, setCurrentIndex] = useState(0);

  const allImages = useMemo(
    () =>
      listing.images?.length
        ? [...listing.images].sort((a, b) => {
            if (a.is_primary) return -1;
            if (b.is_primary) return 1;
            return a.order - b.order;
          })
        : [],
    [listing.images],
  );

  const hasMultipleImages = allImages.length > 1;

  const imageSrc = hasMultipleImages
    ? toPublicUrl(allImages[currentIndex].image_url)
    : getImageSrc(listing);

  const location = getListingLocation(listing);
  const dateStr = formatListingDate(listing.created_at);

  const handlePrev = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setCurrentIndex((prev) => (prev === 0 ? allImages.length - 1 : prev - 1));
  }, [allImages.length]);

  const handleNext = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setCurrentIndex((prev) => (prev === allImages.length - 1 ? 0 : prev + 1));
  }, [allImages.length]);

  const handleDotClick = (e: React.MouseEvent, idx: number) => {
    e.preventDefault();
    e.stopPropagation();
    setCurrentIndex(idx);
  };

  const handleCarouselKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      setCurrentIndex((prev) => (prev === 0 ? allImages.length - 1 : prev - 1));
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      setCurrentIndex((prev) => (prev === allImages.length - 1 ? 0 : prev + 1));
    }
  };

  return (
    <Link
      to={`/productdetail/${listing.id}`}
      className="block bg-white rounded-xl shadow-md overflow-hidden hover:shadow-lg transition-shadow"
    >
      <div
        className="aspect-4/3 bg-gray-200 flex items-center justify-center relative overflow-hidden"
        role={hasMultipleImages ? "region" : undefined}
        aria-label={hasMultipleImages ? `Galeria de imagens: ${listing.title || listing.product.name}` : undefined}
        onKeyDown={hasMultipleImages ? handleCarouselKeyDown : undefined}
      >
        {imageSrc ? (
          <img
            src={imageSrc}
            alt={`${listing.title || listing.product.name}${hasMultipleImages ? ` — imagem ${currentIndex + 1} de ${allImages.length}` : ""}`}
            className="w-full h-full object-cover transition-opacity duration-200"
            loading="lazy"
            decoding="async"
            sizes="(min-width: 768px) 25vw, 50vw"
          />
        ) : (
          <div className="text-gray-400 text-center p-4">
            <Package size={40} className="mx-auto mb-2" aria-hidden="true" />
            <p className="text-sm">Sem imagem</p>
          </div>
        )}

        {hasMultipleImages && (
          <>
            <button
              type="button"
              onClick={handlePrev}
              className="absolute left-1 top-1/2 -translate-y-1/2 bg-black/40 hover:bg-black/60 active:bg-black/70 text-white rounded-full p-1.5 transition-colors focus:outline-none focus:ring-2 focus:ring-white"
              aria-label="Imagem anterior"
            >
              <ChevronLeft size={14} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={handleNext}
              className="absolute right-1 top-1/2 -translate-y-1/2 bg-black/40 hover:bg-black/60 active:bg-black/70 text-white rounded-full p-1.5 transition-colors focus:outline-none focus:ring-2 focus:ring-white"
              aria-label="Próxima imagem"
            >
              <ChevronRight size={14} aria-hidden="true" />
            </button>

            <div
              role="tablist"
              aria-label="Selecionar imagem"
              className="absolute bottom-2 left-0 right-0 flex justify-center gap-1.5"
            >
              {allImages.map((_, idx) => (
                <button
                  key={idx}
                  type="button"
                  role="tab"
                  aria-selected={idx === currentIndex}
                  aria-label={`Imagem ${idx + 1} de ${allImages.length}`}
                  onClick={(e) => handleDotClick(e, idx)}
                  className={`h-1.5 rounded-full transition-all duration-200 focus:outline-none focus:ring-1 focus:ring-white ${
                    idx === currentIndex ? "w-4 bg-white" : "w-1.5 bg-white/50 hover:bg-white/75"
                  }`}
                />
              ))}
            </div>
          </>
        )}
      </div>
      <div className="p-3">
        <h3 className="font-semibold text-gray-800 text-sm truncate">
          {listing.title || listing.product.name}
        </h3>
        <p className="text-lg font-bold text-blue-800 mt-1">
          R$ {formatPrice(listing.price)}
        </p>
        {location && (
          <div className="flex items-center gap-1 mt-1.5">
            <MapPin size={12} className="text-gray-400 shrink-0" aria-hidden="true" />
            <p className="text-xs text-gray-500 truncate">{location}</p>
          </div>
        )}
        <p className="text-xs text-gray-400 mt-0.5">Publicado em {dateStr}</p>
      </div>
    </Link>
  );
}
