# Sources

Provenance for `web-accessibility-qa`. Runtime files hold no source quotes and no copied
structure.

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
| A code-level audit is a complementary lane that documents rather than fixes, limited to what the implementation makes verifiable | `SKILL.md` run plan step 6, `references/evidence-sources.md` code review section | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L1-L3](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L1-L3) |
| Name what produced the evidence and what stayed untested, because a rendered viewport proves layout and not an interaction | `SKILL.md` claim limits and coverage reporting | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L51](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L51) |
| Keep deterministic output separate from judgment and call out likely false positives | `references/evidence-sources.md` automated checker section | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L60](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L60) |
| Every finding states user impact, and a finding without impact is not reportable | `SKILL.md` report shape | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L133](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L133) |
| Report a repeated defect once as a systemic issue with an instance count | `SKILL.md` report shape | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L105-L109](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L105-L109) |
| Web-only scope with native platforms routed elsewhere | `SPEC.md` scope, native requests Blocked | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L5](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L5) |
| A property the reference does not cover is out of scope, not a Fail | `SKILL.md` verdict rules | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/source-fidelity-qa/SKILL.md#L55](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/source-fidelity-qa/SKILL.md#L55) |
| A gate that an empty evidence set can satisfy is not a gate | `SKILL.md` verdict rules | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/compare_visual.py#L35](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/compare_visual.py#L35) |
| O-A11: every claim about rendered state needs a capture, and a capture must actually be viewed | `SKILL.md` evidence capture and claim limits | [https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L93](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L93) |
| O-A13: the skill states what it does not do, including no auto-fixing and no health score | `SKILL.md` opening lines and verdict rules | [https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L111](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L111) |
| W-A18: inspect the rendered state and identify the target from what is actually rendered before acting | `SKILL.md` run plan, structure evidence before the keyboard traversal | [https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/SKILL.md#L28](https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/SKILL.md#L28) |
| W-A16: a claimed limitation carries evidence before it is reported as blocked | `SKILL.md` claim limits, screen reader Blocked with the reason named | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L292](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L292) |
| W-A17: native mobile QA belongs in a separate skill with its own device tooling | `SPEC.md` scope, native requests Blocked | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/ios-qa/SKILL.md](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/ios-qa/SKILL.md) |
| O-A1: platform is a required input, and a native request is Blocked rather than guessed | `SPEC.md` scope | [https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L18](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L18) |

## Local decisions

| Decision | Source | Why |
|---|---|---|
| Claim-limit table placed before the workflow | brief | The main failure mode is a sentence the evidence cannot support |
| Accessible name requires an accessibility-tree node, DOM attributes are labeled DOM inference | brief | Markup and computed name differ, and assistive technology reads the computed one |
| Real key input plus a focus readback for every keyboard claim | brief, local runner | Synthetic key events move no focus and trigger no browser defaults |
| Screen reader checks are Blocked | brief, installed skill capabilities | No verified screen reader control exists in this environment |
| No tool installation, and a named tool is reported with version and ruleset | brief | Automated rules cover a subset, and the brief bars external install recipes |
| Contrast limited to CSS-resolved colors unless sampling is approved | behavior of `getComputedStyle` | Stacked images and blends are not readable from computed styles |
| Status mapping: Blocked for unexecuted, Unknown for absent evidence, Fail for evidenced violations | parent instruction | Keeps a real defect visible even when a run ends early |
| Budget ledger, attempt policy, severity separate from confidence | brief | The prior art has none of these, as the research report states |

## Rejected material

| Rejected | Reason | Evidence |
|---|---|---|
| Copying any wording, table, rubric, or file layout from the prior art | `adshine/skills` has no license, so all rights reserved, and the brief forbids copying in any case | research report section 2 |
| An audit health score with rating bands | Averaging lets a failing accessibility dimension total as "Good", and re-running to improve the number becomes the goal | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L68-L77](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L68-L77) |
| A rating band that reads "WCAG AA fully met, approaches AAA" | It invites a conformance claim from a code read, which no evidence chain here supports | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L22](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L22) |
| A score with no Unknown or Not-run state | An unchecked dimension gets an invented number instead of honest coverage | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L68-L77](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L68-L77) |
| Command-router and repository-file coupling such as a required context script, `PRODUCT.md`, and `DESIGN.md` | This skill runs on `browser_use.run` plus files, and the brief prefers instructions over another framework | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L103](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L103) |
| Fixing markup or filing issues as part of the audit | Report-only by instruction, and the separate `qa` skill files issues | brief |
| Any gate that an empty evidence list can satisfy, such as zero focus steps or a tool summary with no findings | Absence of evidence scored as compliance is the exact fake pass the brief forbids | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/scripts/fsqa.py#L153-L189](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/full-stack-interaction-qa/scripts/fsqa.py#L153-L189) |
| Screenshots used as proof of names, roles, or reading order | A static image cannot carry that information | brief |
| O-R13: scoring dimensions the method never observed | An unexercised state is Not run or Unknown, not a number | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L82](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L82) |
| O-R14: the fix-and-rescore loop | This skill does not modify application code, and looping until a number turns green is the banned pattern | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L207](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L207) |
| O-R12: a score threshold read as acceptable for production | The same production-ready score the brief forbids, and it would hide a failed accessibility check | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L94](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L94) |
| O-R9: the conclusion form "the screenshot shows the UI looks correct" | A static image cannot carry names, roles, order, or keyboard behavior | [https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L61](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L61) |
| O-R6: severity expressed as error against warning against visual | That is a source channel, not user impact. Severity and confidence stay separate | [https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L87](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L87) |
| W-R6 and W-R7: a weighted health score and a start-at-100 deduction model | Deduction points are not evidence, and averaging hides a failed check | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L849](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L849) |
| W-R9: retry once to confirm a finding is not a fluke, with a passing retry erasing it | One passing retry never erases an observed failure | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L911](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L911) |
| O-R3: porting device capabilities into a web skill | No device control exists here, so native accessibility stays Blocked | [https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L96](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L96) |
| Copying the shared status and budget policy into this skill | `web-qa` owns `../web-qa/references/evidence-contract.md` | brief |

## Open gaps

1. Prior-art rows are complete for all seven reviewed sources. Not read at source: the upstream
   `callstack/agent-device` collection, the four tool reference files in `save-the-tokens`, and the
   vendored Callstack report template. Those gaps are recorded in the research files.
2. Accessibility-tree retrieval inside the browser run is unverified in this repository. The
   `source` field on each node and the claim mapping cover this, and a live check would let the
   wording be firmer.
3. No live validation run of this skill has happened yet. `SPEC.md` names the bounded live check.
4. `../web-qa/references/evidence-contract.md` did not exist when this skill was drafted.
5. The local `impeccable` install is 4.0.2 while the cited pin is HEAD, so line numbers can differ
   from the local copy.

## Changelog

| Date | Change |
|---|---|
| 2026-09-21 | First draft from private implementation brief, the installed browser-use skill, and the local runner implementation. |
| 2026-09-21 | Parent corrections: report the actual model, precondition classes, status mapping for Blocked, Unknown, and Fail, no universal risk scoring. |
| 2026-09-21 | Added prior-art provenance from private contracts prior-art report, with attributed adopted ideas and rejections, plus the systemic-pattern and false-positive rules. |
| 2026-09-21 | Finalized prior-art rows from private other-source prior-art report and `web-prior-art.md`: adopted O-A1, O-A11, O-A13, W-A16 to W-A18; rejected O-R3, O-R6, O-R9, O-R12 to O-R14, W-R6, W-R7, W-R9. No behavior was added to create a citation. |
