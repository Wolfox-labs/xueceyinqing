import { Routes, Route, Navigate } from 'react-router-dom'
import { useThemeStore } from './stores/themeStore'
import { useAuthStore } from './stores/authStore'
import { useEffect } from 'react'
import Layout from './components/ui/Layout'
import RequireAuth from './components/auth/RequireAuth'
import RequireRole from './components/auth/RequireRole'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import AlgorithmLabPage from './pages/AlgorithmLabPage'
import ChatPage from './pages/ChatPage'
import LearningPathPage from './pages/LearningPathPage'
import AssessPage from './pages/AssessPage'
import ProfilePage from './pages/ProfilePage'
import GeneratePage from './pages/GeneratePage'
import TeacherDashboardPage from './pages/TeacherDashboardPage'
import TasksPage from './pages/TasksPage'
import AccountPage from './pages/AccountPage'

function RoleHome() {
  const session = useAuthStore((state) => state.session)
  return <Navigate to={session?.role === 'teacher' ? '/teacher' : '/dashboard'} replace />
}
function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<RoleHome />} />
      <Route path="/dashboard" element={<RequireRole roles={['student']}><DashboardPage /></RequireRole>} />
      <Route path="/algorithm-lab" element={<AlgorithmLabPage />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="/learning-path" element={<LearningPathPage />} />
      <Route path="/assess" element={<AssessPage />} />
      {/* 「学情洞察」已并入「学习者档案」：该页原有内容（4 项学情指标、正确率趋势、
          策略建议）与仪表盘面板 07 完全重复，画像六维又与档案页重复，写死的测评历史
          是假数据。这里保留重定向，避免旧书签/外链 404。 */}
      <Route path="/report" element={<Navigate to="/profile" replace />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/account" element={<AccountPage />} />
      <Route path="/generate" element={<GeneratePage />} />
      <Route path="/tasks" element={<RequireRole roles={['student']}><TasksPage /></RequireRole>} />
      <Route path="/teacher" element={<RequireRole roles={['teacher']}><TeacherDashboardPage /></RequireRole>} />
    </Routes>
  )
}

export default function App() {
  const theme = useThemeStore((s) => s.theme)

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', theme === 'dark')
    root.classList.toggle('light', theme === 'light')
  }, [theme])

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<LoginPage initialMode="register" />} />
      <Route path="*" element={(
        <RequireAuth>
          <Layout>
            <AppRoutes />
          </Layout>
        </RequireAuth>
      )} />
    </Routes>
  )
}
