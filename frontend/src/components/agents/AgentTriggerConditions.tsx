import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAgentTriggerRules, type AgentTriggerRules } from '../../api/agent-triggers'
import type { AgentStatusEvent } from '../../api/sse'
import Icon from '../ui/Icon'

export default function AgentTriggerConditions({ events }: { events: AgentStatusEvent[] }) {
  const [configuredRules, setConfiguredRules] = useState<AgentTriggerRules | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  useEffect(() => {
    let active = true
    getAgentTriggerRules().then((rules) => {
      if (active) setConfiguredRules(rules)
    }).catch(() => { if (active) setLoadFailed(true) })
    return () => { active = false }
  }, [])

  const route = events.find((event) => event.stage === 'route')
  // 本轮 SSE 配置快照优先，避免教师改配置后误解释已经执行的历史轨迹。
  const rules = route?.trigger_rules ?? configuredRules
  const routing = route?.routing
  const criticRan = events.some((event) => event.stage.startsWith('critique_'))
  const interrupted = events.some((event) => event.state === 'error')
  const criticBlocked = rules && (
    rules.orchestration_mode === 'single_agent' || !rules.critic_enabled ||
    !rules.reviewer_enabled || rules.max_rounds === 0
  )
  const quizBlocked = rules && (rules.orchestration_mode === 'single_agent' || !rules.quiz_agent_enabled)
  const criticStatus = criticRan ? '已触发' : routing?.critic_scheduled
    ? interrupted ? '前序中断，未执行' : '已安排'
    : criticBlocked ? '当前停用' : routing ? '本次跳过' : '等待判断'
  const blockedReason = !rules ? '' : rules.orchestration_mode === 'single_agent' ? '当前为单 Agent 模式。'
    : !rules.critic_enabled ? '当前配置关闭了质疑 Agent。'
    : !rules.reviewer_enabled ? '当前配置关闭了审核，质疑链路随之跳过。'
    : rules.max_rounds === 0 ? '当前协商轮数上限为 0。' : ''

  return (
    <section className="agent-triggers" aria-label="按需智能体触发条件">
      <div className="agent-triggers__head">
        <strong>触发条件与本次判断</strong>
        <small>普通问答：画像 → 教学 → 审核</small>
      </div>
      <div className="agent-triggers__grid">
        <article className={`agent-triggers__card ${criticRan || routing?.critic_scheduled ? 'is-scheduled' : ''}`}>
          <header><span><Icon name="activity" size={15} />质疑 Agent</span><b>{criticStatus}</b></header>
          <p>综合评分 ≥ <strong>{rules ? rules.deliberate_threshold.toFixed(2) : '当前深度协商阈值'}</strong>，且质疑、审核均开启、多 Agent 模式、协商轮数大于 0。</p>
          {routing && <div className="agent-triggers__decision" aria-live="polite">
            <span>本次评分 <strong>{routing.score.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')}</strong>
              {rules && <> / 触发阈值 <strong>{rules.deliberate_threshold.toFixed(2)}</strong></>}</span>
            <p>{criticRan ? '已进入质疑检查，检查结果可点击上方节点查看。'
              : routing.critic_scheduled ? interrupted ? '已满足条件，但前序阶段中断，未开始质疑。' : '已满足条件，教学初答完成后进入质疑检查。'
                : blockedReason || '本次未进入深度协商，跳过质疑，按当前路径处理。'}</p>
          </div>}
          {!routing && blockedReason && <p className="agent-triggers__notice">{blockedReason}</p>}
          <details className="agent-triggers__details">
            <summary>查看评分依据</summary>
            <p>评分综合考虑问题长度、解释与比较要求、设计与证明要求、绝对化判断，以及画像中的基础风险、知识点优先级、掌握度和遗忘风险。单个关键词不保证触发。</p>
            {routing ? <><strong>本次路由依据</strong><ul>{routing.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></>
              : <p>提问后显示本次实际评分与路由依据。</p>}
          </details>
        </article>
        <article className="agent-triggers__card">
          <header><span><Icon name="assessment" size={15} />出题 Agent</span><b>{quizBlocked ? '当前停用' : '聊天不调用'}</b></header>
          <p>在<strong>学习资源 → 练习题</strong>中发起生成，且出题 Agent 开启、处于多 Agent 模式时触发。</p>
          <p className="agent-triggers__notice">聊天里说“出一道题”仍由教学 Agent 回答；文档、思维导图和 PPT 也由教学 Agent 生成。</p>
          {quizBlocked && <p className="agent-triggers__notice">{rules?.orchestration_mode === 'single_agent' ? '当前为单 Agent 模式。' : '当前配置关闭了出题 Agent。'}练习题改由教学 Agent 生成。</p>}
          <Link className="agent-triggers__action" to="/generate?resource_type=exercise">去生成练习题 <span aria-hidden="true">↗</span></Link>
        </article>
      </div>
      {!rules && <p className="agent-triggers__notice">{loadFailed ? '当前配置暂未读取成功；提问后的路由结果会提供本轮规则。' : '正在读取当前触发配置…'}</p>}
    </section>
  )
}
