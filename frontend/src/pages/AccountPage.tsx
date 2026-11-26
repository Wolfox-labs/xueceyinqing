import { FormEvent, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { changePasswordRequest } from '../api/auth'
import { useAuthStore } from '../stores/authStore'

export default function AccountPage() {
  const navigate = useNavigate()
  const { session, logout } = useAuthStore()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (!session) return <Navigate to="/login" replace />

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!currentPassword || !newPassword) {
      setError('请填写当前密码和新密码')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('两次输入的新密码不一致')
      return
    }
    setLoading(true)
    setError('')
    try {
      await changePasswordRequest(currentPassword, newPassword)
      await logout()
      navigate('/login', { replace: true })
    } catch (err) {
      setError((err as Error).message || '密码修改失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="account-page">
      <header className="account-hero">
        <div>
          <span className="core-kicker">ACCOUNT & SECURITY</span>
          <h1>账号设置</h1>
          <p>管理登录密码和当前账号的安全状态。</p>
        </div>
      </header>

      <div className="account-grid">
        <section className="account-summary">
          <div className="account-avatar">{session.name.slice(0, 1).toUpperCase()}</div>
          <h2>{session.name}</h2>
          <span>{session.role === 'teacher' ? '教师账号' : '学生账号'}</span>
          <dl>
            <div><dt>账号状态</dt><dd>正常</dd></div>
            <div><dt>登录方式</dt><dd>账号密码</dd></div>
            <div><dt>会话保护</dt><dd>Bearer Token</dd></div>
          </dl>
          <p>修改密码后，当前账号在所有设备上的旧会话都会失效，需要重新登录。</p>
        </section>

        <section className="account-form-panel">
          <div className="account-form-head">
            <h2>修改登录密码</h2>
            <p>新密码至少 6 位，并且不能与当前密码相同。</p>
          </div>
          <form onSubmit={handleSubmit}>
            <label><span>当前密码</span><input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" /></label>
            <label><span>新密码</span><input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" /></label>
            <label><span>确认新密码</span><input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" /></label>
            {error && <div className="core-error">{error}</div>}
            <button type="submit" disabled={loading}>{loading ? '正在修改...' : '修改密码并退出登录'}</button>
          </form>
          <div className="account-help">
            <strong>忘记密码？</strong>
            <span>比赛演示版暂不接入邮件或短信找回，请联系系统管理员重置。</span>
          </div>
        </section>
      </div>
    </div>
  )
}