interface ShortcutHelpProps {
  open: boolean
  onClose: () => void
}

const shortcuts = [
  { keys: 'Ctrl + Enter', desc: '发送消息' },
  { keys: 'Ctrl + K', desc: '打开命令面板' },
  { keys: 'Ctrl + /', desc: '显示快捷键帮助' },
  { keys: 'Esc', desc: '关闭弹窗 / 命令面板' },
]

export default function ShortcutHelp({ open, onClose }: ShortcutHelpProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <div
        className="relative w-full max-w-sm rounded-xl shadow-2xl border border-border bg-bg-secondary overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-primary">快捷键</h2>
          <button onClick={onClose} className="text-lg hover:opacity-70 text-tertiary" aria-label="关闭">✕</button>
        </div>
        <div className="p-4 space-y-2">
          {shortcuts.map((s, i) => (
            <div key={i} className="flex items-center justify-between py-2">
              <span className="text-sm text-secondary">{s.desc}</span>
              <kbd
                className="px-2 py-1 rounded text-xs font-mono bg-bg-tertiary text-primary border border-border"
              >
                {s.keys}
              </kbd>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}