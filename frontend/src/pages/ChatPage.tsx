import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useChatStore } from '../stores/chatStore'
import { createSession, getSessions, getMessages, getStreamUrl } from '../api/sessions'
import { createGetSSEStream, type AgentStatusEvent } from '../api/sse'
import MessageBubble from '../components/chat/MessageBubble'
import ChatInput from '../components/chat/ChatInput'
import SessionList from '../components/chat/SessionList'
import WelcomeScreen from '../components/chat/WelcomeScreen'
import AgentPipeline from '../components/agents/AgentPipeline'
import AgentTriggerConditions from '../components/agents/AgentTriggerConditions'
import Icon from '../components/ui/Icon'

export default function ChatPage() {
  const { t } = useTranslation()
  const {
    sessions, currentSessionId, messages, isStreaming,
    setSessions, setCurrentSession, setMessages, addMessage, updateLastMessage, setStreaming, finishStreaming, createSession: addSession,
  } = useChatStore()
  const [agentTrace, setAgentTrace] = useState<AgentStatusEvent[]>([])
  const [traceFinished, setTraceFinished] = useState(false)
  const [searchParams] = useSearchParams()
  const simulationId = searchParams.get('simulation_id') || undefined
  const [historyOpen, setHistoryOpen] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const sseRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    return () => {
      sseRef.current?.()
    }
  }, [])

  useEffect(() => {
    if (!historyOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setHistoryOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [historyOpen])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => { scrollToBottom() }, [messages])

  useEffect(() => {
    getSessions().then(setSessions).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const upsertTrace = useCallback((status: AgentStatusEvent) => {
    setAgentTrace((prev) => {
      const index = prev.findIndex((item) => item.stage === status.stage)
      if (index < 0) return [...prev, status]
      const next = [...prev]
      next[index] = status
      return next
    })
  }, [])

  const loadMessages = useCallback(async (sid: string) => {
    try {
      const msgs = await getMessages(sid)
      setMessages(msgs.map(m => ({ ...m, role: m.role as 'user' | 'assistant', timestamp: m.timestamp || new Date().toISOString(), isStreaming: false })))
    } catch {
      setMessages([])
    }
  }, [setMessages])

  const handleNewSession = async () => {
    setTraceFinished(false)
    setAgentTrace([])
    setHistoryOpen(false)
    try {
      const session = await createSession()
      addSession(session)
    } catch {
      const sid = `session-${Date.now()}`
      addSession({ id: sid, title: t('chat.newSession'), updated_at: new Date().toISOString() })
    }
  }

  const handleSelectSession = (sid: string) => {
    sseRef.current?.()
    setTraceFinished(false)
    setAgentTrace([])
    setHistoryOpen(false)
    setCurrentSession(sid)
    loadMessages(sid)
  }

  const handleSend = async (question: string) => {
    let sid = currentSessionId
    if (!sid) {
      try {
        const session = await createSession()
        addSession(session)
        sid = session.id
      } catch {
        sid = `session-${Date.now()}`
        addSession({ id: sid, title: question.slice(0, 20), updated_at: new Date().toISOString() })
      }
    }

    setHistoryOpen(false)
    setTraceFinished(false)
    setAgentTrace([])
    const userMsg = { id: `msg-${Date.now()}`, role: 'user' as const, content: question, timestamp: new Date().toISOString() }
    addMessage(userMsg)

    const aiMsg = { id: `msg-${Date.now() + 1}`, role: 'assistant' as const, content: '', timestamp: new Date().toISOString(), isStreaming: true }
    addMessage(aiMsg)
    setStreaming(true)

    const url = getStreamUrl(sid, question, simulationId)
    sseRef.current?.()
    sseRef.current = await createGetSSEStream(url, {
      onChunk: (content) => { updateLastMessage(content) },
      onStatus: upsertTrace,
      onDone: () => {
        finishStreaming()
        setTraceFinished(true)
      },
      onError: (err) => {
        setTraceFinished(false)
        setStreaming(false)
        updateLastMessage(`\n\n[${t('common.error')}: ${err.message}]`)
        finishStreaming()
      },
    })
  }

  const traceState = agentTrace[agentTrace.length - 1]?.state
  const currentTitle = sessions.find((session) => session.id === currentSessionId)?.title || t('chat.newSession')

  return (
    <section className="chat-workspace">
      <header className="chat-toolbar">
        <div className="chat-toolbar__title">
          <span className="core-kicker">CONVERSATION / MULTI-AGENT</span>
          <h2>{currentTitle}</h2>
          <p>{simulationId ? '算法实验室虚拟学习者模式' : isStreaming ? '多智能体协商进行中' : '围绕当前学习任务进行个性化问答'}</p>
        </div>
        <div className="chat-toolbar__actions">
          <button className="chat-action-button chat-action-button--primary" onClick={handleNewSession}>
            + {t('chat.newSession')}
          </button>
          <button
            className={`chat-action-button chat-history-button ${historyOpen ? 'active' : ''}`}
            onClick={() => setHistoryOpen((open) => !open)}
            aria-expanded={historyOpen}
            aria-controls="chat-session-drawer"
          >
            <Icon name="clock" size={16} />
            历史会话
          </button>
        </div>
      </header>

      <div className="chat-workspace__body">
        <div className="chat-thread">
          <div className="chat-thread__scroll">
            {agentTrace.length > 0 && (
              <section className="chat-agent-trace" aria-label="多智能体协商轨迹">
                <div className="chat-agent-trace__head">
                  <div>
                    <span className="live-dot" />
                    <strong>多智能体协商轨迹</strong>
                  </div>
                  <small>{traceState === 'error' ? '已中止' : traceState === 'running' || isStreaming ? '运行中' : '已完成'}</small>
                </div>
                <AgentPipeline events={agentTrace} />
              </section>
            )}

            {traceFinished && !isStreaming && agentTrace.length > 0 &&
              !agentTrace.some((event) => event.state === 'running') && (
              <AgentTriggerConditions events={agentTrace} />
            )}

            {messages.length === 0 ? (
              <WelcomeScreen onExampleClick={handleSend} />
            ) : (
              messages.map((msg) => (
                <MessageBubble key={msg.id} role={msg.role} content={msg.content} isStreaming={msg.isStreaming} />
              ))
            )}
            <div ref={messagesEndRef} />
          </div>
          <ChatInput onSend={handleSend} disabled={isStreaming} />
        </div>

        {historyOpen && (
          <>
            <button
              className="chat-drawer-backdrop"
              aria-label="关闭历史会话"
              onClick={() => setHistoryOpen(false)}
            />
            <aside className="chat-session-drawer" id="chat-session-drawer" aria-label="历史会话">
              <div className="chat-session-drawer__head">
                <div>
                  <span className="core-kicker">SESSION ARCHIVE</span>
                  <strong>历史会话</strong>
                </div>
                <button className="chat-drawer-close" onClick={() => setHistoryOpen(false)} aria-label="关闭历史会话">×</button>
              </div>
              <div className="chat-session-drawer__body">
                <SessionList
                  sessions={sessions}
                  currentId={currentSessionId}
                  onSelect={handleSelectSession}
                  onNew={handleNewSession}
                />
              </div>
            </aside>
          </>
        )}
      </div>
    </section>
  )
}
