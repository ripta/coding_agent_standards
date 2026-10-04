import type { RenderElement } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import { FRAMES } from '../hooks/frames'
import { frameFor, PANE, previewFrameFor } from '../hooks/register'

const SPINNER = {
  plugin: 'gopher-spinner',
  component: 'Spinner',
  viewport: { columns: 120, rows: 40 },
} as const

// The engine's own one-line spinner, which the mod falls back to, and a clock.
function engine(on: Parameters<typeof mock.clock>[0]) {
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return h(Text, { key: 'engine-spinner' }, 'engine spinner') as RenderElement
  })
  return mock.clock(on)
}

function props(mode: 'thinking' | 'tool-use' | 'responding') {
  return { word: 'Burrowing', message: null, suffix: '…', mode }
}

test('frames follow the mode', async () => {
  expect(frameFor('tool-use', 0)).toBe('idle')
  expect(frameFor('tool-use', 1)).toBe('hop')
  expect(frameFor('thinking', 2)).toBe('lookLeft')
  expect(frameFor('thinking', 6)).toBe('lookRight')
  expect(frameFor('responding', 14)).toBe('blink')
  expect(frameFor('responding', 3)).toBe('idle')
})

test('the terminal draws the gopher beside the word', async ($, on) => {
  engine(on)
  const ui = await $.ui.mount({ ...SPINNER, surface: 'terminal', props: props('responding') })
  const gopher = await ui.find({ key: 'gopher' })
  expect(gopher?.type).toBe('Raster')
  expect(gopher?.props.cells).toBe(FRAMES.idle)
  expect(await ui.find({ type: 'Text', text: 'Burrowing…' })).toBeDefined()
  await ui.unmount()
})

test('the desktop keeps its own spinner', async ($, on) => {
  engine(on)
  const ui = await $.ui.mount({ ...SPINNER, surface: 'desktop', props: props('responding') })
  expect(await ui.find({ key: 'gopher' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: 'engine spinner' })).toBeDefined()
  await ui.unmount()
})

test('a narrow terminal keeps the one-line spinner', async ($, on) => {
  engine(on)
  const ui = await $.ui.mount({
    ...SPINNER,
    surface: 'terminal',
    viewport: { columns: 30, rows: 40 },
    props: props('responding'),
  })
  expect(await ui.find({ key: 'gopher' })).toBeUndefined()
  await ui.unmount()
})

function preview(bodyColumns: number) {
  return {
    plugin: 'gopher-spinner',
    component: 'Pane',
    requestId: PANE,
    viewport: { columns: 120, rows: 40 },
    props: {
      title: 'Gopher',
      isFocused: true,
      bodyColumns,
      placement: 'inline',
      scroll: { offset: 0, bodyRows: 26 },
      view: {},
    },
  } as const
}

test('the preview cycles every frame', async ($, on) => {
  const clock = engine(on)
  expect(previewFrameFor(0)).toBe('idle')
  expect(previewFrameFor(4)).toBe('blink')
  expect(previewFrameFor(16)).toBe('hop')
  expect(previewFrameFor(20)).toBe('idle')

  const ui = await $.ui.mount({ ...preview(120), surface: 'terminal' })
  expect((await ui.find({ key: 'preview' }))?.props.cells).toBe(FRAMES.idle)
  expect(await ui.find({ key: 'strip-hop' })).toBeDefined()
  await clock.advance(800)
  expect((await ui.find({ key: 'preview' }))?.props.cells).toBe(FRAMES.blink)
  await ui.unmount()
})

test('a narrow preview drops the strip', async ($, on) => {
  engine(on)
  const ui = await $.ui.mount({ ...preview(40), surface: 'terminal' })
  expect(await ui.find({ key: 'preview' })).toBeDefined()
  expect(await ui.find({ key: 'strip-hop' })).toBeUndefined()
  await ui.unmount()
})

test('the gopher hops while a tool runs', async ($, on) => {
  const clock = engine(on)
  const ui = await $.ui.mount({ ...SPINNER, surface: 'terminal', props: props('tool-use') })
  expect((await ui.find({ key: 'gopher' }))?.props.cells).toBe(FRAMES.idle)
  await clock.advance(200)
  expect((await ui.find({ key: 'gopher' }))?.props.cells).toBe(FRAMES.hop)
  await clock.advance(200)
  expect((await ui.find({ key: 'gopher' }))?.props.cells).toBe(FRAMES.idle)
  await ui.unmount()
})
