import { ReactNode, HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  hover?: boolean
}

export default function Card({ children, hover = true, className = '', style, ...props }: CardProps) {
  return (
    <div
      className={`rounded border border-border bg-bg-secondary transition-all duration-300 ${hover ? 'hover:-translate-y-0.5' : ''} ${className}`}
      style={{
        boxShadow: 'var(--shadow-card)',
        ...style,
      }}
      onMouseEnter={(e) => {
        if (hover) e.currentTarget.style.boxShadow = 'var(--shadow-card-hover)'
      }}
      onMouseLeave={(e) => {
        if (hover) e.currentTarget.style.boxShadow = 'var(--shadow-card)'
      }}
      {...props}
    >
      {children}
    </div>
  )
}
