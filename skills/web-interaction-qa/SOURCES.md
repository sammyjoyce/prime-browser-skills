# Sources

Provenance for `web-interaction-qa`. Runtime files hold no source quotes and no copied structure.

## Contents

1. Prior-art status and handling
2. Local source inventory
3. Adopted ideas with attribution
4. Local decisions
5. Rejected material
6. Open gaps
7. Changelog

## Prior-art status and handling

The private contracts prior-art report (research subagent `qa-sources-contract`, 2026-09-21)
resolved and reviewed the contract sources. This author read that report, not the upstream files,
and copied no text, table, section order, schema, or script from any of them. Every rule here was
written from the private implementation brief, the installed browser-use skill, the local runner, and the
report's evaluated conclusions.

| Prior art | Pin | License | Handling |
|---|---|---|---|
| `adshine/skills` (`source-fidelity-qa`, `measured-visual-qa`, `full-stack-interaction-qa`) | `30da9d4750255a8bcc4222536b425d7e6050e8a8` | none declared in the repo, treated as all rights reserved | ideas and evaluated defects only, no copying and no near-paraphrase, each borrowed idea attributed below with a pinned permalink |
| `pbakaus/impeccable` audit reference | `f2c7051853848826aac2f4646581d62a732155ad` (local install is 4.0.2, line numbers are from the pin) | Apache 2.0 | ideas only, no material copied, so no attribution or NOTICE obligation is triggered, permalinks recorded anyway |
| `callstackincubator/agent-skills` `plugins/vendored/.agents/skills/dogfood/` | `61e6e7dfdf3a8ee862254c200d751fcb1fb863dc` | MIT | vendored copy only, cited at this path and commit, may lag the upstream `callstack/agent-device` collection which was not read; used as evidence that native mobile QA needs device tooling this suite does not have |
| `csepulv/save-the-tokens` `skills/visual-qa/SKILL.md` | `5e7497206480c0c81dadd9d71887891c552fb4b7` | MIT | ideas only, one author's practice rather than an industry standard |
| `spencerpauly/awesome-cursor-skills` `resources/visual-qa-testing/SKILL.md` | `99cd2655788456cc1c685944dcf8c2de82c1ded4` | CC0 1.0 | ideas only |
| `vibeeval/vibecosystem` `skills/visual-verdict/SKILL.md` | `3b763b1fb288f57bfa3cce76ef18184b96461a78` | MIT | two measurement ideas adopted, its scoring and fix-until-pass loop rejected |
| `vercel-labs/agent-browser` `skill-data/dogfood/` | `44583ac8385d814ab98cbf40feec97620376b50e` | Apache 2.0 | ideas only, no material copied |
| `garrytan/gstack` `qa-only/SKILL.md` and `ios-qa/SKILL.md` | `a6b3a57512ca6d5c6aa5b68f74f736195021f96e` | MIT | ideas only, its health score rejected |
| `anthropics/skills` `skills/webapp-testing/` | `34040c9c568585f6929bedeaad110ad08f079624` | per-skill `LICENSE.txt`, no repository-level license | ideas only |

The private other-source prior-art report and the private web prior-art report are now on disk.
Their decision identifiers (`O-A*`, `O-R*`, `W-A*`, `W-R*`) are cited in the tables below. Only
identifiers whose rule already exists in this skill are cited. Nothing was added to this skill to
create a citation.

## Local source inventory

Repository paths below are relative to this repository. Rows marked private stay in the
implementation project and are not published here.

| Source | Type | Retrieved | Confidence | Contribution |
|---|---|---|---|---|
| private implementation brief | user brief, canonical | 2026-09-21 | high | Suite split, report-only stance, evidence and budget rules, status set, ban on aggregate scores |
| `~/.prime/agent/skills/browser-use/SKILL.md` | installed skill, canonical | 2026-09-21 | high | Exact run arguments, default model, error behavior, profile semantics, screenshot and `attach_image` rules |
| `skills/browser-use/src/browser_use/__init__.py` | implementation in this repo | 2026-09-21 | high | `run` signature and defaults, typed errors, result keys |
| `skills/browser-use/runner.mjs` | implementation in this repo | 2026-09-21 | high | The final PNG is captured after the model run with `page.cdp('Page.captureScreenshot', {format:'png'})`, and a capture failure is a warning on an otherwise completed run |
| private POC handoff and session notes | validated session records | 2026-09-21 | high | Absolute artifact paths, one Chrome process per call, soft cost cap, unsanitized screenshots, profile locking, live checks on exact `openai/gpt-6-astra` |
| Parent session messages | direct instruction | 2026-09-21 | high | Report the actual model, precondition classes, Blocked for unexecuted work, Unknown for absent evidence, Fail for evidenced violations, keep a proven Fail, no universal risk scoring |
| private contracts prior-art report | research report | 2026-09-21 | high | Pinned sources, license decisions, adopted ideas, reproduced helper defects |
| `skill-writer` references, `skill-creator`, `unslop` | authoring and writing standards | 2026-09-21 | high | Router-shaped `SKILL.md`, flat references, `SPEC.md` shape, frontmatter rules, plain wording |

## Adopted ideas with attribution

Each row is an idea taken from prior art and rewritten independently for this skill.

| Idea adopted | Where it lives here | Prior-art permalink |
|---|---|---|
| The UI is one evidence lane and never the backend truth, so a scenario with no backend evidence is never a Pass | `SKILL.md` evidence model and verdict rules | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/SKILL.md#L8](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/SKILL.md#L8) |
| Declare the available evidence channels before running and name the missing ones as gaps | `SKILL.md` preconditions, `references/persistence-readback.md` channel table | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/SKILL.md#L30-L32](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/SKILL.md#L30-L32) |
| Separate the identity of one gesture from the identity of one business change | `references/failure-mode-protocol.md`, "One gesture against one business change" | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/references/correlation-contract.md#L5-L15](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/references/correlation-contract.md#L5-L15) |
| Join by identifier, with timing used only as a stated inference and clock skew marked rather than failed | `references/persistence-readback.md` identity section | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/references/correlation-contract.md#L25-L32](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/references/correlation-contract.md#L25-L32) |
| Report proof boundaries separately, because a rendered state, a completed request, a durable write, and async completion are different claims | `references/persistence-readback.md`, "Proof boundaries" | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/SKILL.md#L54-L55](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/SKILL.md#L54-L55) |
| A named set of race and partial-failure cases: duplicate submit, stale response overwriting newer state, unresolved optimistic state, cancellation, auth expiry | `references/failure-mode-protocol.md` check designs | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/SKILL.md#L70-L78](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/SKILL.md#L70-L78) |
| No production data changes without explicit authorization, and missing evidence stays unknown | `SKILL.md` preconditions, `references/authorization-and-test-data.md` | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/SKILL.md#L82-L86](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/SKILL.md#L82-L86) |
| A property the reference does not cover is out of scope, not a Fail | `SKILL.md` verdict rules | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/source-fidelity-qa/SKILL.md#L55](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/source-fidelity-qa/SKILL.md#L55) |
| Every finding states user impact | `SKILL.md` report shape | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L133](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L133) |
| O-A14: audit network requests as a named step, including 4xx and 5xx, CORS failures, and duplicate requests | `references/failure-mode-protocol.md` request instrumentation and duplicate check | [https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L8](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L8) |
| O-A3: cover the states that matter, including error and offline | `references/failure-mode-protocol.md` network interruption check | [https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L87](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L87) |
| W-A9: invocation is consent to look, not consent to act, and a mutating action on a non-local target needs one explicit confirmation | `SKILL.md` preconditions, `references/authorization-and-test-data.md` action classes | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L474](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L474) |
| W-A11: the user signs in, the agent never types passwords or one-time codes, and repro steps redact them | `references/authorization-and-test-data.md` test data rules | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L475](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L475) |
| W-A12: one whole flow in one call, and a missing success condition is a failure rather than a blind retry | `SKILL.md` browser call contract and verdict rules | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L478](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L478) |
| W-A16: a claimed limitation carries evidence before it is reported as blocked | `references/persistence-readback.md` Unknown against Blocked table | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L292](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L292) |
| O-A13: the skill states what it does not do, including no auto-fixing | `SKILL.md` opening lines | [https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L111](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L111) |

## Local decisions

| Decision | Source | Why |
|---|---|---|
| Authoritative readback ranked above a fresh-session reload, which ranks above UI state | brief | Only the first proves storage, and the report must say which one it used |
| Unique data markers in every created value, per attempt | brief, local reasoning about cleanup and duplicates | A marker is what makes a duplicate, a leftover, or a race outcome provable |
| No blind retry after a failed run | installed skill warning that a failed run may already have submitted | Retrying can create the second record you are testing for |
| One flow inside one run, and a second run as a fresh-session readback | installed skill profile semantics | A new call is a new Chrome process with cookies but no tabs or unsaved input |
| Concurrency uses distinct profiles and reports observed timestamps | installed skill profile locking | One profile has one owner, and interleaving is not controllable from Python |
| Report `result["model"]` | parent instruction | The default is exactly `openai/gpt-6-astra`, an environment override is possible |
| Status mapping: Blocked for unexecuted, Unknown for absent evidence, Fail for evidenced violations, and a proven Fail is kept | parent instruction | Keeps a real defect visible even when a later attempt passes |
| Budget ledger, three-attempt default, severity separate from confidence, state left behind | brief | The prior art has none of these, as the research report states |

## Rejected material

| Rejected | Reason | Evidence |
|---|---|---|
| Copying any wording, table, rubric, schema, or script from the prior art | `adshine/skills` has no license, so all rights reserved, and the brief forbids copying in any case | research report section 2 |
| Gates computed from agent-supplied payload flags | Gates for correlation, idempotency, stale response, and optimistic state read flags the agent sets about itself, so an empty evidence pack passes five of six gates while the prose says unknown | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/scripts/fsqa.py#L153-L189](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/scripts/fsqa.py#L153-L189) |
| A gate that an empty evidence list can satisfy | With no recorded requests the mutating list is empty and the check passes, which scores absence of evidence as compliance | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/scripts/fsqa.py#L153-L189](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/scripts/fsqa.py#L153-L189) |
| A privacy check that only greps for one literal token pattern | It reports clean on data it never inspected | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/scripts/fsqa.py#L180-L185](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/scripts/fsqa.py#L180-L185) |
| The artifact-pack command-line framework | This skill runs on `browser_use.run` plus files, and the brief prefers instructions over another framework | research report section 5 |
| Application test headers required as a precondition | They need application cooperation; here they are optional and recorded when they already exist | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/references/correlation-contract.md#L25-L32](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/references/correlation-contract.md#L25-L32) |
| Any aggregate pass rate or weighted risk index | Averaging hides a hard failure, and the brief bans it | brief |
| Unsolicited production mutation, including "just submit it and see" | Report-only default, and hard-to-reverse actions need written authorization naming the action | brief |
| W-R6, W-R7, and W-R8: a weighted health score, a deduction model, and a ship-readiness score | A critical functional failure inside a small weight moves the total by a few points, which averages failures away | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L876](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L876) |
| W-R9: retry once to confirm a finding is not a fluke, with a passing retry erasing it | A duplicate or race defect is often intermittent, so the observation and its attempt ratio are kept | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L911](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L911) |
| W-R11: a fixed delay after an action as the readiness step | A timer proves nothing about hydration, streaming, or polling | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L773](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L773) |
| O-R2: a fixed millisecond wait after a submit as readiness | The same defect, and a submit is exactly where a wrong readiness rule creates a false pass | [https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L62](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L62) |
| W-R12: a preamble binary, telemetry, marker files, and score baselines as the package pattern | This skill is markdown plus the installed browser-use skill, with no subproject | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L23](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L23) |
| O-R14: the fix-and-rescore loop driven by the QA skill | Report-only by instruction, and looping until green is the banned pattern | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L207](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L207) |
| Copying the shared status and budget policy into this skill | `web-qa` owns `../web-qa/references/evidence-contract.md` | brief |

## Open gaps

1. Prior-art rows are complete for all seven reviewed sources. Not read at source: the upstream
   `callstack/agent-device` collection, the four tool reference files in `save-the-tokens`, and the
   vendored Callstack report template. Those gaps are recorded in the research files.
2. Fault injection such as network interruption is unverified in this environment, so those checks
   can end as Blocked until a live run shows what the browser agent can do.
3. No live validation run of this skill has happened yet. `SPEC.md` names the bounded live check.
4. `../web-qa/references/evidence-contract.md` did not exist when this skill was drafted.
5. Server-side evidence depends entirely on what the user can supply. No default channel exists.

## Changelog

| Date | Change |
|---|---|
| 2026-09-21 | First draft from private implementation brief, the installed browser-use skill, and the local runner implementation, including the parent corrections on model reporting, precondition classes, and status mapping. |
| 2026-09-21 | Added prior-art provenance from private contracts prior-art report, with attributed adopted ideas, defect-backed rejections, proof boundaries, and the gesture-against-business-change split. |
| 2026-09-21 | Finalized prior-art rows from private other-source prior-art report and `web-prior-art.md`: adopted O-A3, O-A13, O-A14, W-A9, W-A11, W-A12, W-A16; rejected O-R2, O-R14, W-R6 to W-R9, W-R11, W-R12. No behavior was added to create a citation. |
