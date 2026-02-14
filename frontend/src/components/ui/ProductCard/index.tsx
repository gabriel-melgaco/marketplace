import { Link } from "react-router-dom";
import { Package } from "lucide-react";
import type { MarketplaceListing } from "@/types/product";

function formatPrice(price: string): string {
  const num = Number(price);
  if (isNaN(num)) return price;
  return num.toLocaleString("pt-BR", { minimumFractionDigits: 2 });
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "Data inválida";
  return date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

function getLocation(listing: MarketplaceListing): string {
  const addr = listing.seller_shipping_address;
  if (!addr) return "Brasil";
  return `${addr.city}-${addr.state}`;
}

export function ProductCard({ listing }: { listing: MarketplaceListing }) {
  return (
    <Link
      to={`/productdetail/${listing.id}`}
      className="block bg-white rounded-xl shadow-md overflow-hidden hover:shadow-lg transition-shadow"
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
        <p className="text-xs text-gray-500 truncate mt-1">
          {formatDate(listing.created_at)} - {getLocation(listing)}
        </p>
      </div>
    </Link>
  );
}