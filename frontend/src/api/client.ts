const BASE_URL = import.meta.env.VITE_API_BASE || '/api'
const SESSION_KEY = 'xuece-session'

interface RequestOptions {
  method?: string
  headers?: Record<string, string>
  body?: unknown
  signal?: AbortSignal
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export function getAccessToken(): string | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { token?: string }
    return parsed.token || null
  } catch {
    return null
  }
}

/**
 * 当前登录用户的 ID；未登录时返回 undefined。
 *
 * 为什么必须用它：后端有一份 key 为 "default" 的**共享**数据。前端过去把
 * 'default' 硬编码进 8 个 API 模块并当查询参数发出去，于是"换个账号登录，
 * 档案页显示的仍是同一个人（甚至别人的）薄弱知识点"。
 * 这里返回 undefined，让 query 参数整个不出现——后端会以认证用户为准。
 *
 * ⚠ 字段名必须和 authStore.persistSession() 写的一致：
 *   { id, name, role, token, loginAt }
 * 这里曾错写成 parsed.user?.user_id（那是**接口响应**的形状，不是本地会话的
 * 形状），导致永远取不到 ID；一旦取不到，请求就不带 user_id，虽然后端有
 * 认证兜底、不至于串数据，但任何依赖该参数的逻辑都会静默失效。
 */
export function getCurrentUserId(): string | undefined {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return undefined
    const parsed = JSON.parse(raw) as { id?: string; user?: { user_id?: string } }
    // 兼容两种来源：本地会话用 id；若某处直接存了接口响应则有 user.user_id。
    const id = parsed.id || parsed.user?.user_id
    // "default" 不是真实用户 ID（真实 ID 是 uuid4().hex），不要把它当用户发出去。
    return id && id !== 'default' ? id : undefined
  } catch {
    return undefined
  }
}

/** 拼查询串：值为 undefined/空时整项省略，避免发出 user_id=default 这种脏参数。 */
export function withUserId(path: string, userId?: string): string {
  const uid = userId && userId !== 'default' ? userId : getCurrentUserId()
  if (!uid) return path
  return `${path}${path.includes('?') ? '&' : '?'}user_id=${encodeURIComponent(uid)}`
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', headers = {}, body, signal } = options
  const token = getAccessToken()
  const config: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    signal,
  }
  if (body) {
    config.body = JSON.stringify(body)
  }
  const res = await fetch(`${BASE_URL}${path}`, config)
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/auth/')) {
      localStorage.removeItem(SESSION_KEY)
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, err.detail || err.message || 'Request failed')
  }
  return res.json()
}

export { request }