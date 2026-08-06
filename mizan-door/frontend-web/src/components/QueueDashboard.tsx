import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import axios from 'axios'
import { LogOut, PhoneCall, RefreshCw, Users } from 'lucide-react'
import type { Clinic } from '../types'
import { useClinicQueue } from '../hooks/useClinicQueue'
import { callNextPatient } from '../api'
import QueueEntryCard from './QueueEntryCard'
import ConnectionBadge from './ConnectionBadge'
import LanguageToggle from './LanguageToggle'

interface QueueDashboardProps {
  clinic: Clinic
  onLogout: () => void
}

export default function QueueDashboard({ clinic, onLogout }: QueueDashboardProps) {
  const { t } = useTranslation()
  const { queue, loading, error, status, refresh } = useClinicQueue(clinic.id)
  const [callingNext, setCallingNext] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const currentlyServing = queue.find((entry) => entry.status === 'in_consultation') ?? null
  const waitingCount = queue.filter((entry) => entry.status === 'waiting').length

  async function handleCallNext() {
    setCallingNext(true)
    setActionError(null)
    try {
      // The REST response updates state immediately; the WebSocket broadcast
      // (triggered by this same call, server-side) keeps every other
      // connected client in sync too.
      await callNextPatient(clinic.id)
    } catch (err) {
      // The staff session may have expired since login; force a fresh login
      // rather than leaving the receptionist stuck on a broken button.
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        onLogout()
        return
      }
      setActionError(t('dashboard.callNextError'))
    } finally {
      setCallingNext(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
          <div>
            <h1 className="text-lg font-bold text-slate-900">{clinic.name}</h1>
            <p className="text-sm text-slate-500">{clinic.specialty}</p>
          </div>
          <div className="flex items-center gap-3">
            <LanguageToggle />
            <ConnectionBadge status={status} />
            <button
              type="button"
              onClick={onLogout}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-slate-500 hover:bg-slate-100"
            >
              <LogOut size={14} /> {t('dashboard.logout')}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-8">
        <div className="mb-8 grid grid-cols-2 gap-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <p className="text-sm text-slate-500">{t('dashboard.currentlyServing')}</p>
            <p className="mt-1 text-3xl font-bold text-emerald-600">
              {currentlyServing ? `#${currentlyServing.queue_number}` : '—'}
            </p>
            {currentlyServing && (
              <p className="mt-1 text-sm text-slate-600">{currentlyServing.patient.name}</p>
            )}
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <p className="flex items-center gap-1 text-sm text-slate-500">
              <Users size={14} /> {t('dashboard.waiting')}
            </p>
            <p className="mt-1 text-3xl font-bold text-slate-900">{waitingCount}</p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleCallNext}
          disabled={callingNext}
          className="mb-8 flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-6 py-5 text-lg font-bold text-white shadow-lg shadow-emerald-600/20 transition-all hover:bg-emerald-700 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <PhoneCall size={22} />
          {callingNext ? t('dashboard.calling') : t('dashboard.callNext')}
        </button>

        {(error || actionError) && (
          <div className="mb-4 flex items-center justify-between gap-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>{actionError ?? error}</span>
            <button
              type="button"
              onClick={refresh}
              className="flex shrink-0 items-center gap-1 font-medium hover:underline"
            >
              <RefreshCw size={14} /> {t('dashboard.retry')}
            </button>
          </div>
        )}

        <div className="space-y-3">
          {loading && queue.length === 0 ? (
            <p className="py-8 text-center text-slate-400">{t('dashboard.loadingQueue')}</p>
          ) : queue.length === 0 ? (
            <p className="py-8 text-center text-slate-400">{t('dashboard.noPatients')}</p>
          ) : (
            queue.map((entry) => <QueueEntryCard key={entry.id} entry={entry} />)
          )}
        </div>
      </main>
    </div>
  )
}
