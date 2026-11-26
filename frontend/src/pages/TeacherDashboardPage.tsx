import { FormEvent, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  createAssignment,
  getTeacherOverview,
  type Assignment,
  type TeacherOverview,
} from '../api/assignments'

const RESOURCE_TYPES = [
  { value: 'document', label: '讲解文档' },
  { value: 'mindmap', label: '思维导图' },
  { value: 'exercise', label: '练习题库' },
  { value: 'ppt', label: '演示文稿' },
]

function formatDate(value?: string | null) {
  if (!value) return '未设置'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function TeacherDashboardPage() {
  const [overview, setOverview] = useState<TeacherOverview | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    title: '',
    topic: '',
    resource_type: 'document',
    instructions: '',
    due_at: '',
  })

  const load = async () => {
    setError('')
    try {
      setOverview(await getTeacherOverview())
    } catch (err) {
      setError((err as Error).message || '教师工作台加载失败')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!form.title.trim() || !form.topic.trim()) {
      setError('请填写任务名称和学习主题')
      return
    }
    setSaving(true)
    setError('')
    try {
      await createAssignment({
        title: form.title.trim(),
        topic: form.topic.trim(),
        resource_type: form.resource_type,
        instructions: form.instructions.trim(),
        due_at: form.due_at || null,
      })
      setForm({ title: '', topic: '', resource_type: 'document', instructions: '', due_at: '' })
      await load()
    } catch (err) {
      setError((err as Error).message || '任务布置失败')
    } finally {
      setSaving(false)
    }
  }

  const stats = overview?.stats
  const students = overview?.students || []
  const assignments = overview?.assignments || []

  return (
    <div className="teacher-workspace">
      <header className="teacher-hero">
        <div>
          <span className="core-kicker">TEACHER WORKSPACE</span>
          <h1>教师工作台</h1>
          <p>查看学生概况、布置学习任务，并跟踪任务完成情况。</p>
        </div>
        <div className="teacher-hero-actions">
          <Link to="/generate" className="teacher-primary-link">生成教学资源</Link>
          <Link to="/algorithm-lab" className="teacher-secondary-link">算法实验室</Link>
        </div>
      </header>

      {error && <div className="core-error">{error}</div>}

      <section className="teacher-stat-grid">
        <div><span>注册学生</span><strong>{stats?.student_count ?? 0}</strong><small>当前可查看的学生账号</small></div>
        <div><span>累计任务</span><strong>{stats?.assignment_count ?? 0}</strong><small>由当前教师账号布置</small></div>
        <div><span>完成记录</span><strong>{stats?.completed_count ?? 0}</strong><small>学生标记完成的任务数</small></div>
        <div><span>总体完成率</span><strong>{stats?.completion_rate ?? 0}%</strong><small>完成记录 / 应完成记录</small></div>
      </section>

      <div className="teacher-main-grid">
        <section className="teacher-panel">
          <div className="teacher-panel-head">
            <div><h2>布置学习任务</h2><p>任务会出现在所有学生账号的“我的任务”中。</p></div>
          </div>
          <form className="teacher-task-form" onSubmit={handleSubmit}>
            <label><span>任务名称</span><input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="例如：完成分数加减法练习" /></label>
            <label><span>学习主题</span><input value={form.topic} onChange={(event) => setForm({ ...form, topic: event.target.value })} placeholder="例如：分数加减法" /></label>
            <div className="teacher-form-row">
              <label><span>资源类型</span><select value={form.resource_type} onChange={(event) => setForm({ ...form, resource_type: event.target.value })}>{RESOURCE_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
              <label><span>截止时间</span><input type="datetime-local" value={form.due_at} onChange={(event) => setForm({ ...form, due_at: event.target.value })} /></label>
            </div>
            <label><span>任务说明</span><textarea value={form.instructions} onChange={(event) => setForm({ ...form, instructions: event.target.value })} placeholder="说明学习目标、完成要求或需要重点掌握的内容。" /></label>
            <button type="submit" disabled={saving}>{saving ? '正在布置...' : '发布给全体学生'}</button>
          </form>
        </section>

        <section className="teacher-panel">
          <div className="teacher-panel-head">
            <div><h2>学生概况</h2><p>这里只展示账号与学习状态，不展示学生私人资料。</p></div>
            <span>{students.length} 人</span>
          </div>
          {students.length === 0 ? <div className="teacher-empty">还没有学生注册。学生注册后会自动出现在这里。</div> : (
            <div className="teacher-student-list">
              {students.map((student) => (
                <div key={student.user_id}>
                  <b>{student.username.slice(0, 1).toUpperCase()}</b>
                  <span><strong>{student.username}</strong><small>注册于 {formatDate(student.created_at)}</small></span>
                  <i>学生</i>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="teacher-panel">
        <div className="teacher-panel-head">
          <div><h2>已布置任务</h2><p>跟踪每个任务的完成人数。</p></div>
          <span>{assignments.length} 项</span>
        </div>
        {assignments.length === 0 ? <div className="teacher-empty">尚未布置任务。填写上方表单即可发布第一项任务。</div> : (
          <div className="teacher-assignment-list">
            {assignments.map((item: Assignment) => (
              <div key={item.id}>
                <div><strong>{item.title}</strong><small>{item.topic} · {RESOURCE_TYPES.find((type) => type.value === item.resource_type)?.label || item.resource_type}</small></div>
                <span>截止 {formatDate(item.due_at)}</span>
                <b>{item.completion_count} 人完成</b>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}