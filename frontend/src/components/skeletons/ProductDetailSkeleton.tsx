import { Skeleton } from "@/components/ui/Skeleton";
import { ProductCardSkeleton } from "./ProductCardSkeleton";

const THUMBNAIL_COUNT = 4;
const DETAILS_ITEM_COUNT = 6;
const SUGGESTED_PRODUCTS_COUNT = 8;

function SidebarSkeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`space-y-4 ${className}`}>
      {/* Price + Chat */}
      <div className="bg-white rounded-xl p-5 lg:p-6 shadow-md space-y-4">
        {/* Price - matches text-3xl font-bold */}
        <Skeleton className="h-10 w-2/3" />
        {/* Chat button - matches px-4 py-3 with icon */}
        <Skeleton className="h-12 w-full rounded-lg" />
      </div>

      {/* Seller info */}
      <div className="bg-white rounded-xl p-5 lg:p-6 shadow-md">
        {/* "Vendedor" label - matches text-xs uppercase */}
        <Skeleton className="h-3 w-20 mb-3" />
        <div className="flex items-center gap-3">
          <Skeleton className="w-12 h-12 rounded-full shrink-0" />
          <div className="space-y-2 flex-1">
            {/* Seller name - matches font-semibold */}
            <Skeleton className="h-5 w-3/4" />
            {/* State - matches text-sm */}
            <Skeleton className="h-4 w-1/2" />
          </div>
        </div>
      </div>
    </div>
  );
}

export function ProductDetailSkeleton() {
  return (
    <div className="min-h-screen bg-blue-900">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 pb-24">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column */}
          <div className="lg:col-span-2 space-y-5">
            {/* Image carousel */}
            <div className="bg-white rounded-xl p-4 sm:p-6 shadow-md">
              <Skeleton className="aspect-4/3 rounded-xl" />
              {/* Thumbnail strip */}
              <div className="flex gap-2 mt-4">
                {Array.from({ length: THUMBNAIL_COUNT }, (_, i) => (
                  <Skeleton key={i} className="w-20 h-20 rounded-lg shrink-0" />
                ))}
              </div>
            </div>

            {/* Mobile sidebar */}
            <SidebarSkeleton className="lg:hidden" />

            {/* Title + meta */}
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-3">
              {/* Title - matches text-2xl sm:text-3xl font-bold */}
              <Skeleton className="h-8 sm:h-9 w-4/5" />
              <Skeleton className="h-8 sm:h-9 w-2/3 hidden sm:block" />
              {/* Meta info with icons - matches text-sm */}
              <div className="flex flex-wrap items-center gap-3 sm:gap-4">
                <Skeleton className="h-4 w-36" />
                <Skeleton className="h-4 w-32" />
              </div>
            </div>

            {/* Description */}
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-3">
              {/* Section title - matches text-lg font-semibold */}
              <Skeleton className="h-6 w-28" />
              {/* Description text - matches text-sm sm:text-base leading-relaxed */}
              <div className="space-y-2.5">
                <Skeleton className="h-4 sm:h-5 w-full" />
                <Skeleton className="h-4 sm:h-5 w-full" />
                <Skeleton className="h-4 sm:h-5 w-11/12" />
                <Skeleton className="h-4 sm:h-5 w-4/5" />
              </div>
            </div>

            {/* Location */}
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-3">
              {/* Section title - matches text-lg font-semibold */}
              <Skeleton className="h-6 w-52" />
              <div className="flex items-start gap-3">
                {/* MapPin icon placeholder */}
                <Skeleton className="w-5 h-5 rounded shrink-0 mt-0.5" />
                <div className="space-y-2 flex-1">
                  {/* City - State - matches font-medium */}
                  <Skeleton className="h-5 w-1/2" />
                  {/* Full address - matches text-sm */}
                  <Skeleton className="h-4 w-2/3" />
                </div>
              </div>
            </div>

            {/* Details */}
            <div className="bg-white rounded-xl p-6 shadow-md space-y-4">
              {/* Section title - matches text-lg font-semibold */}
              <Skeleton className="h-6 w-44" />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {Array.from({ length: DETAILS_ITEM_COUNT }, (_, i) => (
                  <div key={i} className="flex items-center gap-3">
                    {/* Icon placeholder */}
                    <Skeleton className="w-[18px] h-[18px] rounded shrink-0" />
                    <div className="space-y-1.5 flex-1">
                      {/* Label - matches text-xs */}
                      <Skeleton className="h-3 w-20" />
                      {/* Value - matches text-sm font-medium */}
                      <Skeleton className="h-4 w-28" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right sidebar - desktop only */}
          <SidebarSkeleton className="hidden lg:block" />
        </div>

        {/* Suggested products */}
        <div className="mt-10">
          {/* Section title on dark background - matches text-xl font-bold text-white */}
          <Skeleton variant="light" className="h-7 w-72 mb-6" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
            {Array.from({ length: SUGGESTED_PRODUCTS_COUNT }, (_, i) => (
              <ProductCardSkeleton key={i} />
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
