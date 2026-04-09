interface SkeletonProps {
  className?: string;
  variant?: "default" | "light";
}

export function Skeleton({ className = "", variant = "default" }: SkeletonProps) {
  const variantClasses = {
    default: "bg-gray-300/70",
    light: "bg-white/20",
  };

  return (
    <div
      className={`animate-pulse rounded-md ${variantClasses[variant]} ${className}`}
      aria-hidden="true"
    />
  );
}
