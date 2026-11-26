import { ChangeEvent, DragEvent, useEffect, useRef, useState } from 'react'
import {
  deleteMaterial,
  listMaterials,
  MAX_CONTEXT_CHARS,
  MAX_MATERIAL_BYTES,
  setMaterialEnabled,
  uploadMaterial,
  type Material,
} from '../../api/materials'

const ACCEPT = '.docx,.pdf,.md,.markdown,.txt,.png,.jpg,.jpeg,.webp,.bmp,.gif,.tif,.tiff'

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// 展示材料真实状态。原先无论后端返回什么，界面一律写死"已解析"，
// 解析失败的资料也显示成已解析。
function materialStatusLabel(status: string) {
  if (status === 'ready') return '已解析'
  if (status === 'failed') return '解析失败'
  return status ? `状态：${status}` : '状态未知'
}

export default function MaterialsPanel({
  onGenerate,
  onboarding = false,
}: {
  onGenerate: (topic: string, materialIds: string[]) => void
  onboarding?: boolean
}) {
  const [materials, setMaterials] = useState<Material[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [topic, setTopic] = useState('')
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const items = await listMaterials()
      setMaterials(items)
      setSelected(new Set(items.filter((item) => item.enabled).map((item) => item.id)))
    } catch (err) {
      setError((err as Error).message || '资料加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleFiles = async (files: File[]) => {
    if (files.length === 0) return
    setError('')
    setUploading(true)
    try {
      for (const file of files) {
        const suffix = `.${file.name.split('.').pop()?.toLowerCase() || ''}`
        if (!ACCEPT.split(',').includes(suffix)) {
          throw new Error(`${file.name}：仅支持 DOCX、PDF、Markdown、TXT 和图片（PNG/JPG 等）`)
        }
        if (file.size > MAX_MATERIAL_BYTES) {
          throw new Error(`${file.name}：文件超过 20 MB 上限`)
        }
        const item = await uploadMaterial(file)
        setMaterials((current) => [item, ...current])
        setSelected((current) => new Set(current).add(item.id))
      }
    } catch (err) {
      setError((err as Error).message || '上传失败')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    void handleFiles(Array.from(event.target.files || []))
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    void handleFiles(Array.from(event.dataTransfer.files || []))
  }

  const toggleSelected = (id: string) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleEnabled = async (item: Material) => {
    try {
      const updated = await setMaterialEnabled(item.id, !item.enabled)
      setMaterials((current) => current.map((entry) => entry.id === updated.id ? updated : entry))
      if (!updated.enabled) {
        setSelected((current) => {
          const next = new Set(current)
          next.delete(updated.id)
          return next
        })
      }
    } catch (err) {
      setError((err as Error).message || '状态更新失败')
    }
  }

  const removeMaterial = async (item: Material) => {
    if (!window.confirm(`确定删除《${item.name}》吗？删除后需要重新上传。`)) return
    try {
      await deleteMaterial(item.id)
      setMaterials((current) => current.filter((entry) => entry.id !== item.id))
      setSelected((current) => {
        const next = new Set(current)
        next.delete(item.id)
        return next
      })
    } catch (err) {
      setError((err as Error).message || '删除失败')
    }
  }

  return (
    <div className="materials-panel">
      {onboarding && (
        <div className="materials-onboarding">
          <strong>先添加一份自己的资料</strong>
          <span>后续讲解、练习和学习路径会优先参考你上传的内容。</span>
        </div>
      )}

      <div
        className={`materials-dropzone ${dragging ? 'is-dragging' : ''}`}
        onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input ref={fileInputRef} type="file" accept={ACCEPT} multiple hidden onChange={handleFileInput} />
        <strong>{uploading ? '正在解析资料...' : '拖拽资料到这里，或点击选择文件'}</strong>
        <span>支持 DOCX、PDF、Markdown、TXT、图片（PNG/JPG 等），扫描版 PDF 自动识别</span>
        <div className="materials-capacity">
          <b>单个文件最大 20 MB</b>
          <b>单次生成最多引用 {MAX_CONTEXT_CHARS.toLocaleString('zh-CN')} 字正文</b>
        </div>
        <small>文件仅归当前账号所有，不会出现在公开下载目录。</small>
      </div>

      {error && <div className="materials-error">{error}</div>}

      <div className="materials-list-head">
        <div>
          <h2>已添加资料</h2>
          <p>选择真正相关的资料，生成结果会显示本次参考来源。</p>
        </div>
        <span>{materials.length} 份</span>
      </div>

      {loading ? (
        <div className="materials-empty">正在加载资料...</div>
      ) : materials.length === 0 ? (
        <div className="materials-empty">还没有资料。上传后可以勾选并生成个性化内容。</div>
      ) : (
        <div className="materials-list">
          {materials.map((item) => (
            <article className={`material-card ${selected.has(item.id) ? 'is-selected' : ''}`} key={item.id}>
              <label className="material-select">
                <input
                  type="checkbox"
                  checked={selected.has(item.id)}
                  disabled={!item.enabled}
                  onChange={() => toggleSelected(item.id)}
                />
                <span className="material-icon">{item.file_type.toUpperCase()}</span>
                <span className="material-copy">
                  <strong>{item.name}</strong>
                  <small>{formatSize(item.size_bytes)} · {formatDate(item.created_at)} · {materialStatusLabel(item.status)}</small>
                </span>
              </label>
              <div className="material-actions">
                <button type="button" onClick={() => void toggleEnabled(item)}>{item.enabled ? '停用' : '启用'}</button>
                <button type="button" className="danger" onClick={() => void removeMaterial(item)}>删除</button>
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="materials-generate-bar">
        <div>
          <span>本次已选择 {selected.size} 份资料</span>
          <small>生成内容会明确标注参考资料，不会把它们当成系统通用知识。</small>
        </div>
        <input
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          placeholder="输入本次要生成的学习主题"
        />
        <button
          type="button"
          disabled={selected.size === 0 || !topic.trim()}
          onClick={() => onGenerate(topic.trim(), Array.from(selected))}
        >
          根据选中的资料生成
        </button>
      </div>
    </div>
  )
}