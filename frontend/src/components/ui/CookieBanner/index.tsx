import { useState, useEffect } from 'react'
import { hasConsented, saveConsent } from '@/utils/cookieConsent'

// ─── Toggle ───────────────────────────────────────────────────────────────────

interface ToggleProps {
  checked: boolean
  onChange: () => void
  disabled?: boolean
  ariaLabel: string
}

function Toggle({ checked, onChange, disabled, ariaLabel }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={onChange}
      // Padding para garantir area de toque minima de ~44px em mobile
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1 disabled:opacity-50 disabled:cursor-not-allowed ${
        checked ? 'bg-gold' : 'bg-white/10'
      }`}
    >
      <span
        aria-hidden="true"
        className={`inline-block h-4 w-4 rounded-full transition-transform duration-200 ${
          checked ? 'translate-x-6 bg-gold-deep' : 'translate-x-1 bg-ink-1'
        }`}
      />
    </button>
  )
}

// ─── CookieBanner ─────────────────────────────────────────────────────────────

interface CookiePrefs {
  functional: boolean
  analytics: boolean
  marketing: boolean
}

export function CookieBanner() {
  const [visible, setVisible] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [prefs, setPrefs] = useState<CookiePrefs>({
    functional: true,
    analytics: false,
    marketing: false,
  })

  useEffect(() => {
    const timer = setTimeout(() => {
      if (!hasConsented()) setVisible(true)
    }, 1000)
    return () => clearTimeout(timer)
  }, [])

  function handleAcceptAll() {
    saveConsent({ functional: true, analytics: true, marketing: true })
    setVisible(false)
  }

  function handleRejectOptional() {
    saveConsent({ functional: false, analytics: false, marketing: false })
    setVisible(false)
  }

  function handleSavePrefs() {
    saveConsent(prefs)
    setVisible(false)
  }

  function togglePref(key: keyof CookiePrefs) {
    setPrefs((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  if (!visible) return null

  return (
    <div
      role="region"
      aria-label="Preferências de cookies"
      // pb-20 em mobile para nao sobrepor o BottomNav; sm:pb-4 em telas maiores
      className="fixed bottom-0 left-0 right-0 z-50 bg-bg-1 border-t border-white/10 shadow-[0_-4px_24px_rgba(0,0,0,0.4)] pb-20 sm:pb-4"
    >
      <div className="max-w-4xl mx-auto px-4 py-4 space-y-4">

        {/* Linha principal: texto + botoes */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <p className="text-sm text-ink-1 flex-1 leading-relaxed">
            Usamos cookies para melhorar sua experiência. Veja nossa{' '}
            <a
              href="/politica-de-cookies"
              className="text-gold underline underline-offset-2 hover:text-gold/80 font-medium"
            >
              Política de Cookies
            </a>
            .
          </p>

          {/*
            Hierarquia visual progressiva:
            1. Personalizar — peso baixo (ghost/outline discreto)
            2. Recusar opcionais — peso medio (outline com borda visivel)
            3. Aceitar todos — peso alto (fundo solido, destaque maximo)
          */}
          <div className="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 shrink-0">
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              aria-controls="cookie-preferences-panel"
              className="px-4 py-2.5 rounded-xl text-sm font-medium text-gold border border-gold/30 hover:bg-gold/10 hover:border-gold/50 transition-colors text-center focus:outline-none focus:ring-2 focus:ring-gold/40"
            >
              {expanded ? 'Ocultar opções' : 'Personalizar'}
            </button>
            <button
              type="button"
              onClick={handleRejectOptional}
              className="px-4 py-2.5 rounded-xl text-sm font-medium bg-bg-2 border border-white/10 text-ink-1 hover:bg-bg-3 hover:border-white/15 transition-colors text-center focus:outline-none focus:ring-2 focus:ring-gold/40"
            >
              Recusar opcionais
            </button>
            <button
              type="button"
              onClick={handleAcceptAll}
              className="px-4 py-2.5 rounded-xl text-sm font-semibold bg-gold text-gold-deep hover:bg-gold/90 active:bg-gold/80 transition-colors text-center focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
            >
              Aceitar todos
            </button>
          </div>
        </div>

        {/* Painel expandido de preferencias — com transicao suave */}
        <div
          id="cookie-preferences-panel"
          className={`overflow-hidden transition-all duration-200 ease-in-out ${
            expanded ? 'max-h-[600px] opacity-100' : 'max-h-0 opacity-0'
          }`}
          aria-hidden={!expanded}
        >
          <div className="border-t border-white/10 pt-4 space-y-1">
            <p className="text-xs font-semibold text-ink-3 uppercase tracking-wide mb-3">
              Categorias de cookies
            </p>

            {/* Essenciais — sempre ativos */}
            <div className="flex items-start gap-3 justify-between py-3 border-b border-white/5">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-ink-1">Essenciais</p>
                <p className="text-xs text-ink-2 mt-0.5 leading-relaxed">
                  JWT, carrinho, sessão — necessários para o funcionamento do site
                </p>
              </div>
              <span className="shrink-0 text-xs font-medium text-gold bg-gold/10 border border-gold/30 px-2.5 py-1 rounded-full">
                Sempre ativo
              </span>
            </div>

            {/* Funcionais */}
            <div className="flex items-start gap-3 justify-between py-3 border-b border-white/5">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-ink-1">Funcionais</p>
                <p className="text-xs text-ink-2 mt-0.5 leading-relaxed">
                  Login persistente, preferências de interface e idioma
                </p>
              </div>
              <div className="shrink-0 pt-0.5">
                <Toggle
                  checked={prefs.functional}
                  onChange={() => togglePref('functional')}
                  ariaLabel="Ativar cookies funcionais"
                />
              </div>
            </div>

            {/* Analytics */}
            <div className="flex items-start gap-3 justify-between py-3 border-b border-white/5">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-ink-1">Analytics</p>
                <p className="text-xs text-ink-2 mt-0.5 leading-relaxed">
                  Métricas anônimas de uso para melhorar o serviço
                </p>
              </div>
              <div className="shrink-0 pt-0.5">
                <Toggle
                  checked={prefs.analytics}
                  onChange={() => togglePref('analytics')}
                  ariaLabel="Ativar cookies de analytics"
                />
              </div>
            </div>

            {/* Marketing */}
            <div className="flex items-start gap-3 justify-between py-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-ink-1">Marketing</p>
                <p className="text-xs text-ink-2 mt-0.5 leading-relaxed">
                  Personalização de anúncios e conteúdo patrocinado
                </p>
              </div>
              <div className="shrink-0 pt-0.5">
                <Toggle
                  checked={prefs.marketing}
                  onChange={() => togglePref('marketing')}
                  ariaLabel="Ativar cookies de marketing"
                />
              </div>
            </div>

            {/* Salvar preferencias */}
            <div className="pt-3">
              <button
                type="button"
                onClick={handleSavePrefs}
                className="w-full sm:w-auto bg-gold text-gold-deep px-6 py-2.5 rounded-xl text-sm font-semibold hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-1"
              >
                Salvar preferências
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
