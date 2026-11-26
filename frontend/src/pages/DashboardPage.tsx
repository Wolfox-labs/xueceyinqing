import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import RadarChart from '../components/charts/RadarChart'
import Icon from '../components/ui/Icon'
import KnowledgeGraph from '../components/graph/KnowledgeGraph'
import SkeletonPage from '../components/ui/Skeleton'
import { getAdaptiveDashboard, type AdaptiveDashboardResponse } from '../api/adaptive'
import { completeAssignment, listAssignments, type Assignment } from '../api/assignments'

const agentSteps = [
  { code: 'PROFILE AGENT', title: '画像智能体', detail: '读取并更新学习者状态', state: 'done' },
  { code: 'POLICY ENGINE', title: '自适应路由算法', detail: '判断快速、标准或协商路径', state: 'active' },
  { code: 'TEACHER AGENT', title: '教学智能体', detail: '生成初答并在协商后修订', state: 'waiting' },
  { code: 'CRITIC AGENT', title: '质疑智能体', detail: '复杂问题按需寻找反例与漏洞', state: 'waiting' },
  { code: 'REVIEWER AGENT', title: '审核智能体', detail: '核验证据、事实和适用边界', state: 'waiting' },
  { code: 'QUIZ AGENT', title: '出题智能体', detail: '生成练习时按需创建', state: 'waiting' },
]

function MetricCard({ label, value, unit, note, tone = 'cyan', progress }: {
  label: string
  value: string
  unit?: string
  note: string
  tone?: 'cyan' | 'violet' | 'green' | 'amber'
  progress: number
}) {
  return (
    <div className={`metric-card tone-${tone}`}>
      <div className="metric-card__head">
        <span>{label}</span>
        <span className="metric-card__pulse" />
      </div>
      <div className="metric-card__value">
        {value}<small>{unit}</small>
      </div>
      <div className="metric-card__track"><span style={{ width: `${progress}%` }} /></div>
      <div className="metric-card__note">{note}</div>
    </div>
  )
}



export default function DashboardPage() {
  const navigate = useNavigate()
  const [now, setNow] = useState(() => new Date())
  const [adaptive, setAdaptive] = useState<AdaptiveDashboardResponse | null>(null)
  const [tasks, setTasks] = useState<Assignment[]>([])
  const [adaptiveLoading, setAdaptiveLoading] = useState(true)
  const [adaptiveError, setAdaptiveError] = useState(false)

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  const loadAdaptive = () => {
    setAdaptiveLoading(true)
    setAdaptiveError(false)
    getAdaptiveDashboard()
      .then(setAdaptive)
      .catch(() => setAdaptiveError(true))
      .finally(() => setAdaptiveLoading(false))
  }

  useEffect(() => {
    loadAdaptive()
  }, [])

  useEffect(() => {
    listAssignments().then((data) => setTasks(data.assignments)).catch(() => setTasks([]))
  }, [])

  const dateLabel = useMemo(
    () => new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', weekday: 'short' }).format(now),
    [now],
  )

  const displaySummary = adaptive?.summary ?? {
    mastery: 0,
    study_minutes: 0,
    risk_points: 0,
    policy_hit_rate: 0,
  }
  const displayRecommendation = adaptive?.recommendation
  const needsOnboarding = adaptive?.needs_onboarding === true
  const displayMasteryData = {
    labels: adaptive?.knowledge_states.map((item) => item.knowledge_point) ?? [],
    values: adaptive?.knowledge_states.map((item) => Math.round(item.effective_mastery * 100)) ?? [],
  }
  const displayPriorityRows = adaptive?.recommendations.map((item) => ({
    name: item.knowledge_point,
    mastery: Math.round(item.effective_mastery * 100),
    forgetting: Math.round(item.forgetting_risk * 100),
    dependency: Math.round(item.priority * 10),
    gain: Math.round(item.priority * 33),
    action: item.action_label || '策略选择',
  })) ?? []
  const displayComparison = (adaptive?.experiment ?? []).map((item) => ({
    ...item,
    // is_demo_data 是后端标注的原型内置仿真数据；必须让用户看见标签，
    // 而不是换个名字当成产品实测结论。
    label: item.is_demo_data
      ? `${item.label.replace(/mlqk/ig, '学策引擎')}（演示数据）`
      : item.label.replace(/mlqk/ig, '学策引擎'),
  }))
  // 最薄弱 / 掌握最好一律从真实知识状态推导；没有证据就显示"暂无证据"，
  // 不再硬编码"算法基础 / 列表与迭代"这类编造的观测结论。
  // 单次快照无法度量"提升速度"，所以这里不写"提升最快"。
  const masteryStates = adaptive?.knowledge_states ?? []
  const weakestState = masteryStates.length
    ? [...masteryStates].sort((a, b) => a.effective_mastery - b.effective_mastery)[0]
    : null
  const bestState = masteryStates.length
    ? [...masteryStates].sort((a, b) => b.effective_mastery - a.effective_mastery)[0]
    : null
  const pendingTasks = tasks.filter((item) => !item.completed)
  const visibleTasks = [...pendingTasks, ...tasks.filter((item) => item.completed)].slice(0, 3)
  const completedTaskCount = tasks.filter((item) => item.completed).length

  const handleTaskComplete = async (id: string) => {
    try {
      await completeAssignment(id)
      setTasks((current) => current.map((item) => item.id === id ? { ...item, completed: true } : item))
    } catch {
      // 任务状态更新失败时保持原列表，不影响驾驶舱其他内容。
    }
  }
  const focusGain = displayRecommendation ? Math.round(displayRecommendation.priority * 33) : 0

  if (adaptiveLoading && !adaptive) {
    return <SkeletonPage panels={3} />
  }

  if (adaptiveError || !adaptive) {
    return (
      <div className="core-page dashboard-onboarding-error">
        <div className="core-error">学习画像加载失败，请确认后端服务正常。</div>
        <button type="button" onClick={loadAdaptive}>重新加载</button>
      </div>
    )
  }
  return (
    <div className={`dashboard-shell ${needsOnboarding ? 'is-onboarding' : ''}`}>
      <section className="dashboard-hero">
        <div>
          <span className="eyebrow">ADAPTIVE LEARNING COMMAND CENTER</span>
          <h1>学习决策控制台</h1>
          <p>{needsOnboarding ? '完成一次初始诊断后，系统才会建立你的掌握度、薄弱点和个性化学习策略。' : '系统正在根据知识掌握、遗忘风险与前置依赖，生成今天的个性化学习策略。'}</p>
        </div>
        <div className="hero-side">
          <div className="hero-time"><Icon name="clock" size={16} /> {dateLabel}</div>
          <div className="status-chip"><span /> 引擎运行中</div>
        </div>
      </section>

      <section className="metric-grid">
        <MetricCard label="综合掌握度" value={displaySummary.mastery.toFixed(1)} unit="%" note="实时计算有效掌握度" tone="cyan" progress={displaySummary.mastery} />
        <MetricCard label="今日有效学习" value={String(displaySummary.study_minutes)} unit="min" note="前端活跃时自动累计" tone="violet" progress={Math.min(100, (displaySummary.study_minutes / 60) * 100)} />
        <MetricCard label="遗忘风险点" value={String(displaySummary.risk_points)} unit="项" note={'优先级最高：' + (displayRecommendation?.knowledge_point || '暂无')} tone="amber" progress={displayRecommendation ? Math.round(displayRecommendation.forgetting_risk * 100) : 0} />
        <MetricCard label="策略命中率" value={displaySummary.policy_hit_rate.toFixed(1)} unit="%" note="拉动落在该上下文经验最优动作的比例" tone="green" progress={displaySummary.policy_hit_rate} />
      </section>

      <section className="panel dashboard-task-panel">
        <div className="panel-head compact">
          <div>
            <span className="panel-index">TASK</span>
            <div>
              <h2>我的任务</h2>
              <p>教师布置的学习任务与完成进度</p>
            </div>
          </div>
          <div className="dashboard-task-actions">
            <span>已完成 {completedTaskCount}/{tasks.length}</span>
            <button type="button" onClick={() => navigate('/tasks')}>查看全部</button>
          </div>
        </div>
        {visibleTasks.length === 0 ? (
          <div className="dashboard-task-empty">当前没有学习任务。</div>
        ) : (
          <div className="dashboard-task-list">
            {visibleTasks.map((task) => (
              <div className={task.completed ? 'is-completed' : ''} key={task.id}>
                <i>{task.completed ? '✓' : '•'}</i>
                <span>
                  <strong>{task.title}</strong>
                  <small>{task.topic}{task.due_at ? ` · 截止 ${new Date(task.due_at).toLocaleDateString('zh-CN')}` : ''}</small>
                </span>
                <button type="button" disabled={task.completed} onClick={() => void handleTaskComplete(task.id)}>
                  {task.completed ? '已完成' : '完成任务'}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
      {needsOnboarding && (
        <section className="panel dashboard-onboarding-panel">
          <div className="dashboard-onboarding-mark">01</div>
          <div className="dashboard-onboarding-copy">
            <span className="core-kicker">INITIALIZE LEARNING PROFILE</span>
            <h2>先建立你的学习画像</h2>
            <p>当前账号还没有测评或学习证据。系统不会展示推测数据，完成一次初始诊断后，才会生成掌握度、薄弱知识点和个性化学习路径。</p>
            <div>
              <button type="button" onClick={() => navigate('/assess')}>开始初始诊断</button>
              <button type="button" className="ghost" onClick={() => navigate('/generate?tab=materials&onboarding=1')}>先添加学习资料</button>
            </div>
          </div>
        </section>
      )}

      <div className="dashboard-main-grid">
        <section className="panel decision-panel">
          <div className="panel-head">
            <div>
              <span className="panel-index">01</span>
              <div>
                <h2>下一项学习决策</h2>
                <p>Contextual UCB · 在线策略优化</p>
              </div>
            </div>
            <span className="confidence">规则可解释</span>
          </div>

          <div className="decision-focus">
            <div className="focus-copy">
              <span className="tagline">建议优先学习</span>
              <h3>{displayRecommendation ? `${displayRecommendation.knowledge_point}：${displayRecommendation.action_label ?? `目标难度 ${Math.round(displayRecommendation.target_difficulty * 100)}%`}` : '暂无推荐：先完成一次诊断测评'}</h3>
              <p>{displayRecommendation?.reason ?? '还没有掌握度证据。完成一次诊断测评后，这里会给出可解释的推荐理由。'}</p>
              <div className="decision-actions">
                <button onClick={() => navigate('/generate')}>生成定制讲解 <Icon name="arrow" size={16} /></button>
                <button className="ghost" onClick={() => navigate('/learning-path')}>查看学习路径</button>
                <button className="ghost" onClick={() => navigate('/algorithm-lab')}>查看算法依据</button>
              </div>
            </div>
            <div className="gain-ring">
              <div><strong>{focusGain}%</strong><span>优先级映射值（启发式）</span></div>
            </div>
          </div>

          <div className="reason-grid">
            <div><span>掌握度缺口</span><strong>{displayRecommendation ? `${Math.round((1 - displayRecommendation.effective_mastery) * 100)}%` : '—'}</strong><small>低于目标阈值 85%</small></div>
            <div><span>遗忘风险</span><strong>{displayRecommendation ? `${Math.round(displayRecommendation.forgetting_risk * 100)}%` : '—'}</strong><small>按时间衰减实时修正</small></div>
            <div><span>推荐优先级</span><strong>{displayRecommendation?.priority.toFixed(2) ?? '—'}</strong><small>多因素融合得分</small></div>
            <div><span>目标难度</span><strong>{displayRecommendation ? `${Math.round(displayRecommendation.target_difficulty * 100)}%` : '—'}</strong><small>启发式难度上移，后续用真实正确率校准</small></div>
          </div>
        </section>

        <section className="panel mastery-panel">
          <div className="panel-head compact">
            <div>
              <span className="panel-index">02</span>
              <div><h2>知识状态观测</h2><p>实时掌握度与薄弱结构</p></div>
            </div>
          </div>
          <RadarChart data={displayMasteryData} />
          <div className="mastery-footer">
            <span>最薄弱：{weakestState?.knowledge_point ?? '暂无证据'}</span>
            <span>掌握最好：{bestState?.knowledge_point ?? '暂无证据'}</span>
          </div>
        </section>
      </div>

      <div className="dashboard-secondary-grid">
        <section className="panel priority-panel">
          <div className="panel-head compact">
            <div>
              <span className="panel-index">03</span>
              <div><h2>知识点优先级</h2><p>掌握缺口 × 遗忘风险 × 图谱依赖</p></div>
            </div>
          </div>
          <div className="priority-table">
            <div className="priority-table__head">
              <span>知识点</span><span>掌握</span><span>遗忘</span><span>依赖</span><span>策略</span>
            </div>
            {displayPriorityRows.map((row, index) => (
              <div className="priority-table__row" key={row.name}>
                <span><b>{String(index + 1).padStart(2, '0')}</b>{row.name}</span>
                <span className="bar-cell"><i style={{ width: `${row.mastery}%` }} />{row.mastery}%</span>
                <span>{row.forgetting}%</span>
                <span>{row.dependency}</span>
                <span className="policy-label">{row.action}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel agent-panel">
          <div className="panel-head compact">
            <div>
              <span className="panel-index">04</span>
              <div><h2>智能体协作链路（静态示意）</h2><p>5 类 Agent 角色的固定编排关系，不是本次请求的实时轨迹；质疑与出题 Agent 按需启用</p></div>
            </div>
          </div>
          <div className="agent-flow">
            {agentSteps.map((step, index) => (
              <div className={`agent-step ${step.state}`} key={step.code}>
                <div className="agent-step__rail">
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  {index < agentSteps.length - 1 && <i />}
                </div>
                <div className="agent-step__copy">
                  <small>{step.code}</small>
                  <strong>{step.title}</strong>
                  <p>{step.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="dashboard-bottom-grid">
        <section className="panel graph-panel">
          <div className="panel-head compact">
            <div>
              <span className="panel-index">05</span>
              <div><h2>知识依赖图谱</h2><p>前置知识解锁与风险传播</p></div>
            </div>
          </div>
          <KnowledgeGraph
            nodes={adaptive?.knowledge_graph ?? []}
            onSelect={(name) => navigate(`/generate?topic=${encodeURIComponent(name)}`)}
          />
        </section>

        <section className="panel comparison-panel">
          <div className="panel-head compact">
            <div>
              <span className="panel-index">06</span>
              <div><h2>算法效果对照</h2><p>掌握增益与七天保持率</p></div>
            </div>
          </div>
          {displayComparison.length > 0 ? (
            <>
              <div className="comparison-chart">
                {displayComparison.map((item) => (
                  <div className="comparison-row" key={item.label}>
                    <span>{item.label}</span>
                    <div className="comparison-bars">
                      <i className="gain" style={{ width: `${item.gain * 2.8}%` }}><b>{item.gain}%</b></i>
                      <i className="retention" style={{ width: `${item.retention * 0.9}%` }}><b>{item.retention}%</b></i>
                    </div>
                  </div>
                ))}
              </div>
              {displayComparison.some((item) => item.is_demo_data) && (
                <div className="comparison-note">
                  <Icon name="activity" size={16} />
                  <span>含原型内置仿真数据，仅用于展示实验界面；真实教学效果以对照测试为准。</span>
                </div>
              )}
            </>
          ) : (
            <div className="comparison-empty">
              <strong>暂无对照数据</strong>
              <p>
                掌握增益与七天保持率必须来自真实对照测试，系统不会用编造的数字填充这里。
                可在「算法实验室」发起消融实验，用真实运行结果评估各组件贡献。
              </p>
              <button type="button" className="core-button secondary" onClick={() => navigate('/algorithm-lab')}>
                去算法实验室
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}











