import { useTranslation } from 'react-i18next'
import type { Session } from '../../stores/chatStore'

interface SessionListProps {
  sessions: Session[]
  currentId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}

export default function SessionList({ sessions, currentId, onSelect, onNew }: SessionListProps) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="p-3 border-b border-border">
        <button
          onClick={onNew}
          className="w-full py-2 rounded-lg text-sm font-medium transition-colors"
          style={{ backgroundColor: 'var(--color-accent)', color: '#fff' }}
        >
          + {t('chat.newSession')}
        </button>
      </div>
      <div className="flex-1 overflow-auto p-2">
        {sessions.length === 0 ? (
          <p className="text-center text-sm py-8 text-tertiary">{t('chat.noSessions')}</p>
        ) : (
          sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => onSelect(s.id)}
              className="w-full text-left px-3 py-3 rounded-lg mb-1 transition-all duration-200 text-primary"
              style={{
                backgroundColor: currentId === s.id ? 'var(--color-bg-tertiary)' : 'transparent',
              }}
            >
              <div className="text-sm font-medium truncate">{s.title}</div>
              <div className="text-xs mt-0.5 text-tertiary">{s.updated_at}</div>
            </button>
          ))
        )}
      </div>
    </div>
  )
}
