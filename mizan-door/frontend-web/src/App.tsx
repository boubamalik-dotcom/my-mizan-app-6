import { useEffect, useState } from 'react'
import ClinicSelect from './components/ClinicSelect'
import QueueDashboard from './components/QueueDashboard'
import type { Clinic } from './types'

const STORAGE_KEY = 'mizan-door.selected-clinic'

export default function App() {
  const [clinic, setClinic] = useState<Clinic | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      try {
        setClinic(JSON.parse(stored) as Clinic)
      } catch {
        localStorage.removeItem(STORAGE_KEY)
      }
    }
    setReady(true)
  }, [])

  function handleSelectClinic(selected: Clinic) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(selected))
    setClinic(selected)
  }

  function handleSwitchClinic() {
    localStorage.removeItem(STORAGE_KEY)
    setClinic(null)
  }

  if (!ready) return null

  return clinic ? (
    <QueueDashboard clinic={clinic} onSwitchClinic={handleSwitchClinic} />
  ) : (
    <ClinicSelect onSelect={handleSelectClinic} />
  )
}
