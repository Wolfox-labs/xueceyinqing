import { create } from 'zustand'

export type NodeStatus = 'completed' | 'in_progress' | 'locked' | 'pending'

interface LearningNode {
  id: string
  title: string
  type: string
  duration: string
  status: NodeStatus
  deps?: string[]
  knowledge_point?: string
  resource_type?: string
  resource_ref?: string
}

export type { LearningNode }

interface LearningPathState {
  nodes: LearningNode[]
  pathTopic: string
  setNodes: (nodes: LearningNode[]) => void
  setPathTopic: (topic: string) => void
}

export const useLearningPathStore = create<LearningPathState>((set) => ({
  nodes: [],
  pathTopic: '',
  setNodes: (nodes) => set({ nodes }),
  setPathTopic: (pathTopic) => set({ pathTopic }),
}))