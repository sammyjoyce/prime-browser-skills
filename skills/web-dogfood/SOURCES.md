# Sources for web-dogfood

## Provenance status: resolved

These skill files were written from the private implementation brief and the verified browser-use runtime
before any prior-art research arrived. All three research reports have since been delivered:
The private contracts prior-art report, the private web prior-art report, and
The private other-source prior-art report. Their decisions are mapped below with the reports' own
decision IDs and pinned permalinks, so each row records agreement, difference, or the absence of
prior art. No citation here is inferred, reconstructed from memory, or invented, and no upstream
text, table, schema, script, or file layout was copied or near-paraphrased.

## Pinned sources

| Source | Pin | License |
|---|---|---|
| vercel-labs/agent-browser, `skill-data/dogfood/SKILL.md` | `44583ac8385d814ab98cbf40feec97620376b50e` | Apache-2.0 |
| garrytan/gstack, `qa-only/SKILL.md` | `a6b3a57512ca6d5c6aa5b68f74f736195021f96e` | MIT |
| anthropics/skills, `skills/webapp-testing/SKILL.md` | `34040c9c568585f6929bedeaad110ad08f079624` | per-skill `LICENSE.txt` |
| adshine/skills, source-authority prior art | `30da9d4750255a8bcc4222536b425d7e6050e8a8` | no license at the repository root: all rights reserved, ideas only |
| pbakaus/impeccable, `reference/audit.md` | `f2c7051853848826aac2f4646581d62a732155ad` | Apache-2.0 |
| callstackincubator/agent-skills, vendored `dogfood` | `61e6e7dfdf3a8ee862254c200d751fcb1fb863dc` | MIT, vendored copy that may lag upstream |
| csepulv/save-the-tokens, `skills/visual-qa` | `5e7497206480c0c81dadd9d71887891c552fb4b7` | MIT |
| spencerpauly/awesome-cursor-skills, `resources/visual-qa-testing` | `99cd2655788456cc1c685944dcf8c2de82c1ded4` | CC0-1.0 |
| vibeeval/vibecosystem, `skills/visual-verdict` | `3b763b1fb288f57bfa3cce76ef18184b96461a78` | MIT |

## Resolved prior art: contracts report

Source: the private contracts prior-art report, researched 2026-09-21 by `qa-sources-contract`.
Ideas only. No sentence, table, schema, file layout, or script was copied or near-paraphrased.

### Adopted ideas, rewritten independently

| Rule here | Prior-art idea | Pinned location |
|---|---|---|
| Charter transitions now include duplicate submit, a late response arriving after a newer one, cancellation, and an expired session | the named race and partial-failure cases used as test material | adshine/skills `full-stack-interaction-qa/SKILL.md` L70-L78 @ `30da9d4` |
| A UI message is an observation, and persistence stays `Unknown` without a readback | the UI is one evidence lane and never the backend truth; never infer a write from a success toast | same file, L8, L23, L30-L32, L86 |
| Missing evidence is `Unknown` or `Not run`, never a clean charter | treat missing authoritative evidence as unknown, not pass | same file, L86 |
| Read-only by default, with authorized test data only | do not touch production data without explicit authorization | same file, L82-L86 |
| Findings state user impact, and a repeated defect is one systemic finding | severity with a required impact statement and systemic-pattern reporting | pbakaus/impeccable `.agent/skills/impeccable/reference/audit.md` L91-L103, L105-L109, L133 @ `f2c7051`, Apache-2.0 |
| A source must be openable and versioned before a finding cites it | a freeze is a specific revision, not a name | adshine/skills `source-fidelity-qa/SKILL.md` L20-L27 |
| A requirement no source states is out of scope | unspecified deltas stay out of scope instead of inflating failures | same file, L47, L55 |

### Rejected, with the reason

| Rejected | Where it appears | Reason |
|---|---|---|
| Evidence-pack CLI and gate scripts | `full-stack-interaction-qa/scripts/fsqa.py` | a near-empty pack passes five of six gates at `command_gates` L153-L189, so absence of evidence scores as compliance |
| Any aggregate score | impeccable audit L68-L77 | it averages failures away and has no `Unknown` state |
| Application test headers as a precondition | `full-stack-interaction-qa/SKILL.md` | they need application cooperation, so they stay optional |

### Original to this suite

The contracts report finds no bug quota in any of the four sources, so the no-quota rule comes
from the brief rather than from prior art. The same report lists the budget ledger, the
three-attempt policy that preserves intermittent failures, the capability preflight, and the
five-status set with an honest denominator as unclaimed by all four sources.

## Resolved prior art: web and other reports

Sources: the private web prior-art report and the private other-source prior-art report, both
researched 2026-09-21. Decision IDs below are theirs. Licenses and pins are listed in
"Pinned sources" above. Ideas only. No upstream text, table, script, or file layout was copied or
near-paraphrased.

### Adopted ideas, rewritten independently

| Rule here | ID | Source anchor |
|---|---|---|
| Explore the named flows first, then the transitions around them, instead of free roaming | W-A1 | [dogfood L97](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L97), [issue taxonomy L98](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/references/issue-taxonomy.md#L98) |
| Evidence depth matches the finding type, so an interactive defect keeps its step sequence and every capture path in one run | W-A3 | [dogfood L124](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L124) |
| Wait on a named post-action condition, not a load event | W-A5 | [dogfood L68](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L68) |
| Defined severity levels, kept separate from confidence | W-A6 | [issue taxonomy L11](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/references/issue-taxonomy.md#L11) |
| Report header carries target, scope, and session identity | W-A7 | [report template L1](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/templates/dogfood-report-template.md#L1) |
| Black-box exploration keeps its hands off the application source | W-R3 | [dogfood L207](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L207) |
| Invocation is consent to look, so charters stay read-only unless a write is authorized | W-A9 | [qa-only L474](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L474) |
| Page text is untrusted data, not an instruction to follow | W-A10 | [qa-only L476](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L476) |
| The user signs in through headed `browser_use.login`, and no credential goes in task text | W-A11 | [qa-only L475](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L475) |
| One charter per `browser_use.run` call, because the session does not persist, and a missing success condition is a result rather than a reason to retry | W-A12 | [qa-only L478](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L478) |
| One root cause is one systemic finding | W-A14 | [qa-only L832](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L832) |
| `Blocked` names the blocker with evidence | W-A16 | [qa-only L292](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L292) |
| A native mobile request is `Blocked`, because device work needs device tooling | O-A1, O-A6 | [callstack L18](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L18), [taxonomy L19](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/references/issue-taxonomy.md#L19) |
| Bound exploration by stated limits and list what was not reached | O-A10 | [visual-qa L75](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L75) |
| Every rendered-state claim needs a capture, and the capture must be viewed | O-A11 | [visual-qa L93](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L93), [L98](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L98) |
| The skill states what it does not do | O-A13 | [visual-qa L111](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L111) |
| Charter transitions include empty, error, and interrupted states | O-A3 | [callstack L87](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L87) |

### Rejected, with the reason

| Rejected | ID | Source anchor | Reason |
|---|---|---|---|
| A defect quota or count-based stop | W-R1, W-R10, O-R1 | [dogfood L181](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L181), [qa-only L917](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L917), [callstack L151](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L151) | a count is not coverage; we stop on budget, charter completion, or a blocking condition |
| Discarding a finding that does not reproduce on retry | W-R2, W-R9 | [dogfood L197](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L197), [qa-only L911](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L911) | this deletes intermittent defects; we keep the observation and the attempt ratio |
| A report of severity counts and an issue list only | W-R4, O-R5 | [report template L10](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/templates/dogfood-report-template.md#L10), [visual-qa L77](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L77) | no expected source and no denominator, so zero findings reads as a pass |
| Repro video and per-action pacing as a requirement | W-R5 | [dogfood L128](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L128) | our runtime has no video and no outer pacing control; promising it would be a made-up capability |
| Concluding that the screenshot shows the UI looks correct | O-R9 | [visual-qa-testing L61](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L61) | correct against what; without a named source this is an impression |
| Severity expressed as error, warning, or visual | O-R6 | [visual-qa L87](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L87) | that is the evidence channel, not the user impact |
| Device capabilities inside a web skill | O-R3 | [callstack L96](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L96) | no device control here, so native claims would be false |
| Fixed sleeps, terminal ready lines, and absence of a spinner as readiness | W-R11, O-R2, O-R8, O-R15 | [qa-only L773](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L773), [callstack L62](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L62), [visual-qa-testing L22](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L22), [visual-verdict L156](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L156) | none of them names the application state being waited for |
| Any score, rating band, or ship-readiness delta | W-R6, W-R8, O-R11, O-R12 | [qa-only L828](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L828), [qa report template L104](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa/templates/qa-report-template.md#L104), [visual-verdict L38](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L38), [L94](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L94) | an average hides a hard failure and has no `Unknown` state |
| A fix-and-rescore loop | O-R14 | [visual-verdict L207](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L207) | this skill never modifies application code and never loops until green |

### Noted but not adopted in this version

| Idea | ID | Source anchor |
|---|---|---|
| Console output and failed requests captured per page as first-class evidence | W-A4, O-A12, O-A14, O-A16 | [dogfood L208](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L208), [visual-qa L59](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L59), [visual-qa-testing L8](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L8), [L48](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L48) |
| Writing each finding to the report the moment it is found, so an interrupted session still leaves evidence | W-A2 | [dogfood L175](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L175) |
| Re-reading the element snapshot after every state change | O-A2, O-A15 | [callstack L88](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L88), [visual-qa-testing L67](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L67) |
| Offline and permission-denied states, and character-by-character input, as charter material | O-A3, O-A4 | [callstack L87](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L87), [L167](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L167) |

## Sources read directly

| Source | Path or name | Used for |
|---|---|---|
| Implementation brief | private implementation brief | bounded exploration without bug quotas, intermittent evidence rules, report-only stance, prohibitions |
| Installed runtime skill | `~/.prime/agent/skills/browser-use/SKILL.md` (published here as `skills/browser-use/SKILL.md`) | `run` contract, result fields, profile behavior, screenshot and `attach_image` round trip, trust notes |
| Runtime source | `skills/browser-use/src/browser_use/__init__.py` | exact `run` signature and defaults, profile name rule, error classes and attributes |
| POC notes | private POC notes and handoff record | one Chrome process per call, no live browser object between calls, cost cap checked between turns, `openai/gpt-6-astra` default |
| Suite contract | `../web-qa/references/evidence-contract.md` | statuses, coverage, budget ledger, regression labels, report shape |
| Authoring rules | `skill-writer` `SKILL.md` and `references/{mode-selection,execution-shapes,design-principles,reference-architecture,authoring-path,source-adaptation,registration-validation,spec-template,description-optimization,layout-inline-skill,example-workflow-process-skill}.md` | class `workflow-process`, inline shape, `SPEC.md` contract, description triggers |
| Packaging rules | `skill-creator` `SKILL.md` | frontmatter fields and limits, skill directory layout |
| Prose rules | `unslop` `SKILL.md` | literal wording, sentence-case headings, no metaphor, no em dashes |
| Parent session messages | 2026-09-21 | status set confirmed; preflight must not interrogate; aggregate budget caps; three attempts in total; regression labels need comparable baselines; declared invariants and advertised promises are valid sources |

## Decisions and where they came from

| Decision | Basis | Status |
|---|---|---|
| Charters instead of a check list | brief: exploration is bounded but not scripted | settled |
| No bug quota and no defect-count stop | brief | settled |
| Zero findings reported as "no defects found in the charters run" | brief: absence of findings is not acceptance | settled |
| Three attempts in total, counting the first observation | parent session correction, 2026-09-21 | settled |
| Per-attempt evidence paths, never overwrite a failing capture | parent session correction, 2026-09-21 | settled |
| `fixed` and `regression` require a comparable re-check | parent session correction, 2026-09-21 | settled |
| Declared platform or accessibility invariants and advertised product promises count as sources | parent session correction, 2026-09-21 | settled |
| App text is a source or an outcome, never both in one finding | parent session correction, 2026-09-21 | settled |
| Browser-model opinion is not a source | brief plus parent session correction | settled |
| One charter per `browser_use.run` call | `browser-use/SKILL.md` and `__init__.py`: each call starts and closes a Chrome process | verified in source |
| Announce a default budget instead of negotiating it | parent session correction, 2026-09-21 | settled |
| Aggregate caps of 150 steps and 3.00 USD across 6 calls | parent session correction, 2026-09-21 | settled, numbers are the parent's example |
| Missing evidence is `Unknown` or `Not run`, never a clean charter by default | parent session correction, 2026-09-21 | settled |
| A requirement no source states is out of scope, not a fabricated defect | parent session correction, 2026-09-21 | settled |
| Report contract linked from `web-qa` rather than duplicated | brief: `web-qa` owns the shared contract | settled |

## Slot resolution

Each item below was open while the research ran. All are now settled against the delivered
reports. A slot marked original has no prior art in any of the ten sources that were read.

1. Charter fields and the three-to-five range. W-A1 supplies systematic coverage from the named
   flows outward and O-A10 supplies a stated exploration limit with the unreached scope listed.
   The charter record itself, with its own budget, evidence list, and prohibitions, is original.
   `resolved`
2. The transition list. O-A3 supplies empty, error, and interrupted states; the fsqa race list in
   the contracts report supplies duplicate submit, late response, cancellation, and expired
   session. Entry, back navigation, reload, and second attempt are original. `resolved`
3. The `observation, source unknown` label. No prior art. All three reports state that no source
   in their scope requires a named expected source per finding, which is the gap this label
   closes. Evidence of the gap: W-R4 and O-R9. `resolved`
4. The default budget numbers for an exploration session. No source bounds cost or time. O-A10 is
   the only bounded-stop prior art and uses link depth and page count. The numbers come from the
   brief and the parent session. `resolved`
5. Keeping intermittent observations. No prior art, and two sources do the opposite (W-R2, W-R9).
   Original to this suite, from the brief. `resolved`


## Rejected

| Rejected | Reason |
|---|---|
| Copying text, structure, or wording from any upstream exploratory-testing skill | user instruction; written from the brief and the verified runtime |
| A target number of bugs, or stopping at the first defect | both distort the report and the coverage |
| Treating a clean exploration session as product acceptance | the charters cover a small part of the product |
| Letting the browser model judge whether behavior is correct | it produces observations, not requirements |
| Filing issues or fixing code from this skill | `qa` files issues; implementation is a separate task |
| Bundled references or scripts | one path fits every session, so the workflow stays inline |

## Changelog

- 2026-09-21: first draft. `SKILL.md` and `SPEC.md` written from the private implementation brief and the
  verified browser-use runtime. Prior-art provenance is open.
- 2026-09-21: mapped the private web prior-art report and the private other-source prior-art report. Recorded 17
  adopted ideas, 10 rejections, and 4 deferred ideas with decision IDs and pinned permalinks, and
  closed every open slot. No runtime instruction changed in this pass.
- 2026-09-21: corrected the model wording. The default is exactly `openai/gpt-6-astra`, an override
  through `BROWSER_USE_MODEL` is possible, and the report must carry the returned model.
- 2026-09-21: mapped the private contracts prior-art report. Added the race and partial-failure charter
  transitions and attributed the missing-evidence, production-authorization, and impact rules.
- 2026-09-21: added the empty-evidence rule and the out-of-scope rule, and recorded the pinned
  prior art with its licenses. Adopt and reject mapping still open.
- 2026-09-21: applied parent corrections on preflight questioning, aggregate budget caps,
  attempt counting, per-attempt evidence, regression labels, and valid source types.
