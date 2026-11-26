import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLearningPathStore, type LearningNode } from '../stores/learningPathStore'
import { useNavigate } from 'react-router-dom'
import { getLearningPath, generateLearningPath, updateNodeStatus, type LearningPathGenerated } from '../api/learning-path'
import PathFlow from '../components/graph/PathFlow'

export default function LearningPathPage() {
  const { t } = useTranslation()
  const { nodes, pathTopic, setNodes, setPathTopic } = useLearningPathStore()
  const [topic, setTopic] = useState('Python 编程')
  const [generating, setGenerating] = useState(false)
  const [statusText, setStatusText] = useState('')
  const [error, setError] = useState('')
  const [initialLoaded, setInitialLoaded] = useState(false)
  const abortRef = useRef<(() => void) | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    getLearningPath().then((data) => {
      if (data.nodes && data.nodes.length > 0) setNodes(data.nodes as LearningNode[])
      if (data.topic) setPathTopic(data.topic)
      setInitialLoaded(true)
    }).catch(() => setInitialLoaded(true))

    return () => abortRef.current?.()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleGenerate = async () => {
    if (!topic.trim() || generating) return
    setGenerating(true)
    setError('')
    setStatusText(t('learningPath.generating'))
    abortRef.current?.()

    abortRef.current = await generateLearningPath(
      topic.trim(),
      (content) => setStatusText(content),
      (path: LearningPathGenerated) => {
        setNodes(path.nodes as LearningNode[])
        setPathTopic(path.topic || topic.trim())
        setGenerating(false)
        setStatusText('')
        setInitialLoaded(true)
      },
      () => {
        setGenerating(false)
        setStatusText('')
      },
      (err) => {
        setError(err)
        setGenerating(false)
        setStatusText('')
      }
    )
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleGenerate()
  }

  const handleToggleComplete = async (node: LearningNode) => {
    const nextStatus = node.status === 'completed' ? 'pending' : 'completed'
    try {
      await updateNodeStatus(pathTopic || topic, node.id, nextStatus)
      setNodes(nodes.map((item) => item.id === node.id ? { ...item, status: nextStatus } : item))
    } catch (err) {
      setError((err as Error).message || '更新节点状态失败')
    }
  }

  // 列表与流程图共用同一个跳转逻辑，避免两处各写一份 URL 拼装后漂移。
  const openNode = (node: LearningNode) => {
    navigate(`/generate?topic=${encodeURIComponent(node.knowledge_point || node.title)}&node_id=${node.id}&path_topic=${encodeURIComponent(pathTopic || topic)}&resource_type=${encodeURIComponent(node.resource_type || node.type)}&resource_ref=${encodeURIComponent(node.resource_ref || '')}`)
  }

  const completed = nodes.filter((n) => n.status === 'completed').length
  const inProgress = nodes.filter((n) => n.status === 'in_progress').length
  const total = nodes.length
  const progress = total > 0 ? (completed / total) * 100 : 0

  return (
    <div className="core-page">
      <header className="core-page-head">
        <div>
          <span className="core-kicker">PATH ENGINE / KNOWLEDGE GRAPH</span>
          <h1>{t('learningPath.title')}</h1>
          <p>根据前置知识解锁、掌握度和遗忘风险动态重排学习顺序。</p>
        </div>
        <div className="core-page-meta">
          <span>{pathTopic || topic}</span>
          <span>{total} 个节点</span>
        </div>
      </header>

      <section className="core-panel">
        <div className="core-panel-head">
          <div><h2>路径生成器</h2><p>输入目标主题后，系统将调用规划与知识检索流程</p></div>
          <span className="core-tag">STRATEGY LAYER</span>
        </div>
        <div className="core-panel-body">
          <div className="core-form">
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={generating}
              className="core-input"
              placeholder={t('learningPath.generateTopic')}
            />
            <button className="core-button" onClick={handleGenerate} disabled={generating}>
              {generating ? t('learningPath.generating') : t('learningPath.generate')}
            </button>
          </div>
          {statusText && <p className="mt-3 text-xs text-accent">{statusText}</p>}
          {error && <p className="mt-3 text-xs text-error">{error}</p>}
        </div>
      </section>

      {total > 0 && (
        <>
          <section className="core-stat-grid">
            <div className="core-stat"><span>路径完成度</span><strong>{progress.toFixed(0)}%</strong><small>{completed} / {total} 个节点已完成</small></div>
            <div className="core-stat"><span>当前学习节点</span><strong>{inProgress}</strong><small>按动态优先级实时调整</small></div>
            <div className="core-stat"><span>图谱依赖</span><strong>{nodes.reduce((sum, n) => sum + (n.deps?.length || 0), 0)}</strong><small>前置依赖边数量</small></div>
          </section>

          <section className="core-panel">
            <div className="core-panel-head">
              <div><h2>路径依赖流程</h2><p>按前置依赖分层，自上而下就是真实的解锁顺序；点节点可跳转生成资源</p></div>
              <span className="core-tag">DEPENDENCY DAG</span>
            </div>
            <PathFlow nodes={nodes} onSelect={openNode} />
          </section>

          <div className="core-grid-main">
            <section className="core-panel">
              <div className="core-panel-head">
                <div><h2>路径节点</h2><p>点击节点可生成或加载对应学习资源</p></div>
                <span className="core-tag">TOPOLOGICAL ORDER</span>
              </div>
              <div className="core-panel-body core-list">
                {nodes.map((node, index) => {
                  const locked = node.status !== 'completed' && (node.deps || []).some((dep) => nodes.find((item) => item.id === dep)?.status !== 'completed')
                  return (
                    <NodeItem
                      key={node.id}
                      node={node}
                      index={index}
                      locked={locked}
                      onClick={() => openNode(node)}
                      onToggleComplete={() => handleToggleComplete(node)}
                    />
                  )
                })}
              </div>
            </section>

            <aside className="core-panel">
              <div className="core-panel-head">
                <div><h2>规划依据</h2><p>Explainable Adaptive Policy</p></div>
              </div>
              <div className="core-panel-body">
                <div className="space-y-4 text-xs text-secondary">
                  <div><div className="text-accent mb-1">01 前置知识</div><p>只有完成必要条件后，后续节点才会解锁。</p></div>
                  <div><div className="text-accent mb-1">02 掌握度缺口</div><p>掌握度越低，节点优先级越高。</p></div>
                  <div><div className="text-accent mb-1">03 遗忘风险</div><p>长时间未复习的内容会被重新加入路径。</p></div>
                  <div><div className="text-accent mb-1">04 策略收益</div><p>系统根据历史测评增益选择讲解、练习或复习动作。</p></div>
                </div>
              </div>
            </aside>
          </div>
        </>
      )}

      {total === 0 && initialLoaded && (
        <section className="core-panel core-empty">暂无学习路径，请先生成一个主题路径。</section>
      )}
    </div>
  )
}

function NodeItem({ node, index, locked, onClick, onToggleComplete }: {
  node: LearningNode
  index: number
  locked: boolean
  onClick: () => void
  onToggleComplete: () => void
}) {
  const isCompleted = node.status === 'completed'
  const isInProgress = node.status === 'in_progress'
  const statusLabel = locked ? '未解锁' : isCompleted ? '已完成' : isInProgress ? '进行中' : '待开始'
  const statusColor = locked ? 'var(--color-text-tertiary)' : isCompleted ? 'var(--color-success)' : isInProgress ? 'var(--color-accent)' : 'var(--color-text-secondary)'

  return (
    <div
      role="button"
      tabIndex={locked ? -1 : 0}
      aria-disabled={locked}
      onClick={() => { if (!locked) onClick() }}
      onKeyDown={(event) => { if (!locked && (event.key === 'Enter' || event.key === ' ')) onClick() }}
      className={`core-list-row w-full text-left transition-colors ${locked ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-[var(--color-accent)]'}`}
    >
      <div className="flex items-start gap-3">
        <span className="text-[10px] font-mono text-tertiary pt-0.5">{String(index + 1).padStart(2, '0')}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-3">
            <h3>{node.title}</h3>
            <span className="core-tag" style={{ color: statusColor, borderColor: statusColor }}>{statusLabel}</span>
          </div>
          <p>{node.knowledge_point || node.title} · {node.duration || '待评估'} · {node.type || 'resource'}</p>
        </div>
        {!locked && (
          <button
            type="button"
            onClick={(event) => { event.stopPropagation(); onToggleComplete() }}
            className="text-xs px-2 py-1 rounded border border-border text-secondary hover:text-accent"
          >
            {isCompleted ? '重新学习' : '标记完成'}
          </button>
        )}
      </div>
    </div>
  )
}
