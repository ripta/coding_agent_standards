import { atom, read, update } from 'claude-code'
import type { EngineInterface, Hook, Register } from 'claude-code'

import type { Milestone, MilestoneStatus, Row, Run, Step, Worker } from '../types'
import { isLanding } from './land-branch-progress'
import { ACCENT, fitChips } from './progress-band'
import type { Band } from './progress-band'

type CallHook = Hook<'tool.call'>

// Each file names the atoms it reads. The engine's validator reads an atom only where it is made.
const run = atom({ plugin: 'coding-standards', key: 'run' } as const, null)
const workers = atom({ plugin: 'coding-standards', key: 'workers' } as const, [])
const landing = atom({ plugin: 'coding-standards', key: 'landing' } as const, null)

export const TOOL = 'work_queue_status'
export const PANE = 'work-queue'
const LABEL = 'work-queue'
// The pane lists this many recent subagents.
const WORKER_HISTORY = 8

const STATUSES: readonly MilestoneStatus[] = ['QUEUED', 'IN PROGRESS', 'DONE', 'DROPPED', 'HELD', 'BLOCKED']
const STEPS: readonly Step[] = [
  'implementing', 'reviewing', 'fixing', 'committing', 'row-review', 'final-review', 'finished',
]

const GLYPH: Record<MilestoneStatus, string> = {
  QUEUED: '○',
  'IN PROGRESS': '●',
  DONE: '✓',
  DROPPED: '–',
  HELD: '⏸',
  BLOCKED: '✗',
}
const DIM: ReadonlySet<MilestoneStatus> = new Set(['QUEUED', 'DROPPED', 'HELD'])
const COLOR: Partial<Record<MilestoneStatus, string>> = {
  'IN PROGRESS': ACCENT,
  DONE: 'green',
  BLOCKED: 'red',
}

const INPUT_SCHEMA = {
  type: 'object',
  properties: {
    rows: {
      type: 'array',
      description: 'Every queue row in the run, in run order',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'Milestone range, e.g. "PROJ-004 M3-M5"' },
          title: { type: 'string' },
          held: { type: 'string', description: 'Why the row is held, when it is' },
          blocked: { type: 'string', description: 'Why the row is blocked, when it is' },
          milestones: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                id: { type: 'string', description: 'Milestone ID, e.g. "PROJ-004 M3"' },
                title: { type: 'string' },
                status: { type: 'string', enum: STATUSES },
                commit: { type: 'string', description: 'Short SHA once committed' },
              },
              required: ['id', 'status'],
            },
          },
        },
        required: ['id', 'milestones'],
      },
    },
    current: {
      type: 'object',
      description: 'What the coordinator is doing now',
      properties: {
        milestone: { type: 'string', description: 'Milestone being worked, e.g. "PROJ-004 M3"' },
        step: { type: 'string', enum: STEPS },
      },
      required: ['step'],
    },
  },
  required: ['rows'],
}

const DESCRIPTION = [
  'Report /work-queue run progress so the person can see it above the prompt.',
  'Send the whole queue every time. Each call replaces the previous snapshot.',
  'Call it after the plan is approved, and whenever a milestone status or the current step changes.',
  'Send step "finished" when the run is done.',
  'Only the /work-queue coordinator may call it. Calls from a subagent are denied.',
].join(' ')

export function parseRun(input: Record<string, unknown>, now: number): Run | string {
  if (!Array.isArray(input.rows)) return 'rows must be an array'
  const rows: Row[] = []
  for (const raw of input.rows as unknown[]) {
    const p = raw as Partial<Row>
    if (typeof p?.id !== 'string' || !Array.isArray(p.milestones)) {
      return 'each row needs an id and a milestones array'
    }
    const milestones: Milestone[] = []
    for (const m of p.milestones as Partial<Milestone>[]) {
      if (typeof m?.id !== 'string' || !STATUSES.includes(m.status as MilestoneStatus)) {
        return `milestone ${String(m?.id)} needs an id and a status of ${STATUSES.join(', ')}`
      }
      milestones.push({ id: m.id, title: m.title, status: m.status as MilestoneStatus, commit: m.commit })
    }
    rows.push({ id: p.id, title: p.title, held: p.held, blocked: p.blocked, milestones })
  }
  const cur = input.current as Run['current'] | undefined
  if (cur !== undefined && !STEPS.includes(cur.step)) {
    return `current.step must be one of ${STEPS.join(', ')}`
  }
  return { rows, current: cur, updatedAt: now }
}

export function milestonesOf(r: Run): Milestone[] {
  return r.rows.flatMap(p => p.milestones)
}

export function countOf(r: Run, status: MilestoneStatus): number {
  return milestonesOf(r).filter(m => m.status === status).length
}

// The headline: what runs now, then the tallies worth a glance.
export function headline(r: Run): string {
  const all = milestonesOf(r)
  const parts: string[] = []
  const step = r.current?.step
  if (step === 'finished') {
    parts.push('finished')
  } else if (step !== undefined) {
    parts.push(r.current?.milestone ? `${r.current.milestone} ${step}` : step)
  }
  // A dropped milestone is never work to do, so it counts toward neither side of the tally.
  const dropped = countOf(r, 'DROPPED')
  parts.push(`${countOf(r, 'DONE')}/${all.length - dropped} done`)
  if (dropped > 0) parts.push(`${dropped} dropped`)
  const held = r.rows.filter(p => p.held).length
  const blocked = r.rows.filter(p => p.blocked).length
  if (held > 0) parts.push(`${held} held`)
  if (blocked > 0) parts.push(`${blocked} blocked`)
  return parts.join(' · ')
}

// The chips that fit in `columns`, kept around the current milestone.
export function visibleChips(r: Run, columns: number): { chips: Milestone[]; before: number; after: number } {
  return fitChips(milestonesOf(r), focusOf(r), columns)
}

function focusOf(r: Run): number {
  const all = milestonesOf(r)
  const at = all.findIndex(m => m.status === 'IN PROGRESS')
  return at >= 0 ? at : Math.max(0, all.findIndex(m => m.status === 'QUEUED'))
}

export function isQueueRunning(r: Run | null): boolean {
  return r !== null && r.current?.step !== 'finished'
}

export function workQueueBand(r: Run, worker?: Worker): Band {
  return {
    label: LABEL,
    headline: headline(r),
    chips: milestonesOf(r).map(m => ({
      id: m.id,
      glyph: GLYPH[m.status],
      color: COLOR[m.status],
      isDim: DIM.has(m.status),
      isBold: m.status === 'IN PROGRESS',
    })),
    focus: focusOf(r),
    worker,
  }
}

// A few words on what a subagent's tool call touched.
export function describeCall(tool: string, input: Record<string, unknown>): string {
  const pick = input.file_path ?? input.path ?? input.command ?? input.pattern
  if (typeof pick !== 'string') return tool
  const brief = typeof input.command === 'string' ? pick : (pick.split('/').pop() ?? pick)
  return `${tool} ${brief.length > 40 ? `${brief.slice(0, 39)}…` : brief}`
}

// The run's only gate is plan approval, so the status tool never prompts.
export function isQueueStatusTool(tool: string): boolean {
  return tool.endsWith(`__${TOOL}`)
}

export async function startWorkQueue($: EngineInterface): Promise<void> {
  await $.tool.register({ name: TOOL, description: DESCRIPTION, inputSchema: INPUT_SCHEMA })
  await $.command.register({
    name: 'queue',
    description: 'Show the /work-queue run in a pane (/queue clear hides the band)',
  })
}

// A function declaration, since the engine's validator follows `$` across files only into one.
export async function onQueueToolCall(
  $: Parameters<CallHook>[0],
  e: Parameters<CallHook>[1],
  next: Parameters<CallHook>[2],
): Promise<Awaited<ReturnType<CallHook>>> {
  const tool = String(e.tool)
  const input = e as unknown as Record<string, unknown>

  if (isQueueStatusTool(tool)) {
    if (e.agentId !== undefined) {
      return { deny: 'Only the /work-queue coordinator reports run status.' }
    }
    const parsed = parseRun(input, await $.clock.now())
    if (typeof parsed === 'string') return { deny: `${TOOL}: ${parsed}` }
    await update($, run, () => parsed)
    const n = milestonesOf(parsed).length
    return { result: `Recorded ${n} milestones in ${parsed.rows.length} rows.` }
  }

  const agentId = e.agentId
  if (agentId !== undefined && (await read($, workers)).some(w => w.agentId === agentId)) {
    const lastTool = describeCall(tool, input)
    // A fix round reaches the same agent by SendMessage, so a finished one
    // turns active again on its next call.
    await update($, workers, list =>
      list.map(w =>
        w.agentId === agentId ? { ...w, isActive: true, toolCalls: w.toolCalls + 1, lastTool } : w,
      ),
    )
  }
  return next(e)
}

// The session-wide events are hooked once, in progress.tsx. A plugin may hook an event only once
// without a matcher.
export const registerWorkQueue: Register = on => {
  on('agent.spawn', async ($, e, next) => {
    const spawned = await next(e)
    const isRunning = isQueueRunning(await read($, run)) || isLanding(await read($, landing))
    if (spawned.agentId !== undefined && e.parentAgentId === undefined && isRunning) {
      const worker: Worker = {
        agentId: spawned.agentId,
        type: e.subagentType.replace(/^.*:/, ''),
        description: e.description,
        isActive: true,
        toolCalls: 0,
      }
      await update($, workers, list => [...list, worker].slice(-WORKER_HISTORY))
    }
    return spawned
  })

  on('turn.complete', async ($, e, next) => {
    const agentId = e.agentId
    if (agentId !== undefined && (await read($, workers)).some(w => w.agentId === agentId)) {
      await update($, workers, list =>
        list.map(w => (w.agentId === agentId ? { ...w, isActive: false } : w)),
      )
    }
    return next(e)
  })

  on('command.run', { command: 'queue' }, async ($, e) => {
    if (e.args.trim() === 'clear') {
      await update($, run, () => null)
      await update($, workers, () => [])
      await $.ui.close({ id: PANE })
      return { text: 'Cleared the work-queue progress.' }
    }
    if ((await read($, run)) === null) {
      return { text: 'No /work-queue run has reported progress in this session.' }
    }
    await $.ui.open({ id: PANE, title: 'Work queue', closeOnEscape: true })
    return { text: 'Work queue pane opened. Esc closes it.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const r = await read($, run)
    if (r === null) return <Text dimColor>No run has reported progress.</Text>
    const list = await read($, workers)

    return (
      <Box flexDirection="column">
        <Text bold>{headline(r)}</Text>
        {r.rows.map(p => (
          <Box key={`row-${p.id}`} flexDirection="column" marginTop={1}>
            <Text bold color={ACCENT} wrap="truncate-end">
              {p.id}{p.title ? ` · ${p.title}` : ''}
            </Text>
            {p.held && <Text dimColor wrap="wrap">⏸ held: {p.held}</Text>}
            {p.blocked && <Text color="red" wrap="wrap">✗ blocked: {p.blocked}</Text>}
            {p.milestones.map(m => (
              <Text
                key={`row-${m.id}`}
                color={COLOR[m.status]}
                dimColor={DIM.has(m.status)}
                wrap="truncate-end"
              >
                {GLYPH[m.status]} {m.id}{m.commit ? ` ${m.commit}` : ''}{m.title ? ` ${m.title}` : ''}
              </Text>
            ))}
          </Box>
        ))}
        {list.length > 0 && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>Subagents</Text>
            {list.map(w => (
              <Text key={`worker-${w.agentId}`} dimColor={!w.isActive} wrap="truncate-end">
                {w.isActive ? '●' : '✓'} {w.type} · {w.description} · {w.toolCalls} tools
                {w.lastTool ? ` · ${w.lastTool}` : ''}
              </Text>
            ))}
          </Box>
        )}
      </Box>
    )
  })
}
