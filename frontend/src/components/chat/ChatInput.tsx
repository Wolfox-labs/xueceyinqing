import { useState, useRef, KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const { t } = useTranslation()
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
    textareaRef.current?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex items-end gap-3 p-4 border-t border-border bg-bg-secondary">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={t('chat.placeholder')}
        rows={1}
        className="flex-1 resize-none rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 border border-border bg-bg-tertiary text-primary"
        style={{
          maxHeight: '120px',
        }}
        disabled={disabled}
        aria-label={t('chat.placeholder')}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        className="px-5 py-3 rounded-xl text-white font-medium text-sm transition-all duration-200 disabled:opacity-50 bg-accent"
        aria-label={t('chat.send')}
      >
        {t('chat.send')}
      </button>
    </div>
  )
}