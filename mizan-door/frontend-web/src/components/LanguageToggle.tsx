import { useTranslation } from 'react-i18next'
import { Languages } from 'lucide-react'
import { SUPPORTED_LANGUAGES } from '../i18n/i18n'

export default function LanguageToggle() {
  const { t, i18n } = useTranslation()

  return (
    <div
      role="group"
      aria-label={t('language.toggle')}
      className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white p-1"
    >
      <Languages size={14} className="ms-1.5 shrink-0 text-slate-400" />
      {SUPPORTED_LANGUAGES.map((language) => (
        <button
          key={language}
          type="button"
          onClick={() => i18n.changeLanguage(language)}
          aria-pressed={i18n.language === language}
          className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase transition-colors ${
            i18n.language === language
              ? 'bg-emerald-600 text-white'
              : 'text-slate-500 hover:bg-slate-100'
          }`}
        >
          {language}
        </button>
      ))}
    </div>
  )
}
