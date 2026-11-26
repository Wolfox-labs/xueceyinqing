import { useTranslation } from 'react-i18next'
import { useGenerateStore } from '../stores/generateStore'
import { connectGenerateStream, getPptThemes, type PptThemeOption } from '../api/generate'
import MarkdownRenderer from '../components/markdown/MarkdownRenderer'
import MindmapViewer from '../components/chat/MindmapViewer'
import { useRef, useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { saveQuestions, updateNodeResource, getQuestionsByTopic } from '../api/question-bank'
import { updateNodeStatus } from '../api/learning-path'
import { createFileTicket } from '../api/files'
import MaterialsPanel from '../components/materials/MaterialsPanel'
import type { MaterialSource } from '../api/materials'
import { submitResourceFeedback, type ResourceRating } from '../api/feedback'
import AgentPipeline from '../components/agents/AgentPipeline'
import type { AgentStatusEvent } from '../api/sse'

const RESOURCE_TYPES = ['document', 'mindmap', 'exercise', 'ppt'] as const

const THEME_DOT_COLORS: Record<string, string> = {
  dark_tech: '#38BDF8',
  academic_clean: '#1E3A8A',
  education_fresh: '#2E7D32',
  business_blue: '#0F4C81',
}

const FALLBACK_PPT_THEMES: PptThemeOption[] = [
  { key: 'dark_tech', name: '深色科技风', description: '深蓝黑底、青蓝强调色，适合算法展示、答辩和技术演示。', is_dark: true },
  { key: 'academic_clean', name: '学术简洁风', description: '米白底与深蓝标题，适合课堂讲授、论文和正式汇报。', is_dark: false },
  { key: 'education_fresh', name: '清新教育风', description: '浅绿与暖黄配色，适合通识课程、青少年教学和科普。', is_dark: false },
  { key: 'business_blue', name: '商务蓝风', description: '稳定商务蓝与暖橙点缀，适合项目路演和教师培训。', is_dark: false },
]

export default function GeneratePage() {
  const { t } = useTranslation()
  const {
    type, topic, pptTheme, content, isStreaming, error,
    result, filepath, showStreaming,
    setType, setTopic, setPptTheme, appendContent, setStreaming, setError, setResult, setShowStreaming, reset,
  } = useGenerateStore()
  const abortRef = useRef<(() => void) | null>(null)
  const [searchParams] = useSearchParams()
  const queryTopic = searchParams.get('topic') || ''
  const queryNodeId = searchParams.get('node_id') || ''
  const queryPathTopic = searchParams.get('path_topic') || ''
  const queryResourceType = searchParams.get('resource_type') || ''
  const queryResourceRef = searchParams.get('resource_ref') || ''
  const [streamingExpanded, setStreamingExpanded] = useState(false)
  const [, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')
  const [savingToPath, setSavingToPath] = useState(false)
  const [pathSaveMsg, setPathSaveMsg] = useState('')
  const [pptThemes, setPptThemes] = useState<PptThemeOption[]>(FALLBACK_PPT_THEMES)
  const [view, setView] = useState<'generate' | 'materials'>(searchParams.get('tab') === 'materials' ? 'materials' : 'generate')
  const [materialIds, setMaterialIds] = useState<string[]>([])
  const [materialSources, setMaterialSources] = useState<MaterialSource[]>([])
  const [generationStrategy, setGenerationStrategy] = useState('')
  const [agentTrace, setAgentTrace] = useState<string[]>([])
  const [feedbackMsg, setFeedbackMsg] = useState('')

  // 生成接口只在结束时一次性返回 agent_trace（string[]），不像对话那样逐阶段推状态事件，
  // 所以这里映射成流水线组件需要的形状，并统一标记为已完成——这是如实的：
  // 能拿到轨迹，就说明这些阶段确实都跑过了。
  // 必须 useMemo：每次渲染都新建数组会让组件的计时逻辑误判成"新一轮"，
  // 从而显示 0.0s 这种看起来像真实测量的假数字。
  const traceEvents: AgentStatusEvent[] = useMemo(
    () => agentTrace.map((label, index) => ({
      stage: `gen-${index}`,
      label,
      state: 'completed',
    })),
    [agentTrace],
  )

  useEffect(() => {
    let active = true
    getPptThemes()
      .then((themes) => {
        if (active && themes.length > 0) setPptThemes(themes)
      })
      .catch(() => {
        // 保留本地主题作为离线兜底，不影响资源生成。
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (isStreaming) {
      setStreamingExpanded(true)
    }
  }, [isStreaming])

  useEffect(() => {
    if (result) {
      setStreamingExpanded(false)
    }
  }, [result])

  useEffect(() => {
    if (queryTopic && !topic) {
      setTopic(queryTopic)
    }
  }, [queryTopic])

  useEffect(() => {
    if (!queryResourceRef && RESOURCE_TYPES.some((resourceType) => resourceType === queryResourceType)) {
      reset()
      setType(queryResourceType)
    }
  }, [queryResourceType, queryResourceRef, reset, setType])

  useEffect(() => {
    const loadExisting = async () => {
      if (!queryResourceRef) return
      setType(queryResourceType || 'document')
      setTopic(queryTopic)
      
      if (queryResourceType === 'mindmap') {
        try {
          const filename = queryResourceRef.split('/').pop() || queryResourceRef.split('\\').pop() || queryResourceRef
          const ticket = await createFileTicket(filename)
          const res = await fetch(ticket.url)
          if (res.ok) {
            const md = await res.text()
            setResult(md, filename)
          } else {
            setError(`文件不存在: ${filename}`)
          }
        } catch { setError('无法加载已有资源') }
      } else if (queryResourceType === 'exercise') {
        try {
          const data = await getQuestionsByTopic(queryResourceRef)
          if (data.questions?.length) {
            const lines = data.questions.map((q, i) => 
              `### 第${i + 1}题\n￥题型：${q.type}\n￥知识点：${q.knowledge_point}\n￥题目：${q.question}\n${q.options?.map((o: {label: string, text: string}) => `￥选项${o.label}：${o.text}`).join('\n') || ''}\n￥答案：${q.answer}\n￥解析：${q.explanation}\n￥难度：${q.difficulty}\n`
            ).join('\n\n')
            setResult(lines, queryResourceRef)
          } else {
            setError('题库中没有找到相关题目')
          }
        } catch { setError('无法加载习题资源') }
      } else {
        const filename = queryResourceRef.split('/').pop() || queryResourceRef.split('\\').pop() || queryResourceRef
        setType(queryResourceType || 'document')
        setTopic(queryTopic)
        const typeLabel = queryResourceType === 'ppt' ? 'PPT演示文稿' : queryResourceType === 'mindmap' ? '思维导图' : '讲解文档'
        setResult(`# 已有资源：${typeLabel}\n\n文件：**${filename}**\n\n点击下方按钮下载或重新生成`, filename)
        setShowStreaming(false)
      }
    }
    loadExisting()
  }, [queryResourceRef])

  const handleGenerate = async (overrideTopic?: string, overrideMaterialIds?: string[]) => {
    const activeTopic = (overrideTopic ?? topic).trim()
    if (!activeTopic || isStreaming) return

    reset()
    setMaterialSources([])
    setGenerationStrategy('')
    setAgentTrace([])
    setFeedbackMsg('')
    setStreaming(true)
    setShowStreaming(true)
    setError(null)

    try {
      const abort = await connectGenerateStream(
        type, activeTopic,
        {
          onChunk: (text) => {
            appendContent(text)
          },
          onResult: (content, fp, sources, strategy, trace) => {
            setResult(content, fp)
            setMaterialSources(sources || [])
            setGenerationStrategy(strategy || '')
            setAgentTrace(trace || [])
          },
          onDone: () => {
            setStreaming(false)
            abortRef.current = null
          },
          onError: (err) => {
            setStreaming(false)
            setError(err.message || t('common.error'))
            abortRef.current = null
          },
        },
        undefined,   // user_id 交给 client 从登录态取；不要再传 'default'
        type === 'ppt' ? pptTheme : 'dark_tech',
        overrideMaterialIds ?? materialIds,
      )
      abortRef.current = abort
    } catch (err) {
      setStreaming(false)
      setError((err as Error).message || t('common.error'))
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleGenerate()
    }
  }

  const hasContent = content || result || isStreaming

  const handleFeedback = async (rating: ResourceRating) => {
    if (!topic.trim()) return
    try {
      await submitResourceFeedback({
        topic: topic.trim(),
        resource_type: type,
        rating,
        difficulty: 'appropriate',
        source_match: materialSources.length > 0,
      })
      setFeedbackMsg('反馈已写入算法，后续推荐会参考这次结果。')
    } catch (err) {
      setFeedbackMsg('反馈提交失败：' + (err as Error).message)
    }
  }

  return (
    <div className="flex flex-col h-full w-full max-w-[1380px] mx-auto">
      {/* Header */}
      <header className="core-page-head px-1">
        <div>
          <span className="core-kicker">RESOURCE FACTORY / MULTI-AGENT PIPELINE</span>
          <h1>{t('generate.title')}</h1>
          <p>讲解、思维导图、题库和 PPT 由多智能体生成，并经过内容审核。</p>
        </div>
        <div className="core-page-meta"><span>资源生成</span><span>结构化输出</span></div>
      </header>

      <div className="resource-view-tabs">
        <button type="button" className={view === 'generate' ? 'active' : ''} onClick={() => setView('generate')}>
          资源生成
        </button>
        <button type="button" className={view === 'materials' ? 'active' : ''} onClick={() => setView('materials')}>
          我的资料
        </button>
      </div>

      {view === 'materials' ? (
        <MaterialsPanel
          onboarding={searchParams.get('onboarding') === '1'}
          onGenerate={(materialTopic, ids) => {
            setTopic(materialTopic)
            setMaterialIds(ids)
            setView('generate')
            void handleGenerate(materialTopic, ids)
          }}
        />
      ) : (
        <>
      {/* Controls */}
      <div className="border border-[var(--panel-line)] bg-[var(--panel-bg)] p-4">
        {/* Type selector */}
        <div className="flex flex-wrap gap-2 mb-4">
          {RESOURCE_TYPES.map((rt) => (
            <button
              key={rt}
              onClick={() => { if (!isStreaming) { reset(); setType(rt) } }}
              disabled={isStreaming}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 border"
              style={{
                backgroundColor: type === rt ? 'var(--color-accent)' : 'transparent',
                color: type === rt ? '#fff' : 'var(--color-text-secondary)',
                borderColor: type === rt ? 'var(--color-accent)' : 'var(--color-border)',
                opacity: isStreaming ? 0.6 : 1,
              }}
            >
              {t(`generate.types.${rt}`)}
            </button>
          ))}
        </div>

        {type === 'ppt' && (
          <div className="mb-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-3">
            <div className="flex items-center justify-between gap-3 mb-3">
              <div>
                <div className="text-sm font-semibold text-primary">PPT 视觉主题</div>
                <div className="text-xs text-tertiary mt-0.5">主题会同步控制封面、版式、卡片、图表强调色和代码块。</div>
              </div>
              <span className="text-[11px] font-mono text-tertiary">AUTO LAYOUT</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2">
              {pptThemes.map((theme) => {
                const active = pptTheme === theme.key
                return (
                  <button
                    key={theme.key}
                    type="button"
                    onClick={() => setPptTheme(theme.key)}
                    disabled={isStreaming}
                    className="text-left rounded-lg border px-3 py-2.5 transition-all duration-200 disabled:opacity-60"
                    style={{
                      borderColor: active ? 'var(--color-accent)' : 'var(--color-border)',
                      backgroundColor: active ? 'var(--color-bg-tertiary)' : 'transparent',
                      boxShadow: active ? 'inset 0 0 0 1px var(--color-accent)' : 'none',
                    }}
                  >
                    <span className="flex items-center gap-2 text-sm font-medium text-primary">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: THEME_DOT_COLORS[theme.key] || 'var(--color-accent)' }}
                      />
                      {theme.name}
                    </span>
                    <span className="block mt-1 text-[11px] leading-4 text-tertiary">{theme.description}</span>
                  </button>
                )
              })}
            </div>
          </div>
        )}
        {/* Topic input */}
        <div className="flex gap-2">
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('generate.topicPlaceholder')}
            disabled={isStreaming}
            className="flex-1 px-4 py-2 rounded-lg text-sm border border-border transition-colors outline-none bg-bg-primary text-primary"
          />
          <button
            onClick={() => void handleGenerate()}
            disabled={!topic.trim() || isStreaming}
            className="px-6 py-2 rounded-lg text-sm font-medium transition-all duration-200"
            style={{
              backgroundColor: !topic.trim() || isStreaming ? 'var(--color-bg-tertiary)' : 'var(--color-accent)',
              color: !topic.trim() || isStreaming ? 'var(--color-text-tertiary)' : '#fff',
              cursor: !topic.trim() || isStreaming ? 'not-allowed' : 'pointer',
            }}
          >
            {isStreaming ? t('generate.generating') : t('generate.generate')}
          </button>
        </div>

        <div className="text-xs mt-2 text-tertiary">
          {t('generate.type')}: {t(`generate.types.${type}`)}{type === 'ppt' && ` · PPT 主题: ${pptThemes.find((item) => item.key === pptTheme)?.name || pptTheme}`}{materialIds.length > 0 && ` · 参考资料 ${materialIds.length} 份`}
        </div>
      </div>

      {/* Content display */}
      <div className="flex-1 overflow-auto px-4 py-6">
        {error ? (
          <div
            className="rounded-2xl px-4 py-3 text-sm leading-relaxed border-2 flex items-start gap-2 bg-bg-tertiary"
            style={{
              borderColor: '#ef4444',
              color: '#dc2626',
            }}
          >
            <span className="flex-shrink-0">{'\u26A0'}</span>
            <div>
              <p className="font-medium mb-1">{t('common.error')}</p>
              <p>{error}</p>
              <button
                onClick={() => void handleGenerate()}
                className="mt-2 px-3 py-1 rounded text-sm font-medium"
                style={{ backgroundColor: 'var(--color-accent)', color: '#fff' }}
              >
                {t('common.retry')}
              </button>
            </div>
          </div>
        ) : hasContent ? (
          <div className="flex flex-col gap-4">
            {/* Streaming section */}
            {showStreaming && content && (
              <div
              className="rounded-2xl overflow-hidden bg-bg-tertiary"
            >
                <button
                  onClick={() => setStreamingExpanded(!streamingExpanded)}
                  className="w-full flex items-center justify-between px-4 py-2 text-sm font-medium transition-colors text-secondary"
                  style={{
                    borderBottom: streamingExpanded ? '1px solid var(--color-border)' : 'none',
                  }}
                >
                  <span>{t('generate.collapse')}</span>
                  <span>{streamingExpanded ? '\u25BC' : '\u25B6'}</span>
                </button>
                {streamingExpanded && (
                  <div className="px-4 py-3 text-sm leading-relaxed">
                    <MarkdownRenderer content={content} />
                  </div>
                )}
              </div>
            )}

            {materialSources.length > 0 && (
              <div className="material-source-panel">
                <div className="material-source-head">
                  <strong>本次生成参考了 {materialSources.length} 份资料</strong>
                  <span>生成依据</span>
                </div>
                <div className="material-source-list">
                  {materialSources.map((source) => (
                    <div className="material-source-item" key={source.id}>
                      <b>{source.name}</b>
                      <p>{source.excerpt}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(generationStrategy || agentTrace.length > 0) && (
              <div className="generation-trace-panel">
                <div className="generation-trace-head">
                  <strong>本次生成过程</strong>
                  {generationStrategy && <span>算法策略：{generationStrategy}</span>}
                </div>
                <AgentPipeline events={traceEvents} />
              </div>
            )}

            {result && (
              <div className="resource-feedback-panel">
                <div>
                  <strong>这份内容对你有帮助吗？</strong>
                  <small>反馈会作为奖励写回 Contextual UCB，影响后续推荐。</small>
                </div>
                <div>
                  <button type="button" onClick={() => void handleFeedback('helpful')}>有帮助</button>
                  <button type="button" onClick={() => void handleFeedback('neutral')}>一般</button>
                  <button type="button" onClick={() => void handleFeedback('not_helpful')}>没帮助</button>
                </div>
                {feedbackMsg && <p>{feedbackMsg}</p>}
              </div>
            )}

            {/* Result section */}
            {result && (
              type === 'mindmap' ? (
                <MindmapViewer content={result} />
              ) : type === 'exercise' ? (
                <ExerciseEditor
                  rawText={result}
                  onSave={async (rawText) => {
                    setSaving(true)
                    setSaveMsg('')
                    try {
                      const data = await saveQuestions(topic.trim(), rawText)
                      setSaveMsg(`已保存 ${data.saved} 道题目到题库`)
                    } catch (e) {
                      setSaveMsg('保存失败: ' + (e as Error).message)
                    } finally {
                      setSaving(false)
                    }
                  }}
                />
              ) : (
                <div className="rounded-2xl px-4 py-3 text-sm leading-relaxed bg-bg-tertiary text-primary">
                  <MarkdownRenderer content={result} />
                </div>
              )
            )}

            {saveMsg && (
              <div className={`text-sm font-medium ${saveMsg.includes('失败') ? 'text-[#ef4444]' : 'text-[#22c55e]'}`}>
                {saveMsg}
              </div>
            )}

            {/* Post-result toolbar */}
            {result && (
              <div className="flex flex-wrap items-center gap-3">
                {type !== 'exercise' && filepath && (
                  <button
                    onClick={async () => {
                      const filename = filepath.split('/').pop() || filepath.split('\\').pop() || filepath
                      try {
                        const ticket = await createFileTicket(filename)
                        const res = await fetch(ticket.url)
                        if (!res.ok) throw new Error(`HTTP ${res.status}`)
                        const blob = await res.blob()
                        const url = URL.createObjectURL(blob)
                        const a = document.createElement('a')
                        a.href = url
                        a.download = filename
                        document.body.appendChild(a)
                        a.click()
                        document.body.removeChild(a)
                        URL.revokeObjectURL(url)
                      } catch (e) {
                        setError('下载失败: ' + (e as Error).message)
                      }
                    }}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium"
                    style={{ backgroundColor: 'var(--color-accent)', color: '#fff' }}
                  >
                    {t('generate.download')} ({filepath.split('/').pop()})
                  </button>
                )}
                {type !== 'exercise' && !filepath && (
                  <span className="text-sm text-tertiary">{t('generate.noFile')}</span>
                )}
                {queryNodeId && queryPathTopic && (
                  <button
                    onClick={async () => {
                      setSavingToPath(true)
                      setPathSaveMsg('')
                      try {
                        const ref = type === 'exercise' ? topic.trim() : (filepath ? (filepath.split('/').pop() || filepath.split('\\').pop() || filepath) : '')
                        await updateNodeResource(queryPathTopic, queryNodeId, type, ref)
                        await updateNodeStatus(queryPathTopic, queryNodeId, 'in_progress')
                        setPathSaveMsg('已保存，并更新学习节点状态')
                      } catch (e) {
                        setPathSaveMsg('保存失败: ' + (e as Error).message)
                      } finally {
                        setSavingToPath(false)
                      }
                    }}
                    disabled={savingToPath}
                    className="px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 disabled:opacity-50"
                    style={{ backgroundColor: 'var(--color-bg-tertiary)', color: 'var(--color-text-primary)', border: '1px solid var(--color-border)' }}
                  >
                    {savingToPath ? '保存中...' : '保存到学习路径'}
                  </button>
                )}
                <button
                  onClick={reset}
                  className="px-4 py-2 rounded-lg text-sm font-medium"
                  style={{ backgroundColor: 'var(--color-accent)', color: '#fff' }}
                >
                  {t('generate.regenerate')}
                </button>
                <button
                  onClick={reset}
                  className="px-4 py-2 rounded-lg text-sm font-medium"
                  style={{ backgroundColor: 'var(--color-bg-tertiary)', color: 'var(--color-text-secondary)' }}
                >
                  关闭
                </button>
              </div>
            )}
            {pathSaveMsg && (
              <div className={`text-sm font-medium ${pathSaveMsg.includes('失败') ? 'text-[#ef4444]' : 'text-[#22c55e]'}`}>
                {pathSaveMsg}
              </div>
            )}

            {/* Loading indicator during streaming */}
            {isStreaming && (
              <LoadingIndicator />
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-tertiary">
            <p className="text-sm">{t('generate.topicPlaceholder')}</p>
          </div>
        )}
      </div>
        </>
      )}
    </div>
  )
}

function LoadingIndicator() {
  return (
    <div className="flex gap-1 items-center justify-center py-2">
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

function ExerciseEditor({ rawText, onSave }: { rawText: string; onSave: (text: string) => Promise<void> }) {
  const [text, setText] = useState(rawText)

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-border bg-bg-secondary overflow-hidden">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="w-full px-4 py-3 text-sm leading-relaxed bg-bg-tertiary text-primary outline-none resize-y min-h-[200px] font-mono"
          placeholder="可在这里修改题目内容"
        />
      </div>
      <div className="flex gap-3">
        <button
          onClick={() => onSave(text)}
          className="px-5 py-2 rounded-lg text-sm font-medium transition-all duration-200"
          style={{ backgroundColor: 'var(--color-accent)', color: '#fff' }}
        >
          保存到题库
        </button>
      </div>
    </div>
  )
}



