// Dry run of workflow.js's deterministic logic with every agent stubbed.
// Exercises layout, slugs, heading assignment, link targets, ToC, verify
// batching, and every failure path.
//
// The fixture is a synthetic backend service, sized to the largest run the
// constants in workflow.js are calibrated for: ~1,400 citations over ~320
// files, which predicts ~290 KB and forces the multi-file split.
//
// Run: node workflow.test.mjs
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const src = fs.readFileSync(path.join(here, 'workflow.js'), 'utf8').replace('export const meta', 'const meta')

// Five shards under Public Surface Area, three under Key Flows, the rest solo.
// "Webhook API v2.1 handlers" is deliberate: a dot inside a heading is the slug
// case most likely to break anchors, since it vanishes instead of separating.
const FULL_PLAN = [
  { key: 'orientation', title: 'Orientation', n: 95, mode: 'narrative' },
  { key: 'surface-rest', title: 'REST endpoints', group: 'Public Surface Area', n: 120, mode: 'reference' },
  { key: 'surface-rpc', title: 'RPC services', group: 'Public Surface Area', n: 95, mode: 'reference' },
  { key: 'surface-cli', title: 'CLI commands and flags', group: 'Public Surface Area', n: 70, mode: 'reference' },
  { key: 'surface-hook', title: 'Webhook API v2.1 handlers', group: 'Public Surface Area', n: 135, mode: 'reference' },
  { key: 'surface-ui', title: 'Frontend pages and components', group: 'Public Surface Area', n: 30, mode: 'reference' },
  { key: 'flow-read', title: 'Flow 1: an authenticated read', group: 'Key Flows', n: 95, mode: 'reference' },
  { key: 'flow-write', title: 'Flow 2: sign-in and session setup', group: 'Key Flows', n: 130, mode: 'reference' },
  { key: 'flow-boot', title: 'Flow 3: config load and startup', group: 'Key Flows', n: 115, mode: 'reference' },
  { key: 'crosscutting', title: 'Cross-cutting Concerns', n: 296, mode: 'reference' },
  { key: 'mental', title: 'Mental Model', n: 146, mode: 'narrative' },
  { key: 'onboarding', title: 'Onboarding Cheatsheet', n: 110, mode: 'narrative' },
]

// Under SHARD_SYNTHESIS_CLAIMS (150): should collapse to one writer, one file.
const SMALL_PLAN = [
  { key: 'orientation', title: 'Orientation', n: 20, mode: 'narrative' },
  { key: 'surface', title: 'Public Surface Area', n: 40, mode: 'reference' },
  { key: 'mental', title: 'Mental Model', n: 15, mode: 'narrative' },
]

async function run(plan, { failVerifyFile, failWrite } = {}) {
  const logs = []
  const writePrompts = new Map()
  let assemblerPrompt = null

  const globals = {
    args: {
      scope: '/repo',
      citationBase: '/repo',
      citationBaseLabel: 'the repository root',
      skillDir: '/skill',
      types: ['backend', 'frontend'],
      sections: plan.map(({ key, title, group, mode }) => ({ key, title, group, mode, brief: `spec for ${title}` })),
    },
    log: (m) => logs.push(m),
    phase: () => {},
    parallel: (thunks) => Promise.all(thunks.map((t) => Promise.resolve().then(t).catch(() => null))),
    agent: async (prompt, opts) => {
      const label = opts?.label || ''
      if (label.startsWith('discover:')) {
        const key = label.slice('discover:'.length)
        const n = plan.find((p) => p.key === key).n
        return {
          claims: Array.from({ length: n }, (_, i) => ({
            path: `pkg/${key}/file${i % 27}.go`,
            line: 10 + i,
            snippet: `func Handler${i}() {}`,
            claim: `${key} does thing ${i}`,
          })),
        }
      }
      if (label.startsWith('verify:')) {
        // A batch holding the poisoned file dies, in every round.
        if (failVerifyFile && prompt.includes(failVerifyFile)) return null
        const ids = [...prompt.matchAll(/"id":\s*(\d+)/g)].map((m) => Number(m[1]))
        return { verdicts: ids.map((id) => ({ id, status: 'confirmed' })) }
      }
      if (label === 'spine') {
        return {
          summary: 'The service fronts a queue-backed worker pool.',
          glossary: [{ canonical: 'work item', aliases: ['job', 'task'] }],
          sharedTopics: [
            { topic: 'the authorization check', owner: 'flow-read', alsoAppearsIn: ['surface-rpc', 'mental'] },
            { topic: 'the storage decorator chain', owner: 'crosscutting', alsoAppearsIn: ['surface-rpc'] },
          ],
        }
      }
      if (label.startsWith('write:')) {
        const key = label.slice('write:'.length).replace(/-retry$/, '')
        writePrompts.set(key, prompt)
        if (failWrite && key === failWrite) return null
        return { outline: `Summary of ${key}.`, openQuestions: [`open q from ${key}`] }
      }
      if (label === 'assemble') {
        assemblerPrompt = prompt
        return { files: [{ path: '/repo/ARCHITECTURE.md', bytes: 40000 }], scratchRemoved: true }
      }
      throw new Error(`unstubbed agent label: ${label}`)
    },
  }

  const body = `return (async () => {\n${src}\n})()`
  const result = await new Function(...Object.keys(globals), body)(...Object.values(globals))
  const outputs = assemblerPrompt
    ? JSON.parse(assemblerPrompt.slice(assemblerPrompt.indexOf('## Outputs') + '## Outputs'.length).trim())
    : null
  return { result, logs, outputs, writePrompts, assemblerPrompt }
}

// ---------------------------------------------------------------------------

let failures = 0
const check = (name, cond, detail) => {
  console.log(`${cond ? 'ok  ' : 'FAIL'}  ${name}`)
  if (!cond) {
    failures++
    if (detail) console.log(`        ${String(detail).split('\n').join('\n        ')}`)
  }
}

const total = (plan) => plan.reduce((a, p) => a + p.n, 0)

// === scenario 1: full run, everything succeeds ==============================
console.log('\n--- full run ---')
{
  const { result, logs, outputs, writePrompts } = await run(FULL_PLAN)
  for (const l of logs) console.log(`      ${l}`)

  check('every claim verified', result.citations.confirmed === total(FULL_PLAN), result.citations)
  check('nothing unchecked', result.citations.unchecked === 0)
  check('no failed parts', result.failedParts.length === 0)
  check('four output files', outputs.length === 4, outputs.map((o) => o.file).join(', '))

  const main = outputs.find((o) => o.file.endsWith('/ARCHITECTURE.md'))
  const surface = outputs.find((o) => o.file.endsWith('ARCHITECTURE-public-surface-area.md'))
  const flows = outputs.find((o) => o.file.endsWith('ARCHITECTURE-key-flows.md'))
  const cross = outputs.find((o) => o.file.endsWith('ARCHITECTURE-cross-cutting-concerns.md'))

  check('narrative sections stay in the main file', main.partFiles.length === 3)
  check('surface promoted with all five shards', surface?.partFiles.length === 5)
  check('flows promoted with all three shards', flows?.partFiles.length === 3)
  check('cross-cutting promoted', !!cross)

  check('main ToC links out to promoted files', main.preamble.includes('](ARCHITECTURE-key-flows.md#key-flows)'))
  check('main ToC links inline sections by bare anchor', main.preamble.includes('](#mental-model)'))
  check('promoted sections keep a stub in the main doc', main.preamble.includes('→ **[Read the full section](ARCHITECTURE-key-flows.md)**'))
  check('citation base note present', main.preamble.includes('All paths are relative to the repository root.'))
  check('spine summary reaches the main doc', main.preamble.includes('queue-backed worker pool'))
  check('companion file gets a back-link', flows.preamble.includes('← Back to [Architecture](ARCHITECTURE.md)'))

  // A dot inside a heading must vanish, not become a separator.
  check('version numbers in headings slug correctly', main.preamble.includes('#webhook-api-v21-handlers'))

  check(
    'parts concatenate in plan order',
    surface.partFiles.join() ===
      ['02-surface-rest', '03-surface-rpc', '04-surface-cli', '05-surface-hook', '06-surface-ui']
        .map((n) => `/repo/.architecture-parts/${n}.md`)
        .join(),
    surface.partFiles.join('\n')
  )

  check('verify batches scale with claim count', /(\d+) verifiers/.exec(logs.find((l) => l.includes('verifiers')))?.[1] === '18')

  // Heading levels: promoted-solo writes none (its title is the file's H1),
  // promoted-shard starts at H2, inline-solo owns the H2 itself.
  check('promoted solo part writes no heading', writePrompts.get('crosscutting').includes('do\n**not** write a heading'))
  check('promoted solo part sub-topics start at H2', writePrompts.get('crosscutting').includes('Use `##` for your own sub-topics'))
  check('promoted shard owns its H2', writePrompts.get('surface-rest').includes('```\n## REST endpoints\n```'))
  check('inline solo part owns its H2', writePrompts.get('orientation').includes('```\n## Orientation\n```'))

  // Ownership: the spine's assignment must reach both sides.
  check('topic owner is told it owns the topic', writePrompts.get('flow-read').includes('## Topics you own'))
  check('borrower is told to link instead', writePrompts.get('surface-rpc').includes('## Topics you must NOT explain'))
  check(
    'borrower gets a resolved link to the owner',
    writePrompts.get('surface-rpc').includes('[Flow 1: an authenticated read](ARCHITECTURE-key-flows.md#flow-1-an-authenticated-read)')
  )
  check('glossary reaches the writers', writePrompts.get('mental').includes('**work item** (not: job, task)'))
  check('writers can link to parts not yet written', writePrompts.get('orientation').includes('](ARCHITECTURE-public-surface-area.md#rest-endpoints)'))
}

// === scenario 2: small scope collapses to one writer ========================
console.log('\n--- small scope ---')
{
  const { result, logs, outputs } = await run(SMALL_PLAN)
  for (const l of logs) console.log(`      ${l}`)

  check('single writer path taken', logs.some((l) => l.includes('single writer, single file')))
  check('no assembler ran', outputs === null)
  check('wrote one file', result.files.length === 1 && result.files[0].path === '/repo/ARCHITECTURE.md')
  check('all claims still verified', result.citations.confirmed === total(SMALL_PLAN))
}

// === scenario 3: a verifier batch dies in every round =======================
console.log('\n--- poisoned verify batch ---')
{
  const { result, logs } = await run(FULL_PLAN, { failVerifyFile: 'pkg/crosscutting/file0.go' })
  for (const l of logs) console.log(`      ${l}`)

  check('retry rounds ran', logs.filter((l) => l.startsWith('retry ')).length >= 1)
  check('unchecked citations are reported, not hidden', result.citations.unchecked > 0, result.citations)
  check('unchecked is distinct from refuted', result.citations.refuted === 0)
  check('loud warning emitted', logs.some((l) => l.includes('never verified by any agent')))
  check('sample returned to caller', result.uncheckedSample.length > 0)
  check(
    'blast radius is one file, not one batch',
    result.citations.confirmed > total(FULL_PLAN) - 30,
    `lost ${total(FULL_PLAN) - result.citations.confirmed}`
  )
  check('document still written', result.wrote === true)
}

// === scenario 4: a part writer dies twice ===================================
console.log('\n--- dead part writer ---')
{
  const { result, logs, assemblerPrompt } = await run(FULL_PLAN, { failWrite: 'mental' })
  for (const l of logs) console.log(`      ${l}`)

  check('failure is isolated to the one part', result.failedParts.join() === 'mental')
  check('document still written', result.wrote === true)
  check('placeholder is prepared for the dead part', assemblerPrompt.includes('This part failed to generate'))
  check('surviving parts still contribute outlines', result.outline.includes('Orientation'))
  check('dead part contributes none', !result.outline.includes('Mental Model'))
}

// === scenario 5: sharded writers but still one file =========================
// Between SHARD_SYNTHESIS_CLAIMS and SINGLE_FILE_BYTES: parts fan out, nothing
// is promoted. This is the only shape that produces an inline multi-part group.
console.log('\n--- sharded, single file ---')
{
  const MID_PLAN = [
    { key: 'orientation', title: 'Orientation', n: 40, mode: 'narrative' },
    { key: 'surface-a', title: 'HTTP endpoints', group: 'Public Surface Area', n: 60, mode: 'reference' },
    { key: 'surface-b', title: 'CLI commands', group: 'Public Surface Area', n: 60, mode: 'reference' },
    { key: 'mental', title: 'Mental Model', n: 40, mode: 'narrative' },
  ]
  const { logs, outputs, writePrompts } = await run(MID_PLAN)
  for (const l of logs) console.log(`      ${l}`)

  check('parts fan out', logs.some((l) => l.includes('4 part writers')))
  check('nothing promoted below the size floor', outputs.length === 1, outputs.map((o) => o.file).join(', '))
  check('first inline shard carries the group heading', writePrompts.get('surface-a').includes('```\n## Public Surface Area\n\n### HTTP endpoints\n```'))
  check('later inline shard carries only its own', writePrompts.get('surface-b').includes('```\n### CLI commands\n```'))
  check('inline shards drop to H4 for sub-topics', writePrompts.get('surface-b').includes('Use `####` for your own sub-topics'))
  check('single-file ToC uses bare anchors throughout', !outputs[0].preamble.includes('.md#'))
}

console.log(`\n${failures ? `${failures} CHECK(S) FAILED` : 'all checks passed'}\n`)
process.exit(failures ? 1 : 0)
