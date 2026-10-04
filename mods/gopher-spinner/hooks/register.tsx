import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import { COLUMNS, FRAMES, ROWS } from './frames'
import type { FrameName } from './frames'

const tick = atom({ plugin: 'gopher-spinner', key: 'tick' } as const, 0)

const TICK_MS = 200
// The timer stops itself once the spinner has not drawn for this long.
const STALE_MS = 1000
// Below this width the engine's own one-line spinner is drawn.
const MIN_COLUMNS = COLUMNS + 24

const THINKING: readonly FrameName[] = [
  'idle', 'idle', 'lookLeft', 'lookLeft', 'idle', 'idle', 'lookRight', 'lookRight',
]
const BLINK_EVERY = 15

export const PANE = 'gopher-preview'
const PREVIEW: readonly FrameName[] = ['idle', 'blink', 'lookLeft', 'lookRight', 'hop']
const TICKS_PER_PREVIEW_FRAME = 4

type Mode = 'requesting' | 'responding' | 'thinking' | 'tool-input' | 'tool-use'

export function frameFor(mode: Mode, n: number): FrameName {
  if (mode === 'tool-use' || mode === 'tool-input') {
    return n % 2 === 0 ? 'idle' : 'hop'
  }
  if (mode === 'thinking') {
    return THINKING[n % THINKING.length] ?? 'idle'
  }
  return n % BLINK_EVERY === BLINK_EVERY - 1 ? 'blink' : 'idle'
}

export function previewFrameFor(n: number): FrameName {
  return PREVIEW[Math.floor(n / TICKS_PER_PREVIEW_FRAME) % PREVIEW.length] ?? 'idle'
}

let timer: Timer | undefined
let lastDrawnAt = 0

function ensureTicking($: EngineInterface) {
  if (timer) return
  timer = $.clock.every(TICK_MS, async () => {
    if ((await $.clock.now()) - lastDrawnAt > STALE_MS) {
      timer?.cancel()
      timer = undefined
      return
    }
    await update($, tick, n => (n ?? 0) + 1)
  })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'gopher',
      description: 'Preview the gopher spinner frames in a pane',
    })
    return next(e)
  })

  on('command.run', { command: 'gopher' }, async $ => {
    await $.ui.open({
      id: PANE,
      title: 'Gopher',
      focus: true,
      closeOnEscape: true,
      // Inline above the prompt, one gopher tall. Docked beside a fullscreen
      // transcript the pane is full height, so keep it one gopher wide.
      rows: ROWS + 3,
      columns: COLUMNS + 4,
    })
    return { text: 'Gopher preview opened. Esc closes it.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    lastDrawnAt = await $.clock.now()
    ensureTicking($)

    if (e.surface !== 'terminal') {
      const { Text } = $.ui.resolve(e)
      return <Text dimColor>The gopher draws in the terminal only.</Text>
    }

    const n = await read($, tick)
    const frame = previewFrameFor(n)
    const { Box, Text, Raster } = $.ui.resolve(e)
    // The animated gopher plus each still, side by side, two columns apart.
    const hasRoomForStrip = e.props.bodyColumns >= (PREVIEW.length + 1) * (COLUMNS + 2)

    return (
      <Box flexDirection="row" gap={2}>
        <Box flexDirection="column" alignItems="center">
          <Raster key="preview" columns={COLUMNS} rows={ROWS} cells={FRAMES[frame]} />
          <Text color="#56b4e0">{frame}</Text>
        </Box>
        {hasRoomForStrip &&
          PREVIEW.map(name => (
            <Box flexDirection="column" alignItems="center">
              <Raster key={`strip-${name}`} columns={COLUMNS} rows={ROWS} cells={FRAMES[name]} />
              <Text dimColor={name !== frame}>{name}</Text>
            </Box>
          ))}
      </Box>
    )
  })

  on('turn.start', async ($, e, next) => {
    lastDrawnAt = await $.clock.now()
    ensureTicking($)
    return next(e)
  })

  on('ui.render', { component: 'Spinner' }, async ($, e, next) => {
    if (e.surface !== 'terminal') return next(e)
    if (e.viewport && e.viewport.columns < MIN_COLUMNS) return next(e)

    lastDrawnAt = await $.clock.now()
    ensureTicking($)

    const n = await read($, tick)
    const frame = frameFor(e.props.mode, n)
    const label = `${e.props.message ?? e.props.word}${e.props.suffix}`
    const { Box, Text, Raster } = $.ui.resolve(e)

    return (
      <Box flexDirection="row" alignItems="center" gap={1}>
        <Raster key="gopher" columns={COLUMNS} rows={ROWS} cells={FRAMES[frame]} />
        <Text color="#56b4e0">{label}</Text>
      </Box>
    )
  })
}
