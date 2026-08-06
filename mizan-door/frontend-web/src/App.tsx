import { useEffect, useState } from 'react'
import AuthScreen from './components/AuthScreen'
import QueueDashboard from './components/QueueDashboard'
import { fetchMe, setAuthToken } from './api'
import type { AuthSession } from './types'

const STORAGE_KEY = 'mizan-door.auth-session'

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) {
      setReady(true)
      return
    }

    try {
      const parsed = JSON.parse(stored) as AuthSession
      setAuthToken(parsed.access_token)
      // Verify the token is still valid (it may have expired since the last
      // visit) before trusting the cached session.
      fetchMe()
        .then(() => setSession(parsed))
        .catch(() => {
          localStorage.removeItem(STORAGE_KEY)
          setAuthToken(null)
        })
        .finally(() => setReady(true))
    } catch {
      localStorage.removeItem(STORAGE_KEY)
      setReady(true)
    }
  }, [])

  function handleAuthenticated(newSession: AuthSession) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newSession))
    setAuthToken(newSession.access_token)
    setSession(newSession)
  }

  function handleLogout() {
    localStorage.removeItem(STORAGE_KEY)
    setAuthToken(null)
    setSession(null)
  }

  if (!ready) return null

  return session ? (
    <QueueDashboard clinic={session.clinic} onLogout={handleLogout} />
  ) : (
    <AuthScreen onAuthenticated={handleAuthenticated} />
  )
}
