import { atom, read } from 'claude-code'
import type { Register } from 'claude-code'

import {
  followRunFile, isLanding, isLandingStatusTool, landingBand, registerLanding, reportLanding, startLanding,
} from './land-branch-progress'
import { drawBand } from './progress-band'
import type { Band } from './progress-band'
import {
  isQueueRunning, isQueueStatusTool, onQueueToolCall, registerWorkQueue, startWorkQueue, workQueueBand,
} from './work-queue-progress'

// Each file names the atoms it reads. The engine's validator reads an atom only where it is made.
const run = atom({ plugin: 'coding-standards', key: 'run' } as const, null)
const workers = atom({ plugin: 'coding-standards', key: 'workers' } as const, [])
const landing = atom({ plugin: 'coding-standards', key: 'landing' } as const, null)

export const register: Register = (on, options) => {
  registerWorkQueue(on, options)
  registerLanding(on, options)

  on('session.start', async ($, e, next) => {
    await startWorkQueue($)
    await startLanding($)
    return next(e)
  })

  on('tool.check', ($, e, next) =>
    isQueueStatusTool(e.tool) || isLandingStatusTool(e.tool) ? { decision: 'allow' } : next(e),
  )

  on('tool.call', async ($, e, next) => {
    if (isLandingStatusTool(String(e.tool))) return reportLanding($, e)

    const result = await onQueueToolCall($, e, next)
    // The band is only a display. A failure to refresh it must never cost a tool its result.
    await followRunFile($, e).catch(() => undefined)
    return result
  })

  // One hook draws every run's band. A plugin gets one row above the prompt, so two hooks would
  // hide each other.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const r = await read($, run)
    const l = await read($, landing)
    if ((r === null && l === null) || e.props.hasSurvey) return next(e)

    // The subagent line goes to the run that is still going. The queue takes it when both are.
    const active = (await read($, workers)).filter(w => w.isActive).at(-1)
    const isQueues = r !== null && (isQueueRunning(r) || !isLanding(l))
    const bands: Band[] = []
    if (r !== null) bands.push(workQueueBand(r, isQueues ? active : undefined))
    if (l !== null) bands.push(landingBand(l, isQueues ? undefined : active))

    const ui = $.ui.resolve(e)
    const { Box } = ui
    const rows = Math.max(1, Math.floor(e.props.maxRows / bands.length))
    return (
      <Box flexDirection="column">
        {bands.map(b => drawBand(ui, b, e.props.bodyColumns, rows))}
      </Box>
    )
  })
}
