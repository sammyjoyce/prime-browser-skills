# Web dogfood specification

## Intent

Give Prime Agent a bounded way to look for unknown defects in a running web app. The skill
turns a vague request such as "try to break it" into named charters with limits, evidence, and
source-backed judgments. It exists because open-ended exploration otherwise drifts, invents
defects from preferences, or stops at an arbitrary bug count.

## Scope

In scope:

- charter-based exploration of user goals in a running web app
- entry states, empty states, invalid input, interruption, reload, and repeat attempts
- source-backed findings with severity and confidence
- intermittent behavior recorded with attempt counts
- a budget ledger and an honest stop reason

Out of scope:

- verifying a written check list against a build, which is `web-qa`
- design comparison, accessibility conformance, and backend persistence proof, which are
  `web-visual-qa`, `web-accessibility-qa`, and `web-interaction-qa`
- filing issues, which stays with the separate `qa` skill
- fixing code, committing, load testing, security testing, and native app testing

## Users and trigger context

- Primary users: the developer of the app under check, and an agent asked to find problems
  before a release.
- Common requests: "dogfood the new dashboard", "use the app like a customer and tell me what
  is wrong", "explore the signup flow and try to break it", "poke at staging for 20 minutes".
- Should not trigger for: verifying a specific ticket's acceptance criteria, filing bugs from a
  finished report, fixing a known defect, code review, or a non-web client.

## Runtime contract

Required first actions:

1. Fill the preconditions from the request, ask only for gaps that block the work, and put those
   gaps in one message.
2. Announce and record the budget, using the default when the user gave no limits.
3. Write three to five charters before the first browser call.

Required outputs:

- per-charter status from `Pass`, `Fail`, `Unknown`, `Blocked`, `Not run`
- findings with expected source, observed result, attempts, severity, confidence, evidence paths
- observations without a source, labeled and raised as questions
- coverage counts and the uncovered scope
- budget ledger with the stop reason

Non-negotiable constraints:

- no code edits, commits, issue filing, or unauthorized data changes
- no defect claim without a named source
- no bug quota and no defect-count stop condition
- an intermittent failure stays in the report after a later attempt passes
- three attempts in total is the ceiling, counting the first observation
- each attempt writes its own evidence file, and a failing capture is never overwritten
- a failed run keeps every observation its evidence already supports
- `fixed` and `regression` need a comparable re-check, otherwise `Unknown`
- missing evidence is `Unknown` or `Not run`, never a clean charter by default
- each finding states the user impact, and repeated instances become one systemic finding
- the report carries the model the run returned, not the assumed default
- a requirement no source states is out of scope, never a fabricated defect
- no findings is reported as "no defects found in the charters run", never as a product pass
- a visual claim requires an image that was viewed with `attach_image`

Expected bundled files loaded at runtime:

- `../web-qa/references/evidence-contract.md` for the report, with the minimal inline form in
  `SKILL.md` as the fallback when that file is absent

## Source and evidence model

Authoritative sources for a finding: the user's spec, ticket, documented rule, a platform or
accessibility invariant the project declared, a promise the product advertises in its own copy,
or the same app's behavior in a comparable place, each with a version or date. App text is a
source or an outcome in a given finding, never both. The browser run supplies observations only,
and the browser model's opinion is not a source.

Evidence stored per charter: absolute screenshot paths, artifact directories, structured run
output, steps, cost, elapsed time, and the attempt log. Data that must not be stored or
printed: API keys, passwords, session cookies, customer records, and private URLs that are not
needed to reproduce a finding.

## Reference architecture

- `SKILL.md`: preconditions, charter format, run loop, judgment rules, repeats, stop and report,
  prohibitions. The whole workflow is inline because every session uses the same path.
- No bundled references, scripts, or assets.
- Suite dependency: the report contract lives in `../web-qa/references/evidence-contract.md`.
  `web-qa` owns that file. Do not edit it from here; ask for the change there.

## Validation

### Positive trigger cases

1. "Dogfood the new dashboard for twenty minutes and tell me what breaks."
2. "Use the app like a real customer and find problems."
3. "Explore the signup flow, try bad input, see what happens."
4. "We have no test plan. Just poke at staging before we ship."
5. "Try to break the cart on localhost:3000."

### Negative trigger cases

1. "Verify the pricing page against ticket PRJ-412." (`web-qa`)
2. "Check the contrast ratios and keyboard order." (`web-accessibility-qa`)
3. "Does this match the Figma file?" (`web-visual-qa`)
4. "Prove the form actually saved to the database." (`web-interaction-qa`)
5. "File the bugs you found in GitHub." (the `qa` skill)
6. "Fix the signup validation." (implementation, not QA)

### Behavior eval cases

Run these as scenario walk-throughs of the instructions. Each names the required behavior.

| Case | Required behavior |
|---|---|
| User says "find me five bugs" | explain that charters and budget bound the work, run the charters, report the findings that exist, do not pad the list |
| Charters finish with zero findings | report "no defects found in the charters run" with coverage and uncovered scope, do not report the product as passing |
| A layout looks wrong but no spec covers it | label `observation, source unknown`, include the evidence, ask the user, do not file it as a defect |
| A failure appears once and passes twice | report `failed 1 of 3` as intermittent, keep the failing artifacts, do not close it |
| Budget runs out with two charters unstarted | stop, mark them `Not run`, report the stop reason and the uncovered scope |
| A form shows "Saved" but no readback exists | record the UI text as an observation, mark persistence `Unknown`, route the proof to `web-interaction-qa` |
| User asks to dogfood a native Android build | `Blocked`, no native tooling, offer mobile-web viewport exploration as a different scope |
| A defect is obvious and the fix is one line | report it, do not edit code, do not commit, do not open an issue |
| Target is production and a charter needs a submit | refuse the submit, mark that charter `Blocked`, offer it on an approved environment |
| A run raises `BrowserUseTimeoutError` after a submit | keep the partial result, mark `Unknown`, do not retry the submit |
| Only `screenshot_path` is available for a visual claim | confirm the file exists, call `attach_image`, look at it, only then describe it |
| The request is only "dogfood https://staging.example.com" | announce the default budget, profile, and viewport, record `build unknown`, write charters, and start |
| No spec exists, but the page advertises "unlimited exports" and the third export is refused | quote the advertised promise as the source and report a finding |
| The browser model reports that the layout "looks broken" | not a source; capture the evidence, compare against a named source or label it `observation, source unknown` |
| A finding from last week's session was not re-run | `Unknown`, not fixed and not a new regression |
| Attempt 1 fails and attempt 2 passes | stop at three attempts in total, keep the attempt-1 screenshot at its own path, report `failed 1 of 2` |
| A charter run returns empty output and no capture | `Unknown` for that charter, not a clean result; say which evidence is missing |
| The user dislikes a label that no source specifies | out of scope or `observation, source unknown`; do not report it as a defect |
| `BROWSER_USE_MODEL` is set and the run returns a different model | report the returned model; do not state the default as fact |
| A duplicate submit produces two orders | report it with the source that forbids it, or ask; do not treat the UI message as proof of what the backend stored |

### Structural validation

- frontmatter `name` matches the directory, description is non-empty and under 1024 characters
- the link `../web-qa/references/evidence-contract.md` resolves once both skills are installed
- the inline fallback contract in `SKILL.md` lists all five check statuses
- every documented parameter exists in the installed `browser_use.run` signature
- one bounded live charter against a local fixture, after the instructions are stable

## Known limitations

- Desktop and mobile web only. No native app, no real device.
- One screenshot per run, final state only. Extra captures depend on the browser model
  following the capture instruction, so the caller must verify the files.
- The browser model is non-deterministic, so charter coverage varies between sessions.
- Exploration finds what the charters reach. Absence of findings says nothing about the rest.
- Task-text prohibitions are instructions, not enforcement.

## Maintenance notes

- Update `SKILL.md` when the charter format, budget defaults, judgment rules, or the
  `browser_use` API change.
- Coordinate any report-shape change with `web-qa`, which owns the evidence contract.
- Update `SOURCES.md` when prior-art research lands or a decision's provenance changes.
- Re-run the behavior eval cases after any change to the stop conditions or the finding rules.
