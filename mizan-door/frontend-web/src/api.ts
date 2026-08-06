import axios from 'axios'
import { API_BASE_URL } from './config'
import type { AuthSession, Clinic, QueueEntry, User } from './types'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

/** Attach (or clear) the bearer token used for staff-only endpoints, e.g. after login/logout. */
export function setAuthToken(token: string | null) {
  if (token) {
    apiClient.defaults.headers.common.Authorization = `Bearer ${token}`
  } else {
    delete apiClient.defaults.headers.common.Authorization
  }
}

export async function registerClinic(payload: {
  clinicName: string
  specialty: string
  fullName: string
  email: string
  password: string
}): Promise<AuthSession> {
  const { data } = await apiClient.post<AuthSession>('/auth/register', {
    clinic_name: payload.clinicName,
    specialty: payload.specialty,
    full_name: payload.fullName,
    email: payload.email,
    password: payload.password,
  })
  return data
}

export async function login(email: string, password: string): Promise<AuthSession> {
  const { data } = await apiClient.post<AuthSession>('/auth/login', { email, password })
  return data
}

export async function fetchMe(): Promise<{ user: User; clinic: Clinic }> {
  const { data } = await apiClient.get<{ user: User; clinic: Clinic }>('/auth/me')
  return data
}

export async function getClinicQueue(clinicId: string): Promise<QueueEntry[]> {
  const { data } = await apiClient.get<QueueEntry[]>(`/clinics/${clinicId}/queue`)
  return data
}

export async function callNextPatient(clinicId: string): Promise<QueueEntry[]> {
  const { data } = await apiClient.post<QueueEntry[]>(`/clinics/${clinicId}/next`)
  return data
}
