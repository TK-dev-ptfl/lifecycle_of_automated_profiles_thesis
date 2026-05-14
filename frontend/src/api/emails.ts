import { api } from './client'
import type { EmailAccount, EmailPlatform, EmailType } from '../types'

export const getEmailPlatforms = async (type?: EmailType) => {
  const { data } = await api.get<EmailPlatform[]>('/api/email-platforms', { params: type ? { type } : undefined })
  return data
}

export const createEmailPlatform = async (payload: Pick<EmailPlatform, 'type' | 'name' | 'domain'>) => {
  const { data } = await api.post<EmailPlatform>('/api/email-platforms', payload)
  return data
}

export const deleteEmailPlatform = async (id: string) => api.delete(`/api/email-platforms/${id}`)

export const getEmails = async (params?: { type?: EmailType; provider_id?: string; used_by_bot_id?: string }) => {
  const { data } = await api.get<EmailAccount[]>('/api/emails', { params })
  return data
}

export const createEmail = async (payload: Omit<EmailAccount, 'id' | 'created_at'>) => {
  const { data } = await api.post<EmailAccount>('/api/emails', payload)
  return data
}

export const updateEmail = async (id: string, payload: Partial<Omit<EmailAccount, 'id' | 'created_at' | 'type'>>) => {
  const { data } = await api.patch<EmailAccount>(`/api/emails/${id}`, payload)
  return data
}

export const deleteEmail = async (id: string) => api.delete(`/api/emails/${id}`)
