import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Building2, Loader2, Lock, Mail, User as UserIcon } from 'lucide-react'
import axios from 'axios'
import { login, registerClinic } from '../api'
import type { AuthSession } from '../types'
import LanguageToggle from './LanguageToggle'

interface AuthScreenProps {
  onAuthenticated: (session: AuthSession) => void
}

type Mode = 'login' | 'register'

export default function AuthScreen({ onAuthenticated }: AuthScreenProps) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [clinicName, setClinicName] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      const session =
        mode === 'login'
          ? await login(email.trim(), password)
          : await registerClinic({
              clinicName: clinicName.trim(),
              specialty: specialty.trim(),
              fullName: fullName.trim(),
              email: email.trim(),
              password,
            })
      onAuthenticated(session)
    } catch (err) {
      if (axios.isAxiosError(err)) {
        if (mode === 'login' && err.response?.status === 401) {
          setError(t('auth.loginError'))
        } else if (mode === 'register' && err.response?.status === 409) {
          setError(t('auth.emailTakenError'))
        } else if (!err.response) {
          setError(t('auth.networkError'))
        } else {
          setError(mode === 'login' ? t('auth.loginError') : t('auth.registerError'))
        }
      } else {
        setError(mode === 'login' ? t('auth.loginError') : t('auth.registerError'))
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-emerald-600 p-3 text-white">
              <Building2 size={24} />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900">{t('app.name')}</h1>
              <p className="text-sm text-slate-500">{t('app.tagline')}</p>
            </div>
          </div>
          <LanguageToggle />
        </div>

        <div className="mb-6 flex rounded-lg bg-slate-100 p-1">
          <button
            type="button"
            onClick={() => switchMode('login')}
            className={`flex-1 rounded-md py-2 text-sm font-semibold transition-colors ${
              mode === 'login' ? 'bg-white text-emerald-700 shadow-sm' : 'text-slate-500'
            }`}
          >
            {t('auth.loginTab')}
          </button>
          <button
            type="button"
            onClick={() => switchMode('register')}
            className={`flex-1 rounded-md py-2 text-sm font-semibold transition-colors ${
              mode === 'register' ? 'bg-white text-emerald-700 shadow-sm' : 'text-slate-500'
            }`}
          >
            {t('auth.registerTab')}
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          {mode === 'register' && (
            <>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="clinic-name">
                  {t('auth.clinicNameLabel')}
                </label>
                <input
                  id="clinic-name"
                  value={clinicName}
                  onChange={(event) => setClinicName(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                  placeholder={t('auth.clinicNamePlaceholder')}
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="specialty">
                  {t('auth.specialtyLabel')}
                </label>
                <input
                  id="specialty"
                  value={specialty}
                  onChange={(event) => setSpecialty(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                  placeholder={t('auth.specialtyPlaceholder')}
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="full-name">
                  {t('auth.fullNameLabel')}
                </label>
                <div className="relative">
                  <UserIcon
                    size={16}
                    className="pointer-events-none absolute inset-y-0 start-3 my-auto text-slate-400"
                  />
                  <input
                    id="full-name"
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 ps-9 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                    placeholder={t('auth.fullNamePlaceholder')}
                    required
                  />
                </div>
              </div>
            </>
          )}

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="email">
              {t('auth.email')}
            </label>
            <div className="relative">
              <Mail
                size={16}
                className="pointer-events-none absolute inset-y-0 start-3 my-auto text-slate-400"
              />
              <input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 ps-9 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                placeholder="receptionist@clinic.com"
                required
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="password">
              {t('auth.password')}
            </label>
            <div className="relative">
              <Lock
                size={16}
                className="pointer-events-none absolute inset-y-0 start-3 my-auto text-slate-400"
              />
              <input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 ps-9 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                minLength={mode === 'register' ? 8 : undefined}
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 disabled:opacity-60"
          >
            {submitting && <Loader2 size={14} className="animate-spin" />}
            {mode === 'login' ? t('auth.loginButton') : t('auth.registerButton')}
          </button>
        </form>
      </div>
    </div>
  )
}
