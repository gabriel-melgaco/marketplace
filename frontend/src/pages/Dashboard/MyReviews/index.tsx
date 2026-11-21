import { Star, Construction } from "lucide-react";

export function MyReviews() {
  return (
    <div className="min-h-screen bg-bg-0">
      <div className="max-w-6xl mx-auto px-4 py-6 sm:py-8">
        {/* Page heading */}
        <div className="mb-6 sm:mb-8 flex items-center gap-4">
          <div className="w-12 h-12 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center shrink-0">
            <Star size={22} className="text-gold" aria-hidden="true" />
          </div>
          <div>
            <h1 className="font-display text-2xl sm:text-3xl font-bold text-ink-1 tracking-[-0.02em]">
              Minhas Avaliações
            </h1>
            <p className="text-sm text-ink-2 mt-1">
              Avaliações que você fez e recebeu
            </p>
          </div>
        </div>

        {/* Empty state — feature in development */}
        <div className="bg-bg-1 border border-white/10 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] p-8 md:p-12 text-center">
          <div className="w-16 h-16 bg-bg-2 border border-white/10 rounded-2xl flex items-center justify-center mx-auto mb-5">
            <Construction size={28} className="text-ink-3" aria-hidden="true" />
          </div>
          <h2 className="font-display text-xl md:text-2xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
            Em breve
          </h2>
          <p className="text-ink-2 text-sm leading-relaxed max-w-md mx-auto">
            A área de avaliações está em desenvolvimento. Em breve você poderá
            avaliar suas compras e ver as avaliações que recebeu como vendedor.
          </p>
        </div>
      </div>
    </div>
  );
}
