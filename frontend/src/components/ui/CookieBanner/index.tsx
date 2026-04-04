import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
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
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed ${
        checked ? 'bg-blue-700' : 'bg-gray-300'
      }`}
    >
      <span
        aria-hidden="true"
        className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 ${
          checked ? 'translate-x-6' : 'translate-x-1'
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
      className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-gray-200 shadow-lg pb-20 sm:pb-4"
    >
      <div className="max-w-4xl mx-auto px-4 py-4 space-y-4">

        {/* Linha principal: texto + botoes */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <p className="text-sm text-gray-700 flex-1 leading-relaxed">
            Usamos cookies para melhorar sua experiência. Veja nossa{' '}
            <Link
              to="/politica-de-cookies"
              className="text-blue-800 underline underline-offset-2 hover:text-blue-900 font-medium"
            >
              Política de Cookies
            </Link>
            .
          </p>

          {/*
            Hierarquia visual progressiva:
            1. Personalizar — peso baixo (ghost/outline discreto)
            2. Recusar opcionais — peso medio (outline com borda visivel)
            3. Aceitar todos — peso alto (fundo solido, destaque maximo)
          */}
          <div className="flex flex-col xs:flex-row flex-wrap items-stretch xs:items-center gap-2 sm:gap-3 shrink-0">
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              aria-controls="cookie-preferences-panel"
              className="px-4 py-2.5 rounded-xl text-sm font-medium text-blue-800 border border-blue-200 hover:bg-blue-50 hover:border-blue-300 transition-colors text-center"
            >
              {expanded ? 'Ocultar opções' : 'Personalizar'}
            </button>
            <button
              type="button"
              onClick={handleRejectOptional}
              className="px-4 py-2.5 rounded-xl text-sm font-medium border border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-colors text-center"
            >
              Recusar opcionais
            </button>
            <button
              type="button"
              onClick={handleAcceptAll}
              className="px-4 py-2.5 rounded-xl text-sm font-semibold bg-blue-900 text-white hover:bg-blue-800 active:bg-blue-950 transition-colors text-center shadow-sm"
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
          <div className="border-t border-gray-100 pt-4 space-y-1">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
              Categorias de cookies
            </p>

            {/* Essenciais — sempre ativos */}
            <div className="flex items-start gap-3 justify-between py-3 border-b border-gray-100">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-800">Essenciais</p>
                <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                  JWT, carrinho, sessão — necessários para o funcionamento do site
                </p>
              </div>
              <span className="shrink-0 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-100 px-2.5 py-1 rounded-full">
                Sempre ativo
              </span>
            </div>

            {/* Funcionais */}
            <div className="flex items-start gap-3 justify-between py-3 border-b border-gray-100">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-800">Funcionais</p>
                <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
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
            <div className="flex items-start gap-3 justify-between py-3 border-b border-gray-100">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-800">Analytics</p>
                <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
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
                <p className="text-sm font-semibold text-gray-800">Marketing</p>
                <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
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
                className="w-full sm:w-auto bg-blue-900 text-white px-6 py-2.5 rounded-xl text-sm font-semibold hover:bg-blue-800 active:bg-blue-950 transition-colors shadow-sm"
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
