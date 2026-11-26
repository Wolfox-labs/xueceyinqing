import { request } from './client'

/** 后端健康状态。用于界面上"系统在线 / 模型就绪"这类状态标签，
 *  避免把状态写死成永远为真（原先登录页与顶栏都是硬编码文案）。 */
export interface HealthStatus {
  status: string
  timestamp: string
  crewai_ready: boolean
}

export async function getHealth(): Promise<HealthStatus> {
  return request<HealthStatus>('/health')
}
