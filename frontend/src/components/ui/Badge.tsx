import { ReactNode } from 'react'

interface BadgeProps {
  variant?: 'success' | 'warning' | 'error' | 'info'
  children: ReactNode
}

const colors = {
  success: { bg: '#dcfce7', color: '#166534' },
  warning: { bg: '#fef3c7', color: '#92400e' },
  error: { bg: '#fee2e2', color: '#991b1b' },
  info: { bg: '#dbeafe', color: '#1e40af' },
}

export default function Badge({ variant = 'info', children }: BadgeProps) {
  const c = colors[variant]
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium" style={{ backgroundColor: c.bg, color: c.color }}>
      {children}
    </span>
  )
}