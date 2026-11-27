import { atom, read, update } from 'claude-code'
import type { EngineInterface, Hook, Register } from 'claude-code'

import type { Batch, BatchStatus, Landing, LandingStep, Worker } from '../types'
import { ACCENT } from './progress-band'
import type { Band } from './progress-band'

type CallHook = Hook<'tool.call'>

const landing = atom({ plugin: 'coding-standards', key: 'landing' } as const, null)

export const LANDING_TOOL = 'land_branch_status'
export const LANDING_PANE = 'landing'
const LABEL = 'land-branch'
const RUN_SCRIPT = 'land_batch.py'

const STATUSES: readonly BatchStatus[] = ['not-started', 'open', 'merged', 'stopped']
const STEPS: readonly LandingStep[] = [
  'detecting', 'planning', 'opening', 'waiting', 'fixing', 'confirming', 'finished', 'stopped',
]
// The run is over at these steps, so the mod stops following its run file.
const ENDED: ReadonlySet<LandingStep> = new Set(['finished', 'stopped'])

const GLYPH: Record<BatchStatus, string> = {
  'not-started': '○',
  open: '●',
  merged: '✓',
  stopped: '✗',
}
const COLOR: Partial<Record<BatchStatus, string>> = {
  open: ACCENT,
  merged: 'green',
  stopped: 'red',
}

const INPUT_SCHEMA = {
  type: 'object',
  properties: {
    run_file: {
      type: 'string',
      description: "Absolute path of land_batch.py's run file. The batches are read from it, so leave `batches` out",
    },
    batches: {
      type: 'array',
      description: 'Every batch in the plan, in plan order. Send it only when no land_batch.py run file exists',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          status: { type: 'string', enum: STATUSES },
          pr: { type: 'number', description: 'PR number, once the PR is open' },
          after: { type: 'array', items: { type: 'string' }, description: 'Batches this one lands after' },
        },
        required: ['name', 'status'],
      },
    },
    notes: {
      type: 'object',
      description: 'A few words on a batch that needs them, such as why it stopped, keyed by batch name',
      additionalProperties: { type: 'string' },
    },
    current: {
      type: 'object',
      description: 'What the coordinator is doing now',
      properties: {
        batch: { type: 'string', description: 'The batch being worked, when the step is about one batch' },
        step: { type: 'string', enum: STEPS },
      },
      required: ['step'],
    },
  },
}

const DESCRIPTION = [
  'Report /land-branch run progress so the person can see it above the prompt.',
  'Each call replaces the previous snapshot.',
  'Pass `run_file` once land_batch.py init has written one, and the batches are read from it.',
  'They are read again after every tool call, so call this only when the step or a note changes.',
  'Before the run file exists, and in a run that stacks, pass every batch in `batches` instead.',
  'Send step "finished" when every batch merged and the run is cleaned up, and "stopped" when the run stops short.',
  'Only the /land-branch coordinator may call it. Calls from a subagent are denied.',
].join(' ')

function parseBatch(raw: unknown): Batch | string {
  const p = raw as Partial<Batch>
  if (typeof p?.name !== 'string' || !STATUSES.includes(p.status as BatchStatus)) {
    return `batch ${String(p?.name)} needs a name and a status of ${STATUSES.join(', ')}`
  }
  return {
    name: p.name,
    status: p.status as BatchStatus,
    pr: typeof p.pr === 'number' ? p.pr : undefined,
    after: Array.isArray(p.after) ? p.after.filter(a => typeof a === 'string') : undefined,
  }
}

// The batches of a land_batch.py run file, in plan order. The plan holds the order and what each
// batch lands after. The file's own `batches` object holds each one's status and PR.
export function parseRunFile(text: string): Batch[] | string {
  let file: { plan?: { batches?: unknown }; batches?: Record<string, unknown> }
  try {
    file = JSON.parse(text)
  } catch {
    return 'the run file is not JSON'
  }
  const planned = file?.plan?.batches
  if (!Array.isArray(planned) || typeof file.batches !== 'object' || file.batches === null) {
    return 'the run file has no plan or no batches'
  }

  const batches: Batch[] = []
  for (const raw of planned as { name?: unknown; after?: unknown }[]) {
    const state = file.batches[String(raw?.name)] as { status?: unknown; pr?: unknown } | undefined
    const batch = parseBatch({ name: raw?.name, after: raw?.after, status: state?.status, pr: state?.pr })
    if (typeof batch === 'string') return batch
    batches.push(batch)
  }
  return batches
}

async function readRunFile($: Pick<EngineInterface, 'fs'>, path: string): Promise<Batch[] | string> {
  try {
    return parseRunFile(await $.fs.read(path))
  } catch {
    return `cannot read the run file ${path}`
  }
}

function parseInput(input: Record<string, unknown>): Omit<Landing, 'batches' | 'updatedAt'> | string {
  const cur = input.current as Landing['current'] | undefined
  if (cur !== undefined && !STEPS.includes(cur.step)) {
    return `current.step must be one of ${STEPS.join(', ')}`
  }
  if (input.run_file !== undefined && typeof input.run_file !== 'string') return 'run_file must be a path'
  if ((input.run_file === undefined) === (input.batches === undefined)) {
    return 'pass either run_file or batches, not both and not neither'
  }

  const notes: Record<string, string> = {}
  for (const [name, note] of Object.entries((input.notes ?? {}) as Record<string, unknown>)) {
    if (typeof note === 'string') notes[name] = note
  }
  return { notes, current: cur, runFile: input.run_file as string | undefined }
}

export function isLanding(l: Landing | null): boolean {
  return l !== null && !(l.current !== undefined && ENDED.has(l.current.step))
}

export function landingHeadline(l: Landing): string {
  const count = (status: BatchStatus) => l.batches.filter(b => b.status === status).length
  const parts: string[] = []
  const cur = l.current
  if (cur !== undefined) parts.push(cur.batch && !ENDED.has(cur.step) ? `${cur.batch} ${cur.step}` : cur.step)
  if (l.batches.length > 0) parts.push(`${count('merged')}/${l.batches.length} merged`)
  if (count('open') > 0) parts.push(`${count('open')} open`)
  if (count('stopped') > 0) parts.push(`${count('stopped')} stopped`)
  return parts.join(' · ')
}

export function landingBand(l: Landing, worker?: Worker): Band {
  // Several batches can be open at once. The one the coordinator named is the one to keep in view.
  let focus = l.batches.findIndex(b => b.name === l.current?.batch)
  if (focus < 0) focus = l.batches.findIndex(b => b.status === 'open')
  if (focus < 0) focus = Math.max(0, l.batches.findIndex(b => b.status === 'not-started'))

  return {
    label: LABEL,
    headline: landingHeadline(l),
    chips: l.batches.map(b => ({
      id: b.name,
      glyph: GLYPH[b.status],
      color: COLOR[b.status],
      isDim: b.status === 'not-started',
      isBold: b.status === 'open',
    })),
    focus,
    worker,
  }
}

// The run file a land_batch.py call names with `--run`, when the call is one.
export function runFileOf(input: Record<string, unknown>): { isRunScript: boolean; runFile?: string } {
  const command = input.command
  const words = Array.isArray(command)
    ? command.map(String)
    : typeof command === 'string' ? command.split(/\s+/) : []
  if (!words.some(w => w.endsWith(RUN_SCRIPT))) return { isRunScript: false }
  const at = words.indexOf('--run')
  return { isRunScript: true, runFile: at >= 0 ? words[at + 1] : undefined }
}

// Approving the plan authorized the run, so the status tool never prompts.
export function isLandingStatusTool(tool: string): boolean {
  return tool.endsWith(`__${LANDING_TOOL}`)
}

export async function startLanding($: EngineInterface): Promise<void> {
  await $.tool.register({ name: LANDING_TOOL, description: DESCRIPTION, inputSchema: INPUT_SCHEMA })
  await $.command.register({
    name: 'landing',
    description: 'Show the /land-branch run in a pane (/landing clear hides the band)',
  })
}

// Answers a call of the status tool. These are function declarations, since the engine's validator
// follows `$` across files only into one.
export async function reportLanding(
  $: Parameters<CallHook>[0],
  e: Parameters<CallHook>[1],
): Promise<Awaited<ReturnType<CallHook>>> {
  const input = e as unknown as Record<string, unknown>
  if (e.agentId !== undefined) {
    return { deny: 'Only the /land-branch coordinator reports run status.' }
  }
  const parsed = parseInput(input)
  if (typeof parsed === 'string') return { deny: `${LANDING_TOOL}: ${parsed}` }

  let batches: Batch[] | string
  if (parsed.runFile === undefined) {
    batches = []
    for (const raw of input.batches as unknown[]) {
      const batch = parseBatch(raw)
      if (typeof batch === 'string') return { deny: `${LANDING_TOOL}: ${batch}` }
      batches.push(batch)
    }
  } else {
    batches = await readRunFile($, parsed.runFile)
    // The last report of a run comes after its run file is deleted. The batches read before
    // then still stand.
    const last = await read($, landing)
    if (typeof batches === 'string' && last?.runFile === parsed.runFile) batches = last.batches
    if (typeof batches === 'string') return { deny: `${LANDING_TOOL}: ${batches}` }
  }

  const now = await $.clock.now()
  await update($, landing, () => ({ ...parsed, batches: batches as Batch[], updatedAt: now }))
  return { result: `Recorded ${batches.length} batches.` }
}

// Runs after every other tool call, and reads the run file again while a run is going.
//
// A land_batch.py call often outlives the tool call that started it, since `open` runs the local
// checks and a long call moves to the background. So the file is read after every call, not only
// after the script's own.
//
// A land_batch.py call that names a run file this session has not seen starts following it. That
// covers a resumed run whose coordinator has not reported yet.
export async function followRunFile($: Parameters<CallHook>[0], e: Parameters<CallHook>[1]): Promise<void> {
  const { runFile } = runFileOf(e as unknown as Record<string, unknown>)
  const last = await read($, landing)
  const path = runFile ?? (isLanding(last) ? last?.runFile : undefined)
  const batches = path === undefined ? 'no run file' : await readRunFile($, path)
  if (typeof batches === 'string') return
  if (last?.runFile === path && JSON.stringify(last?.batches) === JSON.stringify(batches)) return

  const now = await $.clock.now()
  // A report made before the run file existed keeps its step and notes.
  await update($, landing, l =>
    l !== null && (l.runFile === path || (l.runFile === undefined && isLanding(l)))
      ? { ...l, batches, runFile: path, updatedAt: now }
      : { batches, notes: {}, runFile: path, updatedAt: now },
  )
}

// The session-wide events are hooked once, in progress.tsx. A plugin may hook an event only once
// without a matcher.
export const registerLanding: Register = on => {
  on('command.run', { command: 'landing' }, async ($, e) => {
    if (e.args.trim() === 'clear') {
      await update($, landing, () => null)
      await $.ui.close({ id: LANDING_PANE })
      return { text: 'Cleared the land-branch progress.' }
    }
    if ((await read($, landing)) === null) {
      return { text: 'No /land-branch run has reported progress in this session.' }
    }
    await $.ui.open({ id: LANDING_PANE, title: 'Landing', closeOnEscape: true })
    return { text: 'Landing pane opened. Esc closes it.' }
  })

  on('ui.render', { component: 'Pane', requestId: LANDING_PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const l = await read($, landing)
    if (l === null) return <Text dimColor>No run has reported progress.</Text>

    return (
      <Box flexDirection="column">
        <Text bold>{landingHeadline(l)}</Text>
        {l.batches.length === 0 && <Text dimColor>No batches planned yet.</Text>}
        {l.batches.map(b => (
          <Box key={`batch-${b.name}`} flexDirection="column" marginTop={1}>
            <Text color={COLOR[b.status]} dimColor={b.status === 'not-started'} wrap="truncate-end">
              {GLYPH[b.status]} {b.name}{b.pr !== undefined ? ` #${b.pr}` : ''} · {b.status}
            </Text>
            {b.after !== undefined && b.after.length > 0 && (
              <Text dimColor wrap="wrap">lands after: {b.after.join(', ')}</Text>
            )}
            {l.notes[b.name] !== undefined && <Text wrap="wrap">{l.notes[b.name]}</Text>}
          </Box>
        ))}
      </Box>
    )
  })
}
