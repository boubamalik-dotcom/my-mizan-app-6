import axios from 'axios'
import { API_BASE_URL } from './config'
import type { Clinic, QueueEntry } from './types'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

export async function listClinics(): Promise<Clinic[]> {
  const { data } = await apiClient.get<Clinic[]>('/clinics')
  return data
}

export async function createClinic(name: string, specialty: string): Promise<Clinic> {
  const { data } = await apiClient.post<Clinic>('/clinics', { name, specialty })
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
