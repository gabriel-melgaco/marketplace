export type CookieConsent = {
  analytics: boolean
  marketing: boolean
  functional: boolean
  decidedAt: string // ISO 8601
  version: string   // "1.0" — mudar aqui força re-exibição do banner
}

const CONSENT_KEY = 'megdev_cookie_consent'
const CONSENT_VERSION = '1.0'

export function getConsent(): CookieConsent | null {
  try {
    const raw = localStorage.getItem(CONSENT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as CookieConsent
    if (parsed.version !== CONSENT_VERSION) return null
    return parsed
  } catch {
    return null
  }
}

export function saveConsent(consent: Omit<CookieConsent, 'decidedAt' | 'version'>) {
  const full: CookieConsent = {
    ...consent,
    decidedAt: new Date().toISOString(),
    version: CONSENT_VERSION,
  }
  localStorage.setItem(CONSENT_KEY, JSON.stringify(full))
}

export function hasConsented(): boolean {
  return getConsent() !== null
}

export function clearConsent() {
  localStorage.removeItem(CONSENT_KEY)
}
