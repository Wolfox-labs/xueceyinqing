import { create } from 'zustand'
import { loginRequest, logoutRequest, registerRequest } from '../api/auth'

export type UserRole = 'student' | 'teacher'

export interface UserSession {
  id: string
  name: string
  role: UserRole
  token: string
  loginAt: string
}

interface AuthState {
  session: UserSession | null
  login: (payload: { username: string; password: string; role: UserRole }) => Promise<UserSession>
  // 注册不接受 role：自助注册一律是学生，教师由运维开通。
  register: (payload: { username: string; password: string }) => Promise<UserSession>
  logout: () => Promise<void>
}

const STORAGE_KEY = 'xuece-session'

function loadSession(): UserSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as UserSession
    if (!parsed?.id || !parsed?.role || !parsed?.token) return null
    return parsed
  } catch {
    return null
  }
}

function persistSession(result: Awaited<ReturnType<typeof loginRequest>>): UserSession {
  return {
    id: result.user.user_id,
    name: result.user.username,
    role: result.user.role as UserRole,
    token: result.access_token,
    loginAt: new Date().toISOString(),
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  session: loadSession(),
  login: async ({ username, password, role }) => {
    const result = await loginRequest(username.trim(), password, role)
    const session = persistSession(result)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
    set({ session })
    return session
  },
  register: async ({ username, password }) => {
    const result = await registerRequest(username.trim(), password)
    const session = persistSession(result)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
    set({ session })
    return session
  },
  logout: async () => {
    try {
      await logoutRequest()
    } catch {
      // 本地会话已失效时也要允许退出。
    }
    localStorage.removeItem(STORAGE_KEY)
    set({ session: null })
  },
}))