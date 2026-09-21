# Sources

Provenance for `web-visual-qa`. Runtime files hold no source quotes and no copied structure.

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
| A named frozen reference, or the verdict is Unknown, never "looks good" | `SKILL.md` preconditions and verdict rules | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/source-fidelity-qa/SKILL.md#L27](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/source-fidelity-qa/SKILL.md#L27) |
| A property the reference does not specify is out of scope, not a Fail | `SKILL.md` verdict rules, `references/measurement-protocol.md` status mapping | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/source-fidelity-qa/SKILL.md#L55](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/source-fidelity-qa/SKILL.md#L55) |
| Screenshots are one evidence lane, not the reference | `SKILL.md` evidence capture | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/source-fidelity-qa/SKILL.md#L46](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/source-fidelity-qa/SKILL.md#L46) |
| Reconcile the DOM box, the painted extent, and the perceived container when a layout looks wrong | `references/measurement-protocol.md`, "Three readings when a layout looks wrong" | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L30-L48](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L30-L48) |
| Stated CSS-pixel tolerances instead of a similarity percentage | `references/measurement-protocol.md` tolerance table | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L83-L84](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L83-L84) |
| A person must inspect the image after any automated measurement | `SKILL.md` evidence capture, `attach_image` requirement | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L72](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L72) |
| Freeze the measurement specification across before and after | `references/measurement-protocol.md`, "Same spec before and after" | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L73](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L73) |
| Do not compare captures across browsers, fonts, operating systems, zoom, or device pixel ratio without accounting for it | same section | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L70](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L70) |
| A stale asset is a deployment defect, not visual evidence | `SKILL.md` verdict rules | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L54-L56](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/SKILL.md#L54-L56) |
| Say what produced the evidence and what stayed untested, because a rendered viewport proves layout and not a gesture | `SKILL.md` responsive scope and report shape | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L51](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L51) |
| Web-only scope with native platforms routed elsewhere | `SKILL.md` responsive scope | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L5](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L5) |
| O-A11: every claim about rendered state needs a capture, and the excuses "markup looks right" or "already verified in code" are refused | `SKILL.md` evidence capture, `attach_image` before any image claim | [https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L93](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L93) |
| O-A13: the skill states what it does not do, including no auto-fixing and no health score | `SKILL.md` opening lines and verdict rules | [https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L111](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L111) |
| O-A17: re-capture after an interaction so the resulting state is evidenced, not only the starting state | `SKILL.md` evidence capture, one file per variant and per intermediate state | [https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L58](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L58) |
| O-A18: compare typography from computed styles rather than from pixels | `references/measurement-protocol.md` metric table | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L245](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L245) |
| O-A19: extract the computed color and report reference against actual | `references/measurement-protocol.md` metric table and color limits | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L236](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L236) |
| O-A20: fix the responsive widths in advance and record the exact viewport per capture | `SKILL.md` run plan and responsive scope, `references/render-controls.md` readback | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L181](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L181) |
| O-A21: state the accepted reference types up front, such as an exported design image, an approved capture, or another running build | `SKILL.md` preconditions | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L161](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L161) |
| O-A22: write each mismatch as expected against actual with the element named | `SKILL.md` checks table, `references/evidence-examples.md` | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L122](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L122) |
| O-A1: platform is a required input, and a native request is Blocked rather than guessed | `SKILL.md` responsive scope | [https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L18](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L18) |
| W-A12: one whole flow in one call, because the session does not persist between calls | `SKILL.md` browser call contract | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L478](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L478) |

## Local decisions

| Decision | Source | Why |
|---|---|---|
| Readback proof for every render condition | local runner plus brief | Only the capture call is verified in this repository, so requested emulation needs measured confirmation |
| One scenario per run, before and after inside one run | installed skill profile semantics | A new call is a new Chrome process with no tabs or unsaved state |
| Different profiles for parallel variants | installed skill | One profile has one owner and a second caller fails |
| Report `result["model"]` | parent instruction | The default is exactly `openai/gpt-6-astra`, an environment override is possible, and the report must state what ran |
| Qualitative checks allowed with a written criterion and viewed evidence | parent instruction | Real defects such as clipping have no natural number, and inventing one is worse |
| Budget ledger, attempt policy, severity separate from confidence | brief | The prior art has none of these, as the research report states |

## Rejected material

| Rejected | Reason | Evidence |
|---|---|---|
| Copying any wording, table, rubric, or file layout from the prior art | `adshine/skills` has no license, so all rights reserved, and the brief forbids copying in any case | research report section 2 |
| Porting the upstream measurement helper scripts | Five reproduced defects, listed below | research report section 4 |
| Painted-pixel bounding boxes trusted without a DOM measurement | The foreground rule keeps bright pixels, so on a light theme it selects the background and returns the crop box as the "painted center" | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/measure_visual.py#L30-L48](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/measure_visual.py#L30-L48) |
| Whitespace-based rule or rhythm detection | The same polarity rule reports white background bands as rules, producing four rules where three exist | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/measure_visual.py#L51-L75](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/measure_visual.py#L51-L75) |
| Any gate that a zero-sample statistic can satisfy | An empty interval list collapses the spread to `0` and the comparison reports a pass, which is measuring nothing and scoring it perfect | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/compare_visual.py#L35](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/compare_visual.py#L35) |
| Before-and-after center shift as the acceptance metric | The comparator takes no expected value, so a no-op passes and a correct fix that moves a glyph to its intended position fails | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/compare_visual.py#L46-L52](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/compare_visual.py#L46-L52) |
| Recording the device pixel ratio without applying it | Device-pixel deltas were compared against CSS-pixel tolerances, so the real gate was half or a third of the documented one | [https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/measure_visual.py#L88](https://github.com/adshine/skills/blob/30da9d4750255a8bcc4222536b425d7e6050e8a8/measured-visual-qa/scripts/measure_visual.py#L88) |
| An audit health score with rating bands | Averaging lets a failing dimension total as "Good", and the score becomes the goal | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L68-L77](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L68-L77) |
| A score with no Unknown or Not-run state | Every dimension must take a number, so an unchecked dimension gets an invented one | [https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L68-L77](https://github.com/pbakaus/impeccable/blob/f2c7051853848826aac2f4646581d62a732155ad/.agent/skills/impeccable/reference/audit.md#L68-L77) |
| Routing to skills that do not exist | The prior art routes to unshipped siblings; every route here resolves to an installed skill or to an explicit Blocked | research report section 3 |
| A Figma adapter | No Figma capability exists in this runtime; a Figma file is one possible user-supplied reference | research report section 3 |
| O-R11 and O-R12: dimension scores with fixed weights, and a score threshold where 90 and above reads as acceptable for production | A missing critical element can sit inside a small weight, so a broken page still totals in the eighties. This is the production-ready score the brief forbids | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L49](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L49) and [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L94](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L94) |
| O-R14: the fix-and-rescore loop with a maximum iteration count | This suite does not modify application code, and looping until the number turns green is the banned pattern | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L207](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L207) |
| O-R13: scoring dimensions the method never observed, such as interactive states judged from still images | An unexercised state is Not run or Unknown, not a number | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L82](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L82) |
| O-R16: promoting a passing capture to the next baseline automatically | A baseline is an approved reference with a version, not whatever scored well last time | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L276](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L276) |
| O-R17: the closing instruction to trust the number over the impression | The same model produces both, so the number adds false precision rather than independent evidence | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L289](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L289) |
| O-R15: readiness expressed as "no spinners visible" | Absence of a spinner is not presence of the expected content | [https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L156](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L156) |
| O-R9: the conclusion form "the screenshot shows the UI looks correct" | Correct against what? With no named reference this is an impression | [https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L61](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L61) |
| O-R10: a viewport resize call as the responsive mechanism | The Python API has no resize option, so viewport changes live inside the task text and each capture reports its measured size | [https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L68](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L68) |
| O-R5: a per-page report of URL, screenshot, console, network, and a count summary | With no expected source a visual finding has nothing to be wrong against | [https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L77](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L77) |
| O-R3: porting device capabilities such as device sessions, native video, and application logs into a web skill | This runtime has no device control, so native iOS or Android stays Blocked | [https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L96](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L96) |
| W-R6 and W-R8: a weighted health score out of 100 and a ship-readiness score block | Averaging lets a critical failure move the total by a few points | [https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L876](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L876) |
| Copying the shared status and budget policy into this skill | `web-qa` owns `../web-qa/references/evidence-contract.md` and duplication would drift | brief |

## Open gaps

1. Prior-art rows are complete for all seven reviewed sources. Not read at source: the upstream
   `callstack/agent-device` collection, the four tool reference files in `save-the-tokens`, and the
   vendored Callstack report template. Those gaps are recorded in the research files.
2. Emulation calls beyond `Page.captureScreenshot` are unverified in this repository. The readback
   requirement covers this, and a live check would let the wording be firmer.
3. No live validation run of this skill has happened yet. `SPEC.md` names the bounded live check.
4. `../web-qa/references/evidence-contract.md` did not exist when this skill was drafted. The
   header fallback covers a missing file, and the link needs re-verification after web-qa lands.
5. The local `impeccable` install is 4.0.2 while the cited pin is HEAD, so line numbers can differ
   from the local copy.

## Changelog

| Date | Change |
|---|---|
| 2026-09-21 | First draft from private implementation brief, the installed browser-use skill, and the local runner implementation. |
| 2026-09-21 | Parent corrections: report the actual model, precondition classes, status mapping for Blocked, Unknown, and Fail, qualitative criteria allowed, no universal risk scoring. |
| 2026-09-21 | Added prior-art provenance from private contracts prior-art report, with attributed adopted ideas and defect-backed rejections. |
| 2026-09-21 | Finalized prior-art rows from private other-source prior-art report and `web-prior-art.md`: adopted O-A1, O-A11, O-A13, O-A17 to O-A22, W-A12; rejected O-R3, O-R5, O-R9 to O-R17, W-R6, W-R8. No behavior was added to create a citation. |
