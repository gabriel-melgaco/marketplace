import { Skeleton } from "@/components/ui/Skeleton";

export function ProductCardSkeleton() {
  return (
    <div className="bg-white rounded-xl shadow-md overflow-hidden">
      {/* Image area - matches aspect-4/3 */}
      <Skeleton className="aspect-4/3 rounded-none" />

      {/* Text content - matches ProductCard padding/structure */}
      <div className="p-3 space-y-1.5">
        {/* Product name - matches text-sm font-semibold */}
        <Skeleton className="h-5 w-3/4" />
        {/* Price - matches text-lg font-bold mt-1 */}
        <Skeleton className="h-6 w-1/2 mt-1" />
        {/* Date + location - matches text-xs mt-1 */}
        <Skeleton className="h-3.5 w-2/3 mt-1" />
      </div>
    </div>
  );
}

export function ProductGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
      {Array.from({ length: count }).map((_, i) => (
        <ProductCardSkeleton key={i} />
      ))}
    </div>
  );
}
