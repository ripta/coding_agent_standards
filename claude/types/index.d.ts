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

export type BatchStatus = 'not-started' | 'open' | 'merged' | 'stopped'

export type LandingStep =
  | 'detecting'
  | 'planning'
  | 'opening'
  | 'waiting'
  | 'fixing'
  | 'confirming'
  | 'finished'
  | 'stopped'

// One batch of a /land-branch run: the commits that land as one PR.
export type Batch = {
  name: string
  status: BatchStatus
  pr?: number
  after?: string[]
}

export type Landing = {
  batches: Batch[]
  // What the coordinator said about a batch, such as why it stopped, keyed by batch name.
  notes: Record<string, string>
  current?: { batch?: string; step: LandingStep }
  // A serial run's land_batch.py run file. When set, the batches are read from it.
  runFile?: string
  updatedAt: number
}

declare module 'claude-code' {
  interface PluginState {
    'coding-standards': { run: Run | null; workers: Worker[]; landing: Landing | null }
  }
}
