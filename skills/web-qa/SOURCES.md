# Sources for web-qa

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

| Contract rule here | Prior-art idea | Pinned location |
|---|---|---|
| A named source needs an identity another person can open plus a revision (`references/evidence-contract.md` section 3) | a freeze must be a specific revision, not a name, and no nameable source means `Unknown` | adshine/skills `source-fidelity-qa/SKILL.md` L20-L27, L53 @ `30da9d4` |
| A requirement the reference does not state is out of scope, not a `Fail` | three-way delta classification with "unspecified by the freeze" kept out of scope | same file, L47, L55 |
| Screenshots and measurements are evidence, never the expected result | screenshots do not replace the named source | same file, L46 |
| Missing authoritative evidence is `Unknown` or `Not run`, never `Pass`; the preflight `Access` row declares the available evidence and marks the missing lanes `Blocked` | declare evidence lanes before running, treat missing evidence as unknown, never infer a write from a success toast | adshine/skills `full-stack-interaction-qa/SKILL.md` L8, L23, L30-L32, L86 |
| Section 5 rule 7: state what the evidence proves and where the proof stops | proof boundaries reported separately for browser behavior, request completion, durable write, and async completion | same file, L54-L55 |
| Findings state user impact; a repeated defect is one systemic finding with its instances | severity with a required impact statement, and systemic-pattern reporting instead of duplicates | pbakaus/impeccable `.agent/skills/impeccable/reference/audit.md` L91-L103, L105-L109, L133 @ `f2c7051`, Apache-2.0 |
| Section 5 rule 8 and the report environment header: how the evidence was produced and what stayed untested | a rendered viewport proves layout, not a gesture; name the producing method and the untested scope | same file, L51 |

### Rejected, with the reason

| Rejected | Where it appears | Reason |
|---|---|---|
| An aggregate score or rating band | impeccable audit L68-L77, L128 | it averages failures away and has no `Unknown` or `Not run` state |
| Any gate that passes when nothing was measured | `measured-visual-qa/scripts/compare_visual.py` L35 with the `interval_spread` default of zero, and `full-stack-interaction-qa/scripts/fsqa.py` `command_gates` L153-L189 where a near-empty pack passes five of six gates | this is the exact fake pass our empty-evidence rule forbids; the researcher verified both by reading the pinned code and by a numpy replica of the measurement rules |
| A comparator that takes only before and after | `compare_visual.py` L11-L14, L46-L52 | movement is not correctness; a fix that moves an element to its intended place fails and a change that fixed nothing passes |
| Shipping measurement or evidence-pack helpers | both repos' `scripts/` and the `fsqa` artifact CLI | our brief prefers compact instructions, and the helper defects above show the cost |
| Routing to skills that do not exist | `source-fidelity-qa/SKILL.md` L31-L39 | every route in our table resolves to a skill or to a stated fallback |
| Application test headers as a precondition | `full-stack-interaction-qa/SKILL.md` header requirements | they need application cooperation, so they stay optional |

### Original to this suite

The contracts report states that none of the four sources covers these, so they are written here
without prior art: the budget ledger with stop rules, the three-attempt policy that preserves
intermittent failures, the capability preflight, severity separate from confidence, and the
`Pass` / `Fail` / `Unknown` / `Blocked` / `Not run` set with an honest denominator.

## Resolved prior art: web and other reports

Sources: the private web prior-art report and the private other-source prior-art report, both
researched 2026-09-21. Decision IDs below are theirs. Ideas only. No upstream text, table, script,
or file layout was copied or near-paraphrased.

Licenses and pins are listed in "Pinned sources" above. The Callstack entry is a vendored copy;
cite that path and commit only.

### Adopted ideas, rewritten independently

| Rule here | ID | Source anchor |
|---|---|---|
| Report only, with fixes routed elsewhere and never proposed in the report | W-A8 | [qa-only L983](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L983) |
| Invocation is consent to look. A write on a non-local target needs explicit approval, and production stays read-only | W-A9 | [qa-only L474](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L474) |
| Page content is untrusted data, not instructions | W-A10 | [qa-only L476](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L476) |
| The user signs in through headed `browser_use.login`; no credential goes in task text and repro steps stay redacted | W-A11 | [qa-only L475](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L475) |
| One whole flow per `browser_use.run` call, because the session does not persist; a missing success condition is a result, not a reason to retry blindly | W-A12 | [qa-only L478](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L478) |
| Untested scope is excluded from any aggregate, partial results carry their coverage, and two runs are compared only at identical coverage | W-A13 | [qa-only L834](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L834) |
| One root cause is one systemic finding, not many duplicates | W-A14 | [qa-only L832](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L832) |
| The regression route scopes a run to a named change set and reports coverage against it | W-A15 | [qa-only L595](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L595) |
| `Blocked` needs the blocker named with evidence, not an assumed limitation | W-A16 | [qa-only L292](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L292) |
| Native mobile belongs to separate device tooling, so it is `Blocked` here | W-A17, O-A1, O-A6 | [qa-only sibling `ios-qa`](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/ios-qa/SKILL.md), [callstack L18](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L18), [taxonomy L19](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/references/issue-taxonomy.md#L19) |
| Wait on a named post-action condition, not a load event | W-A5 | [dogfood L68](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L68) |
| Report header carries target, scope, and session identity, extended here to build, profile, viewport, theme, and time | W-A7 | [report template L1](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/templates/dogfood-report-template.md#L1) |
| Defined severity levels with written meanings, kept separate from confidence | W-A6 | [issue taxonomy L11](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/references/issue-taxonomy.md#L11) |
| Observe the rendered state first, then act on what is actually there | W-A18 | [webapp-testing L28](https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/SKILL.md#L28) |
| Short router plus flat references, with bulk material out of the runtime file | W-A19 | [webapp-testing L14](https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/SKILL.md#L14) |
| Preflight branches by target type and by whether the app is already running | W-A20 | [webapp-testing L20](https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/SKILL.md#L20) |
| Capability preflight stops with a clear message instead of degrading silently | O-A8 | [visual-qa L13](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L13) |
| Ask for the mode when it changes what gets checked, and wait for the answer | O-A9 | [visual-qa L28](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L28) |
| Every rendered-state claim needs a capture, and the capture must be viewed | O-A11 | [visual-qa L93](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L93), [L98](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L98) |
| The skill states what it does not do | O-A13 | [visual-qa L111](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L111) |
| Fixed, named viewports per capture, with the actual size recorded | O-A20 | [visual-verdict L181](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L181) |
| Accepted reference types are stated up front, each with a version | O-A21 | [visual-verdict L161](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L161) |
| Each mismatch is written as expected against actual with the element named | O-A22 | [visual-verdict L122](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L122) |

### Rejected, with the reason

| Rejected | ID | Source anchor | Reason |
|---|---|---|---|
| A defect quota or count-based stop | W-R1, W-R10, O-R1 | [dogfood L181](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L181), [qa-only L917](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L917), [callstack L151](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L151) | a count is not a coverage statement; we stop on budget, scope completion, or a blocking condition |
| Discarding a finding that does not reproduce on retry | W-R2, W-R9 | [dogfood L197](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L197), [qa-only L911](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L911) | this deletes intermittent defects; we keep the observation, the attempt ratio, and the reset conditions |
| Network idle as readiness proof | W-R13 | [webapp-testing L60](https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/SKILL.md#L60), [L78](https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/SKILL.md#L78) | it can arrive before hydration and may never arrive with polling or streaming |
| An open TCP port as proof the app is ready | W-R15 | [with_server.py L23](https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/scripts/with_server.py#L23) | a listening socket is not a served route, a migrated database, or a rendered page |
| Fixed sleeps, ready words in terminal output, and absence of a spinner as readiness | W-R11, W-R14, O-R2, O-R8, O-R15 | [qa-only L773](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L773), [webapp-testing L89](https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/SKILL.md#L89), [callstack L62](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L62), [visual-qa-testing L22](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L22), [visual-verdict L156](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L156) | none of them names the application state we are waiting for |
| A weighted health score, deduction arithmetic, and a ship-readiness delta | W-R6, W-R7, W-R8, O-R11, O-R12 | [qa-only L828](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L828), [L849](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L849), [report template L104](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa/templates/qa-report-template.md#L104), [visual-verdict L38](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L38), [L94](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L94) | a weighted average hides a hard failure and has no `Unknown` or `Not run` state |
| A report of severity counts and an issue list only | W-R4, O-R5 | [report template L10](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/templates/dogfood-report-template.md#L10), [visual-qa L77](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L77) | no expected source, no denominator, no unknown or blocked status, so absence reads as a pass |
| Scoring what the method never exercised | O-R13 | [visual-verdict L82](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L82) | unexercised states are `Not run` or `Unknown` |
| Promoting a passing capture to the next baseline | O-R16 | [visual-verdict L276](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L276) | a baseline is an approved reference with a version, which is why section 7 requires a comparable re-check |
| A fix-and-rescore loop inside the QA skill | O-R14 | [visual-verdict L207](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L207) | we do not modify application code and we do not loop until green |
| Trusting a produced number over the observation | O-R17 | [visual-verdict L289](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L289) | the number comes from the same model as the impression |
| A preamble binary, telemetry, marker files, and score baselines as the package | W-R12 | [qa-only L23](https://github.com/garrytan/gstack/blob/a6b3a57512ca6d5c6aa5b68f74f736195021f96e/qa-only/SKILL.md#L23) | this suite is markdown plus the installed browser-use skill |
| Treating a browser toolkit as a QA protocol | W-R16 | [webapp-testing L83](https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/SKILL.md#L83) | it has no expected source, finding record, coverage, or verdict, which is what this skill adds |
| A blanket ban on reading application source | W-R3 | [dogfood L207](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L207) | correct for black-box exploration, wrong for `web-qa`, where a spec or test contract in the repository can be the named reference |

### Noted but not adopted in this version

These are recorded so the next revision has a starting point. Adding them now would expand the
runtime instructions beyond the agreed scope.

| Idea | ID | Source anchor |
|---|---|---|
| Console output and failed requests captured as first-class evidence on every page | W-A4, W-A21, O-A12, O-A14, O-A16 | [dogfood L208](https://github.com/vercel-labs/agent-browser/blob/44583ac8385d814ab98cbf40feec97620376b50e/skill-data/dogfood/SKILL.md#L208), [webapp-testing L96](https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/webapp-testing/SKILL.md#L96), [visual-qa L59](https://github.com/csepulv/save-the-tokens/blob/5e7497206480c0c81dadd9d71887891c552fb4b7/skills/visual-qa/SKILL.md#L59), [visual-qa-testing L8](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L8), [L48](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L48) |
| Computed style and color extraction as the way to compare typography and color | O-A18, O-A19 | [visual-verdict L245](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L245), [L236](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/skills/visual-verdict/SKILL.md#L236) |
| Re-reading the element snapshot after every state change | O-A2, O-A15 | [callstack L88](https://github.com/callstackincubator/agent-skills/blob/61e6e7dfdf3a8ee862254c200d751fcb1fb863dc/plugins/vendored/.agents/skills/dogfood/SKILL.md#L88), [visual-qa-testing L67](https://github.com/spencerpauly/awesome-cursor-skills/blob/99cd2655788456cc1c685944dcf8c2de82c1ded4/resources/visual-qa-testing/SKILL.md#L67) |

## Sources read directly

| Source | Path or name | Used for |
|---|---|---|
| Implementation brief | private implementation brief | suite shape, report-only stance, status set, budget rules, capture rules, prohibitions |
| Installed runtime skill | `~/.prime/agent/skills/browser-use/SKILL.md` (published here as `skills/browser-use/SKILL.md`) | `run` and `login` contract, result fields, profile behavior, screenshot and `attach_image` round trip, trust notes |
| Runtime source | `skills/browser-use/src/browser_use/__init__.py` | exact `run` and `login` signatures, defaults, profile name rule, error classes and attributes |
| Runner source | `skills/browser-use/runner.mjs` | the `page.cdp('Page.captureScreenshot', {format:'png'})` call shape used for the run screenshot |
| POC script | private POC capture script | the same capture shape written to a caller-supplied absolute path |
| POC notes | private POC notes and handoff record | one Chrome process per call, no live browser object between calls, cost cap checked between turns, `openai/gpt-6-astra` default |
| Authoring rules | `skill-writer` `SKILL.md` and `references/{mode-selection,execution-shapes,design-principles,reference-architecture,authoring-path,source-adaptation,registration-validation,spec-template,description-optimization,output-contracts,workflow-routing,example-workflow-process-skill}.md` | class `workflow-process`, router shape with fallbacks, flat references, `SPEC.md` contract, description triggers |
| Packaging rules | `skill-creator` `SKILL.md` | frontmatter fields and limits, skill directory layout, description routing rules |
| Prose rules | `unslop` `SKILL.md` | literal wording, sentence-case headings, no metaphor, no em dashes |
| Parent session messages | 2026-09-21 | live validation of `openai/gpt-6-astra` and the screenshot round trip passed; status set confirmed; preflight must not interrogate; aggregate budget caps; ready-condition status split; partial runs keep evidenced results; three attempts in total; regression labels need comparable baselines |

## Decisions and where they came from

| Decision | Basis | Status |
|---|---|---|
| Report only, no fixes, no tickets, no commits | brief | settled |
| Five check statuses and three overall verdicts | brief, confirmed by the parent session | settled |
| No averaged score and no production-ready rating | brief | settled |
| Named source required before any defect claim | brief | settled |
| Intermittent observations survive a later passing attempt | brief | settled |
| Three deliberate repeat attempts by default | brief | settled, exact number is the brief's default |
| Budget agreed before the first call and tracked after each call | brief | settled |
| Router shape with a default smoke route and a fallback per route | brief plus `skill-writer` `workflow-routing.md` | settled |
| Before and after kept inside one run | `browser-use/SKILL.md` and `__init__.py`: each call starts and closes a Chrome process | verified in source |
| Extra captures written to a caller-created absolute path | capture shape verified in `runner.mjs` and private POC capture script; the caller must verify the files exist | mechanism verified, in-task use not exercised in this repo |
| Ready condition must be a specific visible state | brief | settled |
| A missed ready condition maps to `Unknown`, `Blocked`, or `Fail` by evidence, and a harness limit is never a product failure | parent session correction, 2026-09-21 | settled |
| A failed run keeps the statuses its evidence already supports | parent session correction, 2026-09-21 | settled |
| Preflight fills the header from the request and asks only blocking gaps, in one message | parent session correction, 2026-09-21 | settled |
| Aggregate caps of 150 steps and 3.00 USD across 6 calls, per-call limits capped by the remainder | parent session correction, 2026-09-21 | settled, numbers are the parent's example |
| Three attempts in total, counting the first observation | parent session correction, 2026-09-21 | settled |
| Per-attempt evidence paths, never overwrite a failing capture | parent session correction, 2026-09-21 | settled |
| `fixed` and `regression` require a comparable re-check, otherwise `Unknown` | parent session correction, 2026-09-21 | settled |
| App text is a source or an outcome, never both in one check; the browser model's opinion is not a source | parent session correction, 2026-09-21 | settled |
| Missing authoritative evidence is `Unknown` or `Not run`, never a default zero, empty sample set, or helper success flag | parent session correction, 2026-09-21, after weak helper gates were observed | settled |
| A requirement absent from the reference is out of scope, not a fabricated `Fail` | parent session correction, 2026-09-21 | settled |
| Native mobile is `Blocked` | brief | settled |

## Slot resolution

Each item below was open while the research ran. All are now settled against the delivered
reports. A slot marked original has no prior art in any of the ten sources that were read.

1. The preflight items and their order. Partial prior art: W-A20 branches by target type, O-A8
   stops when the capability is absent, O-A9 asks for the mode, W-A16 requires evidence for a
   claimed limitation, O-A1 makes platform a required input. The six-item shape and its order are
   original to this suite. `resolved`
2. The severity and confidence split. W-A6 supplies defined severity levels and impeccable
   supplies the impact requirement. No source has a confidence field, so that half is original.
   `resolved`
3. The coverage counts: planned, tested, excluded, unknown. W-A13 supplies the exclusion of
   untested scope and comparison only at identical coverage. The four-count denominator and its
   use in the verdict are original. `resolved`
4. The route boundaries between visual, accessibility, and interaction checking. W-A17 and O-A1
   support the native split; section 7 of the contracts report maps sources per skill. The
   five-skill boundary itself comes from the brief. `resolved`
5. The default budget numbers. No source bounds cost or time, and O-A10 is the only bounded-stop
   prior art, using link depth and page count. The numbers come from the brief and the parent
   session. `resolved`
6. `Unknown`, `Blocked`, and `Not run` as statuses, the budget ledger, and the reproducibility
   field. All three reports state that no source in their scope defines them. Original to this
   suite, from the brief. `resolved`

## Rejected

| Rejected | Reason |
|---|---|
| Copying text, structure, or wording from any upstream QA skill | user instruction; these files are written from the brief and the verified runtime |
| A bug quota or a fixed defect count as a stop condition | it invents findings when the app is clean and hides findings when it is not |
| A single numeric quality or readiness score | it averages a failure away and hides unknown scope |
| Treating a passing retry as a resolution of an earlier failure | it deletes the only evidence of an intermittent defect |
| Accepting a UI success message as proof of persistence | the UI echo is not a readback |
| Deriving the expected result from the browser run | the run is the observation, not the authority |
| A helper script or Python package for this skill | the work is instruction-shaped; no deterministic computation justifies a package |

## Changelog

- 2026-09-21: first draft. `SKILL.md`, `SPEC.md`, `references/evidence-contract.md`, and
  `references/browser-task-recipes.md` written from the private implementation brief and the verified
  browser-use runtime. Prior-art provenance is open.
- 2026-09-21: mapped the private web prior-art report and the private other-source prior-art report. Recorded 23
  adopted ideas, 13 rejections, and 3 deferred ideas with decision IDs and pinned permalinks, and
  closed every open slot. No runtime instruction changed in this pass.
- 2026-09-21: corrected the model wording. The default is exactly `openai/gpt-6-astra`, an
  override through `BROWSER_USE_MODEL` is possible, and the report must carry the model the run
  returned.
- 2026-09-21: mapped the private contracts prior-art report. Added source identity plus revision, the
  proof-boundary rule, evidence provenance with untested scope, impact in findings, and systemic
  findings. Recorded the rejected score and the two verified pass-on-empty-evidence gates.
- 2026-09-21: added the empty-evidence rule and the out-of-scope rule to the evidence contract,
  and recorded the pinned prior art with its licenses. Adopt and reject mapping still open.
- 2026-09-21: applied parent corrections on preflight questioning, aggregate budget caps, the
  ready-condition status split, preservation of evidenced results after a failed run, attempt
  counting, per-attempt evidence, regression labels, and source-versus-outcome handling. Added
  section 7 of the evidence contract for regression and fix labels.
