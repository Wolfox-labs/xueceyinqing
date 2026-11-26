import { ReactNode, useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useThemeStore } from '../../stores/themeStore'
import { useAuthStore } from '../../stores/authStore'
import CommandPalette from './CommandPalette'
import ShortcutHelp from './ShortcutHelp'
import Icon, { type IconName } from './Icon'
import { useLearningTimeTracker } from '../../hooks/useLearningTimeTracker'
import { getHealth } from '../../api/health'

// 顶栏流水线状态：待检查 / 模型就绪 / 服务在线但模型未就绪 / 后端不可达
const PIPELINE_LABEL: Record<'checking' | 'live' | 'degraded' | 'offline', string> = {
  checking: '检查中',
  live: '实时',
  degraded: '模型未就绪',
  offline: '离线',
}

const navItems: { path: string; icon: IconName; labelKey: string; fallback: string }[] = [
  { path: '/dashboard', icon: 'dashboard', labelKey: 'nav.dashboard', fallback: '学习驾驶舱' },
  { path: '/algorithm-lab', icon: 'activity', labelKey: 'nav.algorithmLab', fallback: '算法实验室' },
  { path: '/learning-path', icon: 'path', labelKey: 'nav.learningPath', fallback: '自适应路径' },
  { path: '/assess', icon: 'assessment', labelKey: 'nav.assess', fallback: '诊断测评' },
  { path: '/generate', icon: 'resource', labelKey: 'nav.generate', fallback: '学习资源' },
  { path: '/chat', icon: 'assistant', labelKey: 'nav.chat', fallback: '学习助手' },
  { path: '/profile', icon: 'profile', labelKey: 'nav.profile', fallback: '学习者档案' },
]

const teacherNavItems: { path: string; icon: IconName; labelKey: string; fallback: string }[] = [
  { path: '/teacher', icon: 'dashboard', labelKey: 'nav.teacher', fallback: '教师工作台' },
  { path: '/algorithm-lab', icon: 'activity', labelKey: 'nav.algorithmLab', fallback: '算法实验室' },
  { path: '/generate', icon: 'resource', labelKey: 'nav.generate', fallback: '学习资源' },
  { path: '/chat', icon: 'assistant', labelKey: 'nav.chat', fallback: '教学助手' },
]
const pageMeta: Record<string, { title: string; note: string }> = {
  '/dashboard': { title: '学习决策控制台', note: '自适应策略正在运行' },
  '/algorithm-lab': { title: '算法实验室', note: 'KG-F-CUCB 可解释决策与实验验证' },
  '/learning-path': { title: '自适应学习路径', note: '知识图谱驱动的路径重排' },
  '/assess': { title: '诊断测评', note: '基于薄弱点的动态组卷' },
  '/generate': { title: '个性化资源工厂', note: '多智能体生成与审核' },
  '/chat': { title: '学习助手', note: '围绕当前任务的辅助问答' },
  '/profile': { title: '学习者档案', note: '动态画像与知识状态' },
  '/tasks': { title: '我的任务', note: '教师布置的学习任务' },
  '/teacher': { title: '教师工作台', note: '学生概况与学习任务管理' },
}

export default function Layout({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()
  const { theme, toggleTheme } = useThemeStore()
  const { session, logout } = useAuthStore()
  useLearningTimeTracker(Boolean(session))
  const [commandOpen, setCommandOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  // 顶栏那个"实时"原先写死在 JSX 里，后端不可达时也照样显示"实时"。
  const [pipeline, setPipeline] = useState<'checking' | 'live' | 'degraded' | 'offline'>('checking')

  useEffect(() => {
    let alive = true
    getHealth()
      .then((h) => {
        if (!alive) return
        if (h.status !== 'ok') setPipeline('offline')
        else setPipeline(h.crewai_ready ? 'live' : 'degraded')
      })
      .catch(() => { if (alive) setPipeline('offline') })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setCommandOpen(true)
      }
      if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault()
        setHelpOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const currentPath = location.pathname === '/' ? '/dashboard' : location.pathname
  const activeItem = navItems.find((item) => currentPath.startsWith(item.path))
  // 先按当前路径精确匹配：像 /tasks 这种"不在侧栏里"的页面原本会退化成仪表盘标题
// （页头显示"学习决策控制台"），因为它找不到对应的 nav 项。
  const meta = pageMeta[currentPath] || pageMeta[activeItem?.path || '/dashboard'] || pageMeta['/dashboard']
  const visibleNavItems = session?.role === 'teacher' ? teacherNavItems : navItems
  const displayName = session?.name || '演示学生'
  const displayRole = session?.role === 'teacher' ? '教师账号' : '学生账号'
  const initials = displayName.slice(0, 2).toUpperCase()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-frame">
      <aside className="app-sidebar">
        <div className="brand-block">
          <img className="brand-logo-mark" src="/brand/xuece-mark.svg" alt="学策引擎" />
          <div><strong>学策引擎</strong><small>——算法驱动的多智能体自适应学习系统</small></div>
        </div>
        <div className="sidebar-section-label">CONTROL MODULES</div>
        <nav className="app-nav">
          {visibleNavItems.map((item) => {
            const active = currentPath.startsWith(item.path)
            return (
              <button key={item.path} onClick={() => navigate(item.path)} className={active ? 'active' : ''}>
                <span>{t(item.labelKey, { defaultValue: item.fallback })}</span>
                {active && <i className="nav-cursor" />}
              </button>
            )
          })}
        </nav>
        <div className="sidebar-spacer" />
        <div className="engine-status">
          <div className="engine-status__head"><span>ADAPTIVE CORE</span><i /></div>
          <strong>策略引擎在线</strong>
          <p>知识图谱 · 遗忘模型 · Contextual Bandit</p>
          <div className="engine-status__line"><span /></div>
        </div>
        <button className="theme-switch" onClick={toggleTheme}>
          {theme === 'light' ? '深色控制台' : '浅色控制台'}
        </button>
      </aside>

      <main className="app-main">
        <header className="app-header">
          <div>
            <span className="header-kicker">学策引擎 / {currentPath.replace("/", "").toUpperCase() || "DASHBOARD"}</span>
            <h1>{meta.title}</h1>
            <p>{meta.note}</p>
          </div>
          <div className="header-center">
            <span className="live-dot" />
            <span>INSIGHT PIPELINE</span>
            <b>{PIPELINE_LABEL[pipeline]}</b>
          </div>
          <div className="header-actions">
            <div className="header-profile">
              <div>{initials}</div>
              <span><b>{displayName}</b><small>{displayRole}</small></span>
            </div>
            <button className="header-icon-button" onClick={toggleTheme} aria-label="切换主题">
              <Icon name={theme === 'light' ? 'moon' : 'sun'} size={18} />
            </button>
            <button className="header-logout" onClick={() => navigate('/account')}>账号设置</button>
            <button className="header-logout" onClick={handleLogout}>退出</button>
          </div>
        </header>
        <div className="app-content">{children}</div>
      </main>

      <CommandPalette open={commandOpen} onClose={() => setCommandOpen(false)} />
      <ShortcutHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  )
}
