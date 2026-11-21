import { Link } from "react-router-dom";

export function AuthLogo() {
  return (
    <Link
      to="/"
      className="z-10 absolute top-4 left-4 md:top-8 md:left-8 flex items-center gap-2 text-white lg:hidden"
    >
      <div className="w-8 h-8 md:w-10 md:h-10 bg-gold rounded-full flex items-center justify-center shrink-0">
        <span className="text-gold-deep text-xs md:text-sm font-bold">CS</span>
      </div>
      <span className="font-display font-bold text-lg md:text-2xl text-ink-1 tracking-tight">
        MARKETPLACE
      </span>
    </Link>
  );
}
