import { Wifi, WifiOff } from 'lucide-react'
import type { ConnectionStatus } from '../hooks/useClinicQueue'

export default function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  const isOpen = status === 'open'

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
        isOpen ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
      }`}
    >
      {isOpen ? <Wifi size={12} /> : <WifiOff size={12} />}
      {isOpen ? 'Live' : 'Reconnecting…'}
    </span>
  )
}
