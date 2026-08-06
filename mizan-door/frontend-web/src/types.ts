export type QueueStatus = 'waiting' | 'in_consultation' | 'completed' | 'cancelled'

export interface Clinic {
  id: string
  name: string
  specialty: string
  created_at: string
}

/** A clinic staff account (e.g. a receptionist). */
export interface User {
  id: string
  clinic_id: string
  email: string
  full_name: string
  created_at: string
}

/** Response from POST /auth/register and POST /auth/login. */
export interface AuthSession {
  access_token: string
  token_type: string
  user: User
  clinic: Clinic
}

export interface Patient {
  id: string
  name: string
  phone: string
  created_at: string
}

export interface QueueEntry {
  id: string
  clinic_id: string
  patient_id: string
  queue_number: number
  status: QueueStatus
  is_urgent: boolean
  joined_at: string
  patient: Patient
}

/** Payload broadcast over `WS /ws/clinics/{clinic_id}` after `POST /clinics/{clinic_id}/next`. */
export interface QueueUpdatedMessage {
  event: 'queue_updated'
  clinic_id: string
  queue: QueueEntry[]
}
