import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import ar from './ar.json'
import fr from './fr.json'

export const SUPPORTED_LANGUAGES = ['fr', 'ar'] as const
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number]

const RTL_LANGUAGES: SupportedLanguage[] = ['ar']
const LANGUAGE_STORAGE_KEY = 'mizan-door.language'

function getStoredLanguage(): SupportedLanguage {
  const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY)
  return stored === 'ar' ? 'ar' : 'fr'
}

export function isRtl(language: string): boolean {
  return RTL_LANGUAGES.includes(language as SupportedLanguage)
}

/** Keeps <html dir="..." lang="..."> in sync with the active language, so
 * the browser (and Tailwind's `rtl:`/logical-property utilities) apply the
 * correct layout direction everywhere, not just inside React-rendered DOM. */
export function applyDocumentDirection(language: string): void {
  document.documentElement.dir = isRtl(language) ? 'rtl' : 'ltr'
  document.documentElement.lang = language
}

i18n.use(initReactI18next).init({
  resources: {
    fr: { translation: fr },
    ar: { translation: ar },
  },
  lng: getStoredLanguage(),
  fallbackLng: 'fr',
  supportedLngs: SUPPORTED_LANGUAGES as unknown as string[],
  interpolation: {
    escapeValue: false,
  },
})

applyDocumentDirection(i18n.language)

i18n.on('languageChanged', (language) => {
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language)
  applyDocumentDirection(language)
})

export default i18n
