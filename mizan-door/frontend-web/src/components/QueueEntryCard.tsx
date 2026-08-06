import { useTranslation } from 'react-i18next'
import { AlertTriangle, Phone, Stethoscope } from 'lucide-react'
import type { QueueEntry } from '../types'

interface QueueEntryCardProps {
  entry: QueueEntry
}

export default function QueueEntryCard({ entry }: QueueEntryCardProps) {
  const { t } = useTranslation()
  const isActive = entry.status === 'in_consultation'

  const statusLabel =
    entry.status === 'in_consultation' ? t('status.inConsultation') : t('status.waiting')

  return (
    <div
      className={`flex items-center justify-between rounded-xl border px-4 py-3 transition-colors ${
        isActive ? 'border-emerald-300 bg-emerald-50' : 'border-slate-200 bg-white'
      }`}
    >
      <div className="flex items-center gap-4">
        <div
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-lg font-bold ${
            isActive ? 'bg-emerald-600 text-white' : 'bg-slate-900 text-white'
          }`}
        >
          {entry.queue_number}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <p className="font-semibold text-slate-900">{entry.patient.name}</p>
            {entry.is_urgent && (
              <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                <AlertTriangle size={12} /> {t('queueEntry.urgent')}
              </span>
            )}
          </div>
          <p className="flex items-center gap-1 text-xs text-slate-500">
            <Phone size={12} /> {entry.patient.phone}
          </p>
        </div>
      </div>

      <span
        className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${
          isActive ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-700'
        }`}
      >
        {isActive && <Stethoscope size={12} />}
        {statusLabel}
      </span>
    </div>
  )
}
