import { getAccessToken } from './client'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export const MAX_MATERIAL_BYTES = 20 * 1024 * 1024
export const MAX_CONTEXT_CHARS = 9000

export interface Material {
  id: string
  name: string
  file_type: string
  size_bytes: number
  enabled: boolean
  status: string
  created_at: string
  updated_at: string
}

export interface MaterialSource {
  id: string
  name: string
  excerpt: string
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem('xuece-session')
      if (window.location.pathname !== '/login') window.location.href = '/login'
    }
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || error.message || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

function authHeaders(): HeadersInit {
  const token = getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function listMaterials(): Promise<Material[]> {
  const response = await fetch(`${API_BASE}/materials`, { headers: authHeaders() })
  const data = await parseResponse<{ materials: Material[] }>(response)
  return data.materials || []
}

export async function uploadMaterial(file: File): Promise<Material> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(`${API_BASE}/materials`, {
    method: 'POST',
    headers: authHeaders(),
    body,
  })
  return parseResponse<Material>(response)
}

export async function setMaterialEnabled(id: string, enabled: boolean): Promise<Material> {
  const response = await fetch(`${API_BASE}/materials/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify({ enabled }),
  })
  return parseResponse<Material>(response)
}

export async function deleteMaterial(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/materials/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  await parseResponse<{ status: string }>(response)
}