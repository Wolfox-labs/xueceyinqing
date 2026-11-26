import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuthStore, type UserRole } from '../stores/authStore'
import { getHealth } from '../api/health'

type AuthMode = 'login' | 'register'

export default function LoginPage({ initialMode = 'login' }: { initialMode?: AuthMode }) {
  const navigate = useNavigate()
  const { session, login, register } = useAuthStore()
  const [mode, setMode] = useState<AuthMode>(initialMode)
  const [role, setRole] = useState<UserRole>('student')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  // 状态标签必须来自真实探测：原先这里写死"系统在线 / QWEN CONNECTED"，
  // 即使后端没起来、模型没就绪也照挂不误。
  const [health, setHealth] = useState<{ online: boolean; modelReady: boolean } | null>(null)

  useEffect(() => {
    let alive = true
    getHealth()
      .then((h) => { if (alive) setHealth({ online: h.status === 'ok', modelReady: Boolean(h.crewai_ready) }) })
      .catch(() => { if (alive) setHealth({ online: false, modelReady: false }) })
    return () => { alive = false }
  }, [])

  const roleLabel = useMemo(() => role === 'student' ? '学生' : '教师', [role])

  if (session) {
    return <Navigate to={session.role === 'teacher' ? '/teacher' : '/dashboard'} replace />
  }

  const switchRole = (nextRole: UserRole) => {
    setRole(nextRole)
    setError('')
  }

  const switchMode = (nextMode: AuthMode) => {
    setMode(nextMode)
    setError('')
    setConfirmPassword('')
    // 自助注册一律是学生账号：切到注册时把角色固定回学生，
    // 否则界面会暗示"创建教师账号"（后端已不再接受该角色）。
    if (nextMode === 'register') {
      setRole('student')
    }
    navigate(nextMode === 'login' ? '/login' : '/register', { replace: true })
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!username.trim() || !password) {
      setError('请输入账号和密码')
      return
    }
    if (mode === 'register' && password !== confirmPassword) {
      setError('两次输入的密码不一致')
      return
    }
    setError('')
    setLoading(true)
    try {
      if (mode === 'login') {
        const nextSession = await login({ username: username.trim(), password, role })
        navigate(nextSession.role === 'teacher' ? '/teacher' : '/dashboard', { replace: true })
      } else {
        await register({ username: username.trim(), password })
        navigate('/generate?tab=materials&onboarding=1', { replace: true })
      }
    } catch (err) {
      setError((err as Error).message || (mode === 'login' ? '登录失败' : '注册失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-shell system-login-shell">
      <div className="login-grid" />

      <header className="system-topbar">
        <div className="login-brand">
          <img className="brand-logo-mark login-brand-mark" src="/brand/xuece-mark.svg" alt="学策引擎" />
          <div>
            <strong>学策引擎</strong>
            <small>多智能体自适应学习系统 · V2.0</small>
          </div>
        </div>
        <div className="system-topbar-meta">
          {health === null ? (
            <span>正在检查服务状态…</span>
          ) : (
            <>
              <span className={health.online ? undefined : 'is-offline'}>
                <i />{health.online ? '系统在线' : '服务不可达'}
              </span>
              <span>{health.modelReady ? '模型已就绪' : '模型未就绪'}</span>
            </>
          )}
        </div>
      </header>

      <main className="system-login-stage">
        <section className="system-login-hero">
          <span className="core-kicker">MULTI-AGENT ADAPTIVE LEARNING SYSTEM</span>
          <h1>多智能体自适应学习系统</h1>
          <p>围绕知识状态、学习目标与个人资料，完成学习诊断、路径规划、资源生成和质量审核。</p>
        </section>

        <section className="system-capability-strip">
          <div><b>KNOWLEDGE GRAPH</b><span>结构化知识状态</span></div>
          <div><b>ADAPTIVE POLICY</b><span>KG-F-CUCB 学习决策</span></div>
          <div><b>MULTI-AGENT</b><span>生成与审核闭环</span></div>
          <div><b>PRIVATE MATERIALS</b><span>依据个人资料生成</span></div>
        </section>

        <section className="login-auth-layout">
          <aside className="login-auth-intro">
            <span className="core-kicker">SYSTEM ACCESS</span>
            <h2>{mode === 'login' ? '进入学策引擎' : '建立个性化学习空间'}</h2>
            <p>{mode === 'login' ? '登录后继续你的学习路径、诊断测评和资源生成任务。' : '注册后上传自己的资料，系统会依据资料生成学习内容。'}</p>

            <div className="login-auth-steps">
              <div><b>01</b><span><strong>创建账号</strong><small>独立保存学习记录与个人资料</small></span></div>
              <div><b>02</b><span><strong>添加资料</strong><small>支持 DOCX、PDF、Markdown、TXT 与图片</small></span></div>
              <div><b>03</b><span><strong>开始学习</strong><small>生成内容会标注本次参考资料</small></span></div>
            </div>

            <div className="login-security-note">
              <span>账号隔离</span><span>资料私有</span><span>来源可追溯</span>
            </div>
          </aside>

          <div className="login-form-panel">
            <form className="login-card" onSubmit={handleSubmit}>
              <div className="login-card-head">
                <span className="core-kicker">{mode === 'login' ? '账号登录' : '账号注册'}</span>
                <h2>{mode === 'login' ? `${roleLabel}登录` : `创建${roleLabel}账号`}</h2>
                <p>{mode === 'login' ? '使用你的账号进入系统' : '注册后直接进入个人资料上传'}</p>
              </div>

              <div className="login-mode-tabs">
                <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => switchMode('login')}>登录</button>
                <button type="button" className={mode === 'register' ? 'active' : ''} onClick={() => switchMode('register')}>注册</button>
              </div>

              <div className="login-role-tabs">
                {mode === 'login' ? (
                  <>
                    <button type="button" className={role === 'student' ? 'active' : ''} onClick={() => switchRole('student')}>学生</button>
                    <button type="button" className={role === 'teacher' ? 'active' : ''} onClick={() => switchRole('teacher')}>教师</button>
                  </>
                ) : (
                  <span className="login-role-note">注册即创建学生账号，教师账号由管理员开通</span>
                )}
              </div>

              <label className="login-field">
                <span>{roleLabel}账号</span>
                <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" placeholder="3-32 个字符" />
              </label>

              <label className="login-field">
                <span>密码</span>
                <div className="login-password">
                  <input type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder="至少 6 位" />
                  <button type="button" onClick={() => setShowPassword((value) => !value)}>{showPassword ? '隐藏' : '显示'}</button>
                </div>
              </label>

              {mode === 'register' && (
                <label className="login-field">
                  <span>确认密码</span>
                  <input type={showPassword ? 'text' : 'password'} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" placeholder="再次输入密码" />
                </label>
              )}

              <div className="login-options">
                <label><input type="checkbox" defaultChecked /> 保持登录状态</label>
                <span>安全会话</span>
              </div>

              {error && <div className="login-error">{error}</div>}

              <button className="login-submit" type="submit" disabled={loading}>
                {loading ? (mode === 'login' ? '登录中...' : '注册中...') : (mode === 'login' ? '进入学习驾驶舱' : '注册并添加资料')}
              </button>

              <div className="login-demo-info login-switch-info">
                <span>{mode === 'login' ? '还没有账号？' : '已经有账号？'}</span>
                <button type="button" onClick={() => switchMode(mode === 'login' ? 'register' : 'login')}>
                  {mode === 'login' ? '立即注册' : '返回登录'}
                </button>
              </div>
            </form>
          </div>
        </section>

        <footer className="system-login-footer">
          <span>学策引擎 · 多智能体自适应学习系统</span>
          <span>学习诊断 · 路径规划 · 资源生成 · 质量审核</span>
        </footer>
      </main>
    </div>
  )
}