export type MilestoneStatus = 'QUEUED' | 'IN PROGRESS' | 'DONE' | 'DROPPED' | 'HELD' | 'BLOCKED'

export type Step =
  | 'implementing'
  | 'reviewing'
  | 'fixing'
  | 'committing'
  | 'row-review'
  | 'final-review'
  | 'finished'

export type Milestone = {
  id: string
  title?: string
  status: MilestoneStatus
  commit?: string
}

// A queue row in the run: one contiguous range of one proposal's milestones.
export type Row = {
  id: string
  title?: string
  held?: string
  blocked?: string
  milestones: Milestone[]
}

export type Run = {
  rows: Row[]
  current?: { milestone?: string; step: Step }
  updatedAt: number
}

// A subagent the coordinator spawned while a run was going.
export type Worker = {
  agentId: string
  type: string
  description: string
  isActive: boolean
  toolCalls: number
  lastTool?: string
}

declare module 'claude-code' {
  interface PluginState {
    'coding-standards': { run: Run | null; workers: Worker[] }
  }
}
