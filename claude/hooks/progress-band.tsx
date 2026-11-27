import type { ElementTable, RenderElement } from 'claude-code'

import type { Worker } from '../types'

export const ACCENT = '#56b4e0'
const RULE_LEAD = '──'

// One item of a run, drawn as its glyph and its id. The glyph carries the status, so the color
// never has to.
export type Chip = {
  id: string
  glyph: string
  color?: string
  isDim?: boolean
  isBold?: boolean
}

export type Band = {
  label: string
  headline: string
  chips: Chip[]
  // The chip to keep in view when they do not all fit.
  focus: number
  worker?: Worker
}

// The items that fit in `columns`, kept around the one at `at`. Each item is its glyph, the id,
// and one column of gap.
export function fitChips<T extends { id: string }>(
  all: T[],
  at: number,
  columns: number,
): { chips: T[]; before: number; after: number } {
  const width = (c: T) => c.id.length + 2
  const total = all.reduce((n, c) => n + width(c), 0)
  if (total <= columns) return { chips: all, before: 0, after: 0 }

  const room = columns - 8 // "+N " on each side
  let lo = at
  let hi = at + 1
  let used = width(all[at] as T)
  while (true) {
    const next = hi < all.length ? width(all[hi] as T) : Infinity
    const prev = lo > 0 ? width(all[lo - 1] as T) : Infinity
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

// A band of up to three rows: the headline, the chips, and the active subagent.
export function drawBand(
  ui: Pick<ElementTable, 'Box' | 'Text'>,
  band: Band,
  columns: number,
  rows: number,
): RenderElement {
  const { Box, Text } = ui
  const { chips, before, after } = fitChips(band.chips, band.focus, columns)
  const label = ` ${band.label} `
  // The headline doubles as a rule, setting the band off from the transcript.
  const title = ` ${band.headline} `
  const fill = Math.max(0, columns - RULE_LEAD.length - label.length - RULE_LEAD.length - title.length)
  const worker = band.worker

  return (
    <Box key={`band-${band.label}`} flexDirection="column">
      <Box flexDirection="row">
        <Text dimColor>{RULE_LEAD}</Text>
        <Text bold color={ACCENT}>{label}</Text>
        <Text dimColor>{RULE_LEAD}</Text>
        <Text wrap="truncate-end">{title}</Text>
        {fill > 0 && <Text dimColor>{'─'.repeat(fill)}</Text>}
      </Box>
      {rows >= 2 && chips.length > 0 && (
        <Box flexDirection="row" gap={1}>
          {before > 0 && <Text dimColor>+{before}</Text>}
          {chips.map(c => (
            <Text key={`chip-${c.id}`} color={c.color} dimColor={c.isDim} bold={c.isBold}>
              {c.glyph}{c.id}
            </Text>
          ))}
          {after > 0 && <Text dimColor>+{after}</Text>}
        </Box>
      )}
      {rows >= 3 && worker !== undefined && (
        <Text dimColor wrap="truncate-end">
          ↳ {worker.type} · {worker.description} · {worker.toolCalls} tools
          {worker.lastTool ? ` · ${worker.lastTool}` : ''}
        </Text>
      )}
    </Box>
  ) as RenderElement
}
