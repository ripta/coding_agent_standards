export const meta = {
  name: 'architecture-exploration',
  description: 'Fan out per-section discovery, verify every citation, then write ARCHITECTURE.md',
  whenToUse: 'Escalation path for the architecture-exploration skill, on repos large enough that spot-checking citations is not evidence. The caller resolves scope, classifies the project, and plans the fan-out first, then passes that plan in as args.',
  phases: [
    { title: 'Discover', detail: 'one read-only Explore agent per section' },
    { title: 'Verify', detail: 'confirm every file:line citation, batched by file' },
    { title: 'Synthesize', detail: 'assemble verified claims into ARCHITECTURE.md' },
  ],
}

// ---------------------------------------------------------------------------
// Input. Steps 1-4 of SKILL.md happen in the caller's context, not here:
// scope resolution and project classification need git and the filesystem,
// which workflow scripts cannot touch, and Step 4 reports to the user, which a
// workflow cannot do mid-run. The caller hands the finished plan over.
// ---------------------------------------------------------------------------

const {
  scope, // absolute path to the explored root
  citationBase, // ABSOLUTE path to the dir ARCHITECTURE.md lands in; agents resolve against this
  citationBaseLabel, // the same dir relative to the repo root, for the header note (Step 6 §1)
  skillDir, // dir holding SKILL.md, read by the synthesis agent for the spec
  types, // e.g. ['backend'] or ['frontend', 'backend']
  sections, // fan-out plan from Step 3: [{ key, title, brief }]
} = args || {}

if (!scope || !citationBase || !citationBaseLabel || !skillDir || !types?.length || !sections?.length) {
  throw new Error(
    'args must supply scope, citationBase, citationBaseLabel, skillDir, types[], sections[{key,title,brief}]'
  )
}

if (!citationBase.startsWith('/')) {
  throw new Error(`citationBase must be absolute so agents can resolve against it, got: ${citationBase}`)
}

const archPath = `${citationBase}/ARCHITECTURE.md`

// Cap on concurrent verifier agents. Files beyond this are not dropped; the
// batches just get bigger. See the round-robin distribution below.
const MAX_VERIFY_BATCHES = 8

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

const CLAIMS_SCHEMA = {
  type: 'object',
  required: ['claims'],
  properties: {
    claims: {
      type: 'array',
      description: 'One entry per evidence-backed claim. Prose without a citation does not belong here.',
      items: {
        type: 'object',
        required: ['path', 'line', 'snippet', 'claim'],
        properties: {
          path: { type: 'string', description: `Relative to ${citationBase}. Never absolute, never / or ~ prefixed.` },
          line: { type: 'integer', description: '1-based line the snippet starts at' },
          snippet: { type: 'string', description: 'Verbatim source, a few lines. Not a paraphrase.' },
          claim: { type: 'string', description: 'What this snippet proves, one sentence' },
          isGuess: { type: 'boolean', description: 'True when inferring rather than reading it directly' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'status'],
        properties: {
          id: { type: 'integer', description: 'Echo the claim id you were given' },
          status: {
            type: 'string',
            enum: ['confirmed', 'moved', 'missing'],
            description: 'confirmed: snippet is at that line. moved: present elsewhere in the file. missing: not in the file.',
          },
          correctedLine: { type: 'integer', description: 'Required when status is moved' },
          note: { type: 'string' },
        },
      },
    },
  },
}

const SUMMARY_SCHEMA = {
  type: 'object',
  required: ['outline', 'openQuestions'],
  properties: {
    outline: { type: 'string', description: 'Short prose summary of what the document now contains' },
    openQuestions: {
      type: 'array',
      items: { type: 'string' },
      description: 'What could not be resolved from the code alone',
    },
  },
}

// ---------------------------------------------------------------------------
// Phase 1: Discover. Shared brief is lifted from SKILL.md Step 5 verbatim.
// ---------------------------------------------------------------------------

const SHARED_BRIEF = `You are gathering material for one section of an ARCHITECTURE.md. This is a
strictly read-only task — do not modify any files. Confine your exploration to
the scope \`${scope}\`. The project is classified as \`${types.join(', ')}\`.

Your deliverable IS the evidence, not prose. For every claim, return the exact
file:line plus a **verbatim** code snippet (a few lines) proving it — these
become citations the caller cannot re-derive, so paraphrase is useless. Express
every path **relative to \`${citationBase}\`**; never return an absolute path or
one starting with \`/\` or \`~\`. Prefer reading code over README/docs when they
disagree. If something is ambiguous or you are inferring, say so explicitly and
mark it as a guess. Be thorough within your section and ignore everything
outside it.`

phase('Discover')
log(`${sections.length} sections over ${citationBase} (${types.join(', ')})`)

const discovered = (
  await parallel(
    sections.map((s) => () =>
      agent(`${SHARED_BRIEF}\n\n## Your section: ${s.title}\n\n${s.brief}`, {
        label: `discover:${s.key}`,
        phase: 'Discover',
        schema: CLAIMS_SCHEMA,
        agentType: 'Explore',
      }).then((r) => (r ? { ...s, claims: r.claims || [] } : null))
    )
  )
).filter(Boolean)

const lostSections = sections.filter((s) => !discovered.some((d) => d.key === s.key))
if (lostSections.length) log(`WARNING: no findings from ${lostSections.map((s) => s.key).join(', ')}`)

// Stable ids survive the trip through the verifier and back.
let nextId = 0
const allClaims = discovered.flatMap((s) =>
  s.claims.map((c) => ({ ...c, section: s.key, id: nextId++ }))
)

if (!allClaims.length) {
  return { wrote: false, reason: 'discovery returned no citable claims', sections: sections.length }
}

// ---------------------------------------------------------------------------
// Phase 2: Verify. This is the upgrade over the inline skill, which can only
// afford to "sample a handful" of citations (SKILL.md:159) because reading the
// files would reflood the orchestrator context the fan-out exists to protect.
// Here the file contents stay inside the verifier agents and only verdicts
// come back, so every citation gets checked.
//
// Barrier is deliberate. Sections cite overlapping files, so grouping by file
// across ALL sections means one verifier opens a file once instead of three
// verifiers opening it separately.
// ---------------------------------------------------------------------------

const byFile = new Map()
for (const c of allClaims) {
  if (!byFile.has(c.path)) byFile.set(c.path, [])
  byFile.get(c.path).push(c)
}

// Heaviest files first, then round-robin, so batches come out balanced.
const files = [...byFile.entries()].sort((a, b) => b[1].length - a[1].length)
const batchCount = Math.min(MAX_VERIFY_BATCHES, files.length)
const batches = Array.from({ length: batchCount }, () => [])
files.forEach(([path, claims], i) => batches[i % batchCount].push({ path, claims }))

phase('Verify')
log(`${allClaims.length} citations across ${files.length} files, ${batchCount} verifiers`)

const verified = await parallel(
  batches.map((batch, i) => () =>
    agent(
      `You are checking citations for an ARCHITECTURE.md. Read-only.

All paths are relative to \`${citationBase}\`. Resolve them against that directory.

For each claim below: open the file, go to the line, and decide whether the
snippet actually appears there.

- "confirmed" — the snippet is at that line (allow +/- 2 lines of drift).
- "moved" — the snippet is in the file but elsewhere. Give correctedLine.
- "missing" — the snippet is not in the file at all, or the file does not exist.

Judge only whether the code is where the claim says it is. You are not
reviewing the code and not assessing whether the interpretation is fair.
Return a verdict for every id. Do not skip any.

${JSON.stringify(batch, null, 2)}`,
      { label: `verify:batch-${i + 1}`, phase: 'Verify', schema: VERDICT_SCHEMA, effort: 'low' }
    )
  )
)

const verdictById = new Map()
for (const b of verified.filter(Boolean)) {
  for (const v of b.verdicts || []) verdictById.set(v.id, v)
}

// SKILL.md:162 — "Discard any claim you can't ground." An unreported claim is
// an unverified claim, so it goes too.
const kept = []
const dropped = []
let corrected = 0
for (const c of allClaims) {
  const v = verdictById.get(c.id)
  if (!v || v.status === 'missing') {
    dropped.push({ path: c.path, line: c.line, claim: c.claim, reason: v ? v.note || 'missing' : 'unverified' })
    continue
  }
  if (v.status === 'moved' && v.correctedLine) {
    kept.push({ ...c, line: v.correctedLine })
    corrected++
  } else {
    kept.push(c)
  }
}

log(`${kept.length} confirmed, ${corrected} line-corrected, ${dropped.length} discarded`)

if (!kept.length) {
  return {
    wrote: false,
    reason: 'every citation failed verification',
    discarded: dropped.length,
    droppedSample: dropped.slice(0, 20),
  }
}

// ---------------------------------------------------------------------------
// Phase 3: Synthesize. The section specs live in SKILL.md and are NOT copied
// here — the skill stays the single source for the document format, the same
// way research-to-proposals defers to project-management/proposals.md.
// ---------------------------------------------------------------------------

const bySection = sections
  .map((s) => ({ ...s, claims: kept.filter((c) => c.section === s.key) }))
  .filter((s) => s.claims.length)

phase('Synthesize')

const summary = await agent(
  `Write the ARCHITECTURE.md for this project.

Read \`${skillDir}/SKILL.md\` first. Step 6 defines the document format,
the section list, and the citation rules. Follow it exactly. Emit only the
section variants matching the detected project type(s): ${types.join(', ')}.

Then write the assembled document to \`${archPath}\`, overwriting if present.
That file is the ONLY thing you may write.

Every claim below has already been verified against the source — the line
numbers are correct as given. Do not re-check them, and do not add claims of
your own that are not backed by this evidence. Where a claim is marked
isGuess, carry that caveat into the prose rather than laundering it into a
confident statement.

Citations use the form [path/to/file.ext:42](path/to/file.ext#L42). Paths are
already relative to the citation base and must stay that way. Do not rewrite
them, do not absolutize them, and never emit a path starting with \`/\` or \`~\`.

Per Step 6 section 1, declare the citation base near the top of the document
expressed relative to the repository root — write it as ${citationBaseLabel}.
Do not use the absolute path anywhere in the document.

## Verified evidence, by section

${bySection
  .map(
    (s) =>
      `### ${s.title} (${s.key})\n\n${JSON.stringify(
        s.claims.map(({ path, line, snippet, claim, isGuess }) => ({ path, line, snippet, claim, isGuess })),
        null,
        2
      )}`
  )
  .join('\n\n')}`,
  { label: 'synthesize', phase: 'Synthesize', schema: SUMMARY_SCHEMA }
)

// Cap what travels back to the caller so a bad discovery run cannot flood its
// context with hundreds of rejects. The full count is always reported.
const DROPPED_SAMPLE = 20
if (dropped.length > DROPPED_SAMPLE) {
  log(`returning ${DROPPED_SAMPLE} of ${dropped.length} discarded citations as a sample`)
}

const droppedSample = dropped.slice(0, DROPPED_SAMPLE)

if (!summary) {
  return { wrote: false, reason: 'synthesis agent failed', kept: kept.length, droppedSample }
}

return {
  wrote: true,
  path: archPath,
  citations: { confirmed: kept.length, corrected, discarded: dropped.length },
  droppedSample,
  outline: summary.outline,
  openQuestions: summary.openQuestions,
}
