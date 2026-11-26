import { create } from 'zustand'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  isStreaming?: boolean
}

export interface Session {
  id: string
  title: string
  updated_at: string
}

interface ChatState {
  sessions: Session[]
  currentSessionId: string | null
  messages: Message[]
  isStreaming: boolean
  setSessions: (sessions: Session[]) => void
  setCurrentSession: (id: string) => void
  setMessages: (messages: Message[]) => void
  addMessage: (msg: Message) => void
  updateLastMessage: (content: string) => void
  setStreaming: (v: boolean) => void
  finishStreaming: () => void
  createSession: (session: Session) => void
}

export const useChatStore = create<ChatState>((set) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  isStreaming: false,
  setSessions: (sessions) => set({ sessions }),
  setCurrentSession: (id) => set({ currentSessionId: id, messages: [] }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  updateLastMessage: (content) =>
    set((s) => ({
      messages: s.messages.map((m, i) =>
        i === s.messages.length - 1 ? { ...m, content: m.content + content } : m
      ),
    })),
  setMessages: (messages) => set({ messages }),
  setStreaming: (v) => set({ isStreaming: v }),
  finishStreaming: () =>
    set((s) => ({
      isStreaming: false,
      messages: s.messages.map((m, i) =>
        i === s.messages.length - 1 ? { ...m, isStreaming: false } : m
      ),
    })),
  createSession: (session) =>
    set((s) => ({
      sessions: [session, ...s.sessions],
      currentSessionId: session.id,
      messages: [],
    })),
}))