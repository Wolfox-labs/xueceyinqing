import { useEffect, useState } from 'react'
import {
  getAgentRuntimeConfig,
  resetAgentRuntimeConfig,
  updateAgentRuntimeConfig,
  type AgentRuntimeConfig,
} from '../../api/experiments'
import { useAuthStore } from '../../stores/authStore'

type Preset = 'full' | 'no_critic' | 'no_reviewer' | 'no_profile' | 'single_agent'

const PRESETS: Record<Preset, { label: string; description: string; values: Partial<AgentRuntimeConfig> }> = {
  full: {
    label: '完整系统',
    description: '保留画像、质疑、审核与出题 Agent。',
    values: { profile_enabled: true, critic_enabled: true, reviewer_enabled: true, quiz_agent_enabled: true, orchestration_mode: 'multi_agent' },
  },
  no_critic: {
    label: '无质疑 Agent',
    description: '保留审核，但不进行反例与漏洞检查。',
    values: { profile_enabled: true, critic_enabled: false, reviewer_enabled: true, quiz_agent_enabled: true, orchestration_mode: 'multi_agent' },
  },
  no_reviewer: {
    label: '无审核 Agent',
    description: '跳过质量审核，用于观察风险与成本变化。',
    values: { profile_enabled: true, critic_enabled: true, reviewer_enabled: false, quiz_agent_enabled: true, orchestration_mode: 'multi_agent' },
  },
  no_profile: {
    label: '无画像上下文',
    description: '不改画像数据，但生成时不注入画像上下文。',
    values: { profile_enabled: false, critic_enabled: true, reviewer_enabled: true, quiz_agent_enabled: true, orchestration_mode: 'multi_agent' },
  },
  single_agent: {
    label: '单 Agent',
    description: '仅保留教学 Agent，跳过质疑、审核与专用出题 Agent。',
    values: { profile_enabled: true, critic_enabled: false, reviewer_enabled: false, quiz_agent_enabled: false, orchestration_mode: 'single_agent' },
  },
}

function SwitchRow({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  label: string
  description: string
  checked: boolean
  disabled: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="agent-switch-row">
      <span>
        <strong>{label}</strong>
        <small>{description}</small>
      </span>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <i />
    </label>
  )
}

export default function AgentExperimentPanel() {
  const isTeacher = useAuthStore((state) => state.session?.role === 'teacher')
  const [config, setConfig] = useState<AgentRuntimeConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [loadFailed, setLoadFailed] = useState(false)

  useEffect(() => {
    // 该接口仅教师可访问（学生请求返回 403）。原实现只在 catch 里设 message、
    // 却把 config 留在 null，于是学生看到一个永远不会消失的"正在加载…"。
    getAgentRuntimeConfig()
      .then((cfg) => { setConfig(cfg); setLoadFailed(false) })
      .catch(() => { setLoadFailed(true) })
  }, [])

  const update = (values: Partial<AgentRuntimeConfig>) => {
    setConfig((current) => current ? { ...current, ...values } : current)
    setMessage('')
  }

  const applyPreset = (preset: Preset) => {
    if (!isTeacher) return
    update(PRESETS[preset].values)
  }

  const save = async () => {
    if (!config || !isTeacher) return
    setSaving(true)
    setMessage('')
    try {
      const saved = await updateAgentRuntimeConfig(config)
      setConfig(saved)
      setMessage('实验配置已保存，下一次模型调用生效。')
    } catch (err) {
      setMessage((err as Error).message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const reset = async () => {
    if (!isTeacher) return
    setSaving(true)
    setMessage('')
    try {
      const saved = await resetAgentRuntimeConfig()
      setConfig(saved)
      setMessage('已恢复完整多智能体配置。')
    } catch (err) {
      setMessage((err as Error).message || '重置失败')
    } finally {
      setSaving(false)
    }
  }

  if (!config) {
    return (
      <section className="panel agent-experiment-panel">
        <div className="panel-head compact">
          <div>
            <span className="panel-index">EXPERIMENT</span>
            <div><h2>多智能体消融实验</h2><p>切换 Agent 组件和协商阈值，为后续批量实验准备运行配置。</p></div>
          </div>
        </div>
        <div className="teacher-empty">
          {loadFailed
            ? '当前账号无权查看 Agent 实验配置（仅教师可访问）。'
            : '正在加载 Agent 实验配置...'}
        </div>
      </section>
    )
  }

  const multiMode = config.orchestration_mode === 'multi_agent'
  const criticEffective = multiMode && config.critic_enabled && config.reviewer_enabled
  const reviewerEffective = multiMode && config.reviewer_enabled

  return (
    <section className="panel agent-experiment-panel">
      <div className="panel-head compact">
        <div>
          <span className="panel-index">EXPERIMENT</span>
          <div><h2>多智能体消融实验</h2><p>切换 Agent 组件和协商阈值，为后续批量实验准备运行配置。</p></div>
        </div>
        <span className="core-tag">{isTeacher ? '教师可配置' : '只读配置'}</span>
      </div>

      <div className="agent-preset-grid">
        {(Object.entries(PRESETS) as [Preset, typeof PRESETS[Preset]][]).map(([key, preset]) => (
          <button key={key} type="button" disabled={!isTeacher} onClick={() => applyPreset(key)}>
            <strong>{preset.label}</strong>
            <span>{preset.description}</span>
          </button>
        ))}
      </div>

      <div className="agent-experiment-grid">
        <div className="agent-switch-list">
          <SwitchRow label="画像 Agent" description="控制是否读取并更新学习者画像。" checked={config.profile_enabled} disabled={!isTeacher} onChange={(value) => update({ profile_enabled: value })} />
          <SwitchRow label="质疑 Agent" description="寻找漏洞、反例、前置知识缺口；仅在深度协商时执行。" checked={config.critic_enabled} disabled={!isTeacher} onChange={(value) => update({ critic_enabled: value })} />
          <SwitchRow label="审核 Agent" description="检查事实、安全、难度匹配和输出格式。" checked={config.reviewer_enabled} disabled={!isTeacher} onChange={(value) => update({ reviewer_enabled: value })} />
          <SwitchRow label="出题 Agent" description="资源类型为练习时，由专用出题 Agent 生成题目。" checked={config.quiz_agent_enabled} disabled={!isTeacher} onChange={(value) => update({ quiz_agent_enabled: value })} />
        </div>

        <div className="agent-parameter-panel">
          <label>
            <span>编排模式</span>
            <select value={config.orchestration_mode} disabled={!isTeacher} onChange={(event) => update({ orchestration_mode: event.target.value as AgentRuntimeConfig['orchestration_mode'] })}>
              <option value="multi_agent">多智能体</option>
              <option value="single_agent">单 Agent</option>
            </select>
          </label>
          <label>
            <span>标准审核阈值</span>
            <input type="number" min="0" max="1" step="0.01" value={config.standard_threshold} disabled={!isTeacher} onChange={(event) => update({ standard_threshold: Number(event.target.value) })} />
          </label>
          <label>
            <span>深度协商阈值</span>
            <input type="number" min="0" max="1" step="0.01" value={config.deliberate_threshold} disabled={!isTeacher} onChange={(event) => update({ deliberate_threshold: Number(event.target.value) })} />
          </label>
          <label>
            <span>最大协商轮次</span>
            <input type="number" min="0" max="5" step="1" value={config.max_rounds} disabled={!isTeacher} onChange={(event) => update({ max_rounds: Number(event.target.value) })} />
          </label>
          <div className="agent-effective-status">
            <span>质疑：{criticEffective ? '生效' : '跳过'}</span>
            <span>审核：{reviewerEffective ? '生效' : '跳过'}</span>
            <span>模式：{multiMode ? '多智能体' : '单 Agent'}</span>
          </div>
        </div>
      </div>

      {message && <div className="agent-config-message">{message}</div>}
      {isTeacher && (
        <div className="agent-config-actions">
          <button type="button" onClick={() => void save()} disabled={saving}>{saving ? '保存中...' : '保存实验配置'}</button>
          <button type="button" className="ghost" onClick={() => void reset()} disabled={saving}>恢复完整系统</button>
        </div>
      )}
    </section>
  )
}