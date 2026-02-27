import { Link } from "react-router-dom";
import { ArrowLeft, Home } from "lucide-react";

export function NotFound() {
  return (
    <main
      role="main"
      className="min-h-screen bg-blue-900 flex flex-col items-center justify-center px-4 text-center relative overflow-hidden"
    >
      {/* Decorative background circles for brand depth */}
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none"
      >
        <div className="absolute -top-24 -left-24 w-80 h-80 rounded-full bg-white/5" />
        <div className="absolute -bottom-16 -right-16 w-64 h-64 rounded-full bg-white/5" />
      </div>

      <div className="relative z-10 flex flex-col items-center">
        {/* Icon badge */}
        <div className="w-20 h-20 bg-white/10 rounded-2xl flex items-center justify-center mb-6 backdrop-blur-sm border border-white/10">
          <Home size={36} className="text-white/80" aria-hidden="true" />
        </div>

        <p
          className="text-8xl sm:text-9xl font-extrabold text-white leading-none select-none tracking-tight"
          aria-hidden="true"
        >
          404
        </p>

        <h1 className="text-xl sm:text-2xl font-bold text-white mt-4">
          Página não encontrada
        </h1>

        <p className="text-white/70 text-sm mt-2 max-w-xs sm:max-w-sm leading-relaxed">
          A página que você está procurando não existe ou foi removida.
          Verifique o endereço ou volte ao início.
        </p>

        <div className="flex flex-col sm:flex-row items-center gap-3 mt-8">
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-6 py-3 bg-white text-blue-900 font-semibold rounded-xl hover:bg-gray-100 active:bg-gray-200 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-900"
          >
            <Home size={16} aria-hidden="true" />
            Voltar ao início
          </Link>
          <button
            type="button"
            onClick={() => window.history.back()}
            className="inline-flex items-center gap-2 px-6 py-3 border border-white/30 text-white font-semibold rounded-xl hover:bg-white/10 active:bg-white/20 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-900"
          >
            <ArrowLeft size={16} aria-hidden="true" />
            Página anterior
          </button>
        </div>
      </div>
    </main>
  );
}
