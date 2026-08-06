import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { WS_BASE_URL } from '../config'
import { getClinicQueue } from '../api'
import type { QueueEntry, QueueUpdatedMessage } from '../types'

export type ConnectionStatus = 'connecting' | 'open' | 'closed'

const RECONNECT_DELAY_MS = 2000

/**
 * Loads a clinic's queue over REST, then keeps it in sync in real time by
 * subscribing to `WS /ws/clinics/{clinicId}`. Automatically reconnects the
 * WebSocket if the connection drops.
 */
export function useClinicQueue(clinicId: string | null) {
  const { t } = useTranslation()
  const [queue, setQueue] = useState<QueueEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')

  const socketRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    if (!clinicId) return
    try {
      setLoading(true)
      const data = await getClinicQueue(clinicId)
      setQueue(data)
      setError(null)
    } catch {
      setError(t('dashboard.loadError'))
    } finally {
      setLoading(false)
    }
  }, [clinicId, t])

  useEffect(() => {
    if (!clinicId) return

    let cancelled = false
    refresh()

    const connect = () => {
      const socket = new WebSocket(`${WS_BASE_URL}/ws/clinics/${clinicId}`)
      socketRef.current = socket
      setStatus('connecting')

      socket.onopen = () => {
        if (cancelled) return
        setStatus('open')
      }

      socket.onmessage = (event) => {
        try {
          const message: QueueUpdatedMessage = JSON.parse(event.data)
          if (message.event === 'queue_updated' && message.clinic_id === clinicId) {
            setQueue(message.queue)
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message', err)
        }
      }

      socket.onclose = () => {
        if (cancelled) return
        setStatus('closed')
        reconnectTimerRef.current = window.setTimeout(connect, RECONNECT_DELAY_MS)
      }

      socket.onerror = () => {
        socket.close()
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
      }
      socketRef.current?.close()
    }
  }, [clinicId, refresh])

  return { queue, loading, error, status, refresh }
}
