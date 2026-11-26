import { useEffect, useMemo, useState } from 'react'
import {
  createAblationExperiment,
  getAblationExperiment,
  type AblationExperiment,
  type AblationRun,
} from '../../api/experiments'
import { useAuthStore } from '../../stores/authStore'

const VARIANT_LABELS: Record<string, string> = {
  full_system: '完整系统',
  no_critic: '无质疑 Agent',
  no_reviewer: '无审核 Agent',
  no_profile: '无画像上下文',
  no_quiz_agent: '无出题 Agent',
  single_agent: '单 Agent',
}

// 默认只勾选"完整系统"。原默认值是
// ['full_system', 'no_reviewer', 'no_profile', 'single_agent']，
// 即同时勾选"完整系统 + 无审核 + 单 Agent" —— 三者逻辑上不可能同时成立
// （完整系统意味着所有 Agent 都开启），作为默认值自相矛盾。
const DEFAULT_VARIANTS = ['full_system']

export default function ExperimentRunnerPanel() {
  const isTeacher = useAuthStore((state) => state.session?.role === 'teacher')
  const [variants, setVariants] = useState<string[]>(DEFAULT_VARIANTS)
  const [topicsText, setTopicsText] = useState('变量与数据类型, 函数与参数, 算法基础')
  const [repetitions, setRepetitions] = useState(1)
  const [taskType, setTaskType] = useState<'document' | 'exercise'>('document')
  const [dryRun, setDryRun] = useState(false)
  const [experiment, setExperiment] = useState<AblationExperiment | null>(null)
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)

  const topics = useMemo(
    () => topicsText.split(/[\n,，]+/).map((item) => item.trim()).filter(Boolean),
    [topicsText],
  )
  const plannedRuns = variants.length * topics.length * repetitions

  useEffect(() => {
    if (!experiment || !['pending', 'running'].includes(experiment.status)) return
    const timer = window.setInterval(() => {
      getAblationExperiment(experiment.id)
        .then(setExperiment)
        .catch((err) => setError((err as Error).message || '实验状态读取失败'))
    }, 2000)
    return () => window.clearInterval(timer)
  }, [experiment?.id, experiment?.status])

  const toggleVariant = (variant: string) => {
    setVariants((current) => current.includes(variant)
      ? current.filter((item) => item !== variant)
      : [...current, variant])
  }

  const start = async () => {
    if (!isTeacher || variants.length === 0 || topics.length === 0) return
    setStarting(true)
    setError('')
    try {
      const data = await createAblationExperiment({
        name: `多智能体消融 ${new Date().toLocaleString('zh-CN')}`,
        variants,
        topics,
        repetitions,
        task_type: taskType,
        dry_run: dryRun,
      })
      setExperiment(data)
    } catch (err) {
      setError((err as Error).message || '实验启动失败')
    } finally {
      setStarting(false)
    }
  }

  return (
    <section className="panel ablation-runner-panel">
      <div className="panel-head compact">
        <div>
          <span className="panel-index">RUNNER</span>
          <div><h2>运行消融实验</h2><p>后台逐组生成并保存原始结果、Agent 轨迹、延迟和估算 Token。</p></div>
        </div>
        <span className="core-tag">{isTeacher ? '教师可运行' : '仅教师可运行'}</span>
      </div>

      <div className="ablation-runner-form">
        <div className="ablation-variant-grid">
          {Object.entries(VARIANT_LABELS).map(([key, label]) => (
            <label key={key} className={variants.includes(key) ? 'active' : ''}>
              <input type="checkbox" checked={variants.includes(key)} disabled={!isTeacher} onChange={() => toggleVariant(key)} />
              <span>{label}</span>
            </label>
          ))}
        </div>
        <label className="ablation-wide-field">
          <span>测试主题，每行或逗号分隔</span>
          <textarea value={topicsText} disabled={!isTeacher} onChange={(event) => setTopicsText(event.target.value)} rows={3} />
        </label>
        <div className="ablation-runner-options">
          <label><span>任务类型</span><select value={taskType} disabled={!isTeacher} onChange={(event) => setTaskType(event.target.value as 'document' | 'exercise')}><option value="document">讲解文档</option><option value="exercise">练习题库</option></select></label>
          <label><span>每组重复</span><input type="number" min="1" max="5" value={repetitions} disabled={!isTeacher} onChange={(event) => setRepetitions(Number(event.target.value))} /></label>
          <label className="ablation-dry-run"><input type="checkbox" checked={dryRun} disabled={!isTeacher} onChange={(event) => setDryRun(event.target.checked)} /><span>试运行，不调用模型</span></label>
        </div>
        <div className="ablation-runner-submit">
          <span>预计运行 {plannedRuns} 次</span>
          <button type="button" disabled={!isTeacher || starting || variants.length === 0 || topics.length === 0} onClick={() => void start()}>
            {starting ? '正在创建...' : '开始消融实验'}
          </button>
        </div>
      </div>

      {error && <div className="core-error">{error}</div>}
      {experiment && (
        <div className="ablation-progress">
          <div className="ablation-progress-head">
            <strong>{experiment.name}</strong>
            <span>{experiment.status} · {experiment.completed_runs}/{experiment.total_runs}</span>
          </div>
          <div className="ablation-progress-bar"><i style={{ width: `${experiment.total_runs ? experiment.completed_runs / experiment.total_runs * 100 : 0}%` }} /></div>
          {dryRun && <p>当前为试运行模式，结果只用于验证实验流程，不能作为正式实验数据。</p>}
          <RunTable runs={experiment.runs} />
        </div>
      )}
    </section>
  )
}

function RunTable({ runs }: { runs: AblationRun[] }) {
  if (runs.length === 0) return <div className="teacher-empty">实验运行后，结果会显示在这里。</div>
  return (
    <div className="ablation-result-table">
      <div className="ablation-result-head"><span>实验组</span><span>主题</span><span>状态</span><span>延迟</span><span>估算 Token</span><span>格式</span><span>Agent 轨迹</span></div>
      {runs.map((run) => (
        <div key={run.id}>
          <span>{VARIANT_LABELS[run.variant] || run.variant}</span>
          <span>{run.topic}</span>
          <span>{run.status === 'completed' ? '完成' : '失败'}</span>
          <span>{run.latency_ms != null ? `${(run.latency_ms / 1000).toFixed(1)}s` : '--'}</span>
          <span>{run.estimated_tokens ?? '--'}</span>
          <span>{run.format_pass ? '通过' : run.withdrawn ? '撤回' : '未通过'}</span>
          <span>{run.agent_trace.join(' → ') || run.error || '--'}</span>
        </div>
      ))}
    </div>
  )
}