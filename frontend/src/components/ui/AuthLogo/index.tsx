import { Link } from "react-router-dom";

export function AuthLogo() {
  return (
    <Link to="/">
      <div className="absolute top-4 left-4 md:top-8 md:left-8 flex items-center gap-2 text-white">
        {/* Logo */}
        <div className="w-8 h-8 md:w-10 md:h-10 bg-secundary rounded-full flex items-center justify-center">
          <span className="text-xs md:text-sm font-bold">CS</span>
        </div>
        <span className="font-bold text-lg md:text-2xl">MARKETPLACE</span>
      </div>
    </Link>
  );
}
