import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listQuestionTopics } from '../api/question-bank'
import { generateAssessment, submitAssessment, type AssessResult, type QuestionItem } from '../api/assess'
import { submitAdaptiveEvidence } from '../api/adaptive'
import Card from '../components/ui/Card'
import { SkeletonPanel } from '../components/ui/Skeleton'

export default function AssessPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryTopic = searchParams.get('topic') || ''

  const [topics, setTopics] = useState<string[]>([])
  const [selectedTopic, setSelectedTopic] = useState('')
  const [questions, setQuestions] = useState<QuestionItem[]>([])
  const [assessmentId, setAssessmentId] = useState('')
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [phase, setPhase] = useState<'list' | 'answering' | 'submitting' | 'result'>('list')
  const [result, setResult] = useState<AssessResult | null>(null)
  const [error, setError] = useState('')
  const [loadingTopics, setLoadingTopics] = useState(true)
  const [loadingQuestions, setLoadingQuestions] = useState(false)
  const [adaptiveSync, setAdaptiveSync] = useState('')

  const handleSelectTopic = async (topic: string) => {
    setSelectedTopic(topic)
    setError('')
    setLoadingQuestions(true)
    try {
      const data = await generateAssessment(topic)
      setAssessmentId(data.assessment_id)
      setQuestions(data.questions || [])
      const initial: Record<string, string> = {}
      data.questions?.forEach((q) => { initial[String(q.id)] = '' })
      setAnswers(initial)
      setPhase('answering')
    } catch (e) {
      setError((e as Error).message || t('assess.error'))
    } finally {
      setLoadingQuestions(false)
    }
  }

  useEffect(() => {
    listQuestionTopics().then((data) => {
      const topicList = data.topics || []
      setTopics(topicList)
      setLoadingTopics(false)
      
      // 如果URL中有topic参数，自动选择该主题
      if (queryTopic && topicList.includes(queryTopic)) {
        handleSelectTopic(queryTopic)
      }
    }).catch(() => {
      setLoadingTopics(false)
      setError(t('assess.error'))
    })
  }, [])

  const handleSubmit = async () => {
    setError('')
    setPhase('submitting')
    const answerList = questions.map((q) => ({
      question_id: q.id,
      answer: answers[String(q.id)] || '',
    }))
    try {
      if (!assessmentId) throw new Error('测评题目尚未初始化，请重新选择主题')
      const data = await submitAssessment(assessmentId, answerList)
      setResult(data)
      // 只把测评真实给出的分数写入自适应引擎。
      // 原先还把 strengths 里的每个知识点以硬编码 score: 0.9 提交，等于凭空
      // 抬高掌握度并污染自适应推荐；那一段已删除。
      const observations = (data.weak_points ?? [])
        .map((item) => ({
          knowledge_point: String((item as { knowledge_point?: string }).knowledge_point || ''),
          score: Math.max(0, Math.min(1, ((item as { score?: number }).score ?? 0) / 100)),
        }))
        .filter((item) => item.knowledge_point)
      if (observations.length > 0) {
        try {
          await submitAdaptiveEvidence(observations)
          setAdaptiveSync('掌握度证据已写入自适应引擎')
        } catch {
          // 失败必须如实告知：不能像原先那样 .catch(() => null) 之后仍报成功
          setAdaptiveSync('掌握度证据写入失败，本次未更新自适应引擎')
        }
      }
      setPhase('result')
    } catch (e) {
      setError((e as Error).message || t('assess.error'))
      setPhase('answering')
    }
  }

  const setAnswer = (qid: string, value: string) => {
    setAnswers((prev) => ({ ...prev, [qid]: value }))
  }

  const pctColor = (pct: number) => {
    if (pct >= 80) return '#22c55e'
    if (pct >= 60) return '#f59e0b'
    return '#ef4444'
  }

  return (
    <div className="core-page">
      <header className="core-page-head">
        <div>
          <span className="core-kicker">DIAGNOSTIC ASSESSMENT / MASTERY EVIDENCE</span>
          <h1>{t('assess.title')}</h1>
          <p>答题结果将更新知识点掌握度，并重新计算学习路径优先级。</p>
        </div>
        <div className="core-page-meta"><span>诊断测评</span><span>证据回写</span></div>
      </header>

      {error && (
        <div className="mb-6 p-4 rounded-lg border" style={{ borderColor: '#ef4444', backgroundColor: '#ef444410' }}>
          <p className="text-sm" style={{ color: '#ef4444' }}>{error}</p>
        </div>
      )}

      {/* Phase: topic list */}
      {phase === 'list' && (
        <div className="space-y-4">
          {loadingTopics ? (
            <div className="space-y-3">
              <SkeletonPanel lines={2} />
              <SkeletonPanel lines={2} />
              <SkeletonPanel lines={2} />
            </div>
          ) : topics.length === 0 ? (
            <Card hover={false}>
              <div className="p-8 text-center">
                <p className="text-sm text-tertiary">暂无可用题库，请先生成练习题并保存到题库</p>
              </div>
            </Card>
          ) : (
            <>
              {loadingQuestions && (
                <Card hover={false}>
                  <div className="p-4 flex items-center gap-3 text-sm text-secondary">
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-t-transparent" style={{ borderColor: 'var(--color-accent)', borderTopColor: 'transparent' }} />
                    正在调用模型生成「{selectedTopic}」诊断题，请稍候……
                  </div>
                </Card>
              )}
              {topics.map((topic) => (
                <Card key={topic} hover={true}>
                  <button
                    onClick={() => handleSelectTopic(topic)}
                    disabled={loadingQuestions}
                    className="w-full p-5 text-left flex items-center justify-between disabled:opacity-60"
                  >
                    <span className="text-sm font-medium text-primary">{topic}</span>
                    <span className="text-xs text-tertiary">
                      {loadingQuestions && selectedTopic === topic ? '生成中...' : '开始检测'}
                    </span>
                  </button>
                </Card>
              ))}
            </>
          )}
        </div>
      )}

      {/* Phase: answering */}
      {phase === 'answering' && (
        <div className="space-y-6 mt-6">
          <div className="flex items-center gap-2 mb-4">
            <button onClick={() => setPhase('list')} className="text-sm text-accent hover:underline">返回选题</button>
            <span className="text-sm text-tertiary">| {selectedTopic}</span>
          </div>
          {questions.map((q) => (
            <Card key={q.id} hover={false}>
              <div className="p-5 space-y-3">
                <div className="flex items-start gap-2">
                  <span className="text-sm font-semibold text-accent flex-shrink-0">
                    第 {questions.indexOf(q) + 1} 题
                  </span>
                  <span className="text-sm text-primary leading-relaxed">{q.question}</span>
                </div>
                {q.difficulty && (
                  <span className="text-xs px-2 py-0.5 rounded" style={{ backgroundColor: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}>
                    {q.difficulty}
                  </span>
                )}
                {(() => {
                  const qid = String(q.id)
                  const options = q.type === 'true_false' && (!q.options || q.options.length === 0)
                    ? ['对', '错']
                    : (q.options || []).filter(Boolean)
                  const isMulti = q.type === 'multi_choice'
                  const selectedLabels = (answers[qid] || '').split(';').filter(Boolean)

                  if (options.length > 0) {
                    return (
                      <div className="space-y-1.5">
                        {options.map((opt, optionIndex) => {
                          const label = String.fromCharCode(65 + optionIndex)
                          const isSelected = isMulti ? selectedLabels.includes(label) : answers[qid] === label
                          return (
                            <label
                              key={`${q.id}-${label}`}
                              className={`flex items-center gap-2 px-3 py-2 rounded cursor-pointer transition-colors ${
                                isSelected
                                  ? 'bg-accent/10 border border-accent'
                                  : 'bg-bg-tertiary hover:bg-bg-secondary border border-transparent'
                              }`}
                            >
                              <input
                                type={isMulti ? 'checkbox' : 'radio'}
                                name={`q-${q.id}`}
                                checked={isSelected}
                                onChange={(event) => {
                                  if (!isMulti) {
                                    setAnswer(qid, label)
                                    return
                                  }
                                  const next = event.target.checked
                                    ? [...selectedLabels, label]
                                    : selectedLabels.filter((item) => item !== label)
                                  setAnswer(qid, Array.from(new Set(next)).sort().join(';'))
                                }}
                                className="accent-current"
                                style={{ accentColor: 'var(--color-accent)' }}
                              />
                              <span className="text-sm text-secondary">
                                <span className="font-medium">{label}.</span> {opt}
                              </span>
                            </label>
                          )
                        })}
                      </div>
                    )
                  }

                  return (
                    <textarea
                      value={answers[qid] || ''}
                      onChange={(e) => setAnswer(qid, e.target.value)}
                      placeholder={t('assess.answerPlaceholder')}
                      rows={3}
                      className="w-full px-3 py-2 rounded-lg border text-sm outline-none resize-none transition-colors border-border bg-bg-tertiary text-primary"
                    />
                  )
                })()}
              </div>
            </Card>
          ))}
          <div className="flex justify-center">
            <button
              onClick={handleSubmit}
              className="px-6 py-3 rounded-lg text-sm font-medium transition-all duration-200"
              style={{ backgroundColor: 'var(--color-accent)', color: '#fff' }}
            >
              {t('assess.submitAnswer')}
            </button>
          </div>
        </div>
      )}

      {/* Phase: submitting */}
      {phase === 'submitting' && (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-t-transparent" style={{ borderColor: 'var(--color-accent)', borderTopColor: 'transparent' }} />
          <span className="text-sm text-tertiary">{t('assess.submitting')}</span>
        </div>
      )}

      {/* Phase: result */}
      {phase === 'result' && result && (
        <div className="mt-6 space-y-6">
          {adaptiveSync && <div className="core-tag">{adaptiveSync}</div>}
          <Card hover={false}>
            <div className="p-6 text-center">
              <p className="text-sm mb-2 text-tertiary">{t('assess.percentage')}</p>
              <p className="text-5xl font-bold" style={{ color: pctColor(result.percentage) }}>
                {result.percentage}%
              </p>
              <div className="flex justify-center gap-6 mt-3">
                <div>
                  <span className="text-xs text-tertiary">{t('assess.score')}</span>
                  <p className="text-lg font-bold text-primary">{result.total_score}</p>
                </div>
                <div>
                  <span className="text-xs text-tertiary">{t('assess.maxScore')}</span>
                  <p className="text-lg font-bold text-primary">{result.max_score}</p>
                </div>
              </div>
            </div>
          </Card>

          <div className="grid md:grid-cols-2 gap-6">
            <Card>
              <h3 className="text-sm font-semibold mb-4 px-6 pt-6 text-primary">{t('assess.weakPoints')}</h3>
              <div className="px-6 pb-6 space-y-2">
                {(result.weak_points ?? []).map((wp, i) => {
                  const w = wp as { knowledge_point?: string; score?: number }
                  return (
                  <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-bg-tertiary">
                    <span className="text-sm text-secondary">{w.knowledge_point ?? ''}</span>
                    <span className="text-sm font-bold" style={{ color: pctColor(w.score ?? 0) }}>{w.score ?? 0}%</span>
                  </div>
                )})}
              </div>
            </Card>
            <Card>
              <h3 className="text-sm font-semibold mb-4 px-6 pt-6 text-primary">{t('assess.strengths')}</h3>
              <div className="px-6 pb-6 space-y-2">
                {(result.strengths ?? []).map((s, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-bg-tertiary">
                    <span className="core-tag">优势</span>
                    <span className="text-sm text-secondary">{s}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <Card>
            <h3 className="text-sm font-semibold mb-4 px-6 pt-6 text-primary">{t('assess.suggestions')}</h3>
            <div className="px-6 pb-6 space-y-3">
              {(result.suggestions ?? []).map((s, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-bg-tertiary">
                  <span className="core-tag">策略</span>
                  <p className="text-sm leading-relaxed text-secondary">{s}</p>
                </div>
              ))}
            </div>
          </Card>

          <div className="flex justify-center gap-4">
            <button onClick={() => { setPhase('list'); setResult(null); }} className="px-6 py-3 rounded-lg text-sm font-medium" style={{ backgroundColor: 'var(--color-bg-tertiary)', color: 'var(--color-text-primary)' }}>
              {t('common.retry')}
            </button>
            <button onClick={() => navigate('/algorithm-lab')} className="px-6 py-3 rounded-lg text-sm font-medium" style={{ backgroundColor: 'var(--color-bg-tertiary)', color: 'var(--color-text-primary)' }}>
              查看算法依据
            </button>
            <button onClick={() => navigate('/profile')} className="px-6 py-3 rounded-lg text-sm font-medium" style={{ backgroundColor: 'var(--color-accent)', color: '#fff' }}>
              {t('assess.viewReport')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


