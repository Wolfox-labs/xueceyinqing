import { useEffect, useState } from 'react'
import { completeAssignment, listAssignments, type Assignment } from '../api/assignments'
import { SkeletonPanel } from '../components/ui/Skeleton'

function formatDate(value?: string | null) {
  if (!value) return '未设置截止时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function TasksPage() {
  const [items, setItems] = useState<Assignment[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await listAssignments()
      setItems(data.assignments)
    } catch (err) {
      setError((err as Error).message || '任务加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleComplete = async (id: string) => {
    try {
      await completeAssignment(id)
      setItems((current) => current.map((item) => item.id === id ? { ...item, completed: true } : item))
    } catch (err) {
      setError((err as Error).message || '任务状态更新失败')
    }
  }

  const completed = items.filter((item) => item.completed).length

  return (
    <div className="student-tasks-page">
      <header className="tasks-hero">
        <div>
          <span className="core-kicker">MY LEARNING TASKS</span>
          <h1>我的任务</h1>
          <p>查看教师布置的学习任务，并标记自己的完成情况。</p>
        </div>
        <div className="tasks-progress"><strong>{completed}/{items.length}</strong><span>已完成</span></div>
      </header>

      {error && <div className="core-error">{error}</div>}
      {loading ? <SkeletonPanel lines={3} /> : items.length === 0 ? (
        <div className="teacher-empty">当前没有学习任务。</div>
      ) : (
        <div className="student-task-list">
          {items.map((item) => (
            <article key={item.id} className={item.completed ? 'is-completed' : ''}>
              <div className="student-task-index">{item.completed ? '✓' : '•'}</div>
              <div className="student-task-copy">
                <div><strong>{item.title}</strong><span>{item.completed ? '已完成' : '待完成'}</span></div>
                <p>{item.instructions || `围绕“${item.topic}”完成学习任务。`}</p>
                <small>主题：{item.topic} · 截止：{formatDate(item.due_at)}</small>
              </div>
              <button type="button" disabled={item.completed} onClick={() => void handleComplete(item.id)}>
                {item.completed ? '已完成' : '标记完成'}
              </button>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}