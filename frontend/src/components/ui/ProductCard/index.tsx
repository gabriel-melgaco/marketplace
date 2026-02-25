import { Link } from "react-router-dom";
import { Package } from "lucide-react";
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
  return addr.state;
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
  const imageSrc = getImageSrc(listing);
  const location = getListingLocation(listing);
  const dateStr = formatListingDate(listing.created_at);

  const subtitle = location
    ? `Publicado em ${dateStr} - ${location}`
    : `Publicado em ${dateStr}`;

  return (
    <Link
      to={`/productdetail/${listing.id}`}
      className="block bg-white rounded-xl shadow-md overflow-hidden hover:shadow-lg transition-shadow"
    >
      <div className="aspect-4/3 bg-gray-200 flex items-center justify-center">
        {imageSrc ? (
          <img
            src={imageSrc}
            alt={listing.title || listing.product.name}
            className="w-full h-full object-cover"
            loading="lazy"
            decoding="async"
            sizes="(min-width: 768px) 25vw, 50vw"
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
          {listing.title || listing.product.name}
        </h3>
        <p className="text-lg font-bold text-blue-800 mt-1">
          R$ {formatPrice(listing.price)}
        </p>
        <p className="text-xs text-gray-500 truncate mt-1">{subtitle}</p>
      </div>
    </Link>
  );
}
