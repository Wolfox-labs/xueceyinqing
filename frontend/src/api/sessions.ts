import { request, getCurrentUserId, withUserId } from './client'
import type { paths } from './schema'

type SessionResponse = paths['/api/sessions']['post']['responses']['200']['content']['application/json']
type SessionsListResponse = paths['/api/sessions']['get']['responses']['200']['content']['application/json']
type MessagesResponse = paths['/api/sessions/{session_id}/messages']['get']['responses']['200']['content']['application/json']

// 不再硬编码 'default'：后端那个 key 是共享数据，会让不同账号看到同一批会话。
export async function createSession(userId?: string): Promise<SessionResponse> {
  const resolved = userId && userId !== 'default' ? userId : getCurrentUserId()
  return request<SessionResponse>('/sessions', {
    method: 'POST',
    body: resolved ? { user_id: resolved } : {},
  })
}

export async function getSessions(userId?: string): Promise<SessionsListResponse> {
  return request<SessionsListResponse>(withUserId('/sessions', userId))
}

export async function getMessages(sessionId: string): Promise<MessagesResponse> {
  return request<MessagesResponse>(`/sessions/${sessionId}/messages`)
}

export function getStreamUrl(sessionId: string, question: string, simulationId?: string): string {
  const base = import.meta.env.VITE_API_BASE || '/api'
  const params = new URLSearchParams({ question })
  if (simulationId) params.set('simulation_id', simulationId)
  return `${base}/sessions/${sessionId}/messages/stream?${params.toString()}`
}
