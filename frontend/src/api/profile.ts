import { request, withUserId } from './client'
import type { components } from './schema'

export type ProfileResponse = components['schemas']['ProfileResponse']

export interface ProfileCardItem {
  label: string
  value: string
  source: string
  status: string
  confidence?: number | null
  score?: number | null
}

export interface ProfileCard {
  id: string
  title: string
  subtitle: string
  kind: string
  items: ProfileCardItem[]
  tags: string[]
  updated_at: string
}

export interface ProfileActivity {
  timestamp: string
  source: string
  title: string
  detail: string
}

export interface ProfileDashboardResponse {
  user_id: string
  identity: {
    display_name: string
    learning_stage: string
    subjects: string[]
    last_active: string
  }
  summary: {
    mastery_avg: number
    weak_point_count: number
    topic_count: number
    conversation_count: number
    profile_completeness: number
    latest_topic: string
  }
  cards: ProfileCard[]
  knowledge: {
    labels: string[]
    values: number[]
  }
  activities: ProfileActivity[]
  update_log: ProfileActivity[]
}

// 不再硬编码 'default'：后端那个 key 是**共享**数据，会把别人的画像读出来。
// 见 client.ts 的 withUserId()。
export async function getProfile(userId?: string): Promise<ProfileResponse> {
  return request<ProfileResponse>(withUserId('/profile', userId))
}

export async function getProfileDashboard(userId?: string): Promise<ProfileDashboardResponse> {
  return request<ProfileDashboardResponse>(withUserId('/profile/dashboard', userId))
}
