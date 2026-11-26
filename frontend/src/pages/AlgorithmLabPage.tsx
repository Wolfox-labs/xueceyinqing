import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createAdaptiveSimulation, getAdaptiveDashboard, listAdaptiveDecisions, selectAdaptivePolicy, type AdaptiveDashboardResponse, type AdaptiveDecision } from '../api/adaptive'
import AgentExperimentPanel from '../components/experiments/AgentExperimentPanel'
import ExperimentRunnerPanel from '../components/experiments/ExperimentRunnerPanel'

const strategyLabels: Record<string, string> = {
  explain: '概念讲解',
  example: '案例驱动',
  practice: '基础练习',
  review: '间隔复习',
  challenge: '挑战任务',
}

const decisionEventLabels: Record<string, string> = {
  assessment_evidence: '诊断测评回写',
  resource_generate: '资源生成策略',
  policy_select: '策略选择',
  policy_update: '策略奖励回写',
  student_feedback: '学生学习反馈',
  agent_config: 'Agent 配置变更',
}
// 演示用对照数据：这些数字是原型内置的仿真值，不是实测结论。
// 真实数据由后端 /api/adaptive/dashboard 的 experiment 字段返回（带 is_demo_data
// 标记）；组件优先使用后端数据，避免前后端两处各硬编码一份、彼此漂移。
const DEMO_EXPERIMENT_ROWS = [
  { name: '固定路径（演示）', masteryGain: 11.8, retention: 54, timeLabel: '100%', active: false },
  { name: '知识追踪（演示）', masteryGain: 17.6, retention: 68, timeLabel: '86%', active: false },
  { name: '学策引擎融合策略（演示）', masteryGain: 28.4, retention: 82, timeLabel: '72%', active: true },
]

// 消融演示目前没有对应的后端接口，数值同样只是原型示意。
const DEMO_ABLATION_ROWS = [
  { name: '完整算法（演示）', gain: 28.4, retention: 82, baseline: true },
  { name: '去掉遗忘模型（演示）', gain: 23.1, retention: 71, baseline: false },
  { name: '去掉知识图谱（演示）', gain: 20.5, retention: 65, baseline: false },
  { name: '去掉 Contextual UCB（演示）', gain: 18.7, retention: 61, baseline: false },
]

function clamp(value: number, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value))
}

function ContributionBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="lab-contribution-row">
      <span>{label}</span>
      <div><i style={{ width: `${Math.max(2, value * 100)}%`, backgroundColor: color }} /></div>
      <strong>{value.toFixed(2)}</strong>
    </div>
  )
}

function SliderControl({ label, value, onChange, note }: {
  label: string
  value: number
  onChange: (value: number) => void
  note: string
}) {
  return (
    <label className="lab-slider">
      <span><b>{label}</b><em>{Math.round(value * 100)}%</em></span>
      <input type="range" min="0" max="100" value={Math.round(value * 100)} onChange={(e) => onChange(Number(e.target.value) / 100)} />
      <small>{note}</small>
    </label>
  )
}

export default function AlgorithmLabPage() {
  const [adaptive, setAdaptive] = useState<AdaptiveDashboardResponse | null>(null)
  const [decisions, setDecisions] = useState<AdaptiveDecision[]>([])
  const [selectedDecision, setSelectedDecision] = useState<AdaptiveDecision | null>(null)
  const [decisionError, setDecisionError] = useState('')
  const [mastery, setMastery] = useState(0.47)
  const [forgetting, setForgetting] = useState(0.39)
  const [dependency, setDependency] = useState(0.68)
  const [errors, setErrors] = useState(0.55)
  const [importance, setImportance] = useState(0.95)
  const [serverAction, setServerAction] = useState<string | null>(null)
  const [simulationId, setSimulationId] = useState('')
  const [simulationStatus, setSimulationStatus] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    listAdaptiveDecisions(30)
      .then((data) => setDecisions(data.decisions || []))
      .catch((err) => setDecisionError((err as Error).message || '决策记录加载失败'))
  }, [])

  useEffect(() => {
    getAdaptiveDashboard().then((data) => {
      setAdaptive(data)
      const top = data.recommendation
      if (!top) return
      setMastery(top.effective_mastery)
      setForgetting(top.forgetting_risk)
      setDependency(clamp(top.priority * 1.15))
      setErrors(clamp(top.forgetting_risk * 1.2))
    }).catch(() => setAdaptive(null))
  }, [])

  const priority = useMemo(
    () => clamp(0.40 * (1 - mastery) + 0.20 * forgetting + 0.15 * dependency + 0.15 * errors + 0.10 * importance),
    [mastery, forgetting, dependency, errors, importance],
  )

  const targetDifficulty = useMemo(() => clamp(mastery + 0.14, 0.15, 0.92), [mastery])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      selectAdaptivePolicy({ mastery, urgency: priority, learning_style: 'reading' })
        .then((data) => setServerAction(data.action))
        .catch(() => setServerAction(null))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [mastery, priority])

  const strategyScores = useMemo(() => {
    const raw = {
      explain: 0.46 * (1 - mastery) + 0.24 * forgetting + 0.14 * errors + 0.16,
      example: 0.34 * (1 - mastery) + 0.20 * forgetting + 0.18 * dependency + 0.18,
      practice: 0.38 * mastery + 0.18 * (1 - forgetting) + 0.20 * errors + 0.10,
      review: 0.46 * forgetting + 0.28 * (1 - mastery) + 0.16 * dependency,
      challenge: 0.42 * mastery + 0.25 * (1 - errors) + 0.16 * dependency - 0.08,
    }
    const total = Object.values(raw).reduce((sum, value) => sum + Math.max(0, value), 0)
    return Object.entries(raw).map(([key, value]) => ({
      key,
      value: Math.max(0, value) / Math.max(total, 1),
      raw: Math.max(0, value),
    })).sort((a, b) => b.value - a.value)
  }, [mastery, forgetting, dependency, errors])

  const selectedStrategy = strategyScores[0]
  // 对照表优先使用后端返回的实验行（含 is_demo_data 标记）；
  // 后端没有数据时才退回本地演示行。
  const experimentFromApi = adaptive?.experiment ?? []
  const experimentRows = experimentFromApi.length > 0
    ? experimentFromApi.map((item) => ({
        name: item.is_demo_data ? `${item.label}（演示数据）` : item.label,
        masteryGain: item.gain,
        retention: item.retention,
        // 后端未提供"相对时间成本"，不编造数字。
        timeLabel: '—',
        active: /学策|KG-F-CUCB/.test(item.label),
      }))
    : DEMO_EXPERIMENT_ROWS

  const ablationRows = DEMO_ABLATION_ROWS

  // 没有真实知识状态时不再编造 6 个掌握度数值：空数组由列表显示空态。
  const knowledgeStates = adaptive?.knowledge_states ?? []

  const contributions = [
    { label: '掌握度缺口', value: 0.40 * (1 - mastery), color: 'var(--color-accent)' },
    { label: '遗忘风险', value: 0.20 * forgetting, color: 'var(--color-warning)' },
    { label: '图谱依赖', value: 0.15 * dependency, color: 'var(--color-success)' },
    { label: '最近错误', value: 0.15 * errors, color: 'var(--color-error)' },
    { label: '知识重要度', value: 0.10 * importance, color: '#8a83ff' },
  ]

  return (
    <div className="core-page algorithm-lab">
      <header className="core-page-head">
        <div>
          <span className="core-kicker">KG-F-CUCB / ALGORITHM LABORATORY</span>
          <h1>算法实验室</h1>
          <p>追踪真实测评证据、策略选择和资源生成过程，并保留虚拟参数推演作为对照实验。</p>
        </div>
        <div className="core-page-meta">
          <span>可交互推演</span>
          <span>可解释决策</span>
        </div>
      </header>

      <section className="panel lab-real-panel">
        <div className="panel-head compact">
          <div>
            <span className="panel-index">真实数据</span>
            <div><h2>我的算法决策轨迹</h2><p>来自当前账号的测评回写、策略选择和资源生成记录</p></div>
          </div>
          <div className="lab-real-actions">
            <button type="button" onClick={() => navigate('/assess')}>完成诊断测评</button>
            <button type="button" onClick={() => navigate('/generate')}>生成学习资源</button>
          </div>
        </div>

        <div className="lab-real-summary">
          <div><span>当前掌握度</span><strong>{adaptive?.summary.mastery?.toFixed(1) ?? '--'}%</strong><small>来自真实学习证据</small></div>
          <div><span>遗忘风险点</span><strong>{adaptive?.summary.risk_points ?? 0}</strong><small>优先处理高风险知识</small></div>
          <div><span>当前推荐知识点</span><strong>{adaptive?.recommendation?.knowledge_point || '待初始化'}</strong><small>{adaptive?.recommendation?.action_label || '完成测评后生成'}</small></div>
          <div><span>决策记录</span><strong>{decisions.length}</strong><small>最近 30 条系统事件</small></div>
        </div>

        {decisionError && <div className="core-error">{decisionError}</div>}
        {decisions.length === 0 ? (
          <div className="lab-real-empty">
            <strong>还没有真实决策记录</strong>
            <span>完成一次诊断测评或生成一次学习资源后，算法依据会出现在这里。</span>
          </div>
        ) : (
          <div className="lab-decision-timeline">
            {decisions.map((item) => (
              <div key={item.id} className={selectedDecision?.id === item.id ? 'active' : ''} onClick={() => setSelectedDecision(item)}>
                <i />
                <div>
                  <div className="lab-decision-title">
                    <strong>{decisionEventLabels[item.event_type] || item.event_type}</strong>
                    <time>{new Date(item.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</time>
                  </div>
                  <p>
                    {item.knowledge_point || item.related_id || '当前学习状态'}
                    {item.selected_action ? (` · ${strategyLabels[item.selected_action] || item.selected_action}`) : ''}
                  </p>
                  <small>
                    {item.mastery != null ? (`掌握度 ${Math.round(item.mastery * 100)}%`) : ''}
                    {item.urgency != null ? (` · 优先级 ${item.urgency.toFixed(2)}`) : ''}
                    {item.reward != null ? (` · 奖励 ${item.reward.toFixed(2)}`) : ''}
                  </small>
                </div>
              </div>
            ))}
          </div>
        )}

        {selectedDecision && (
          <div className="lab-decision-details">
            <div>
              <strong>决策回放</strong>
              <button type="button" onClick={() => setSelectedDecision(null)}>关闭</button>
            </div>
            <dl>
              <div><dt>事件</dt><dd>{decisionEventLabels[selectedDecision.event_type] || selectedDecision.event_type}</dd></div>
              <div><dt>知识点 / 主题</dt><dd>{selectedDecision.knowledge_point || selectedDecision.related_id || '无'}</dd></div>
              <div><dt>策略</dt><dd>{strategyLabels[selectedDecision.selected_action] || selectedDecision.selected_action || '无'}</dd></div>
              <div><dt>掌握度</dt><dd>{selectedDecision.mastery != null ? (`${Math.round(selectedDecision.mastery * 100)}%`) : '无'}</dd></div>
              <div><dt>遗忘风险</dt><dd>{selectedDecision.forgetting != null ? (`${Math.round(selectedDecision.forgetting * 100)}%`) : '无'}</dd></div>
              <div><dt>优先级</dt><dd>{selectedDecision.urgency != null ? selectedDecision.urgency.toFixed(2) : '无'}</dd></div>
              <div><dt>奖励</dt><dd>{selectedDecision.reward != null ? selectedDecision.reward.toFixed(2) : '无'}</dd></div>
            </dl>
            {Object.keys(selectedDecision.details || {}).length > 0 && (
              <pre>{JSON.stringify(selectedDecision.details, null, 2)}</pre>
            )}
          </div>
        )}
      </section>

      <AgentExperimentPanel />

      <ExperimentRunnerPanel />

      <section className="panel" style={{ marginBottom: 18 }}>
        <div className="panel-head compact">
          <div>
            <div><h2>算法沙盒：虚拟学习者实验</h2><p>调节虚拟参数进行对照实验，不影响当前账号的真实学习状态</p></div>
          </div>
        </div>
        <div className="p-5 flex flex-wrap items-center gap-3">
          <button
            className="core-button"
            onClick={async () => {
              // 没有真实推荐知识点时不能凭空编一个：原实现回退成 '算法基础'，
              // 相当于替用户虚构了一个他从未学过的知识点去跑仿真。
              const kp = adaptive?.recommendation?.knowledge_point
              if (!kp) {
                setSimulationStatus('暂无真实推荐知识点：请先完成一次测评或产生学习数据后再试')
                return
              }
              try {
                const data = await createAdaptiveSimulation({
                  knowledge_point: kp,
                  mastery,
                  forgetting,
                  dependency,
                  errors,
                  importance,
                })
                setSimulationId(data.simulation_id)
                setSimulationStatus(`虚拟学习者已创建：${data.hint.action_label}`)
              } catch (err) {
                setSimulationStatus(`创建失败：${(err as Error).message}`)
              }
            }}
          >
            用当前参数生成虚拟学习者
          </button>
          <button
            className="core-button"
            disabled={!simulationId}
            onClick={() => navigate(`/chat?simulation_id=${encodeURIComponent(simulationId)}`)}
            style={{ opacity: simulationId ? 1 : 0.5 }}
          >
            用该虚拟状态进入问答
          </button>
          {simulationStatus && <span className="text-xs text-accent">{simulationStatus}</span>}
        </div>
      </section>

      <section className="lab-stat-grid">
        <div className="core-stat"><span>有效掌握度</span><strong>{(mastery * 100).toFixed(0)}%</strong><small>遗忘曲线修正后的状态</small></div>
        <div className="core-stat"><span>遗忘风险</span><strong>{(forgetting * 100).toFixed(0)}%</strong><small>由时间间隔和掌握度估计</small></div>
        <div className="core-stat"><span>推荐优先级</span><strong>{priority.toFixed(2)}</strong><small>五因素加权融合</small></div>
        <div className="core-stat"><span>目标难度</span><strong>{(targetDifficulty * 100).toFixed(0)}%</strong><small>启发式难度上移；后续用真实正确率校准</small></div>
      </section>

      <div className="lab-main-grid">
        <section className="panel lab-control-panel">
          <div className="panel-head compact">
            <div><span className="panel-index">01</span><div><h2>状态参数推演</h2><p>拖动参数可实时观察推荐结果</p></div></div>
          </div>
          <div className="lab-slider-grid">
            <SliderControl label="当前掌握度" value={mastery} onChange={setMastery} note="越低表示知识缺口越大" />
            <SliderControl label="遗忘风险" value={forgetting} onChange={setForgetting} note="越高表示越需要复习" />
            <SliderControl label="图谱依赖" value={dependency} onChange={setDependency} note="越高表示影响更多后续节点" />
            <SliderControl label="最近错误" value={errors} onChange={setErrors} note="反映近期错误频率" />
            <SliderControl label="知识重要度" value={importance} onChange={setImportance} note="课程体系中的核心程度" />
          </div>
        </section>

        <section className="panel lab-decision-panel">
          <div className="panel-head compact">
            <div><span className="panel-index">02</span><div><h2>推荐决策</h2><p>算法当前给出的学习决策</p></div></div>
          </div>
          <div className="lab-decision-body">
            <span className="core-tag">当前推荐策略</span>
            <h3>{strategyLabels[selectedStrategy.key]}</h3>
            <p>该策略在当前掌握度、遗忘风险和依赖关系下获得最高综合收益。</p>
            <div className="lab-decision-metrics">
              <div><span>优先级</span><strong>{priority.toFixed(2)}</strong></div>
              <div><span>目标难度</span><strong>{(targetDifficulty * 100).toFixed(0)}%</strong></div>
              <div><span>策略占比</span><strong>{(selectedStrategy.value * 100).toFixed(1)}%</strong></div>
            </div>
          </div>
        </section>
      </div>

      <div className="lab-secondary-grid">
        <section className="panel">
          <div className="panel-head compact">
            <div><span className="panel-index">03</span><div><h2>优先级贡献拆解</h2><p>0.40 × 缺口 + 0.20 × 遗忘 + 0.15 × 依赖 + 0.15 × 错误 + 0.10 × 重要度</p></div></div>
          </div>
          <div className="lab-contribution-list">
            {contributions.map((item) => <ContributionBar key={item.label} {...item} />)}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head compact">
            <div><span className="panel-index">04</span><div><h2>Contextual UCB 策略分布</h2><p>本地策略评分推演，具体动作由后端 UCB 返回：{serverAction || '计算中'}</p></div></div>
          </div>
          <div className="lab-strategy-list">
            {strategyScores.map((item, index) => (
              <div key={item.key} className={index === 0 ? 'selected' : ''}>
                <span>{strategyLabels[item.key]}</span>
                <div><i style={{ width: `${item.value * 100}%` }} /></div>
                <strong>{(item.value * 100).toFixed(1)}%</strong>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-head compact">
          <div><span className="panel-index">05</span><div><h2>知识状态与算法输入</h2><p>当前学生各知识点有效掌握度</p></div></div>
        </div>
        <div className="lab-knowledge-grid">
          {knowledgeStates.map((item) => {
            const value = item.effective_mastery
            return (
              <div className="lab-knowledge-item" key={item.knowledge_point}>
                <div><span>{item.knowledge_point}</span><strong>{(value * 100).toFixed(0)}%</strong></div>
                <div><i style={{ width: `${value * 100}%` }} /></div>
                <small>{value < 0.4 ? '高风险' : value < 0.7 ? '需巩固' : '较稳定'}</small>
              </div>
            )
          })}
        </div>
      </section>

      <div className="lab-secondary-grid">
        <section className="panel">
          <div className="panel-head compact">
            <div><span className="panel-index">06</span><div><h2>对照实验演示</h2><p>仿真实验数据，真实效果待对照测试</p></div></div>
          </div>
          <div className="lab-experiment-table">
            <div className="lab-table-head"><span>实验组</span><span>掌握增益</span><span>七天保持</span><span>相对时间成本</span></div>
            {experimentRows.map((row) => (
              <div className={row.active ? 'active' : ''} key={row.name}>
                <span>{row.name}</span><span>{row.masteryGain}%</span><span>{row.retention}%</span><span>{row.timeLabel}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head compact">
            <div><span className="panel-index">07</span><div><h2>消融实验演示</h2><p>仿真消融数据，验证各模块的预期贡献</p></div></div>
          </div>
          <div className="lab-ablation-list">
            {ablationRows.map((row) => (
              <div key={row.name}>
                <span>{row.name}</span>
                <div><i style={{ width: `${row.gain * 3}%` }} /></div>
                <strong>{row.gain}%</strong>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="panel lab-formula-panel">
        <div className="panel-head compact">
          <div><span className="panel-index">08</span><div><h2>当前计算记录</h2><p>优先级与难度为本地公式推演；策略动作来自后端 UCB 接口</p></div></div>
        </div>
        <div className="lab-formula-grid">
          <div><span>掌握度更新</span><code>M_new = M_old + α × (S - M_old)</code></div>
          <div><span>遗忘修正</span><code>M_eff = M_record × 2 ^ (-Δt / T_half)</code></div>
          <div><span>推荐优先级</span><code>P = Σ(weight_i × feature_i)</code></div>
          <div><span>策略选择</span><code>a* = argmax(mean_reward + λ × exploration)</code></div>
        </div>
      </section>
    </div>
  )
}
