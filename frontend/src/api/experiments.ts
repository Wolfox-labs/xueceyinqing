import { request } from './client'

export interface AgentRuntimeConfig {
  profile_enabled: boolean
  critic_enabled: boolean
  reviewer_enabled: boolean
  quiz_agent_enabled: boolean
  orchestration_mode: 'multi_agent' | 'single_agent'
  standard_threshold: number
  deliberate_threshold: number
  max_rounds: number
  updated_at?: string
}

export interface AblationRun {
  id: string
  variant: string
  topic: string
  repetition: number
  status: string
  output_text: string
  latency_ms: number | null
  estimated_tokens: number | null
  format_pass: boolean | null
  withdrawn: boolean
  agent_trace: string[]
  error: string
  created_at: string
}

export interface AblationExperiment {
  id: string
  name: string
  task_type: string
  variants: string[]
  topics: string[]
  repetitions: number
  status: string
  total_runs: number
  completed_runs: number
  error: string
  runs: AblationRun[]
  created_at: string
  completed_at?: string | null
}
export function getAgentRuntimeConfig() {
  return request<AgentRuntimeConfig>('/experiments/agent-config')
}

export function updateAgentRuntimeConfig(config: Partial<AgentRuntimeConfig>) {
  return request<AgentRuntimeConfig>('/experiments/agent-config', {
    method: 'PUT',
    body: config,
  })
}

export function resetAgentRuntimeConfig() {
  return request<AgentRuntimeConfig>('/experiments/agent-config/reset', {
    method: 'POST',
  })
}
export function createAblationExperiment(payload: {
  name: string
  variants: string[]
  topics: string[]
  repetitions: number
  task_type?: 'document' | 'exercise'
  dry_run?: boolean
}) {
  return request<AblationExperiment>('/experiments/ablation', {
    method: 'POST',
    body: payload,
  })
}

export function getAblationExperiment(id: string) {
  return request<AblationExperiment>(`/experiments/ablation/${encodeURIComponent(id)}`)
}

export function listAblationExperiments() {
  return request<{ experiments: AblationExperiment[] }>('/experiments/ablation')
}