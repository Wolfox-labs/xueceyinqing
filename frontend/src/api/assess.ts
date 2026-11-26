import { request, getCurrentUserId } from './client'
import type { components } from './schema'

export type AssessResult = components['schemas']['AssessmentResult']

export interface QuestionItem {
  id: number
  type: string
  question: string
  options: string[] | null
  score: number
  knowledge_point: string
  difficulty: string | null
}

export interface AssessGenerateResult {
  assessment_id: string
  title: string
  questions: QuestionItem[]
}

export interface AssessAnswer {
  question_id: number
  answer: string
}

// 不再硬编码 'default'：后端 _uid() 以认证用户为准，这里只在确实知道用户时带上。
export async function generateAssessment(
  topic: string,
  questionCount = 5,
  userId?: string
): Promise<AssessGenerateResult> {
  const resolved = userId && userId !== 'default' ? userId : getCurrentUserId()
  return request<AssessGenerateResult>('/assess/generate', {
    method: 'POST',
    body: { topic, question_count: questionCount, ...(resolved ? { user_id: resolved } : {}) },
  })
}

export async function submitAssessment(
  assessmentId: string,
  answers: AssessAnswer[],
  userId?: string
): Promise<AssessResult> {
  const resolved = userId && userId !== 'default' ? userId : getCurrentUserId()
  return request<AssessResult>('/assess/submit', {
    method: 'POST',
    body: { assessment_id: assessmentId, ...(resolved ? { user_id: resolved } : {}), answers },
  })
}
