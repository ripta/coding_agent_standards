import type { On, RenderElement } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import type { Run } from '../types'
import { describeCall, headline, PANE, visibleChips } from '../hooks/work-queue-progress'

const PLUGIN = 'coding-standards'
const TOOL = `mcp__${PLUGIN}__work_queue_status`
const SURFACES = ['terminal', 'desktop'] as const

const SNAPSHOT = {
  phases: [
    {
      id: '59',
      title: 'Queue core',
      milestones: [
        { id: '59.1', status: 'DONE', commit: 'abc1234' },
        { id: '59.2', status: 'IN PROGRESS' },
        { id: '59.3', status: 'QUEUED' },
      ],
    },
    { id: '61', held: 'depends on 60', milestones: [{ id: '61.1', status: 'HELD' }] },
  ],
  current: { milestone: '59.2', step: 'implementing' },
}

function band(bodyColumns = 100, maxRows = 6) {
  return {
    plugin: PLUGIN,
    component: 'AbovePrompt',
    viewport: { columns: bodyColumns, rows: 40 },
    props: {
      hasSurvey: false,
      isWorking: true,
      maxRows,
      bodyColumns,
      scroll: { offset: 0, bodyRows: maxRows },
      view: {},
    },
  } as const
}

// The engine beneath the plugin: its own band, so a test sees the
// fall-through, and a clock.
function engine(on: On) {
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return h(Text, { key: 'engine-band' }, 'engine band') as RenderElement
  })
  return mock.clock(on)
}

function run(over: Partial<Run> = {}): Run {
  return { phases: [], updatedAt: 0, ...over }
}

test('headline names the step and the tallies', async () => {
  const r = run({
    phases: [
      { id: '59', milestones: [{ id: '59.1', status: 'DONE' }, { id: '59.2', status: 'IN PROGRESS' }] },
      { id: '61', held: 'waits', milestones: [{ id: '61.1', status: 'HELD' }] },
    ],
    current: { milestone: '59.2', step: 'reviewing' },
  })
  expect(headline(r)).toBe('59.2 reviewing · 1/3 done · 1 held')
  expect(headline({ ...r, current: { step: 'finished' } })).toBe('finished · 1/3 done · 1 held')
})

test('chips that do not fit keep the current milestone in view', async () => {
  const milestones = Array.from({ length: 30 }, (_, i) => ({
    id: `70.${i + 1}`,
    status: i < 20 ? ('DONE' as const) : i === 20 ? ('IN PROGRESS' as const) : ('QUEUED' as const),
  }))
  const { chips, before, after } = visibleChips(run({ phases: [{ id: '70', milestones }] }), 40)
  expect(chips.some(m => m.id === '70.21')).toBe(true)
  expect(before > 0).toBe(true)
  expect(after > 0).toBe(true)
  expect(before + chips.length + after).toBe(30)
})

test('tool calls are described briefly', async () => {
  expect(describeCall('Edit', { file_path: '/a/b/foo.go' })).toBe('Edit foo.go')
  expect(describeCall('Bash', { command: 'make test' })).toBe('Bash make test')
  expect(describeCall('Agent', {})).toBe('Agent')
})

test('no run leaves the band to the engine', async ($, on) => {
  engine(on)
  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...band(), surface })
    expect(await ui.find({ type: 'Text', text: 'engine band' })).toBeDefined()
    await ui.unmount()
  }
})

test('a snapshot draws the band', async ($, on) => {
  engine(on)
  const ran = await $.tool.call({ tool: TOOL, ...SNAPSHOT })
  expect(ran.deny).toBeUndefined()

  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...band(), surface })
    expect(await ui.find({ type: 'Text', text: 'engine band' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: '59.2 implementing · 1/4 done · 1 held' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: '✓59.1' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: '⏸61.1' })).toBeDefined()
    await ui.unmount()
  }
})

test('a bad snapshot is refused', async ($, on) => {
  engine(on)
  const ran = await $.tool.call({ tool: TOOL, phases: [{ id: '59', milestones: [{ id: '59.1', status: 'NOPE' }] }] })
  expect(typeof ran.deny === 'string' || ran.isError === true).toBe(true)
})

test('the band follows the active subagent', async ($, on) => {
  engine(on)
  on('agent.spawn', () => ({ model: 'sonnet', agentId: 'agent-1' }))
  on('tool.call', () => ({ result: 'ok' }))
  on('turn.complete', ($, e) => ({ text: e.answer }) as never)

  await $.tool.call({ tool: TOOL, ...SNAPSHOT })
  await $.agent.spawn({
    tool_use_id: 'tu-1',
    prompt: 'Implement 59.2',
    description: 'Implement 59.2',
    subagentType: 'coding-standards:implementer',
    provider: { plugin: 'coding-standards', tier: 'user' },
    parentModel: 'opus',
    background: false,
    fork: false,
  } as never)
  await $.tool.call({ tool: 'Edit', file_path: '/x/foo.go', old_string: 'a', new_string: 'b', agentId: 'agent-1' } as never)
  await $.tool.call({ tool: 'Edit', file_path: '/x/bar.go', old_string: 'a', new_string: 'b', agentId: 'agent-1' } as never)

  const ui = await $.ui.mount({ ...band(), surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: 'implementer · Implement 59.2 · 2 tools · Edit bar.go' })).toBeDefined()
  await ui.unmount()

  await $.turn.complete({ agentId: 'agent-1', answer: 'done', durationMs: 1, isAborted: false, turnId: 't', reason: 'end_turn' } as never)
  const after = await $.ui.mount({ ...band(), surface: 'terminal' })
  expect(await after.find({ type: 'Text', text: /implementer/ })).toBeUndefined()
  await after.unmount()
})

test('the pane lists phases and reasons', async ($, on) => {
  engine(on)
  await $.tool.call({ tool: TOOL, ...SNAPSHOT })
  const ui = await $.ui.mount({
    plugin: PLUGIN,
    surface: 'terminal',
    component: 'Pane',
    requestId: PANE,
    viewport: { columns: 120, rows: 40 },
    props: {
      title: 'Work queue',
      isFocused: true,
      bodyColumns: 80,
      placement: 'inline',
      scroll: { offset: 0, bodyRows: 30 },
      view: {},
    },
  })
  expect(await ui.find({ type: 'Text', text: 'Phase 59 · Queue core' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'held: depends on 60' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '✓ 59.1 abc1234' })).toBeDefined()
  await ui.unmount()
})
