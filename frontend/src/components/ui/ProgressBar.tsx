interface ProgressBarProps {
  value: number
  max?: number
  showLabel?: boolean
}

export default function ProgressBar({ value, max = 100, showLabel = true }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div className="w-full">
      <div className="w-full h-2 rounded-full overflow-hidden bg-bg-tertiary">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: 'var(--color-accent)' }}
        />
      </div>
      {showLabel && <span className="text-xs mt-1 block text-tertiary">{Math.round(pct)}%</span>}
    </div>
  )
}