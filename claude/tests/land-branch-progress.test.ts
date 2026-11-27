import type { On, RenderElement } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import type { Landing } from '../types'
import { landingBand, landingHeadline, LANDING_PANE, parseRunFile, runFileOf } from '../hooks/land-branch-progress'

const PLUGIN = 'coding-standards'
const TOOL = `mcp__${PLUGIN}__land_branch_status`
const QUEUE_TOOL = `mcp__${PLUGIN}__work_queue_status`
const CG_RUN = 'mcp__cg__cg_run'
const RUN_FILE = '/state/land-branch/v3/acme-app-abc1234.json'
const SURFACES = ['terminal', 'desktop'] as const

// A land_batch.py run file, cut down to the keys the mod reads.
function runFile(statuses: Record<string, readonly [string, number | null]>): string {
  return JSON.stringify({
    version: 1,
    plan: {
      batches: [
        { name: 'docs', commits: ['a1'], after: [] },
        { name: 'parser', commits: ['b2'], after: [] },
        { name: 'cli', commits: ['c3'], after: ['parser'] },
      ],
    },
    batches: Object.fromEntries(
      Object.entries(statuses).map(([name, [status, pr]]) => [name, { status, pr, branch: null }]),
    ),
  })
}

const STARTED = { docs: ['merged', 11], parser: ['open', 12], cli: ['not-started', null] } as const
const PARSER_MERGED = { docs: ['merged', 11], parser: ['merged', 12], cli: ['open', 13] } as const

function band(bodyColumns = 100, maxRows = 6) {
  return {
    plugin: PLUGIN,
    component: 'AbovePrompt',
    viewport: { columns: bodyColumns, rows: 40 },
    props: {
      hasSurvey: false,
      isCollapsed: false,
      isWorking: true,
      maxRows,
      bodyColumns,
      scroll: { offset: 0, bodyRows: maxRows },
      view: {},
    },
  } as const
}

// The engine beneath the plugin: its own band, a clock, the run file on disk, and a cg that runs
// nothing. `disk.text` is what the next read of the run file answers, and null is a missing file.
function engine(on: On) {
  const disk: { text: string | null } = { text: null }
  on('ui.render', { plugin: PLUGIN }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return h(Text, { key: 'engine-band' }, 'engine band') as RenderElement
  })
  on('fs.read', ($, e, next) => (disk.text === null ? next(e) : { value: disk.text }))
  on('tool.call', () => ({ result: 'ok' }))
  mock.clock(on)
  return disk
}

function landing(over: Partial<Landing> = {}): Landing {
  return { batches: [], notes: {}, updatedAt: 0, ...over }
}

test('the headline names the step and counts merged, open, and stopped batches', async () => {
  const l = landing({
    batches: [
      { name: 'docs', status: 'merged' },
      { name: 'parser', status: 'open' },
      { name: 'cli', status: 'stopped' },
      { name: 'web', status: 'not-started' },
    ],
    current: { batch: 'parser', step: 'fixing' },
  })
  expect(landingHeadline(l)).toBe('parser fixing · 1/4 merged · 1 open · 1 stopped')
  expect(landingHeadline({ ...l, current: { step: 'waiting' } })).toBe('waiting · 1/4 merged · 1 open · 1 stopped')
  expect(landingHeadline(landing({ current: { step: 'detecting' } }))).toBe('detecting')
})

test('the band keeps the batch being worked in view, else the first open one', async () => {
  const batches = [
    { name: 'docs', status: 'merged' as const },
    { name: 'parser', status: 'open' as const },
    { name: 'cli', status: 'open' as const },
  ]
  expect(landingBand(landing({ batches })).focus).toBe(1)
  expect(landingBand(landing({ batches, current: { batch: 'cli', step: 'fixing' } })).focus).toBe(2)
})

test('a run file gives the batches in plan order with status, PR, and what each lands after', async () => {
  expect(parseRunFile(runFile(STARTED))).toEqual([
    { name: 'docs', status: 'merged', pr: 11, after: [] },
    { name: 'parser', status: 'open', pr: 12, after: [] },
    { name: 'cli', status: 'not-started', pr: undefined, after: ['parser'] },
  ])
  expect(typeof parseRunFile('not json')).toBe('string')
  expect(typeof parseRunFile(JSON.stringify({ snapshot: 'abc' }))).toBe('string')
  expect(typeof parseRunFile(runFile({ docs: ['merged', 11] }))).toBe('string')
})

test('a land_batch.py call is told from any other command', async () => {
  const argv = ['python3', '/plugin/scripts/land_batch.py', 'merge', '--run', RUN_FILE, '--batch', 'docs']
  expect(runFileOf({ command: argv })).toEqual({ isRunScript: true, runFile: RUN_FILE })
  expect(runFileOf({ command: argv.join(' ') })).toEqual({ isRunScript: true, runFile: RUN_FILE })
  expect(runFileOf({ command: ['python3', '/plugin/scripts/land_batch.py', 'init'] }))
    .toEqual({ isRunScript: true, runFile: undefined })
  expect(runFileOf({ command: ['python3', '/plugin/scripts/pr_watch.py', 'watch'] })).toEqual({ isRunScript: false })
  expect(runFileOf({ file_path: '/x/land_batch.py' })).toEqual({ isRunScript: false })
})

test('reported batches draw the band', async ($, on) => {
  engine(on)
  const ran = await $.tool.call({
    tool: TOOL,
    batches: [{ name: 'docs', status: 'open', pr: 11 }, { name: 'parser', status: 'not-started' }],
    current: { step: 'waiting' },
  })
  expect(ran.deny).toBeUndefined()

  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...band(), surface })
    expect(await ui.find({ type: 'Text', text: 'engine band' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: ' land-branch ' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: ' waiting · 0/2 merged · 1 open ' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: '●docs' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: '○parser' })).toBeDefined()
    await ui.unmount()
  }
})

// land_batch.py writes the run file while its call may already have returned to the background, so
// the batches must follow the file after any tool call. Cannot prove the real file is readable from
// a session, since the read is stubbed.
test('the batches follow the run file after any later tool call', async ($, on) => {
  const disk = engine(on)
  disk.text = runFile(STARTED)
  await $.tool.call({ tool: TOOL, run_file: RUN_FILE, current: { step: 'waiting' } })

  const before = await $.ui.mount({ ...band(), surface: 'terminal' })
  expect(await before.find({ type: 'Text', text: ' waiting · 1/3 merged · 1 open ' })).toBeDefined()
  await before.unmount()

  await $.tool.call({
    tool: CG_RUN,
    command: ['python3', '/plugin/scripts/land_batch.py', 'finish', '--run', RUN_FILE, '--batch', 'parser'],
  } as never)
  const unchanged = await $.ui.mount({ ...band(), surface: 'terminal' })
  expect(await unchanged.find({ type: 'Text', text: ' waiting · 1/3 merged · 1 open ' })).toBeDefined()
  await unchanged.unmount()

  disk.text = runFile(PARSER_MERGED)
  await $.tool.call({ tool: 'Edit', file_path: '/x/foo.go', old_string: 'a', new_string: 'b' } as never)
  const after = await $.ui.mount({ ...band(), surface: 'terminal' })
  expect(await after.find({ type: 'Text', text: ' waiting · 2/3 merged · 1 open ' })).toBeDefined()
  expect(await after.find({ type: 'Text', text: '✓parser' })).toBeDefined()
  await after.unmount()
})

test('a resumed run draws from its first land_batch.py call, with no report', async ($, on) => {
  const disk = engine(on)
  disk.text = runFile(STARTED)
  await $.tool.call({
    tool: CG_RUN,
    command: ['python3', '/plugin/scripts/land_batch.py', 'status', '--run', RUN_FILE],
  } as never)

  const ui = await $.ui.mount({ ...band(), surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: ' 1/3 merged · 1 open ' })).toBeDefined()
  await ui.unmount()
})

test('the planned batches and the step survive the move to a run file', async ($, on) => {
  const disk = engine(on)
  await $.tool.call({
    tool: TOOL,
    batches: [{ name: 'docs', status: 'not-started' }],
    notes: { docs: 'docs only, skips the test job' },
    current: { step: 'planning' },
  })

  disk.text = runFile(STARTED)
  await $.tool.call({
    tool: CG_RUN,
    command: ['python3', '/plugin/scripts/land_batch.py', 'open', '--run', RUN_FILE, '--batch', 'docs'],
  } as never)
  const ui = await $.ui.mount({ ...band(), surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: ' planning · 1/3 merged · 1 open ' })).toBeDefined()
  await ui.unmount()
})

test('a run that ended stops following its run file', async ($, on) => {
  const disk = engine(on)
  disk.text = runFile(STARTED)
  await $.tool.call({ tool: TOOL, run_file: RUN_FILE, current: { step: 'stopped' } })

  disk.text = runFile(PARSER_MERGED)
  await $.tool.call({ tool: 'Edit', file_path: '/x/foo.go', old_string: 'a', new_string: 'b' } as never)
  const ui = await $.ui.mount({ ...band(), surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: ' stopped · 1/3 merged · 1 open ' })).toBeDefined()
  await ui.unmount()
})

test('the last report still draws once the run file is deleted', async ($, on) => {
  const disk = engine(on)
  disk.text = runFile(PARSER_MERGED)
  await $.tool.call({ tool: TOOL, run_file: RUN_FILE, current: { step: 'confirming' } })

  disk.text = null
  const ran = await $.tool.call({ tool: TOOL, run_file: RUN_FILE, current: { step: 'finished' } })
  expect(ran.deny).toBeUndefined()
  const ui = await $.ui.mount({ ...band(), surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: ' finished · 2/3 merged · 1 open ' })).toBeDefined()
  await ui.unmount()
})

test('a bad report is refused', async ($, on) => {
  engine(on)
  const refused = async (input: Record<string, unknown>) => {
    const ran = await $.tool.call({ tool: TOOL, ...input } as never)
    return typeof ran.deny === 'string' || ran.isError === true
  }
  expect(await refused({ batches: [{ name: 'docs', status: 'NOPE' }] })).toBe(true)
  expect(await refused({ batches: [], current: { step: 'napping' } })).toBe(true)
  expect(await refused({ current: { step: 'waiting' } })).toBe(true)
  expect(await refused({ run_file: RUN_FILE, batches: [] })).toBe(true)
  expect(await refused({ run_file: '/state/missing.json' })).toBe(true)
  expect(await refused({ batches: [], agentId: 'agent-1' })).toBe(true)
})

test('a work-queue run and a landing each draw a band', async ($, on) => {
  engine(on)
  await $.tool.call({
    tool: QUEUE_TOOL,
    rows: [{ id: 'PX-4 M1', milestones: [{ id: 'PX-4 M1', status: 'IN PROGRESS' }] }],
    current: { milestone: 'PX-4 M1', step: 'implementing' },
  })
  await $.tool.call({ tool: TOOL, batches: [{ name: 'docs', status: 'open' }], current: { step: 'waiting' } })

  const ui = await $.ui.mount({ ...band(), surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: ' work-queue ' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: ' land-branch ' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '●PX-4 M1' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '●docs' })).toBeDefined()
  await ui.unmount()
})

test('the pane lists each batch with its PR, its order, and its note', async ($, on) => {
  const disk = engine(on)
  disk.text = runFile({ docs: ['merged', 11], parser: ['stopped', 12], cli: ['not-started', null] })
  await $.tool.call({
    tool: TOOL,
    run_file: RUN_FILE,
    notes: { parser: 'PR closed without merging' },
    current: { step: 'stopped' },
  })

  const ui = await $.ui.mount({
    plugin: PLUGIN,
    surface: 'terminal',
    component: 'Pane',
    requestId: LANDING_PANE,
    viewport: { columns: 120, rows: 40 },
    props: {
      title: 'Landing',
      isFocused: true,
      bodyColumns: 80,
      placement: 'inline',
      scroll: { offset: 0, bodyRows: 30 },
      view: {},
    },
  })
  expect(await ui.find({ type: 'Text', text: 'stopped · 1/3 merged · 1 stopped' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '✓ docs #11 · merged' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '✗ parser #12 · stopped' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'PR closed without merging' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'lands after: parser' })).toBeDefined()
  await ui.unmount()
})
