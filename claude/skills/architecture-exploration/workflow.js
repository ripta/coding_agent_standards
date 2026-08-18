export const meta = {
  name: 'architecture-exploration',
  description: 'Fan out per-section discovery, verify every citation, then write ARCHITECTURE.md',
  whenToUse: 'Escalation path for the architecture-exploration skill, on repos large enough that spot-checking citations is not evidence. The caller resolves scope, classifies the project, and plans the fan-out first, then passes that plan in as args.',
  phases: [
    { title: 'Discover', detail: 'one read-only Explore agent per section' },
    { title: 'Verify', detail: 'confirm every file:line citation, batched by file' },
    { title: 'Spine', detail: 'fix shared vocabulary and topic ownership before anyone writes' },
    { title: 'Write', detail: 'one agent per part, each writing its own file' },
    { title: 'Assemble', detail: 'concatenate the parts mechanically' },
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
  skillDir, // dir holding SKILL.md, read by the part writers for the section specs
  types, // e.g. ['backend'] or ['frontend', 'backend']
  sections, // fan-out plan from Step 3: [{ key, title, brief, mode?, group? }]
} = args || {}

if (!scope || !citationBase || !citationBaseLabel || !skillDir || !types?.length || !sections?.length) {
  throw new Error(
    'args must supply scope, citationBase, citationBaseLabel, skillDir, types[], sections[{key,title,brief}]'
  )
}

if (!citationBase.startsWith('/')) {
  throw new Error(`citationBase must be absolute so agents can resolve against it, got: ${citationBase}`)
}

const dupeKeys = sections.map((s) => s.key).filter((k, i, a) => a.indexOf(k) !== i)
if (dupeKeys.length) {
  throw new Error(`section keys must be unique; duplicates silently merge shards: ${dupeKeys.join(', ')}`)
}

const archPath = `${citationBase}/ARCHITECTURE.md`

// Scratch dir for the part files. Deterministic on purpose: workflow scripts
// cannot call Date.now(), and a stable name is what lets `resumeFromRunId`
// reuse the parts an earlier run already wrote. Removed only after a
// successful assembly, so a dead run leaves salvageable work behind.
const partsDir = `${citationBase}/.architecture-parts`

// ---------------------------------------------------------------------------
// Tuning. Every constant here is calibrated against a real 287 KB run over a
// 320k-line repo: 1,254 verified claims, 1,437 citations, 323 distinct files.
// ---------------------------------------------------------------------------

// Measured at 193-213 across every section of that run, and 230 per *claim*
// once the 1.15 citations-per-claim ratio is folded in. Stable enough to size
// the writers before a single byte is generated.
const BYTES_PER_CLAIM = 230

// Below this, one writer produces a more coherent document than twelve, and a
// single generation that size is not at risk of dying.
const SHARD_SYNTHESIS_CLAIMS = 150

// ~25 KB of output. The largest parts of the reference run (26.1 KB, 25.1 KB,
// 24.3 KB) all completed; that is the top of the proven-survivable range.
const MAX_CLAIMS_PER_PART = 110

// Whole document under this stays in one file regardless of section modes.
const SINGLE_FILE_BYTES = 60_000

// Verification batch sizes, one entry per round. Round 0 splits all claims into
// ~80-claim batches; each later round re-batches only what came back
// unanswered, smaller each time, which converges on a poisonous input instead
// of discarding everything around it.
const VERIFY_ROUNDS = [80, 40, 15]
const MAX_VERIFY_BATCHES = 32

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
          isAbsenceClaim: {
            type: 'boolean',
            description:
              'True when the claim asserts something does NOT exist. Your search proves presence, never absence, so these are downgraded to hedged prose.',
          },
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

const SPINE_SCHEMA = {
  type: 'object',
  required: ['summary', 'glossary', 'sharedTopics'],
  properties: {
    summary: {
      type: 'string',
      description: 'What this project is and does, one paragraph. Every writer gets this as shared framing.',
    },
    glossary: {
      type: 'array',
      description: 'Recurring entities that the evidence names inconsistently. Only entries with a real conflict.',
      items: {
        type: 'object',
        required: ['canonical', 'aliases'],
        properties: {
          canonical: { type: 'string', description: 'The one name every writer must use' },
          aliases: { type: 'array', items: { type: 'string' }, description: 'Competing names seen in the evidence' },
        },
      },
    },
    sharedTopics: {
      type: 'array',
      description:
        'Mechanisms whose evidence shows up under more than one section. Each gets exactly one owner; everyone else links to it.',
      items: {
        type: 'object',
        required: ['topic', 'owner', 'alsoAppearsIn'],
        properties: {
          topic: { type: 'string', description: 'The mechanism, named in a few words' },
          owner: { type: 'string', description: 'Section key that explains it in full' },
          alsoAppearsIn: { type: 'array', items: { type: 'string' }, description: 'Section keys that must link instead' },
        },
      },
    },
  },
}

const PART_SCHEMA = {
  type: 'object',
  required: ['outline', 'openQuestions'],
  properties: {
    outline: {
      type: 'string',
      description:
        'What your part covers, 2-4 sentences. This is quoted verbatim into the parent document when your part lands in a separate file, so write it to stand alone.',
    },
    openQuestions: {
      type: 'array',
      items: { type: 'string' },
      description: 'What you could not resolve from the evidence alone',
    },
  },
}

// ---------------------------------------------------------------------------
// Phase 1: Discover. Shared brief is lifted from SKILL.md Step 5 verbatim,
// plus the absence-claim rule.
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
outside it.

Your search proves presence, never absence. You searched part of the tree, so
"there is no X here" is a claim you cannot support — another agent searching a
different path may hold the counterexample. If you must say it, anchor it to the
place X would live and set \`isAbsenceClaim\`.`

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
const allClaims = discovered.flatMap((s) => s.claims.map((c) => ({ ...c, section: s.key, id: nextId++ })))

if (!allClaims.length) {
  return { wrote: false, reason: 'discovery returned no citable claims', sections: sections.length }
}

// ---------------------------------------------------------------------------
// Phase 2: Verify. This is the upgrade over the inline skill, which can only
// afford to "sample a handful" of citations because reading the files would
// reflood the orchestrator context the fan-out exists to protect. Here the file
// contents stay inside the verifier agents and only verdicts come back, so
// every citation gets checked.
//
// Barrier is deliberate. Sections cite overlapping files, so grouping by file
// across ALL sections means one verifier opens a file once instead of three
// verifiers opening it separately.
// ---------------------------------------------------------------------------

// Longest-processing-time first: hand each file to whichever batch is currently
// lightest. Round-robin averages out at 8 batches over 300 files but degrades
// badly once batches get small, and small batches are the whole point below.
function packBatches(claims, targetPerBatch) {
  const byFile = new Map()
  for (const c of claims) {
    if (!byFile.has(c.path)) byFile.set(c.path, [])
    byFile.get(c.path).push(c)
  }
  const files = [...byFile.entries()].sort((a, b) => b[1].length - a[1].length)

  // A file never splits across batches, so the most-cited file floors the batch
  // size no matter what target is asked for.
  const wanted = Math.ceil(claims.length / targetPerBatch)
  const count = Math.max(1, Math.min(wanted, files.length, MAX_VERIFY_BATCHES))

  const batches = Array.from({ length: count }, () => ({ weight: 0, files: [] }))
  for (const [path, fileClaims] of files) {
    let lightest = batches[0]
    for (const b of batches) if (b.weight < lightest.weight) lightest = b
    lightest.files.push({ path, claims: fileClaims })
    lightest.weight += fileClaims.length
  }
  return batches.filter((b) => b.files.length)
}

function verifyPrompt(batch) {
  return `You are checking citations for an ARCHITECTURE.md. Read-only.

All paths are relative to \`${citationBase}\`. Resolve them against that directory.

For each claim below: open the file, go to the line, and decide whether the
snippet actually appears there.

- "confirmed" — the snippet is at that line (allow +/- 2 lines of drift).
- "moved" — the snippet is in the file but elsewhere. Give correctedLine.
- "missing" — the snippet is not in the file at all, or the file does not exist.

Judge only whether the code is where the claim says it is. You are not
reviewing the code and not assessing whether the interpretation is fair.

Return a verdict for every id. Do not skip any, and do not truncate the list —
an id you omit is treated as a citation nobody ever checked, not as a pass.

${JSON.stringify(batch.files, null, 2)}`
}

phase('Verify')

const verdictById = new Map()
let pending = allClaims

for (let round = 0; round < VERIFY_ROUNDS.length && pending.length; round++) {
  const batches = packBatches(pending, VERIFY_ROUNDS[round])
  const distinctFiles = new Set(pending.map((c) => c.path)).size
  log(
    round === 0
      ? `${pending.length} citations across ${distinctFiles} files, ${batches.length} verifiers`
      : `retry ${round}: ${pending.length} unanswered citations re-split into ${batches.length} smaller batches`
  )

  const results = await parallel(
    batches.map((batch, i) => () =>
      agent(verifyPrompt(batch), {
        label: `verify:r${round + 1}-batch-${i + 1}`,
        phase: 'Verify',
        schema: VERDICT_SCHEMA,
        effort: 'low',
      })
    )
  )

  let gained = 0
  for (const r of results.filter(Boolean)) {
    for (const v of r.verdicts || []) {
      if (!verdictById.has(v.id)) {
        verdictById.set(v.id, v)
        gained++
      }
    }
  }

  pending = pending.filter((c) => !verdictById.has(c.id))

  // A round that answers nothing will answer nothing again. Stop rather than
  // burning the remaining rounds on an input that reliably kills its agent.
  if (!gained && pending.length) {
    log(`no progress on ${pending.length} citations; quarantining rather than retrying further`)
    break
  }
}

// Three distinct outcomes, deliberately not one bucket. "We checked and it was
// wrong" and "nobody ever checked" are different facts, and reporting the
// second as the first understates how much of the document went missing.
const kept = []
const refuted = []
let corrected = 0
for (const c of allClaims) {
  const v = verdictById.get(c.id)
  if (!v) continue // unchecked; counted separately below
  if (v.status === 'missing') {
    refuted.push({ path: c.path, line: c.line, claim: c.claim, reason: v.note || 'not found in file' })
    continue
  }
  if (v.status === 'moved' && v.correctedLine) {
    kept.push({ ...c, line: v.correctedLine })
    corrected++
  } else {
    kept.push(c)
  }
}

const unchecked = pending.map((c) => ({ path: c.path, line: c.line, claim: c.claim }))

log(`${kept.length} confirmed, ${corrected} line-corrected, ${refuted.length} refuted, ${unchecked.length} unchecked`)
if (unchecked.length) {
  log(`WARNING: ${unchecked.length} citations were never verified by any agent and are excluded from the document`)
}

if (!kept.length) {
  return {
    wrote: false,
    reason: 'no citation survived verification',
    citations: { confirmed: 0, corrected: 0, refuted: refuted.length, unchecked: unchecked.length },
    refutedSample: refuted.slice(0, 20),
  }
}

// ---------------------------------------------------------------------------
// Document layout. Decided here, in JS, BEFORE anything is written — the part
// writers emit cross-section links, and a link target depends on which file its
// section ends up in. Deciding placement after the fact from measured sizes
// would invalidate every link already written.
// ---------------------------------------------------------------------------

// GitHub heading slugification: lowercase, drop punctuation, spaces to hyphens.
// The case that matters is a version number inside a title, where the dot
// vanishes rather than becoming a separator: "Webhook API v2.1" -> "webhook-api-v21".
function slug(title) {
  return title
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
}

const parts = sections
  .map((s, i) => ({ ...s, order: i, claims: kept.filter((c) => c.section === s.key) }))
  .filter((p) => p.claims.length)

const predictedBytes = kept.length * BYTES_PER_CLAIM
const singleFile = predictedBytes < SINGLE_FILE_BYTES
const shardWriters = kept.length >= SHARD_SYNTHESIS_CLAIMS

const oversized = parts.filter((p) => p.claims.length > MAX_CLAIMS_PER_PART)
if (shardWriters && oversized.length) {
  log(
    `WARNING: ${oversized.map((p) => `${p.key} (${p.claims.length})`).join(', ')} exceed ${MAX_CLAIMS_PER_PART} claims; ` +
      `shard these in Step 3 next time — oversized parts are what dies mid-generation`
  )
}

// ---------------------------------------------------------------------------
// Small scope: one writer, one file, no scratch dir. Sharding buys resilience
// at the cost of seams, and below this size there is no risk to insure against
// — a single generation this small does not die, and one author reads better
// than six stitched together.
// ---------------------------------------------------------------------------

if (!shardWriters) {
  phase('Write')
  log(`${kept.length} claims (< ${SHARD_SYNTHESIS_CLAIMS}) — single writer, single file`)

  const solo = await agent(
    `Write the ARCHITECTURE.md for this project.

Read \`${skillDir}/SKILL.md\` first. Step 6 defines the document format, the
section list, and the citation rules. Follow it exactly. Emit only the section
variants matching the detected project type(s): ${types.join(', ')}.

Then write the assembled document to \`${archPath}\`, overwriting if present.
That file is the ONLY thing you may write.

Every claim below has already been verified against the source — the line
numbers are correct as given. Do not re-check them, and do not add claims of
your own that are not backed by this evidence. Where a claim is marked
isGuess, carry that caveat into the prose rather than laundering it into a
confident statement. Where a claim is marked isAbsenceClaim, write it as "no
such marker was found in the files examined" — the evidence proves what exists,
never what is missing.

Citations use the form [path/to/file.ext:42](path/to/file.ext#L42). Paths are
already relative to the citation base and must stay that way. Do not rewrite
them, do not absolutize them, and never emit a path starting with \`/\` or \`~\`.

Per Step 6 section 1, declare the citation base near the top of the document
expressed relative to the repository root — write it as ${citationBaseLabel}.
Do not use the absolute path anywhere in the document.

## Verified evidence, by section

${parts
  .map(
    (p) =>
      `### ${p.title} (${p.key})\n\n${JSON.stringify(
        p.claims.map(({ path, line, snippet, claim, isGuess, isAbsenceClaim }) => ({
          path,
          line,
          snippet,
          claim,
          isGuess,
          isAbsenceClaim,
        })),
        null,
        2
      )}`
  )
  .join('\n\n')}`,
    { label: 'write:single', phase: 'Write', schema: PART_SCHEMA }
  )

  const soloCitations = { confirmed: kept.length, corrected, refuted: refuted.length, unchecked: unchecked.length }

  if (!solo) {
    return { wrote: false, reason: 'writer failed', citations: soloCitations, refutedSample: refuted.slice(0, 20) }
  }

  return {
    wrote: true,
    path: archPath,
    files: [{ path: archPath }],
    citations: soloCitations,
    refutedSample: refuted.slice(0, 20),
    uncheckedSample: unchecked.slice(0, 20),
    failedParts: [],
    outline: solo.outline,
    openQuestions: solo.openQuestions || [],
  }
}

// Sections sharing a `group` render as one H2 with an H3 per part.
const groups = []
for (const p of parts) {
  const title = p.group || p.title
  let g = groups.find((x) => x.title === title)
  if (!g) {
    g = { title, parts: [], mode: p.mode === 'reference' ? 'reference' : 'narrative' }
    groups.push(g)
  }
  g.parts.push(p)
}

// Heading levels are assigned here rather than left to the writers, because the
// anchors other writers link to are these exact strings. A promoted group's
// title is already the H1 of its own file, so its parts sit one level shallower
// than the same parts would inline.
for (const g of groups) {
  g.onePart = g.parts.length === 1
  g.anchor = slug(g.title)
  g.promoted = !singleFile && g.mode === 'reference'
  g.file = g.promoted ? `ARCHITECTURE-${g.anchor}.md` : 'ARCHITECTURE.md'

  g.parts.forEach((p, i) => {
    p.grp = g
    if (g.promoted && g.onePart) {
      // The companion file's H1 is this part's heading. Emitting one here too
      // would just repeat the title.
      p.headingBlock = ''
      p.subLevel = '##'
      p.anchor = g.anchor
    } else if (g.promoted) {
      p.headingBlock = `## ${p.title}`
      p.subLevel = '###'
      p.anchor = slug(p.title)
    } else if (g.onePart) {
      p.headingBlock = `## ${g.title}`
      p.subLevel = '###'
      p.anchor = g.anchor
    } else {
      p.headingBlock = i === 0 ? `## ${g.title}\n\n### ${p.title}` : `### ${p.title}`
      p.subLevel = '####'
      p.anchor = slug(p.title)
    }
    p.link = `${g.promoted ? g.file : ''}#${p.anchor}`
  })
}

const outputCount = new Set(groups.map((g) => g.file)).size
log(
  `${kept.length} claims -> ~${Math.round(predictedBytes / 1024)} KB predicted, ` +
    `${parts.length} part writers, ${outputCount} output file${outputCount === 1 ? '' : 's'}`
)

// ---------------------------------------------------------------------------
// Phase 3: Spine. One cheap agent fixes the shared vocabulary and assigns each
// cross-cutting mechanism a single owner, BEFORE any writer starts. Writers
// working blind is what produced seven independently re-derived explanations of
// the same mechanism in the reference run.
// ---------------------------------------------------------------------------

let spine = { summary: '', glossary: [], sharedTopics: [] }

{
  phase('Spine')
  const raw = await agent(
      `You are setting the shared conventions for an ARCHITECTURE.md that ${parts.length} writers
will produce in parallel. None of them can see each other's work. You are the
only stage that sees all the evidence at once.

The document's sections, in order:

${groups.map((g) => `- ${g.title} — parts: ${g.parts.map((p) => p.key).join(', ')}`).join('\n')}

Do three things.

1. **summary** — one paragraph on what this project is and does. Every writer
   gets it as shared framing, so keep it factual and free of hedging.

2. **glossary** — find entities the evidence names inconsistently and pick one
   canonical name for each. Only include real conflicts. Most codebases name
   things consistently, so one or two entries is the expected result rather than
   a sign you missed something. Do not pad it.

3. **sharedTopics** — the important one. Find mechanisms whose evidence appears
   under more than one section, and give each exactly one owner. Depth belongs
   to whichever section traces it end to end; everyone else gets a sentence and
   a link. Assign ownership so that a reader meets each mechanism once in full.

Below is every verified claim, grouped by section. Snippets are stripped — you
are looking at what the document will cover, not at the code.

${parts
  .map((p) => `### ${p.title} (${p.key})\n${p.claims.map((c) => `- ${c.claim}`).join('\n')}`)
  .join('\n\n')}`,
    { label: 'spine', phase: 'Spine', schema: SPINE_SCHEMA }
  )

  if (!raw?.summary) {
    log('WARNING: spine agent failed; writers proceed without shared vocabulary or topic ownership')
  } else {
    spine = { summary: raw.summary, glossary: raw.glossary || [], sharedTopics: raw.sharedTopics || [] }
    log(`spine: ${spine.glossary.length} glossary entries, ${spine.sharedTopics.length} shared topics assigned`)
  }
}

// ---------------------------------------------------------------------------
// Phase 4: Write. One agent per part, each writing its own file. The section
// specs live in SKILL.md and are NOT copied here — the skill stays the single
// source for the document format, the same way research-to-proposals defers to
// project-management/proposals.md.
// ---------------------------------------------------------------------------

const CONVENTIONS = `## Conventions, binding on every part

These exist because a previous parallel run split roughly evenly between two
different ways of doing each of them, and the seams showed.

- **Sub-topic headings.** Use real Markdown headings, never a bolded paragraph
  lead like \`**Error handling.**\` standing in for one.
- **Citations are inline**, in parentheses, immediately after the claim they
  support. Never collected onto a trailing line of their own.
- **Hedge consistently.** Where a claim is marked \`isGuess\`, carry the caveat
  into the prose. Do not launder an inference into a confident statement, and do
  not hedge a claim that is directly evidenced.
- **Never assert absence.** The evidence proves what exists. A claim marked
  \`isAbsenceClaim\` becomes "no marker was found in the files examined", not
  "nothing in the code is marked". Another part may hold the counterexample.
- **Link, do not restate.** You are given the full outline with a link target
  for every other part. If a mechanism belongs to another part, spend a sentence
  and link to it.`

function outlineFor(me) {
  return groups
    .map((g) => {
      const head = `- **${g.title}**${g.promoted ? ` (separate file: \`${g.file}\`)` : ''}`
      if (g.onePart) {
        const p = g.parts[0]
        return `${head} → link as \`[${g.title}](${p.link})\`${p.key === me.key ? '  ← YOURS' : ''}`
      }
      return [
        head,
        ...g.parts.map(
          (p) => `  - ${p.title} → link as \`[${p.title}](${p.link})\`${p.key === me.key ? '  ← YOURS' : ''}`
        ),
      ].join('\n')
    })
    .join('\n')
}

function partFile(p) {
  return `${partsDir}/${String(p.order + 1).padStart(2, '0')}-${p.key}.md`
}

function writePrompt(p) {
  const owned = spine.sharedTopics.filter((t) => t.owner === p.key)
  const borrowed = spine.sharedTopics.filter((t) => t.alsoAppearsIn?.includes(p.key) && t.owner !== p.key)
  const ownerLink = (key) => {
    const target = parts.find((x) => x.key === key)
    return target ? `[${target.title}](${target.link})` : key
  }

  return `Write ONE part of an ARCHITECTURE.md. Other agents are writing the other parts
right now, in parallel, and the results will be concatenated without an editing
pass. Everything you need to stay consistent with them is below.

Read \`${skillDir}/SKILL.md\` first. Step 6 defines the section specs and the
citation rules. Follow the spec for your part. Emit only the variants matching
the detected project type(s): ${types.join(', ')}.

## What to write

Your part is **${p.title}**.

${p.brief}

Write it to \`${partFile(p)}\`, creating the directory if it does not exist and
overwriting the file if it does. That file is the ONLY thing you may write — do
not touch ARCHITECTURE.md, and do not create any other file.

## Headings

${
  p.headingBlock
    ? `Start the file with exactly this text, verbatim:

\`\`\`
${p.headingBlock}
\`\`\`

Do not reword it. Other writers are already linking to the anchor it generates.

`
    : `Your part's title is the H1 of the file it gets concatenated into, so do
**not** write a heading for it. Start straight into the content.

`
}Use \`${p.subLevel}\` for your own sub-topics, and go deeper from there as needed.
Never emit a heading shallower than \`${p.subLevel}\` beyond the block above —
those levels belong to other parts.

${spine.summary ? `## What this project is\n\n${spine.summary}\n` : ''}
${CONVENTIONS}

${
  spine.glossary.length
    ? `## Glossary — use the canonical name only\n\n${spine.glossary
        .map((g) => `- **${g.canonical}** (not: ${g.aliases.join(', ')})`)
        .join('\n')}\n`
    : ''
}
## The full document, and how to link into it

Every heading below is already fixed. The link targets resolve, including to
parts that have not been written yet — write the links now.

${outlineFor(p)}

${
  owned.length
    ? `## Topics you own\n\nYou are the one part that explains these in full. Other parts link here.\n\n${owned
        .map((t) => `- ${t.topic}`)
        .join('\n')}\n`
    : ''
}
${
  borrowed.length
    ? `## Topics you must NOT explain\n\nYour evidence touches these, but another part owns the depth. One sentence and a link.\n\n${borrowed
        .map((t) => `- ${t.topic} → owned by ${ownerLink(t.owner)}`)
        .join('\n')}\n`
    : ''
}
## Citations

Use the form \`[path/to/file.ext:42](path/to/file.ext#L42)\`. Paths below are
already relative to the citation base and must stay that way. Do not rewrite
them, do not absolutize them, and never emit a path starting with \`/\` or \`~\`.

Every claim below has already been verified against the source — the line
numbers are correct as given. Do not re-check them, and do not add claims of
your own that are not backed by this evidence.

## Your verified evidence

${JSON.stringify(
  p.claims.map(({ path, line, snippet, claim, isGuess, isAbsenceClaim }) => ({
    path,
    line,
    snippet,
    claim,
    isGuess,
    isAbsenceClaim,
  })),
  null,
  2
)}`
}

phase('Write')

// One retry per part, then give up on that part alone. A part that dies costs
// its own subsection and nothing else — which is the whole reason the writing
// is sharded. Never let a thunk reject: parallel() would collapse it to a bare
// null and the part it belonged to would be unrecoverable below.
const written = await parallel(
  parts.map((p) => () =>
    agent(writePrompt(p), { label: `write:${p.key}`, phase: 'Write', schema: PART_SCHEMA })
      .then((r) => r || agent(writePrompt(p), { label: `write:${p.key}-retry`, phase: 'Write', schema: PART_SCHEMA }))
      .catch(() => null)
      .then((r) => ({ part: p, result: r }))
  )
)

const results = parts.map((p) => written.find((w) => w?.part?.key === p.key) || { part: p, result: null })
const done = results.filter((w) => w.result)
const failedParts = results.filter((w) => !w.result).map((w) => w.part)
if (failedParts.length) {
  log(`WARNING: ${failedParts.map((p) => p.key).join(', ')} failed twice; assembling with placeholders in their place`)
}

// ---------------------------------------------------------------------------
// Phase 5: Assemble. Purely mechanical — the assembler concatenates files and
// writes preamble text this script composed. It generates no prose of its own.
// That is the entire point: a 260 KB document that has to survive one
// uninterrupted generation is a document that dies.
// ---------------------------------------------------------------------------

const outlineByKey = new Map(done.map((w) => [w.part.key, w.result.outline]))

function tocFor(file) {
  return groups
    .map((g) => {
      const target = g.file === file ? '' : g.file
      if (g.onePart) return `- [${g.title}](${target}#${g.anchor})`
      return [
        `- [${g.title}](${target}#${g.anchor})`,
        ...g.parts.map((p) => `  - [${p.title}](${target}#${p.anchor})`),
      ].join('\n')
    })
    .join('\n')
}

const baseNote =
  citationBaseLabel === 'the repository root'
    ? 'All paths are relative to the repository root.'
    : `All paths are relative to ${citationBaseLabel}.`

const mainPreamble = [
  '# Architecture',
  '',
  baseNote,
  '',
  spine.summary || '',
  '',
  '## Table of Contents',
  '',
  tocFor('ARCHITECTURE.md'),
  '',
  // Promoted sections keep their heading and summary here so the main document
  // still reads as a complete outline of the system.
  ...groups
    .filter((g) => g.promoted)
    .map((g) =>
      [
        `## ${g.title}`,
        '',
        g.parts
          .map((p) => outlineByKey.get(p.key))
          .filter(Boolean)
          .join('\n\n') || '_This section is documented in a companion file._',
        '',
        `→ **[Read the full section](${g.file})**`,
        '',
      ].join('\n')
    ),
]
  .join('\n')
  .replace(/\n{3,}/g, '\n\n')

const outputs = [...new Set(groups.map((g) => g.file))].map((file) => {
  const fileGroups = groups.filter((g) => g.file === file && !g.promoted)
  const main = file === 'ARCHITECTURE.md'
  const preamble = main
    ? mainPreamble
    : [
        `# ${groups.find((g) => g.file === file).title}`,
        '',
        baseNote,
        '',
        '← Back to [Architecture](ARCHITECTURE.md)',
        '',
        '## Table of Contents',
        '',
        tocFor(file),
        '',
      ].join('\n')

  const bodyGroups = main ? fileGroups : groups.filter((g) => g.file === file)
  return {
    file: `${citationBase}/${file}`,
    preambleFile: `${partsDir}/00-preamble-${slug(file)}.md`,
    preamble,
    partFiles: bodyGroups.flatMap((g) => g.parts.map((p) => partFile(p))),
  }
})

phase('Assemble')

// A part that never landed still gets a file, so the concatenation succeeds and
// the gap is visible in the document instead of silently closing over it.
const missingFallbacks = parts.map((p) => ({
  path: partFile(p),
  content: `${p.headingBlock ? `${p.headingBlock}\n\n` : ''}> **This part failed to generate.** ${p.claims.length} verified citations for it were dropped. Re-run the workflow to fill it in.\n`,
}))

const assembled = await agent(
  `You are assembling a document from parts that other agents already wrote. This
is a mechanical task. Write no prose of your own — every byte of content is
either already on disk or given to you verbatim below.

## Step 1 — backfill anything missing

For each entry below, check whether the file exists. If it does, leave it alone.
If it does not, create it with exactly the content given.

${JSON.stringify(missingFallbacks, null, 2)}

## Step 2 — write the preambles

For each output below, write \`preamble\` verbatim to \`preambleFile\`. Copy it
exactly. Do not reformat, reflow, or improve it.

## Step 3 — concatenate

For each output, concatenate \`preambleFile\` followed by every entry of
\`partFiles\` **in the order given**, into \`file\`. Overwrite if present.

Do this with a shell command, never by reading the parts and re-emitting them —
they total hundreds of kilobytes and must not pass through your response.

Prefer this form. It normalises the seams, so a part that lacks a trailing
newline cannot weld its last line onto the next part's heading:

\`\`\`sh
python3 -c "import sys; open(sys.argv[1],'w').write('\\n\\n'.join(open(p).read().strip() for p in sys.argv[2:]) + '\\n')" <file> <preambleFile> <partFiles...>
\`\`\`

If \`python3\` is unavailable, fall back to \`cat <preambleFile> <partFiles...> > <file>\`.
That form does not normalise, so check afterwards that no heading in the result
has text welded onto its line.

## Step 4 — verify, then clean up

Run \`wc -c\` on each output file. If every one is non-empty, remove the scratch
directory \`${partsDir}\` entirely. If any output is empty or missing, leave the
scratch directory in place — it holds the only copy of that work.

## Outputs

${JSON.stringify(
  outputs.map(({ file, preambleFile, preamble, partFiles }) => ({ file, preambleFile, preamble, partFiles })),
  null,
  2
)}`,
  {
    label: 'assemble',
    phase: 'Assemble',
    schema: {
      type: 'object',
      required: ['files'],
      properties: {
        files: {
          type: 'array',
          items: {
            type: 'object',
            required: ['path', 'bytes'],
            properties: {
              path: { type: 'string' },
              bytes: { type: 'integer', description: 'Result of wc -c on the assembled file' },
            },
          },
        },
        scratchRemoved: { type: 'boolean' },
        notes: { type: 'string' },
      },
    },
  }
)

// Cap what travels back to the caller so a bad run cannot flood its context
// with hundreds of rejects. Full counts are always reported.
const SAMPLE = 20
if (refuted.length > SAMPLE) log(`returning ${SAMPLE} of ${refuted.length} refuted citations as a sample`)

const citations = {
  confirmed: kept.length,
  corrected,
  refuted: refuted.length,
  unchecked: unchecked.length,
}

if (!assembled) {
  return {
    wrote: false,
    reason: 'assembly failed; the individual parts survive on disk',
    partsDir,
    citations,
    refutedSample: refuted.slice(0, SAMPLE),
    uncheckedSample: unchecked.slice(0, SAMPLE),
  }
}

return {
  wrote: true,
  path: archPath,
  files: assembled.files,
  scratchRemoved: assembled.scratchRemoved,
  partsDir: assembled.scratchRemoved ? null : partsDir,
  citations,
  refutedSample: refuted.slice(0, SAMPLE),
  uncheckedSample: unchecked.slice(0, SAMPLE),
  failedParts: failedParts.map((p) => p.key),
  outline: done.map((w) => `**${w.part.title}** — ${w.result.outline}`).join('\n\n'),
  openQuestions: [...new Set(done.flatMap((w) => w.result.openQuestions || []))],
}
