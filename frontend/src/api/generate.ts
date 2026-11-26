import { createPostSSEStream } from './sse'
import { getCurrentUserId } from './client'
import type { MaterialSource } from './materials'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export interface PptThemeOption {
  key: string
  name: string
  description: string
  is_dark: boolean
}

export async function getPptThemes(): Promise<PptThemeOption[]> {
  const response = await fetch(`${API_BASE}/generate/ppt-themes`)
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }
  const data = await response.json() as { themes?: PptThemeOption[] }
  return data.themes || []
}

export async function connectGenerateStream(
  type: string,
  topic: string,
  handlers: {
    onChunk?: (content: string) => void
    onResult?: (content: string, filepath?: string, sources?: MaterialSource[], strategy?: string, agentTrace?: string[]) => void
    onDone?: () => void
    onError?: (error: Error) => void
  },
  userId?: string,
  theme = 'dark_tech',
  materialIds: string[] = [],
): Promise<() => void> {
  // 后端 _uid() 会以认证用户为准覆盖 user_id；这里不再硬编码 'default'，
  // 避免把请求归到那份共享数据上。
  const resolved = userId && userId !== 'default' ? userId : getCurrentUserId()
  return createPostSSEStream(
    `${API_BASE}/generate`,
    {
      type,
      topic,
      ...(resolved ? { user_id: resolved } : {}),
      theme,
      material_ids: materialIds,
    },
    {
      onChunk: (content) => handlers.onChunk?.(content),
      onResult: (data) => {
        const payload = data as { content?: string; filepath?: string; sources?: MaterialSource[]; strategy?: string; agent_trace?: string[] }
        handlers.onResult?.(payload.content || '', payload.filepath, payload.sources || [], payload.strategy || '', payload.agent_trace || [])
      },
      onDone: () => handlers.onDone?.(),
      onError: (err) => handlers.onError?.(err),
    }
  )
}