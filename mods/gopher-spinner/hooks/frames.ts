// Pixel-art gopher, two pixels per terminal cell via the upper half block.

const PALETTE: Record<string, number | null> = {
  '.': null,
  O: 0x2a6f96, // outline
  B: 0x56b4e0, // body
  D: 0x3a8fc0, // body shade
  L: 0x9ad8f0, // belly
  S: 0xf1bf9c, // skin
  W: 0xffffff, // eye white, teeth
  K: 0x151515, // pupil
  N: 0x3a3c40, // nose
  F: 0xe8eef4, // fur collar
  G: 0xa9b9c8, // fur shade
  g: 0x6f8496, // fur outline, so the collar shows on light backgrounds
}

const BASE = [
  '...OO......OO...',
  '..OSSOOOOOOSSO..',
  '..OSBBBBBBBBSO..',
  '.OBBWWBBBBWWBBO.',
  '.OBWKKWBBWKKWBO.',
  '.OBWKKWBBWKKWBO.',
  '.OBBWWBBBBWWBBO.',
  '.OBBBBSNNSBBBBO.',
  '.OBBBBSSSSBBBBO.',
  '.OBBBBBWWBBBBBO.',
  'ggGBBBBBBBBBBGgg',
  '.gFFFGBBBBGFFFg.',
  '.OBSSgFFFFgSSBO.',
  '.ODSSLLLLLLSSDO.',
  '.ODBLLLLLLLLBDO.',
  '.ODBBLLLLLLBBDO.',
  '..OSSDDDDDDSSO..',
  '..SSS......SSS..',
]

function edit(changes: Record<number, string>): string[] {
  return BASE.map((row, i) => changes[i] ?? row)
}

const BLANK = '.'.repeat(BASE[0]?.length ?? 0)

// Two pixels of headroom above every frame, so the hop has room to rise.
function grounded(rows: readonly string[]): string[] {
  return [BLANK, BLANK, ...rows]
}

const SPRITES = {
  idle: BASE,
  blink: edit({
    3: '.OBBBBBBBBBBBBO.',
    4: '.OBBBBBBBBBBBBO.',
    5: '.OBKKKKBBKKKKBO.',
    6: '.OBBBBBBBBBBBBO.',
  }),
  lookLeft: edit({
    4: '.OBKKWWBBKKWWBO.',
    5: '.OBKKWWBBKKWWBO.',
  }),
  lookRight: edit({
    4: '.OBWWKKBBWWKKBO.',
    5: '.OBWWKKBBWWKKBO.',
  }),
}

export type FrameName = keyof typeof SPRITES | 'hop'

const FRAME_ROWS: Record<FrameName, string[]> = {
  idle: grounded(SPRITES.idle),
  blink: grounded(SPRITES.blink),
  lookLeft: grounded(SPRITES.lookLeft),
  lookRight: grounded(SPRITES.lookRight),
  // One pixel up, feet off the ground.
  hop: [BLANK, ...BASE, BLANK],
}

export const COLUMNS = BLANK.length
export const ROWS = (BASE.length + 2) / 2

const DEFAULT_COLOR = 0x01000000
const UPPER_HALF = 0x2580
const LOWER_HALF = 0x2584
const SPACE = 0x20

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

function toBase64(bytes: Uint8Array): string {
  let out = ''
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i] ?? 0
    const b = bytes[i + 1]
    const c = bytes[i + 2]
    const n = (a << 16) | ((b ?? 0) << 8) | (c ?? 0)
    out += B64[(n >> 18) & 63]
    out += B64[(n >> 12) & 63]
    out += b === undefined ? '=' : B64[(n >> 6) & 63]
    out += c === undefined ? '=' : B64[n & 63]
  }
  return out
}

function color(rows: readonly string[], y: number, x: number): number | null {
  return PALETTE[rows[y]?.[x] ?? '.'] ?? null
}

function encode(rows: readonly string[]): string {
  const bytes = new Uint8Array(COLUMNS * ROWS * 12)
  const view = new DataView(bytes.buffer)
  let offset = 0
  const put = (codePoint: number, fg: number, bg: number) => {
    view.setUint32(offset, codePoint, true)
    view.setUint32(offset + 4, fg, true)
    view.setUint32(offset + 8, bg, true)
    offset += 12
  }
  for (let y = 0; y < rows.length; y += 2) {
    for (let x = 0; x < COLUMNS; x++) {
      const top = color(rows, y, x)
      const bottom = color(rows, y + 1, x)
      if (top === null && bottom === null) {
        put(SPACE, DEFAULT_COLOR, DEFAULT_COLOR)
      } else if (top === null) {
        put(LOWER_HALF, bottom ?? DEFAULT_COLOR, DEFAULT_COLOR)
      } else {
        put(UPPER_HALF, top, bottom ?? DEFAULT_COLOR)
      }
    }
  }
  return toBase64(bytes)
}

export const FRAMES = Object.fromEntries(
  Object.entries(FRAME_ROWS).map(([name, rows]) => [name, encode(rows)]),
) as Record<FrameName, string>
