import { SSEClient, type SSEEventHandler } from '../api/sse'

const MCP_BASE = import.meta.env.VITE_API_BASE || '/api'

interface ToolCallRequest {
  id: string
  tool: string
  params: Record<string, string>
}

interface ToolCallResponse {
  id: string
  result?: string
  error?: string
}

type ToolResultHandler = (response: ToolCallResponse) => void

class MCPClient {
  private sseClient: SSEClient | null = null
  private connected = false
  private listeners: Set<ToolResultHandler> = new Set()

  /** 连接 SSE，接收流式推送的工具执行结果 */
  connect() {
    if (this.connected) return
    const handlers: SSEEventHandler = {
      onChunk: (_content) => {
        // SSE 流式块暂时不处理，工具结果通过 tool_result 事件推送
      },
      onDone: (data) => {
        // 通知所有监听器
        const msg = data as { message_id?: string }
        this.listeners.forEach((fn) => {
          // eslint-disable-next-line no-empty
          try { fn({ id: msg?.message_id || '', result: '' }) } catch {}
        })
      },
      onError: (error) => {
        console.error('[MCP] SSE error:', error)
      },
    }
    this.sseClient = new SSEClient(`${MCP_BASE}/mcp/sse`, handlers)
    this.sseClient.connect()
    this.connected = true
    console.log('[MCP] SSE connected')
  }

  /** 订阅工具执行结果 */
  onResult(handler: ToolResultHandler): () => void {
    this.listeners.add(handler)
    return () => this.listeners.delete(handler)
  }

  /** 调用 MCP 工具 — POST 请求，直接返回 JSON 结果 */
  async callTool(tool: string, params: Record<string, string>): Promise<string> {
    const id = `call-${Date.now()}-${Math.random().toString(36).slice(2)}`
    const body: ToolCallRequest = { id, tool, params }

    try {
      const res = await fetch(`${MCP_BASE}/mcp/tools/call`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      const data: ToolCallResponse = await res.json()

      if (data.error) {
        throw new Error(data.error)
      }

      // 通知 SSE 监听器
      this.listeners.forEach((fn) => {
        // eslint-disable-next-line no-empty
        try { fn(data) } catch {}
      })

      return data.result || ''
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Network error'
      throw new Error(msg)
    }
  }

  /** 向 AI 教师提问 */
  async askTeacher(question: string, context = ''): Promise<string> {
    return this.callTool('ask_teacher', { question, context })
  }

  /** 生成学习资源 */
  async generateResource(
    type: 'document' | 'mindmap' | 'exercise' | 'reading' | 'video_script' | 'code_example',
    topic: string
  ): Promise<string> {
    return this.callTool('generate_resource', { type, topic })
  }

  /** 获取用户画像 */
  async getProfile(userId = 'default'): Promise<string> {
    return this.callTool('get_profile', { user_id: userId })
  }

  disconnect() {
    this.sseClient?.close()
    this.connected = false
    this.listeners.clear()
  }
}

export const mcpClient = new MCPClient()
export { MCPClient }
export type { ToolCallRequest, ToolCallResponse }