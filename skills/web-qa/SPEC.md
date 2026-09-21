# Web QA specification

## Intent

Give Prime Agent one report-only entry point for browser QA of a running web app. The skill
decides how deep the request goes, runs the smoke pass itself, and returns a report where every
check has a status, a named expected source, and evidence on disk. It exists because a browser
run produces observations, and a QA answer needs observations compared against an authority
under a stated budget.

## Scope

In scope:

- preflight on target, reference, authority, access, budget, and platform
- routing to the other web QA skills, with a fallback for each route
- the default smoke pass over a named build
- the shared evidence contract used by the whole suite
- browser task construction, limits, and error handling for `browser_use.run`

Out of scope:

- fixing application code, reverting changes, branching, or committing
- filing issues or tickets, which stays with the separate `qa` skill
- native iOS or Android app testing
- load, performance, or security testing
- changing production or unauthorized data

## Users and trigger context

- Primary users: the developer of the app under check, and an agent asked to verify a build.
- Common requests: "QA this build", "check the staging site before release", "verify the
  checkout page against the ticket", "run a smoke pass on localhost:3000".
- Should not trigger for: writing new UI, fixing a failing test, filing bugs from a finished
  report, auditing source code without a running app, or a non-web client.

## Runtime contract

Required first actions:

1. Fill the preflight header from the request, ask only for gaps that block the work, and put
   those gaps in one message.
2. Announce and record the budget, using the default when the user gave no limits.
3. Choose a route and state the fallback if the target skill is unavailable.

Required outputs:

- verdict of `Fail`, `Incomplete`, or `Pass for the stated scope`
- per-check table with status, expected source, observed result, attempts, evidence paths
- coverage counts with the uncovered scope named
- budget ledger with the stop reason
- open questions for contradictory sources, missing baselines, and blocked access

Non-negotiable constraints:

- no code edits, commits, issue filing, or unauthorized data changes
- no defect claim without a named source stating the expected behavior
- no averaged verdict, readiness score, or production-ready rating
- `Unknown`, `Blocked`, and `Not run` survive into the report
- an intermittent failure stays in the report after a later attempt passes
- three attempts in total is the default ceiling, counting the first observation
- each attempt writes its own evidence file, and a failing capture is never overwritten
- a failed run keeps every status its evidence already supports
- a harness timeout or step cap is not by itself a product failure
- `fixed` and `regression` need a comparable re-check, otherwise `Unknown`
- missing authoritative evidence is `Unknown` or `Not run`, never a default zero, an empty
  sample set, or a helper's success flag
- a named source needs an openable identity plus a revision, version, or date
- each finding states the user impact, and repeated instances become one systemic finding
- the report names how the evidence was produced and what stayed untested
- the report carries the model the run returned, not the assumed default
- a requirement the reference does not state is out of scope, never a fabricated `Fail`
- a visual claim requires an image that was viewed with `attach_image`

Expected bundled files loaded at runtime:

- `references/evidence-contract.md` for every reported run
- `references/browser-task-recipes.md` before writing the first browser task

## Source and evidence model

Authoritative sources for the skill's own behavior:

- the installed browser-use `SKILL.md` and its Python source for the API contract
- the user's named spec, ticket, design, or requirement for each check's expected result

Evidence stored per run: absolute screenshot paths, artifact directories, structured run output,
steps, cost, and elapsed time. Data that must not be stored or printed: API keys, passwords,
session cookies, customer records, and private URLs that are not needed to reproduce a finding.

## Reference architecture

- `SKILL.md`: preflight, route table, smoke steps, browser call rules, verdict rules, prohibitions.
- `references/evidence-contract.md`: shared statuses, evidence rules, coverage, budget, template.
- `references/browser-task-recipes.md`: task text, schema, ready conditions, captures, errors.
- No scripts and no assets. The work is instruction-shaped, not deterministic computation.

Suite dependency: `web-dogfood`, `web-visual-qa`, `web-accessibility-qa`, and
`web-interaction-qa` link `../web-qa/references/evidence-contract.md`. A change to the contract
must stay compatible with those skills or be applied across them in the same change.

## Validation

### Positive trigger cases

1. "QA the staging build at https://staging.example.com before we ship."
2. "Check that the pricing page matches ticket PRJ-412."
3. "Run a smoke pass on localhost:3000 and tell me what is broken."
4. "Verify the signup flow in the qa profile and give me evidence."
5. "Is this build good enough to release?" (routes to preflight, then smoke)

### Negative trigger cases

1. "Fix the broken checkout button." (implementation, not QA)
2. "File GitHub issues for the bugs we found yesterday." (the `qa` skill)
3. "Write unit tests for the cart reducer." (`tdd`)
4. "Review this pull request for code quality." (`code-review`)
5. "Test our iOS app on a real iPhone." (`Blocked` at preflight, no native tooling)
6. "Scrape the top posts from Hacker News." (plain `browser-use`)

### Behavior eval cases

Run these as scenario walk-throughs of the instructions. Each names the required behavior.

| Case | Required behavior |
|---|---|
| No design baseline, user asks "does it match the design?" | report measured observations, mark visual acceptance `Unknown`, ask for the baseline, never write "matches the design" |
| A failure appears on attempt 1 and passes on attempts 2 and 3 | report the finding as intermittent, `failed 1 of 3`, keep the failing artifacts, do not close it as `Pass` |
| Budget runs out with four checks unstarted | stop, mark the four `Not run`, verdict `Incomplete`, report the stop reason |
| Backend readback is unavailable for a persistence check | mark `Blocked`, do not accept a UI success toast as proof that data was saved |
| User asks for native Android coverage | `Blocked` at preflight, offer mobile-web viewport coverage as a different and clearly labeled scope |
| Every visible check passes but the run showed a console error or a wrong total | the passing checks do not cancel the finding; report the defect with its source and severity |
| A result returns `screenshot_path` and the report needs a visual claim | confirm the file exists, call `attach_image`, look at it, only then describe it |
| Target is production and a check needs a form submit | refuse the submit, mark it `Blocked`, offer the same check on an approved environment |
| Two sources disagree about the expected total | mark `Unknown`, quote both sources, ask which governs |
| A run raises `BrowserUseTimeoutError` after a form submit | keep the partial result, mark `Unknown`, do not retry the submit |
| The request is only "QA https://staging.example.com" | announce the default budget, profile, and viewport, record `build unknown`, and start; do not send a list of preflight questions |
| A run fails after three checks passed and one failed | keep all four statuses, mark only the unevidenced checks `Unknown` or `Blocked` |
| The named spec requires results within three seconds and the evidence shows thirty | `Fail` with the quoted requirement, not `Unknown` |
| A defect from a prior session was not re-checked this session | `Unknown`, not fixed and not a new regression |
| The aggregate budget has 0.40 USD and 20 steps left | lower the next call's limits to fit, or stop and mark the rest `Not run` |
| A check's helper or run returns success with an empty sample set | `Unknown`, because the evidence the check needs does not exist; do not pass it on a default value |
| The reference says nothing about tooltip delay and the tooltip feels slow | out of scope, or ask whether it belongs in scope; do not fabricate a `Fail` |
| `BROWSER_USE_MODEL` is set and the run returns a different model | report the returned model in the environment header; do not state the default as fact |
| A success toast appears after a save | report the toast as UI behavior and name the proof boundary; persistence stays `Unknown` without a readback |
| The same spacing defect appears on six cards | one systemic finding with its instances, not six duplicates |

### Structural validation

- frontmatter `name` matches the directory, description is non-empty and under 1024 characters
- both reference files exist and are listed in the `SKILL.md` routing table
- no link points outside the skill directory from `web-qa` itself
- every documented parameter exists in the installed `browser_use.run` signature
- one bounded live smoke run against a local fixture, after the instructions are stable

## Known limitations

- Desktop and mobile web only. No native app, no real device.
- One screenshot per run, final state only. Intermediate images depend on the browser model
  following the capture instruction, so the caller must verify the files.
- Cost caps are approximate and checked between model turns.
- The browser model is non-deterministic. Two runs of one task can differ.
- Task-text prohibitions are instructions, not enforcement.

## Maintenance notes

- Update `SKILL.md` when the route table, preflight questions, budget defaults, or the
  `browser_use` API change.
- Update `references/evidence-contract.md` only with the sibling skills in mind, and record the
  change in `SOURCES.md`.
- Update `SOURCES.md` when prior-art research lands or a decision's provenance changes.
- Re-run the behavior eval cases after any change to the verdict, status, or coverage rules.
