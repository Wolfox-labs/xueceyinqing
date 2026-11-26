import { request } from './client'

export interface AgentTriggerRules {
  critic_enabled: boolean
  quiz_agent_enabled: boolean
  reviewer_enabled: boolean
  orchestration_mode: 'multi_agent' | 'single_agent'
  deliberate_threshold: number
  max_rounds: number
}

export function getAgentTriggerRules() {
  return request<AgentTriggerRules>('/agents/trigger-rules')
}
