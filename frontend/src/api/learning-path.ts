import { request, getCurrentUserId, withUserId } from './client'
import { createPostSSEStream } from './sse'
import type { components } from './schema'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export type LearningNodeData = components['schemas']['PathNode']
export type LearningPathGenerated = components['schemas']['LearningPath']

// 不再硬编码 'default'：那是后端的**共享** key，会读到别人的学习路径。
export async function getLearningPath(userId?: string): Promise<{ nodes: LearningNodeData[]; topic: string }> {
  const res = await request<LearningNodeData[] | LearningPathGenerated>(withUserId('/learning-path', userId))
  if (Array.isArray(res)) return { nodes: res, topic: '' }
  return { nodes: res.nodes ?? [], topic: res.topic ?? '' }
}

export async function updateNodeStatus(
  topic: string,
  nodeId: string,
  status: 'pending' | 'in_progress' | 'completed'
): Promise<void> {
  return request(`/learning-path/${encodeURIComponent(topic)}/nodes/${nodeId}/status`, {
    method: 'PUT',
    body: { status },
  })
}

export async function generateLearningPath(
  topic: string,
  onChunk: (content: string) => void,
  onPath: (path: LearningPathGenerated) => void,
  onDone: () => void,
  onError: (err: string) => void,
  userId?: string
): Promise<() => void> {
  // 请求体里的 user_id 由后端 _uid() 以认证用户为准覆盖；
  // 这里只在确实知道用户时才带上，避免发出 "default"。
  const resolved = userId && userId !== 'default' ? userId : getCurrentUserId()
  return createPostSSEStream(
    `${API_BASE}/learning-path/generate`,
    resolved ? { topic, user_id: resolved } : { topic },
    {
      onChunk: (content) => onChunk(content),
      onResult: (data) => onPath(data as unknown as LearningPathGenerated),
      onDone,
      onError: (err) => onError(err.message),
    }
  )
}
