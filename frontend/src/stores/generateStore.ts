import { create } from 'zustand'

interface GenerateState {
  type: string
  topic: string
  pptTheme: string
  content: string
  isStreaming: boolean
  error: string | null
  result: string | null
  filepath: string | null
  showStreaming: boolean
  setType: (t: string) => void
  setTopic: (t: string) => void
  setPptTheme: (t: string) => void
  appendContent: (text: string) => void
  setStreaming: (v: boolean) => void
  setError: (e: string | null) => void
  setResult: (content: string, filepath?: string) => void
  setShowStreaming: (v: boolean) => void
  reset: () => void
}

export const useGenerateStore = create<GenerateState>((set) => ({
  type: 'document',
  topic: '',
  pptTheme: 'dark_tech',
  content: '',
  isStreaming: false,
  error: null,
  result: null,
  filepath: null,
  showStreaming: false,
  setType: (type) => set({ type }),
  setTopic: (topic) => set({ topic }),
  setPptTheme: (pptTheme) => set({ pptTheme }),
  appendContent: (text) => set((s) => ({ content: s.content + text })),
  setStreaming: (v) => set({ isStreaming: v }),
  setError: (e) => set({ error: e }),
  setResult: (content, filepath) => set({ result: content, filepath: filepath || null }),
  setShowStreaming: (v) => set({ showStreaming: v }),
  reset: () => set({ content: '', isStreaming: false, error: null, result: null, filepath: null, showStreaming: false }),
}))
