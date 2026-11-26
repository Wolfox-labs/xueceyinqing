import { request, withUserId } from './client'
import type { components } from './schema'

export type SummaryData = components['schemas']['ReportSummaryResponse']
export type ChartsResponse = components['schemas']['ChartsResponse']

// 注意：这里的 userId 默认值是 undefined，不再硬编码 'default'。
// 后端存在一份 key 为 "default" 的共享数据，硬编码会把别人的档案/报表读出来。
// 真正的用户由 withUserId() 从登录态取；取不到时干脆不发这个参数，
// 后端会以认证上下文（Bearer token）为准。
export async function getSummary(userId?: string): Promise<SummaryData> {
  return request<SummaryData>(withUserId('/reports/summary', userId))
}

export async function getChartData(userId: string | undefined, type: 'radar' | 'line' | 'pie'): Promise<ChartsResponse> {
  return request<ChartsResponse>(withUserId(`/reports/charts?type=${type}`, userId))
}

export async function getSuggestions(userId?: string): Promise<string[]> {
  const res = await request<components['schemas']['ReportSuggestionsResponse']>(
    withUserId('/reports/suggestions', userId)
  )
  return res.suggestions ?? []
}