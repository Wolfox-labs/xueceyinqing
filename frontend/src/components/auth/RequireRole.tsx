import { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore, type UserRole } from '../../stores/authStore'

export default function RequireRole({
  roles,
  children,
}: {
  roles: UserRole[]
  children: ReactNode
}) {
  const session = useAuthStore((state) => state.session)
  if (!session) return <Navigate to="/login" replace />
  if (!roles.includes(session.role)) {
    return <Navigate to={session.role === 'teacher' ? '/teacher' : '/dashboard'} replace />
  }
  return <>{children}</>
}