import { ReactNode, useState } from 'react'

interface CardBaseProps {
  children: ReactNode
  source?: string
  resourceId?: string
}

export default function CardBase({ children, source, resourceId: _resourceId }: CardBaseProps) {
  const [bookmarked, setBookmarked] = useState(false)

  return (
    <div
      className="rounded-xl border border-border bg-bg-secondary transition-all duration-300 hover:-translate-y-0.5"
      style={{
        boxShadow: 'var(--shadow-card)',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.boxShadow = 'var(--shadow-card-hover)' }}
      onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'var(--shadow-card)' }}
    >
      <div className="p-4">{children}</div>
      {/* Bottom action bar */}
      <div className="flex items-center justify-between px-4 py-2.5 border-t text-xs border-border text-tertiary">
        <span>{source || '系统生成'}</span>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setBookmarked(!bookmarked)}
            className="transition-colors hover:opacity-70"
            style={{ color: bookmarked ? '#f59e0b' : 'var(--color-text-tertiary)' }}
            aria-label={bookmarked ? '取消收藏' : '收藏'}
          >
            {bookmarked ? '★' : '☆'}
          </button>
          <button className="hover:opacity-70" aria-label="下载">⬇</button>
          <button className="hover:opacity-70" aria-label="反馈">💬</button>
        </div>
      </div>
    </div>
  )
}