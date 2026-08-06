import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Building2, Loader2, Plus, Stethoscope } from 'lucide-react'
import { createClinic, listClinics } from '../api'
import type { Clinic } from '../types'
import LanguageToggle from './LanguageToggle'

interface ClinicSelectProps {
  onSelect: (clinic: Clinic) => void
}

export default function ClinicSelect({ onSelect }: ClinicSelectProps) {
  const { t } = useTranslation()
  const [clinics, setClinics] = useState<Clinic[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [name, setName] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    listClinics()
      .then((data) => {
        setClinics(data)
        setShowCreateForm(data.length === 0)
      })
      .catch(() => setError(t('clinicSelect.connectionError')))
      .finally(() => setLoading(false))
  }, [t])

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    if (!name.trim() || !specialty.trim()) return

    setCreating(true)
    setError(null)
    try {
      const clinic = await createClinic(name.trim(), specialty.trim())
      onSelect(clinic)
    } catch {
      setError(t('clinicSelect.createError'))
    } finally {
      setCreating(false)
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

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {loading ? (
          <div className="flex justify-center py-8 text-slate-400">
            <Loader2 className="animate-spin" />
          </div>
        ) : (
          <>
            {clinics.length > 0 && (
              <div className="mb-6 space-y-2">
                <p className="mb-2 text-sm font-medium text-slate-600">{t('clinicSelect.selectClinic')}</p>
                {clinics.map((clinic) => (
                  <button
                    key={clinic.id}
                    type="button"
                    onClick={() => onSelect(clinic)}
                    className="flex w-full items-center gap-3 rounded-lg border border-slate-200 px-4 py-3 text-start transition-colors hover:border-emerald-500 hover:bg-emerald-50"
                  >
                    <Stethoscope size={18} className="shrink-0 text-emerald-600" />
                    <div>
                      <p className="font-medium text-slate-900">{clinic.name}</p>
                      <p className="text-xs text-slate-500">{clinic.specialty}</p>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {!showCreateForm ? (
              <button
                type="button"
                onClick={() => setShowCreateForm(true)}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 px-4 py-3 text-sm font-medium text-slate-600 transition-colors hover:border-emerald-500 hover:text-emerald-600"
              >
                <Plus size={16} /> {t('clinicSelect.registerNew')}
              </button>
            ) : (
              <form onSubmit={handleCreate} className="space-y-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="clinic-name">
                    {t('clinicSelect.clinicNameLabel')}
                  </label>
                  <input
                    id="clinic-name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                    placeholder={t('clinicSelect.clinicNamePlaceholder')}
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="clinic-specialty">
                    {t('clinicSelect.specialtyLabel')}
                  </label>
                  <input
                    id="clinic-specialty"
                    value={specialty}
                    onChange={(event) => setSpecialty(event.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                    placeholder={t('clinicSelect.specialtyPlaceholder')}
                    required
                  />
                </div>
                <div className="flex gap-2 pt-1">
                  {clinics.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowCreateForm(false)}
                      className="flex-1 rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
                    >
                      {t('clinicSelect.cancel')}
                    </button>
                  )}
                  <button
                    type="submit"
                    disabled={creating}
                    className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-60"
                  >
                    {creating && <Loader2 size={14} className="animate-spin" />}
                    {t('clinicSelect.createClinic')}
                  </button>
                </div>
              </form>
            )}
          </>
        )}
      </div>
    </div>
  )
}
