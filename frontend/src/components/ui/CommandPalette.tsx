import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
}

const commands = [
  { id: 'chat', label: '学习助手', icon: '💬', path: '/chat' },
  { id: 'path', label: '学习路径', icon: '🗺️', path: '/learning-path' },
  { id: 'profile', label: '个人中心', icon: '👤', path: '/profile' },
  { id: 'theme', label: '切换主题', icon: '🎨', action: 'toggleTheme' },
]

export default function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate()
  const [filter, setFilter] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)

  const filtered = commands.filter((c) =>
    c.label.toLowerCase().includes(filter.toLowerCase())
  )

  useEffect(() => {
    if (open) {
      setFilter('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!open) return
      if (e.key === 'Escape') { onClose(); return }
      if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1)) }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIndex((i) => Math.max(i - 1, 0)) }
      if (e.key === 'Enter' && filtered[selectedIndex]) {
        e.preventDefault()
        const cmd = filtered[selectedIndex]
        if ('path' in cmd && cmd.path) navigate(cmd.path)
        if ('action' in cmd && cmd.action === 'toggleTheme') {
          const btn = document.querySelector('[aria-label="切换主题"]') as HTMLButtonElement
          btn?.click()
        }
        onClose()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, filtered, selectedIndex, navigate, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <div
        className="relative w-full max-w-md rounded-xl shadow-2xl border border-border bg-bg-secondary overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          value={filter}
          onChange={(e) => { setFilter(e.target.value); setSelectedIndex(0) }}
          placeholder="输入命令搜索..."
          className="w-full px-4 py-3 text-sm border-b border-border bg-bg-secondary text-primary focus:outline-none"
          aria-label="搜索命令"
        />
        <div className="max-h-64 overflow-auto p-2">
          {filtered.length === 0 ? (
            <p className="text-center py-4 text-sm text-tertiary">无匹配命令</p>
          ) : (
            filtered.map((cmd, i) => (
              <button
                key={cmd.id}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-sm transition-colors text-primary"
                style={{
                  backgroundColor: i === selectedIndex ? 'var(--color-bg-tertiary)' : 'transparent',
                }}
                onClick={() => {
                  if ('path' in cmd && cmd.path) navigate(cmd.path)
                  if ('action' in cmd && cmd.action === 'toggleTheme') {
                    const btn = document.querySelector('[aria-label="切换主题"]') as HTMLButtonElement
                    btn?.click()
                  }
                  onClose()
                }}
              >
                <span className="text-lg">{cmd.icon}</span>
                <span>{cmd.label}</span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  )
}