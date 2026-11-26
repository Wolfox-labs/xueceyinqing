import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  getProfileDashboard,
  type ProfileActivity,
  type ProfileCard,
  type ProfileCardItem,
  type ProfileDashboardResponse,
} from '../api/profile'
import RadarChart from '../components/charts/RadarChart'
import LineChart from '../components/charts/LineChart'
import { getAdaptiveDashboard, type AdaptiveDashboardResponse } from '../api/adaptive'
import { getSummary, getChartData, getSuggestions } from '../api/reports'
import { useAuthStore } from '../stores/authStore'
import SkeletonPage from '../components/ui/Skeleton'

const STATUS_META: Record<string, { label: string; tone: string }> = {
  default: { label: '待完善', tone: 'muted' },
  inferred: { label: '系统推断', tone: 'cyan' },
  confirmed: { label: '测评确认', tone: 'green' },
  stable: { label: '已稳定', tone: 'violet' },
}

const SOURCE_LABELS: Record<string, string> = {
  profile: '画像初始化',
  qa: '问答证据',
  assessment: '测评证据',
  path: '学习路径',
  resource: '资源生成',
  adaptive: '自适应引擎',
  system: '系统记录',
}

function statusMeta(status: string) {
  return STATUS_META[status] ?? { label: status || '待完善', tone: 'muted' }
}

function sourceLabel(source: string) {
  return SOURCE_LABELS[source] ?? (source || '系统')
}

function formatTimestamp(value: string) {
  if (!value) return '等待首次更新'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function EvidenceRow({ item, showScore = false }: { item: ProfileCardItem; showScore?: boolean }) {
  const meta = statusMeta(item.status)
  const score = typeof item.score === 'number' ? Math.max(0, Math.min(100, Math.round(item.score))) : null
  // 长文本不再塞进标题行右侧：那里是 flex 行，值不收缩就会把整行顶出面板
  // （实测 92 字的偏好描述撑到 1190px，超出面板 544px，直接横穿到右栏上）。
  // 超过阈值就改为正文段落，允许换行。
  const value = item.value ?? ''
  const isLongValue = value.length > 24

  return (
    <div className="profile-evidence-row">
      <div className="profile-evidence-title">
        <strong>{item.label}</strong>
        {!isLongValue && <span>{value}</span>}
      </div>
      {isLongValue && <p className="profile-evidence-text">{value}</p>}
      {showScore && score !== null && (
        <div className="profile-bar" aria-hidden="true">
          <span style={{ width: `${score}%` }} />
        </div>
      )}
      <div className="profile-evidence-meta">
        <span>{sourceLabel(item.source)}</span>
        <span className={`profile-status profile-status--${meta.tone}`}>{meta.label}</span>
        {item.confidence != null && <span>置信度 {Math.round(item.confidence * 100)}%</span>}
      </div>
    </div>
  )
}

function ProfileCardPanel({ card }: { card: ProfileCard }) {
  const isTopicCard = card.kind === 'topics'
  const showScore = card.kind === 'knowledge' || card.kind === 'weak_points'

  return (
    <section className={`profile-panel profile-panel--${card.kind}`}>
      <div className="profile-panel__head">
        <div>
          <h2>{card.title}</h2>
          <p>{card.subtitle}</p>
        </div>
        <span className="profile-panel__count">
          {isTopicCard ? card.tags.length : card.items.length} 条
        </span>
      </div>
      <div className="profile-panel__body">
        {isTopicCard ? (
          card.tags.length > 0 ? (
            <div className="profile-tag-cloud">
              {card.tags.map((tag) => <span key={tag} className="profile-tag">{tag}</span>)}
            </div>
          ) : (
            <p className="profile-empty">完成问答、测评或资源生成后，系统会自动提炼关注主题。</p>
          )
        ) : card.items.length > 0 ? (
          <div className="profile-evidence-list">
            {card.items.map((item, index) => (
              <EvidenceRow key={`${card.id}-${item.label}-${index}`} item={item} showScore={showScore} />
            ))}
          </div>
        ) : (
          <p className="profile-empty">当前条目仍待学习证据补充。</p>
        )}
      </div>
    </section>
  )
}

function ActivityRows({ items, emptyText }: { items: ProfileActivity[]; emptyText: string }) {
  if (items.length === 0) {
    return <p className="profile-empty">{emptyText}</p>
  }

  return (
    <div className="profile-activity-list">
      {items.map((item, index) => (
        <div className="profile-activity-row" key={`${item.timestamp}-${item.source}-${index}`}>
          <span className="profile-activity-dot" aria-hidden="true" />
          <div>
            <div className="profile-activity-title">
              <strong>{item.title}</strong>
              <time>{formatTimestamp(item.timestamp)}</time>
            </div>
            {item.detail && <p>{item.detail}</p>}
            <span className="profile-source-label">{sourceLabel(item.source)}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function ProfilePage() {
  const { t } = useTranslation()
  const [dashboard, setDashboard] = useState<ProfileDashboardResponse | null>(null)
  const [error, setError] = useState(false)
  const session = useAuthStore((state) => state.session)
  // 学情部分的数据（原「学情洞察」页已并入本页，避免同一批数据在多个页面重复展示）。
  const [adaptive, setAdaptive] = useState<AdaptiveDashboardResponse | null>(null)
  const [insightSummary, setInsightSummary] = useState<
    { total_hours: number; completed_nodes: number; avg_accuracy: number; last_topic: string } | null
  >(null)
  const [insightLine, setInsightLine] = useState<{ labels: string[]; values: number[] } | null>(null)
  const [insightSuggestions, setInsightSuggestions] = useState<string[]>([])

  const loadDashboard = () => {
    setError(false)
    getProfileDashboard()
      .then(setDashboard)
      .catch(() => setError(true))
  }

  useEffect(() => {
    loadDashboard()
    getAdaptiveDashboard().then(setAdaptive).catch(() => setAdaptive(null))
    getSummary().then(setInsightSummary).catch(() => setInsightSummary(null))
    getChartData(undefined, 'line')
      .then((data) => { if (data.line) setInsightLine(data.line) })
      .catch(() => setInsightLine(null))
    getSuggestions().then(setInsightSuggestions).catch(() => setInsightSuggestions([]))
  }, [])

  if (error) {
    return (
      <div className="core-page">
        <div className="core-error">无法加载学习者数字画像，请确认后端档案聚合接口已启动。</div>
        <button type="button" className="core-button" onClick={loadDashboard}>
          {t('profile.retry')}
        </button>
      </div>
    )
  }

  if (!dashboard) {
    return <SkeletonPage panels={4} />
  }

  const { identity, summary } = dashboard
  // 后端在用户没有昵称时会把 display_name 回退成 user_id，于是这里会把一串十六进制 ID
  // 当成人名显示（而且上方 eyebrow 已经展示过同一个 ID）。回退到登录用户名。
  const displayName = identity.display_name && identity.display_name !== dashboard.user_id
    ? identity.display_name
    : (session?.name || '学习者')
  const initial = displayName.slice(0, 1).toUpperCase() || 'L'
  // 雷达图优先取自适应引擎的真实掌握度：学习证据会直接写进自适应状态，通常有数据；
  // 画像聚合里的 knowledge 只在测评回写后才非空，留作兜底。
  // 原实现只用画像聚合，导致明明有学习证据、这张图却是空的。
  const adaptiveKnowledge = adaptive?.knowledge_states?.length
    ? {
        labels: adaptive.knowledge_states.map((item) => item.knowledge_point),
        values: adaptive.knowledge_states.map((item) => Math.round(item.effective_mastery * 100)),
      }
    : null
  const knowledgeData = adaptiveKnowledge
    ?? (dashboard.knowledge.labels.length > 0 ? dashboard.knowledge : null)
  const knowledgeCount = (adaptiveKnowledge ?? dashboard.knowledge).labels.length
  // 雷达图最多画 8 根轴。
  //
  // 为什么：30 个知识点全画上去时，recharts 会把 30 个轴标签沿圆周堆叠，
  // 实测出现 12 处标签互相重叠（坐标挤在 x=1543~1639 一条窄带里），
  // 图完全没法看。雷达图的轴数超过 8~10 就失去可读性。
  // 取**掌握度最低**的 8 个：既读得清，也正好是学习者最该关注的部分。
  const RADAR_MAX_AXES = 8
  const radarSource = knowledgeData
    ? knowledgeData.labels
        .map((label, i) => ({ label, value: knowledgeData.values[i] ?? 0 }))
        .sort((a, b) => a.value - b.value)
        .slice(0, RADAR_MAX_AXES)
    : []
  const radarData = radarSource.length
    ? { labels: radarSource.map((item) => item.label), values: radarSource.map((item) => item.value) }
    : null
  const radarTruncated = knowledgeCount > radarSource.length
  const knowledgeCard = dashboard.cards.find((card) => card.kind === 'knowledge')
  const structuredCards = ['preferences', 'weak_points', 'topics']
    .map((id) => dashboard.cards.find((card) => card.id === id))
    .filter((card): card is ProfileCard => Boolean(card))
  const metrics = [
    { label: '画像完整度', value: `${summary.profile_completeness}`, unit: '%', note: '证据源覆盖程度' },
    { label: '平均掌握度', value: `${summary.mastery_avg}`, unit: '%', note: '跨知识点综合估计' },
    { label: '薄弱知识点', value: `${summary.weak_point_count}`, unit: '项', note: '按风险优先级排序' },
    { label: '关注主题', value: `${summary.topic_count}`, unit: '个', note: `最近学习：${summary.latest_topic}` },
  ]

  return (
    <div className="core-page profile-page">
      <header className="core-page-head">
        <div>
          <span className="core-kicker">LEARNER DIGITAL TWIN / EVIDENCE GRAPH</span>
          <h1>{t('profile.title')}</h1>
          <p>问答、测评、学习路径与资源生成共同驱动画像更新，每条信息均保留来源和状态。</p>
        </div>
        <div className="core-page-meta">
          <span>多源证据聚合</span>
          <span>动态更新</span>
        </div>
      </header>

      <div className="profile-summary-grid">
        {metrics.map((metric) => (
          <div className="profile-summary-card" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}<small>{metric.unit}</small></strong>
            <p>{metric.note}</p>
          </div>
        ))}
      </div>

      <div className="profile-overview-grid">
        <section className="profile-panel profile-identity-card">
          <div className="profile-identity-top">
            <div className="profile-avatar">{initial}</div>
            <div className="profile-identity-copy">
              {/* 这里原来直接打印 dashboard.user_id（uuid4 十六进制），
                  既不是给人看的名字，又在页面上暴露内部标识。 */}
              <span className="profile-eyebrow">学习档案 / {displayName}</span>
              <h2>{displayName}</h2>
              <p>{identity.learning_stage || '学习阶段待完善'}</p>
            </div>
            <div className="profile-completion">
              <div
                className="profile-completion-ring"
                style={{ background: `conic-gradient(var(--color-accent) ${summary.profile_completeness}%, rgba(255,255,255,0.07) 0)` }}
              >
                <span>{summary.profile_completeness}%</span>
              </div>
              <small>画像完整度</small>
            </div>
          </div>
          <div className="profile-identity-grid">
            <div>
              <span>最近活动</span>
              <strong>{formatTimestamp(identity.last_active)}</strong>
            </div>
            <div>
              <span>历史会话</span>
              <strong>{summary.conversation_count} 个</strong>
            </div>
            <div>
              <span>当前主题</span>
              <strong>{summary.latest_topic || '待完善'}</strong>
            </div>
          </div>
          <div className="profile-tag-cloud">
            {identity.subjects.map((subject) => <span key={subject} className="profile-tag">{subject}</span>)}
          </div>
        </section>

        <section className="profile-panel profile-radar-panel">
          <div className="profile-panel__head">
            <div>
              <h2>知识状态图谱</h2>
              <p>
                融合画像基线、测评结果和自适应学习证据
                {radarTruncated && `（图中为掌握度最低的 ${radarSource.length} 个，共 ${knowledgeCount} 个）`}
              </p>
            </div>
            <span className="profile-panel__count">{knowledgeCount} 个维度</span>
          </div>
          <div className="profile-panel__body">
            <RadarChart data={radarData} />
          </div>
        </section>
      </div>

      <div className="profile-card-grid">
        {structuredCards.map((card) => <ProfileCardPanel key={card.id} card={card} />)}
        {knowledgeCard && <ProfileCardPanel card={knowledgeCard} />}
      </div>

      <section className="profile-panel">
        <div className="profile-panel__head">
          <div>
            <h2>学情趋势与策略建议</h2>
            <p>测评记录、正确率变化与算法建议（原「学情洞察」页已并入本页）</p>
          </div>
          <span className="profile-panel__count">
            {insightSummary ? 'INTEGRATED INSIGHTS' : 'NO LEARNING RECORDS'}
          </span>
        </div>
        <div className="profile-panel__body">
          <div className="insight-stat-grid">
            <div>
              <span>累计学习时长</span>
              <strong>{insightSummary?.total_hours ?? 0}h</strong>
              <small>{insightSummary && insightSummary.total_hours > 0 ? '来自真实活跃时长' : '开始学习后自动累计'}</small>
            </div>
            <div>
              <span>已完成节点</span>
              <strong>{insightSummary?.completed_nodes ?? 0}</strong>
              <small>知识图谱覆盖进度</small>
            </div>
            <div>
              <span>平均正确率</span>
              <strong>{insightSummary?.avg_accuracy ?? 0}%</strong>
              <small>来自测评结果回写</small>
            </div>
            <div>
              <span>最近评估主题</span>
              <strong>{insightSummary?.last_topic || '暂无'}</strong>
              <small>最近一次策略验证</small>
            </div>
          </div>
          <div className="insight-main-grid">
            <div className="insight-subpanel">
              <h3>评估正确率趋势</h3>
              <LineChart data={insightLine ?? { labels: [], values: [] }} />
            </div>
            <div className="insight-subpanel">
              <h3>学习策略建议</h3>
              <div className="insight-advice-list">
                {insightSuggestions.length > 0 ? (
                  insightSuggestions.map((suggestion, index) => (
                    <div key={index}>
                      <span className="core-tag">策略</span>
                      <p>{suggestion}</p>
                    </div>
                  ))
                ) : (
                  <p className="profile-empty">暂无学习建议（需要先产生学习或测评数据）。</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="profile-bottom-grid">
        <section className="profile-panel">
          <div className="profile-panel__head">
            <div>
              <h2>最近学习活动</h2>
              <p>最近产生的问答、测评、路径和资源证据</p>
            </div>
          </div>
          <div className="profile-panel__body">
            <ActivityRows items={dashboard.activities.slice(0, 6)} emptyText="完成一次学习行为后，这里会自动形成活动记录。" />
          </div>
        </section>

        <section className="profile-panel">
          <div className="profile-panel__head">
            <div>
              <h2>画像更新记录</h2>
              <p>保留来源、更新内容与时间，支持解释画像变化</p>
            </div>
          </div>
          <div className="profile-panel__body">
            <ActivityRows items={dashboard.update_log.slice(0, 8)} emptyText="画像更新日志等待第一条学习证据。" />
          </div>
        </section>
      </div>
    </div>
  )
}

