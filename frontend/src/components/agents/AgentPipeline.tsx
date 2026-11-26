import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { AgentStatusEvent } from '../../api/sse'
import Icon, { type IconName } from '../ui/Icon'

const MODE_LABELS: Record<string, string> = {
  fast: '快速审核', standard: '标准审核', deliberate: '深度协商',
}
const STATE_LABELS: Record<string, string> = {
  running: '处理中', completed: '已完成', error: '已中止',
}

function stageIcon(stage: string): IconName {
  if (stage === 'profile') return 'profile'
  if (stage === 'route') return 'path'
  if (stage.startsWith('review')) return 'assessment'
  if (stage.startsWith('critique')) return 'activity'
  return 'assistant'
}

function SummaryPopover({ event, anchor, id, onClose }: {
  event: AgentStatusEvent
  anchor: HTMLButtonElement
  id: string
  onClose: (restoreFocus?: boolean) => void
}) {
  const cardRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const [position, setPosition] = useState({ left: 12, top: 12 })
  const state = event.state || 'completed'

  // Portal 避免浮层被聊天区域的滚动容器与 clip-path 裁掉。
  useLayoutEffect(() => {
    const card = cardRef.current
    if (!card) return
    const place = () => {
      const rect = anchor.getBoundingClientRect()
      const width = card.offsetWidth
      const height = card.offsetHeight
      const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))
      const below = rect.bottom + 10
      const top = below + height <= window.innerHeight - 12
        ? below : Math.max(12, Math.min(rect.top - height - 10, window.innerHeight - height - 12))
      setPosition({ left, top })
    }
    place()
    const observer = new ResizeObserver(place)
    observer.observe(card)
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [anchor])

  useEffect(() => {
    closeRef.current?.focus({ preventScroll: true })
    const dismiss = (e: PointerEvent) => {
      if (!cardRef.current?.contains(e.target as Node) && !anchor.contains(e.target as Node)) onClose()
    }
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose(true)
    }
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', dismiss)
      document.removeEventListener('keydown', escape)
    }
  }, [anchor, onClose])

  return createPortal(
    <div ref={cardRef} id={id} className={`agent-summary is-${state}`} role="dialog"
      aria-labelledby={`${id}-title`} style={position}>
      <div className="agent-summary__head">
        <span className="agent-summary__icon"><Icon name={stageIcon(event.stage)} size={19} /></span>
        <div><small>处理摘要</small><strong id={`${id}-title`}>{event.label}</strong></div>
        <button ref={closeRef} type="button" onClick={() => onClose(true)} aria-label="关闭处理摘要">×</button>
      </div>
      <div className="agent-summary__body" aria-live="polite" aria-atomic="true">
        <span className={`agent-summary__state is-${state}`}><i />{STATE_LABELS[state] || state}</span>
        <ul>{(event.summary?.length ? event.summary : [event.detail || '等待此阶段的处理结果。']).map((point, index) => (
          <li key={index}>{point}</li>
        ))}</ul>
        {event.handoff && <div className="agent-summary__handoff"><span>下一步</span><p>{event.handoff}</p></div>}
      </div>
      <div className="agent-summary__foot">
        <span>任务要点与处理结果</span>
        {event.elapsed_ms !== undefined && <span>{(event.elapsed_ms / 1000).toFixed(1)} 秒</span>}
      </div>
    </div>, document.body,
  )
}

export default function AgentPipeline({ events }: { events: AgentStatusEvent[] }) {
  const [selected, setSelected] = useState<{ stage: string; anchor: HTMLButtonElement } | null>(null)
  const id = useId()
  const selectedEvent = events.find((event) => event.stage === selected?.stage)
  const close = useCallback((restoreFocus = false) => {
    if (restoreFocus) selected?.anchor.focus({ preventScroll: true })
    setSelected(null)
  }, [selected])

  useEffect(() => {
    if (events.length === 0) setSelected(null)
  }, [events.length])

  if (events.length === 0) return null
  const mode = events.find((event) => event.mode)?.mode

  return (
    <div className="agent-pipe">
      <div className="agent-pipe__toolbar">
        <div className="agent-pipe__mode">
          <small>协商路径</small>
          {mode && <b className={`agent-pipe__badge mode-${mode}`}>{MODE_LABELS[mode] || mode}</b>}
          <span className="agent-pipe__hint">点击节点查看处理摘要</span>
        </div>
        <div className="agent-pipe__legend"><span><i />顺序传递</span><span className="is-feedback"><i />意见回传</span></div>
      </div>
      <div className="agent-pipe__viewport">
        <div className="agent-pipe__track" role="list" aria-label="多智能体协商链路">
          {events.map((event, index) => {
            const state = event.state || 'completed'
            const next = events[index + 1]
            const feedback = event.stage.startsWith('review_') && next?.stage.startsWith('revision_')
            const active = next?.state === 'running'
            const isSelected = selected?.stage === event.stage
            return (
              <div className={`agent-pipe__node is-${state} ${isSelected ? 'is-selected' : ''}`} key={event.stage} role="listitem">
                <button type="button" className="agent-pipe__trigger"
                  aria-label={`${event.label}，${STATE_LABELS[state] || state}，查看处理摘要`}
                  aria-expanded={isSelected} aria-controls={isSelected ? id : undefined} aria-haspopup="dialog"
                  onClick={(e) => setSelected(isSelected ? null : { stage: event.stage, anchor: e.currentTarget })}>
                  <span className="agent-pipe__dot">
                    <Icon name={stageIcon(event.stage)} size={18} />
                    {state === 'completed' && <span className="agent-pipe__check">✓</span>}
                    {state === 'error' && <span className="agent-pipe__check">!</span>}
                  </span>
                  <span className="agent-pipe__copy">
                    <span className="agent-pipe__step">{String(index + 1).padStart(2, '0')} / {STATE_LABELS[state] || state}</span>
                    <b>{event.label}</b>
                    {event.detail && <small>{event.detail}</small>}
                    <span className="agent-pipe__more">{isSelected ? '收起摘要' : '查看摘要'} <span aria-hidden="true">↗</span>
                      {event.elapsed_ms !== undefined && <span className="agent-pipe__ms">{(event.elapsed_ms / 1000).toFixed(1)}s</span>}
                    </span>
                  </span>
                </button>
                {next && (
                  <div className={`agent-pipe__link ${feedback ? 'is-feedback' : ''} ${active ? 'is-active' : ''} ${next.state === 'error' ? 'is-error' : ''}`}
                    role="img" aria-label={`${event.label} → ${next.label}：${feedback ? '审核意见回传给教学 Agent' : '顺序传递'}`}>
                    <svg viewBox="0 0 180 40" preserveAspectRatio="none" aria-hidden="true">
                      <path className="agent-pipe__wire" d={feedback ? 'M 0 30 C 35 2, 140 2, 172 30' : 'M 0 30 H 172'} />
                      {active && <path className="agent-pipe__flow" d={feedback ? 'M 0 30 C 35 2, 140 2, 172 30' : 'M 0 30 H 172'} />}
                      <path className="agent-pipe__arrow" d={feedback ? 'M 162 20 L 172 30 L 158 30' : 'M 164 25 L 172 30 L 164 35'} />
                    </svg>
                    <span>{feedback ? '↩ 回传修订' : next.stage.startsWith('review_') ? '交付核验' : next.stage.startsWith('critique_') ? '交付质疑' : '传递上下文'}</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
      {selected && selectedEvent && <SummaryPopover key={selected.stage} event={selectedEvent} anchor={selected.anchor} id={id} onClose={close} />}
    </div>
  )
}
