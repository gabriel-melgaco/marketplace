import { Link } from "react-router-dom";
import { ArrowLeft, Home } from "lucide-react";

export function NotFound() {
  return (
    <main
      role="main"
      className="min-h-screen bg-bg-0 flex flex-col items-center justify-center px-4 text-center relative overflow-hidden"
    >
      {/* Decorative background circles for brand depth */}
      <div aria-hidden="true" className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-24 -left-24 w-80 h-80 rounded-full bg-gold/5" />
        <div className="absolute -bottom-16 -right-16 w-64 h-64 rounded-full bg-gold/5" />
      </div>

      <div className="relative z-10 flex flex-col items-center">
        {/* Icon badge */}
        <div className="w-20 h-20 bg-gold/10 rounded-2xl flex items-center justify-center mb-6 backdrop-blur-sm border border-gold/30">
          <Home size={36} className="text-gold" aria-hidden="true" />
        </div>

        <p
          className="font-display text-8xl sm:text-9xl font-extrabold text-ink-1 opacity-20 leading-none select-none tracking-tight"
          aria-hidden="true"
        >
          404
        </p>

        <h1 className="font-display text-xl sm:text-2xl font-bold text-ink-1 tracking-[-0.02em] mt-4">
          Página não encontrada
        </h1>

        <p className="text-ink-2 text-sm mt-2 max-w-xs sm:max-w-sm leading-relaxed">
          A página que você está procurando não existe ou foi removida.
          Verifique o endereço ou volte ao início.
        </p>

        <div className="flex flex-col sm:flex-row items-center gap-3 mt-8">
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-6 py-3 bg-gold text-gold-deep font-semibold rounded-xl hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-0"
          >
            <Home size={16} aria-hidden="true" />
            Voltar ao início
          </Link>
          <button
            type="button"
            onClick={() => window.history.back()}
            className="inline-flex items-center gap-2 px-6 py-3 bg-bg-2 border border-white/10 text-ink-1 font-semibold rounded-xl hover:bg-bg-3 hover:border-white/15 active:bg-bg-3 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-0"
          >
            <ArrowLeft size={16} aria-hidden="true" />
            Página anterior
          </button>
        </div>
      </div>
    </main>
  );
}
