import { request } from './client'

export interface TopicListResponse {
  topics: string[]
}

export interface QuestionBankItem {
  _id: string
  _topic: string
  type: string
  knowledge_point: string
  question: string
  options: { label: string; text: string }[]
  answer: string
  explanation: string
  difficulty: string
}

export interface TopicQuestionsResponse {
  topic: string
  questions: QuestionBankItem[]
}

export async function listQuestionTopics(): Promise<TopicListResponse> {
  return request<TopicListResponse>('/question-bank/topics')
}

export async function getQuestionsByTopic(topic: string): Promise<TopicQuestionsResponse> {
  return request<TopicQuestionsResponse>(`/question-bank/${encodeURIComponent(topic)}`)
}

export async function saveQuestions(topic: string, rawText: string): Promise<{ saved: number }> {
  return request<{ saved: number }>('/question-bank/save', {
    method: 'POST',
    body: { topic, raw_text: rawText },
  })
}

export async function updateNodeResource(
  topic: string,
  nodeId: string,
  resourceType: string,
  resourceRef: string
): Promise<void> {
  return request(`/learning-path/${encodeURIComponent(topic)}/nodes/${nodeId}/resource`, {
    method: 'PUT',
    body: { resource_type: resourceType, resource_ref: resourceRef },
  })
}
