import { getAccessToken, request } from './client'

export interface LearningTimeSummary {
  user_id: string
  date: string
  today_seconds: number
  today_minutes: number
  total_seconds: number
  total_minutes: number
  total_hours: number
}

export function sendLearningHeartbeat(seconds: number) {
  return request<LearningTimeSummary>('/activity/heartbeat', {
    method: 'POST',
    body: { seconds, source: 'web' },
  })
}

export function getLearningTimeSummary() {
  return request<LearningTimeSummary>('/activity/summary')
}

export function sendLearningHeartbeatKeepalive(seconds: number) {
  const token = getAccessToken()
  const base = import.meta.env.VITE_API_BASE || '/api'
  void fetch(`${base}/activity/heartbeat`, {
    method: 'POST',
    keepalive: true,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ seconds, source: 'web' }),
  })
}
