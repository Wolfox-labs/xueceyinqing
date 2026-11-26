import { getAccessToken } from './client'
import type { AgentTriggerRules } from './agent-triggers'

export interface AgentStatusEvent {
  stage: string
  label: string
  detail?: string
  state?: string
  mode?: string
  summary?: string[]
  handoff?: string
  elapsed_ms?: number
  routing?: {
    score: number
    reasons: string[]
    critic_scheduled: boolean
    max_rounds: number
  }
  trigger_rules?: AgentTriggerRules
}

/** 内容被审核拦截时的事件负载。 */
export interface WithdrawnEvent {
  /** 简要原因，直接展示给用户。 */
  reason: string
  /** 审核判词：pass / fail / unknown。 */
  verdict?: string
  /** 审核 Agent 的完整意见（可能为空）。 */
  review?: string
  agent_trace?: string[]
}

type SSEEventHandler = {
  onChunk?: (content: string) => void
  onStatus?: (status: AgentStatusEvent) => void
  onDone?: (data: unknown) => void
  onError?: (error: Error) => void
}

class SSEClient {
  private stopStream: (() => void) | null = null
  private closed = false
  private retryCount = 0
  private maxRetries = 5
  private retryTimer: ReturnType<typeof setTimeout> | null = null

  constructor(private url: string, private handlers: SSEEventHandler) {}

  async connect() {
    this.closed = false
    await this.start()
  }

  private async start() {
    this.stopStream = await createGetSSEStream(this.url, {
      onChunk: this.handlers.onChunk,
      onStatus: this.handlers.onStatus,
      onDone: () => {
        this.handlers.onDone?.(undefined)
        this.close()
      },
      onError: (error) => {
        this.handlers.onError?.(error)
        this.stopStream?.()
        this.stopStream = null
        this.retry()
      },
    })
  }

  private retry() {
    if (this.closed || this.retryCount >= this.maxRetries) return
    const delay = Math.min(1000 * Math.pow(2, this.retryCount), 16000)
    this.retryCount++
    this.retryTimer = setTimeout(() => {
      if (!this.closed) void this.start()
    }, delay)
  }

  close() {
    this.closed = true
    this.stopStream?.()
    this.stopStream = null
    if (this.retryTimer) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
  }
}

interface PostSSECallbacks {
  onChunk?: (content: string) => void
  onStatus?: (status: AgentStatusEvent) => void
  onResult?: (data: Record<string, unknown>) => void
  onWithdrawn?: (data: WithdrawnEvent) => void
  onDone?: () => void
  onError?: (error: Error) => void
}

export async function createPostSSEStream(
  url: string,
  body: Record<string, unknown>,
  callbacks: PostSSECallbacks
): Promise<() => void> {
  const controller = new AbortController()

  try {
    const token = getAccessToken()
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    async function readStream() {
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          let currentEvent = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))

                if (currentEvent) {
                  if (currentEvent === 'chunk') {
                    callbacks.onChunk?.(data.content || '')
                  } else if (currentEvent === 'status') {
                    callbacks.onStatus?.(data as AgentStatusEvent)
                  } else if (currentEvent === 'result') {
                    callbacks.onResult?.(data)
                  } else if (currentEvent === 'withdrawn') {
                    callbacks.onWithdrawn?.(data as WithdrawnEvent)
                  } else if (currentEvent === 'done') {
                    callbacks.onDone?.()
                    return
                  }
                } else {
                  if (data.done) {
                    callbacks.onDone?.()
                    return
                  }
                  if (data.error) {
                    callbacks.onError?.(new Error(data.error))
                    return
                  }
                  if (data.stage) {
                    callbacks.onStatus?.(data as AgentStatusEvent)
                  } else if (data.title && data.nodes) {
                    callbacks.onResult?.(data)
                    return
                  } else if (data.content !== undefined) {
                    callbacks.onChunk?.(data.content)
                  }
                }
              } catch {
                /* ignore parse errors */
              }
              currentEvent = ''
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          callbacks.onError?.(err as Error)
        }
      }
    }

    readStream()
  } catch (err) {
    if ((err as Error).name !== 'AbortError') {
      callbacks.onError?.(err as Error)
    }
  }

  return () => controller.abort()
}

export async function createGetSSEStream(
  url: string,
  callbacks: PostSSECallbacks
): Promise<() => void> {
  const controller = new AbortController()
  const token = getAccessToken()

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    const readStream = async () => {
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          let currentEvent = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                if (currentEvent === 'chunk') callbacks.onChunk?.(data.content || '')
                else if (currentEvent === 'status') callbacks.onStatus?.(data as AgentStatusEvent)
                else if (currentEvent === 'result') callbacks.onResult?.(data)
                else if (currentEvent === 'withdrawn') callbacks.onWithdrawn?.(data as WithdrawnEvent)
                else if (currentEvent === 'done' || data.done) {
                  callbacks.onDone?.()
                  return
                }
              } catch {
                /* ignore parse errors */
              }
              currentEvent = ''
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') callbacks.onError?.(err as Error)
      }
    }
    void readStream()
  } catch (err) {
    if ((err as Error).name !== 'AbortError') callbacks.onError?.(err as Error)
  }
  return () => controller.abort()
}

export { SSEClient }
export type { SSEEventHandler }
