import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Milestone, MilestoneStatus, Phase, Run, Step, Worker } from '../types'

const run = atom({ plugin: 'coding-standards', key: 'run' } as const, null)
const workers = atom({ plugin: 'coding-standards', key: 'workers' } as const, [])

export const TOOL = 'work_queue_status'
export const PANE = 'work-queue'
const ACCENT = '#56b4e0'
const LABEL = ' work-queue '
const RULE_LEAD = '──'
// The pane lists this many recent subagents.
const WORKER_HISTORY = 8

const STATUSES: readonly MilestoneStatus[] = ['QUEUED', 'IN PROGRESS', 'DONE', 'HELD', 'BLOCKED']
const STEPS: readonly Step[] = [
  'implementing', 'reviewing', 'fixing', 'committing', 'phase-review', 'final-review', 'finished',
]

const GLYPH: Record<MilestoneStatus, string> = {
  QUEUED: '○',
  'IN PROGRESS': '●',
  DONE: '✓',
  HELD: '⏸',
  BLOCKED: '✗',
}
const COLOR: Partial<Record<MilestoneStatus, string>> = {
  'IN PROGRESS': ACCENT,
  DONE: 'green',
  BLOCKED: 'red',
}

const INPUT_SCHEMA = {
  type: 'object',
  properties: {
    phases: {
      type: 'array',
      description: 'Every queued phase, in run order',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'Phase number, e.g. "59"' },
          title: { type: 'string' },
          held: { type: 'string', description: 'Why the phase is held, when it is' },
          blocked: { type: 'string', description: 'Why the phase is blocked, when it is' },
          milestones: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                id: { type: 'string', description: 'Phase milestone, e.g. "59.3"' },
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
        milestone: { type: 'string', description: 'Phase milestone being worked, e.g. "59.3"' },
        step: { type: 'string', enum: STEPS },
      },
      required: ['step'],
    },
  },
  required: ['phases'],
}

const DESCRIPTION = [
  'Report /work-queue run progress so the person can see it above the prompt.',
  'Send the whole queue every time. Each call replaces the previous snapshot.',
  'Call it after the plan is approved, and whenever a milestone status or the current step changes.',
  'Send step "finished" when the run is done.',
].join(' ')

export function parseRun(input: Record<string, unknown>, now: number): Run | string {
  if (!Array.isArray(input.phases)) return 'phases must be an array'
  const phases: Phase[] = []
  for (const raw of input.phases as unknown[]) {
    const p = raw as Partial<Phase>
    if (typeof p?.id !== 'string' || !Array.isArray(p.milestones)) {
      return 'each phase needs an id and a milestones array'
    }
    const milestones: Milestone[] = []
    for (const m of p.milestones as Partial<Milestone>[]) {
      if (typeof m?.id !== 'string' || !STATUSES.includes(m.status as MilestoneStatus)) {
        return `milestone ${String(m?.id)} needs an id and a status of ${STATUSES.join(', ')}`
      }
      milestones.push({ id: m.id, title: m.title, status: m.status as MilestoneStatus, commit: m.commit })
    }
    phases.push({ id: p.id, title: p.title, held: p.held, blocked: p.blocked, milestones })
  }
  const cur = input.current as Run['current'] | undefined
  if (cur !== undefined && !STEPS.includes(cur.step)) {
    return `current.step must be one of ${STEPS.join(', ')}`
  }
  return { phases, current: cur, updatedAt: now }
}

export function milestonesOf(r: Run): Milestone[] {
  return r.phases.flatMap(p => p.milestones)
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
  parts.push(`${countOf(r, 'DONE')}/${all.length} done`)
  const held = r.phases.filter(p => p.held).length
  const blocked = r.phases.filter(p => p.blocked).length
  if (held > 0) parts.push(`${held} held`)
  if (blocked > 0) parts.push(`${blocked} blocked`)
  return parts.join(' · ')
}

// The chips that fit in `columns`, kept around the current milestone. Each
// chip is its glyph, the id, and one column of gap.
export function visibleChips(r: Run, columns: number): { chips: Milestone[]; before: number; after: number } {
  const all = milestonesOf(r)
  const width = (m: Milestone) => m.id.length + 2
  const total = all.reduce((n, m) => n + width(m), 0)
  if (total <= columns) return { chips: all, before: 0, after: 0 }

  const room = columns - 8 // "+N " on each side
  let at = all.findIndex(m => m.status === 'IN PROGRESS')
  if (at < 0) at = Math.max(0, all.findIndex(m => m.status === 'QUEUED'))
  let lo = at
  let hi = at + 1
  let used = width(all[at] as Milestone)
  while (true) {
    const next = hi < all.length ? width(all[hi] as Milestone) : Infinity
    const prev = lo > 0 ? width(all[lo - 1] as Milestone) : Infinity
    if (Math.min(next, prev) + used > room) break
    if (next <= prev) {
      used += next
      hi += 1
    } else {
      used += prev
      lo -= 1
    }
  }
  return { chips: all.slice(lo, hi), before: lo, after: all.length - hi }
}

// A few words on what a subagent's tool call touched.
export function describeCall(tool: string, input: Record<string, unknown>): string {
  const pick = input.file_path ?? input.path ?? input.command ?? input.pattern
  if (typeof pick !== 'string') return tool
  const brief = typeof input.command === 'string' ? pick : (pick.split('/').pop() ?? pick)
  return `${tool} ${brief.length > 40 ? `${brief.slice(0, 39)}…` : brief}`
}

function isStatusTool(tool: string): boolean {
  return tool.endsWith(`__${TOOL}`)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({ name: TOOL, description: DESCRIPTION, inputSchema: INPUT_SCHEMA })
    await $.command.register({
      name: 'queue',
      description: 'Show the /work-queue run in a pane (/queue clear hides the band)',
    })
    return next(e)
  })

  // The run's only gate is plan approval, so the status tool never prompts.
  on('tool.check', ($, e, next) => (isStatusTool(e.tool) ? { decision: 'allow' } : next(e)))

  on('tool.call', async ($, e, next) => {
    const tool = String(e.tool)
    const input = e as unknown as Record<string, unknown>

    if (isStatusTool(tool)) {
      if (e.agentId !== undefined) {
        return { deny: 'Only the /work-queue coordinator reports run status.' }
      }
      const parsed = parseRun(input, await $.clock.now())
      if (typeof parsed === 'string') return { deny: `${TOOL}: ${parsed}` }
      await update($, run, () => parsed)
      const n = milestonesOf(parsed).length
      return { result: `Recorded ${n} milestones in ${parsed.phases.length} phases.` }
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
  })

  on('agent.spawn', async ($, e, next) => {
    const spawned = await next(e)
    const current = await read($, run)
    const isRunning = current !== null && current.current?.step !== 'finished'
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

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const r = await read($, run)
    if (r === null || e.props.hasSurvey) return next(e)

    const { Box, Text } = $.ui.resolve(e)
    const columns = e.props.bodyColumns
    const { chips, before, after } = visibleChips(r, columns)
    const active = (await read($, workers)).filter(w => w.isActive).at(-1)
    const rows = e.props.maxRows
    // The headline doubles as a rule, setting the band off from the transcript.
    const title = ` ${headline(r)} `
    const fill = Math.max(0, columns - RULE_LEAD.length - LABEL.length - RULE_LEAD.length - title.length)

    return (
      <Box flexDirection="column">
        <Box flexDirection="row">
          <Text dimColor>{RULE_LEAD}</Text>
          <Text bold color={ACCENT}>{LABEL}</Text>
          <Text dimColor>{RULE_LEAD}</Text>
          <Text wrap="truncate-end">{title}</Text>
          {fill > 0 && <Text dimColor>{'─'.repeat(fill)}</Text>}
        </Box>
        {rows >= 2 && (
          <Box flexDirection="row" gap={1}>
            {before > 0 && <Text dimColor>+{before}</Text>}
            {chips.map(m => (
              <Text
                key={`chip-${m.id}`}
                color={COLOR[m.status]}
                dimColor={m.status === 'QUEUED' || m.status === 'HELD'}
                bold={m.status === 'IN PROGRESS'}
              >
                {GLYPH[m.status]}{m.id}
              </Text>
            ))}
            {after > 0 && <Text dimColor>+{after}</Text>}
          </Box>
        )}
        {rows >= 3 && active !== undefined && (
          <Text dimColor wrap="truncate-end">
            ↳ {active.type} · {active.description} · {active.toolCalls} tools
            {active.lastTool ? ` · ${active.lastTool}` : ''}
          </Text>
        )}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const r = await read($, run)
    if (r === null) return <Text dimColor>No run has reported progress.</Text>
    const list = await read($, workers)

    return (
      <Box flexDirection="column">
        <Text bold>{headline(r)}</Text>
        {r.phases.map(p => (
          <Box key={`phase-${p.id}`} flexDirection="column" marginTop={1}>
            <Text bold color={ACCENT} wrap="truncate-end">
              Phase {p.id}{p.title ? ` · ${p.title}` : ''}
            </Text>
            {p.held && <Text dimColor wrap="wrap">⏸ held: {p.held}</Text>}
            {p.blocked && <Text color="red" wrap="wrap">✗ blocked: {p.blocked}</Text>}
            {p.milestones.map(m => (
              <Text
                key={`row-${m.id}`}
                color={COLOR[m.status]}
                dimColor={m.status === 'QUEUED' || m.status === 'HELD'}
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
