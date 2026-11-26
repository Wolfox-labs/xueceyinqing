import { request } from './client'

export interface Assignment {
  id: string
  title: string
  topic: string
  resource_type: string
  instructions: string
  due_at: string | null
  created_at: string
  completed: boolean
  completion_count: number
}

export interface StudentSummary {
  user_id: string
  username: string
  role: string
  created_at: string
}

export interface TeacherOverview {
  stats: {
    student_count: number
    assignment_count: number
    completed_count: number
    completion_rate: number
  }
  students: StudentSummary[]
  assignments: Assignment[]
}

export function getTeacherOverview() {
  return request<TeacherOverview>('/teacher/overview')
}

export function listAssignments() {
  return request<{ assignments: Assignment[] }>('/assignments')
}

export function createAssignment(payload: {
  title: string
  topic: string
  resource_type: string
  instructions?: string
  due_at?: string | null
}) {
  return request<Assignment>('/assignments', { method: 'POST', body: payload })
}

export function completeAssignment(id: string) {
  return request<{ status: string; completed_at: string }>(`/assignments/${encodeURIComponent(id)}/complete`, {
    method: 'POST',
  })
}