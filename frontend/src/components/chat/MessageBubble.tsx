import { useTranslation } from 'react-i18next'
import MarkdownRenderer from '../markdown/MarkdownRenderer'

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
}

const WITHDRAWN_PREFIX = '内容已被审核撤回'

function isWithdrawnContent(content: string): boolean {
  return content.includes(WITHDRAWN_PREFIX)
}

function extractWithdrawnReason(content: string): string {
  const idx = content.indexOf('：')
  if (idx === -1) return ''
  return content.slice(idx + 1)
}

export default function MessageBubble({ role, content, isStreaming }: MessageBubbleProps) {
  const { t } = useTranslation()
  const isUser = role === 'user'
  const withdrawn = !isUser && isWithdrawnContent(content)
  const reason = withdrawn ? extractWithdrawnReason(content) : ''

  return (
    <div className={`flex gap-3 mb-4 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className="w-8 h-8 flex items-center justify-center text-[9px] font-bold flex-shrink-0"
        style={{
          backgroundColor: isUser ? 'var(--color-accent)' : withdrawn ? '#f59e0b' : 'var(--color-success)',
          color: '#fff',
        }}
      >
        {isUser ? '我' : withdrawn ? '!' : '答'}
      </div>

      <div className={`max-w-[80%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div className="text-xs mb-1 text-tertiary">
          {isUser ? '我' : withdrawn ? t('chat.withdrawn') : t('chat.aiName')}
        </div>
        {withdrawn ? (
          <div
            className="rounded-2xl px-4 py-3 text-sm leading-relaxed border-2 flex items-start gap-2 bg-bg-tertiary"
            style={{
              borderColor: '#f59e0b',
              color: '#b45309',
            }}
          >
            <span>
              {reason || content}
            </span>
          </div>
        ) : (
          <div
            className="rounded-2xl px-4 py-3 text-sm leading-relaxed"
            style={{
              backgroundColor: isUser ? 'var(--color-accent)' : 'var(--color-bg-tertiary)',
              color: isUser ? '#fff' : 'var(--color-text-primary)',
              ...(isStreaming ? {
                animation: 'pulse-border 2s infinite',
                border: '2px solid var(--color-accent)',
              } : {}),
            }}
          >
            {isUser
              ? (content || (isStreaming && <TypingIndicator />))
              : <MarkdownRenderer content={content} />}
          </div>
        )}
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex gap-1 items-center py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-2 h-2 rounded-full animate-bounce"
          style={{
            backgroundColor: 'var(--color-text-tertiary)',
            animationDelay: `${i * 0.15}s`,
            animationDuration: '0.6s',
          }}
        />
      ))}
    </div>
  )
}
