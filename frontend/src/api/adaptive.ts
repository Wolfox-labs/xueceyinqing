import { request } from './client'

export interface AdaptiveRecommendation {
  knowledge_point: string
  effective_mastery: number
  forgetting_risk: number
  priority: number
  target_difficulty: number
  reason: string
  action?: string
  action_label?: string
  context?: string
}

export interface KnowledgeGraphNode {
  name: string
  importance: number
  /** 前置知识点名（依赖边由来）。没有前置时为空数组。 */
  prerequisites: string[]
  /** 真实有效掌握度；该知识点还没有任何证据时为 null（不编造初始值）。 */
  mastery: number | null
}

export interface AdaptiveDashboardResponse {
  user_id: string
  needs_onboarding: boolean
  summary: {
    mastery: number
    study_minutes: number
    risk_points: number
    policy_hit_rate: number
  }
  recommendation: AdaptiveRecommendation | null
  recommendations: AdaptiveRecommendation[]
  knowledge_states: {
    knowledge_point: string
    stored_mastery: number
    effective_mastery: number
    evidence_count: number
    last_practiced: string
  }[]
  /** 真实知识依赖图谱：节点、前置边、重要度与有效掌握度。 */
  knowledge_graph: KnowledgeGraphNode[]
  experiment: { label: string; gain: number; retention: number; is_demo_data?: boolean }[]
  policy_snapshot: Record<string, Record<string, { pulls: number; mean_reward: number }>>
}

export interface EvidenceObservation {
  knowledge_point: string
  score: number
  observed_at?: string
}

export interface AdaptiveEvidenceResponse {
  states: {
    knowledge_point: string
    mastery: number
    effective_mastery: number
    evidence_count: number
  }[]
  recommendations: AdaptiveRecommendation[]
  policy_update?: {
    context: string
    action: string
    reward: number
    snapshot: AdaptiveDashboardResponse['policy_snapshot']
  }
}

export interface AdaptiveDecision {
  id: string
  event_type: 'assessment_evidence' | 'resource_generate' | 'policy_select' | 'policy_update' | string
  knowledge_point: string
  mastery: number | null
  forgetting: number | null
  urgency: number | null
  selected_action: string
  reward: number | null
  related_id: string
  details: Record<string, unknown>
  created_at: string
}
export interface PolicySelectResponse {
  context: string
  action: string
  snapshot: AdaptiveDashboardResponse['policy_snapshot']
}

export function listAdaptiveDecisions(limit = 50) {
  return request<{ decisions: AdaptiveDecision[] }>(`/adaptive/decisions?limit=${limit}`)
}
export function getAdaptiveDashboard() {
  return request<AdaptiveDashboardResponse>('/adaptive/dashboard')
}

export function submitAdaptiveEvidence(
  observations: EvidenceObservation[],
  recentErrors: Record<string, number> = {},
) {
  return request<AdaptiveEvidenceResponse>('/adaptive/evidence', {
    method: 'POST',
    body: { observations, recent_errors: recentErrors },
  })
}

export function selectAdaptivePolicy(payload: {
  mastery: number
  urgency: number
  learning_style?: string
  actions?: string[]
}) {
  return request<PolicySelectResponse>('/adaptive/policy/select', {
    method: 'POST',
    body: {
      learning_style: 'reading',
      actions: ['explain', 'example', 'practice', 'review', 'challenge'],
      ...payload,
    },
  })
}

export function updateAdaptivePolicy(context: string, action: string, reward: number) {
  return request<{ status: string; snapshot: AdaptiveDashboardResponse['policy_snapshot'] }>(
    '/adaptive/policy/update',
    {
      method: 'POST',
      body: { context, action, reward },
    },
  )
}

export interface AdaptiveStateInput {
  knowledge_point: string
  mastery: number
  evidence_count?: number
  last_practiced?: string
}

export interface KnowledgeNodeInput {
  name: string
  importance?: number
  prerequisites?: string[]
}

export function recommendAdaptive(
  states: AdaptiveStateInput[],
  graph: KnowledgeNodeInput[] = [],
  recentErrors: Record<string, number> = {},
  limit?: number,
) {
  return request<{ recommendations: AdaptiveRecommendation[] }>('/adaptive/recommend', {
    method: 'POST',
    body: { states, graph, recent_errors: recentErrors, limit },
  })
}

export interface AdaptiveSimulationInput {
  knowledge_point: string
  mastery: number
  forgetting: number
  dependency: number
  errors: number
  importance: number
}

export interface AdaptiveSimulationResponse {
  simulation_id: string
  user_id: string
  created_at: string
  inputs: AdaptiveSimulationInput
  hint: AdaptiveRecommendation
  profile_text: string
}

export function createAdaptiveSimulation(input: AdaptiveSimulationInput) {
  return request<AdaptiveSimulationResponse>('/adaptive/simulations', {
    method: 'POST',
    body: input,
  })
}

export function getAdaptiveSimulation(simulationId: string) {
  return request<AdaptiveSimulationResponse>(`/adaptive/simulations/${simulationId}`)
}

