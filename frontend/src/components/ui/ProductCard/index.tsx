import { useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { Package, ChevronLeft, ChevronRight } from "lucide-react";
import { toPublicUrl } from "@/services/storageService";
import type { MarketplaceListing } from "@/types/product";

function formatRelativeTime(dateStr: string): string {
  const published = new Date(dateStr).getTime();
  if (Number.isNaN(published)) return "";
  const diffDays = Math.floor((Date.now() - published) / (1000 * 60 * 60 * 24));
  if (diffDays < 1) return "Hoje";
  if (diffDays === 1) return "Ontem";
  if (diffDays < 7) return `Há ${diffDays} dias`;
  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return weeks === 1 ? "Há 1 semana" : `Há ${weeks} semanas`;
  }
  if (diffDays < 365) {
    const months = Math.floor(diffDays / 30);
    return months === 1 ? "Há 1 mês" : `Há ${months} meses`;
  }
  const years = Math.floor(diffDays / 365);
  return years === 1 ? "Há 1 ano" : `Há ${years} anos`;
}

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
  const addr = listing.shipping_address;
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
      className="block bg-bg-1 border border-white/[0.06] rounded-[18px] overflow-hidden active:scale-[0.98] active:border-white/[0.12] transition-all duration-200"
    >
      <div
        className="aspect-square flex items-center justify-center relative overflow-hidden"
        style={{ background: 'radial-gradient(circle at 50% 40%, #25252d 0%, #141418 100%)' }}
        role={hasMultipleImages ? "region" : undefined}
        aria-label={hasMultipleImages ? `Galeria de imagens: ${listing.title || listing.product.name}` : undefined}
        onKeyDown={hasMultipleImages ? handleCarouselKeyDown : undefined}
      >
        {imageSrc ? (
          <img
            src={imageSrc}
            alt={`${listing.title || listing.product.name}${hasMultipleImages ? ` — imagem ${currentIndex + 1} de ${allImages.length}` : ""}`}
            className="w-full h-full object-contain p-3.5 drop-shadow-[0_8px_20px_rgba(0,0,0,0.4)] transition-opacity duration-200"
            loading="lazy"
            decoding="async"
            sizes="(min-width: 768px) 25vw, 50vw"
          />
        ) : (
          <div className="text-ink-3 text-center p-4">
            <Package size={40} className="mx-auto mb-2" aria-hidden="true" />
            <p className="text-sm">Sem imagem</p>
          </div>
        )}

        <div
          aria-hidden
          className="absolute inset-0 z-[2] pointer-events-none"
          style={{ background: 'linear-gradient(180deg, transparent 60%, rgba(0,0,0,0.35) 100%)' }}
        />

        {hasMultipleImages && (
          <>
            <button
              type="button"
              onClick={handlePrev}
              className="absolute left-1 top-1/2 -translate-y-1/2 z-[3] bg-black/50 hover:bg-black/70 border border-white/[0.12] text-white rounded-full p-1.5 transition-colors focus:outline-none focus:ring-2 focus:ring-white"
              aria-label="Imagem anterior"
            >
              <ChevronLeft size={14} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={handleNext}
              className="absolute right-1 top-1/2 -translate-y-1/2 z-[3] bg-black/50 hover:bg-black/70 border border-white/[0.12] text-white rounded-full p-1.5 transition-colors focus:outline-none focus:ring-2 focus:ring-white"
              aria-label="Próxima imagem"
            >
              <ChevronRight size={14} aria-hidden="true" />
            </button>

            <div
              role="tablist"
              aria-label="Selecionar imagem"
              className="absolute bottom-2 left-0 right-0 z-[3] flex justify-center gap-1.5"
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
                    idx === currentIndex ? "w-4 bg-gold" : "w-1.5 bg-white/30 hover:bg-white/50"
                  }`}
                />
              ))}
            </div>
          </>
        )}
      </div>

      <div className="px-3.5 pt-3 pb-3.5">
        <h3 className="text-sm font-medium text-ink-1 leading-[1.35] tracking-[-0.005em] mb-2.5 overflow-hidden [display:-webkit-box] [-webkit-line-clamp:2] [-webkit-box-orient:vertical]">
          {listing.title || listing.product.name}
        </h3>
        <p className="font-display font-bold text-[17px] tracking-[-0.02em] text-ink-1 tabular-nums">
          <span className="text-[11px] text-ink-3 font-medium mr-0.5">R$</span>
          {formatPrice(listing.price)}
        </p>
        <div className="mt-2 pt-2 border-t border-white/[0.06] flex items-center text-[10.5px] text-ink-3">
          <div className="flex items-center gap-1.5">
            <span>{formatRelativeTime(listing.created_at)}</span>
            {location && (
              <>
                <span aria-hidden className="w-[3px] h-[3px] rounded-full bg-ink-3" />
                <span>{location}</span>
              </>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
