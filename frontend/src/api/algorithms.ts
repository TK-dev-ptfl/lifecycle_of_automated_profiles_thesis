import { api } from './client'

export interface MethodFile {
  name: string
  path: string
  content: string
}

export type MethodFilesResponse = Record<string, MethodFile[]>

export const getMethodFiles = async () => {
  const { data } = await api.get<MethodFilesResponse>('/api/algorithms/method-files')
  return data
}

