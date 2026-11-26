import { useMemo, useState } from 'react'
import type { KnowledgeGraphNode } from '../../api/adaptive'

/**
 * 真实知识依赖图谱（力导向布局）。
 *
 * 替换掉原先写死在 DashboardPage 里的假图：那张图有 5 个假节点
 * （变量/函数/列表/面向对象/算法）、写死的坐标和状态，和用户真实数据毫无关系。
 * 现在节点、依赖边、重要度、掌握度**全部**来自 /api/adaptive/dashboard
 * 返回的 knowledge_graph，没有证据的节点 mastery 为 null，界面如实显示"无证据"。
 *
 * 布局用带索引种子的确定性力模拟（不是随机数），因此同一份数据每次渲染
 * 得到同一张图——演示与截图可复现，不会每次刷新都变形。
 */
const WIDTH = 470
const HEIGHT = 300
const PAD = 40

type Positioned = KnowledgeGraphNode & { x: number; y: number }

type Tone = 'done' | 'active' | 'risk' | 'unknown'

function toneOf(mastery: number | null): Tone {
  if (mastery === null) return 'unknown'
  if (mastery < 0.4) return 'risk'
  if (mastery < 0.7) return 'active'
  return 'done'
}

const TONE_LABEL: Record<Tone, string> = {
  done: '已掌握',
  active: '学习中',
  risk: '待加强',
  unknown: '无证据',
}

/**
 * 节点标签截断。
 *
 * 图谱节点名不一定是"变量与类型"这种短词：学习路径推导出来的知识点可能是
 * "变量、int/float/str/bool/None" 这类长串，直接画会互相压住、糊成一片。
 * 这里截断显示、完整名放进 <title> 供悬停查看。
 */
function shorten(name: string, max = 8): string {
  return name.length > max ? `${name.slice(0, max)}…` : name
}

function layout(nodes: KnowledgeGraphNode[]): { points: Positioned[]; width: number; height: number } {
  const count = nodes.length
  if (count === 0) return { points: [], width: WIDTH, height: HEIGHT }
  // 节点多时（例如学习路径又推导出一批知识点）加高画布，否则会挤成一团。
  const canvasH = count > 12 ? 392 : HEIGHT
  const cx = WIDTH / 2
  const cy = canvasH / 2
  const points: Positioned[] = nodes.map((node, index) => {
    // 初始位置按索引落在圆周上：确定性，避免每次渲染位置乱跳。
    const angle = (index / count) * Math.PI * 2
    const radius = Math.min(WIDTH, canvasH) * 0.3
    return { ...node, x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius }
  })

  const indexByName = new Map(points.map((point, index) => [point.name, index]))
  const edges: [number, number][] = []
  points.forEach((node, target) => {
    node.prerequisites.forEach((name) => {
      const source = indexByName.get(name)
      if (source !== undefined && source !== target) edges.push([source, target])
    })
  })

  const iterations = 320
  for (let step = 0; step < iterations; step += 1) {
    const cooling = 1 - step / iterations
    const fx = new Array<number>(count).fill(0)
    const fy = new Array<number>(count).fill(0)

    for (let i = 0; i < count; i += 1) {
      for (let j = i + 1; j < count; j += 1) {
        let dx = points[i].x - points[j].x
        let dy = points[i].y - points[j].y
        let distSq = dx * dx + dy * dy
        if (distSq < 1) {
          // 完全重合时给一个确定性的微小偏移，避免除零后炸开。
          dx = (i - j) * 0.5 + 0.5
          dy = 0.5
          distSq = 1
        }
        const dist = Math.sqrt(distSq)
        // 斥力偏强、弹簧偏长：否则 9 个节点会挤在中间，标签互相压住圆点。
        const force = 7000 / distSq
        fx[i] += (dx / dist) * force
        fy[i] += (dy / dist) * force
        fx[j] -= (dx / dist) * force
        fy[j] -= (dy / dist) * force
      }
    }

    for (const [source, target] of edges) {
      const dx = points[target].x - points[source].x
      const dy = points[target].y - points[source].y
      const dist = Math.max(1, Math.hypot(dx, dy))
      const force = (dist - 118) * 0.05
      fx[source] += (dx / dist) * force
      fy[source] += (dy / dist) * force
      fx[target] -= (dx / dist) * force
      fy[target] -= (dy / dist) * force
    }

    for (let i = 0; i < count; i += 1) {
      fx[i] += (cx - points[i].x) * 0.013
      fy[i] += (cy - points[i].y) * 0.013
      const clamp = (value: number) => Math.max(-8, Math.min(8, value))
      points[i].x += clamp(fx[i]) * cooling
      points[i].y += clamp(fy[i]) * cooling
    }
  }

  // 归一化进画布：保留边距，并做一次等比缩放使布局铺满可用区域。
  const xs = points.map((point) => point.x)
  const ys = points.map((point) => point.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const spanX = Math.max(1, maxX - minX)
  const spanY = Math.max(1, maxY - minY)
  const usableW = WIDTH - PAD * 2
  const usableH = canvasH - PAD * 2
  const scale = Math.min(usableW / spanX, usableH / spanY, 1.9)

  return {
    points: points.map((point) => ({
      ...point,
      x: PAD + (point.x - minX) * scale + (usableW - spanX * scale) / 2,
      y: PAD + (point.y - minY) * scale + (usableH - spanY * scale) / 2,
    })),
    width: WIDTH,
    height: canvasH,
  }
}

export default function KnowledgeGraph({
  nodes,
  onSelect,
}: {
  nodes: KnowledgeGraphNode[]
  /** 点击/回车选中某知识点（用于跳转生成资源）。不传则节点不可交互。 */
  onSelect?: (name: string) => void
}) {
  const [focus, setFocus] = useState<string | null>(null)
  const { points: positioned, width, height } = useMemo(() => layout(nodes), [nodes])
  const byName = useMemo(
    () => new Map(positioned.map((node) => [node.name, node])),
    [positioned],
  )
  const edges = useMemo(
    () =>
      positioned.flatMap((node) =>
        node.prerequisites
          .map((name) => byName.get(name))
          .filter((source): source is Positioned => source !== undefined && source.name !== node.name)
          .map((source) => ({ source, target: node })),
      ),
    [positioned, byName],
  )

  if (nodes.length === 0) {
    return (
      <div className="kg-empty">
        <strong>暂无知识图谱</strong>
        <p>完成一次诊断测评或生成一次学习资源后，这里会显示真实的依赖关系与掌握度。</p>
      </div>
    )
  }

  const focused = focus ? byName.get(focus) : undefined

  const isDense = positioned.length > 12

  return (
    <div className="kg-wrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className={`kg-canvas${isDense ? ' kg-canvas--dense' : ''}`}
        role="img"
        aria-label={`知识依赖图谱，共 ${positioned.length} 个知识点`}
      >
        <defs>
          <marker id="kg-arrow" viewBox="0 0 6 6" refX="5.2" refY="3" markerWidth="5" markerHeight="5" orient="auto">
            <path d="M0,0 L6,3 L0,6 z" className="kg-arrow" />
          </marker>
          <marker id="kg-arrow-hot" viewBox="0 0 6 6" refX="5.2" refY="3" markerWidth="5" markerHeight="5" orient="auto">
            <path d="M0,0 L6,3 L0,6 z" className="kg-arrow-hot" />
          </marker>
        </defs>

        {edges.map(({ source, target }) => {
          const hot = focus === source.name || focus === target.name
          // 终点收到节点边缘，避免箭头被圆遮住。
          const dx = target.x - source.x
          const dy = target.y - source.y
          const dist = Math.max(1, Math.hypot(dx, dy))
          const targetRadius = 9 + target.importance * 7
          const endX = target.x - (dx / dist) * (targetRadius + 3)
          const endY = target.y - (dy / dist) * (targetRadius + 3)
          return (
            <line
              key={`${source.name}->${target.name}`}
              className={`kg-edge${hot ? ' is-hot' : ''}`}
              x1={source.x}
              y1={source.y}
              x2={endX}
              y2={endY}
              markerEnd={hot ? 'url(#kg-arrow-hot)' : 'url(#kg-arrow)'}
            />
          )
        })}

        {positioned.map((node) => {
          const tone = toneOf(node.mastery)
          const radius = 9 + node.importance * 7
          const dimmed = focus !== null && focus !== node.name &&
            !edges.some(({ source, target }) =>
              (source.name === focus && target.name === node.name) ||
              (target.name === focus && source.name === node.name))
          return (
            <g
              key={node.name}
              className={`kg-node tone-${tone}${focus === node.name ? ' is-focus' : ''}${dimmed ? ' is-dim' : ''}`}
              role={onSelect ? 'button' : undefined}
              tabIndex={onSelect ? 0 : -1}
              aria-label={`${node.name}，${TONE_LABEL[tone]}${
                node.mastery === null ? '' : `，掌握度 ${Math.round(node.mastery * 100)}%`
              }`}
              onMouseEnter={() => setFocus(node.name)}
              onMouseLeave={() => setFocus(null)}
              onFocus={() => setFocus(node.name)}
              onBlur={() => setFocus(null)}
              onClick={() => onSelect?.(node.name)}
              onKeyDown={(event) => {
                // 键盘可达：与鼠标点击等价的 Enter / 空格
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onSelect?.(node.name)
                }
              }}
            >
              <circle cx={node.x} cy={node.y} r={radius} />
              {/* 完整知识点名放进 title：标签截断显示，但悬停能看到全名 */}
              <title>{node.name}</title>
              <text x={node.x} y={node.y + radius + 13}>{shorten(node.name)}</text>
            </g>
          )
        })}
      </svg>

      <div className="kg-side">
        <div className="kg-legend">
          {(['done', 'active', 'risk', 'unknown'] as Tone[]).map((tone) => (
            <span key={tone}><i className={`kg-dot tone-${tone}`} />{TONE_LABEL[tone]}</span>
          ))}
        </div>
        <div className="kg-detail">
          {focused ? (
            <>
              <strong>{focused.name}</strong>
              <dl>
                <dt>有效掌握度</dt>
                <dd>{focused.mastery === null ? '无证据' : `${Math.round(focused.mastery * 100)}%`}</dd>
                <dt>重要度</dt>
                <dd>{focused.importance.toFixed(2)}</dd>
                <dt>前置</dt>
                <dd>{focused.prerequisites.length ? focused.prerequisites.join('、') : '无（起始节点）'}</dd>
              </dl>
            </>
          ) : (
            <p className="kg-hint">
              共 {positioned.length} 个知识点、{edges.length} 条依赖边。
              {onSelect
                ? '悬停查看前置知识与掌握度；点击（或按回车）可针对该知识点生成学习资源。'
                : '悬停节点查看它的前置知识与真实掌握度。'}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}