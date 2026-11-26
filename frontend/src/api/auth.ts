import { request } from './client'

export interface AuthUserInfo {
  user_id: string
  username: string
  role: 'student' | 'teacher' | string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_at: string
  user: AuthUserInfo
}

export function loginRequest(username: string, password: string, role: 'student' | 'teacher') {
  return request<LoginResponse>('/auth/login', {
    method: 'POST',
    body: { username, password, role },
  })
}

// 自助注册固定创建学生账号：接口不再接受 role，教师账号由运维开通，
// 因此这里也不再传递 role。
export function registerRequest(username: string, password: string) {
  return request<LoginResponse>('/auth/register', {
    method: 'POST',
    body: { username, password },
  })
}

export function changePasswordRequest(currentPassword: string, newPassword: string) {
  return request<{ status: string; message: string }>('/auth/change-password', {
    method: 'POST',
    body: { current_password: currentPassword, new_password: newPassword },
  })
}
export function logoutRequest() {
  return request<{ status: string }>('/auth/logout', { method: 'POST' })
}

export function getCurrentUser() {
  return request<AuthUserInfo>('/auth/me')
}