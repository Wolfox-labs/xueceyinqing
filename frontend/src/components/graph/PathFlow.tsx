import { useMemo } from 'react'
import type { LearningNode } from '../../stores/learningPathStore'

/**
 * 学习路径依赖流程图（分层 DAG，自上而下）。
 *
 * 两个设计决定都来自真实数据，不是拍脑袋：
 *  1) 用分层而不是力导向——学习路径的核心信息是**先后顺序**，力导向会把顺序摊平；
 *  2) 用**自上而下**而不是左右——真实路径（Python 编程，9 节点）层级深达 8 层、
 *     每层最多 2 个节点；左右排会宽到 1400px 需要横向滚动，上下排恰好铺满一屏，
 *     也更像"路线图"。
 *
 * 层级与边全部来自真实 nodes[].deps，无依赖时自然只有一层。
 */

const NODE_W = 150
const NODE_H = 50
const LEVEL_GAP = 36
const SIBLING_GAP = 26
const PAD = 10

interface Positioned extends LearningNode {
  x: number
  y: number
  level: number
  locked: boolean
}

/** 拓扑层级：无前置为 0，否则为所有前置层级最大值 +1。带环保护。 */
function computeLevels(nodes: LearningNode[]): Map<string, number> {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const levels = new Map<string, number>()

  const resolve = (id: string, seen: Set<string>): number => {
    const cached = levels.get(id)
    if (cached !== undefined) return cached
    if (seen.has(id)) return 0 // 数据成环时按最底层处理，避免无限递归
    seen.add(id)
    const deps = (byId.get(id)?.deps ?? []).filter((dep) => byId.has(dep))
    const value = deps.length === 0 ? 0 : 1 + Math.max(...deps.map((dep) => resolve(dep, seen)))
    levels.set(id, value)
    return value
  }

  nodes.forEach((node) => resolve(node.id, new Set()))
  return levels
}

function wrapTitle(text: string, perLine = 12, maxLines = 2): string[] {
  const lines: string[] = []
  for (let index = 0; index < text.length && lines.length < maxLines; index += perLine) {
    lines.push(text.slice(index, index + perLine))
  }
  if (lines.length === maxLines && text.length > perLine * maxLines) {
    lines[maxLines - 1] = `${lines[maxLines - 1].slice(0, perLine - 1)}…`
  }
  return lines.length ? lines : [text]
}

export default function PathFlow({
  nodes,
  onSelect,
}: {
  nodes: LearningNode[]
  onSelect: (node: LearningNode) => void
}) {
  const { positioned, width, height, edges } = useMemo(() => {
    const levels = computeLevels(nodes)
    const byId = new Map(nodes.map((node) => [node.id, node]))
    const isLocked = (node: LearningNode) =>
      node.status !== 'completed' &&
      (node.deps ?? []).some((dep) => byId.get(dep)?.status !== 'completed')

    const rows = new Map<number, LearningNode[]>()
    nodes.forEach((node) => {
      const level = levels.get(node.id) ?? 0
      const bucket = rows.get(level) ?? []
      bucket.push(node)
      rows.set(level, bucket)
    })

    const maxLevel = Math.max(0, ...Array.from(rows.keys()))
    const widestRow = Math.max(1, ...Array.from(rows.values()).map((list) => list.length))
    const canvasW = PAD * 2 + widestRow * NODE_W + (widestRow - 1) * SIBLING_GAP
    const canvasH = PAD * 2 + (maxLevel + 1) * NODE_H + maxLevel * LEVEL_GAP

    const placed: Positioned[] = []
    Array.from(rows.keys())
      .sort((a, b) => a - b)
      .forEach((level) => {
        const list = rows.get(level) ?? []
        const rowW = list.length * NODE_W + (list.length - 1) * SIBLING_GAP
        // 每行水平居中：否则窄行会一律贴左，看着像没画完。
        const offsetX = PAD + (canvasW - PAD * 2 - rowW) / 2
        list.forEach((node, columnIndex) => {
          placed.push({
            ...node,
            level,
            locked: isLocked(node),
            x: offsetX + columnIndex * (NODE_W + SIBLING_GAP),
            y: PAD + level * (NODE_H + LEVEL_GAP),
          })
        })
      })

    const byIdPlaced = new Map(placed.map((node) => [node.id, node]))
    const links = placed.flatMap((node) =>
      (node.deps ?? [])
        .map((dep) => byIdPlaced.get(dep))
        .filter((source): source is Positioned => source !== undefined && source.id !== node.id)
        .map((source) => ({ source, target: node })),
    )

    return { positioned: placed, width: canvasW, height: canvasH, edges: links }
  }, [nodes])

  if (nodes.length === 0) return null

  const statusLabel = (node: Positioned) =>
    node.locked ? '未解锁' : node.status === 'completed' ? '已完成'
      : node.status === 'in_progress' ? '进行中' : '待开始'

  const toneOf = (node: Positioned) =>
    node.locked ? 'locked' : node.status === 'completed' ? 'done'
      : node.status === 'in_progress' ? 'active' : 'pending'

  return (
    <div className="pf-wrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={Math.round(width)}
        height={Math.round(height)}
        className="pf-canvas"
        role="img"
        aria-label={`学习路径依赖流程，共 ${nodes.length} 个节点、${edges.length} 条依赖`}
      >
        <defs>
          <marker id="pf-arrow" viewBox="0 0 6 6" refX="3" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto">
            <path d="M0,0 L6,0 L3,6 z" className="pf-arrow" />
          </marker>
        </defs>

        {edges.map(({ source, target }) => {
          const x1 = source.x + NODE_W / 2
          const y1 = source.y + NODE_H
          const x2 = target.x + NODE_W / 2
          const y2 = target.y
          const mid = (y1 + y2) / 2
          return (
            <path
              key={`${source.id}->${target.id}`}
              className={`pf-edge${target.locked ? ' is-locked' : ''}`}
              d={`M${x1},${y1} C${x1},${mid} ${x2},${mid} ${x2},${y2}`}
              markerEnd="url(#pf-arrow)"
            />
          )
        })}

        {positioned.map((node) => {
          const tone = toneOf(node)
          const lines = wrapTitle(node.title)
          const titleY = node.y + (lines.length > 1 ? 19 : 24)
          return (
            <g
              key={node.id}
              className={`pf-node tone-${tone}${node.locked ? ' is-locked' : ''}`}
              role={node.locked ? undefined : 'button'}
              tabIndex={node.locked ? -1 : 0}
              aria-label={`${node.title}，${statusLabel(node)}`}
              onClick={() => { if (!node.locked) onSelect(node) }}
              onKeyDown={(event) => {
                // 未解锁的节点与鼠标行为一致：不可激活，也不抢 Tab 焦点
                if (node.locked) return
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onSelect(node)
                }
              }}
            >
              <title>{`${node.title}（${statusLabel(node)}）`}</title>
              <rect x={node.x} y={node.y} width={NODE_W} height={NODE_H} rx="4" />
              {lines.map((line, lineIndex) => (
                <text
                  key={line}
                  className="pf-node__title"
                  x={node.x + 11}
                  y={titleY + lineIndex * 13}
                >
                  {line}
                </text>
              ))}
              <text className="pf-node__meta" x={node.x + 11} y={node.y + NODE_H - 8}>
                {statusLabel(node)}
                {node.duration ? ` · ${node.duration}` : ''}
              </text>
            </g>
          )
        })}
      </svg>

      <div className="pf-legend">
        <span><i className="pf-dot tone-done" />已完成</span>
        <span><i className="pf-dot tone-active" />进行中</span>
        <span><i className="pf-dot tone-pending" />待开始</span>
        <span><i className="pf-dot tone-locked" />未解锁（前置未完成）</span>
      </div>
    </div>
  )
}