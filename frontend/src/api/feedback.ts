import { request } from './client'

export type ResourceRating = 'helpful' | 'neutral' | 'not_helpful'
export type DifficultyFeedback = 'too_easy' | 'appropriate' | 'too_hard'

export function submitResourceFeedback(payload: {
  topic: string
  resource_type: string
  rating: ResourceRating
  difficulty?: DifficultyFeedback
  source_match?: boolean | null
}) {
  return request<{ status: string; reward: number }>('/feedback/resource', {
    method: 'POST',
    body: {
      difficulty: 'appropriate',
      source_match: null,
      ...payload,
    },
  })
}