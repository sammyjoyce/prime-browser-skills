# Evidence contract

The shared reporting contract for the web QA skills. `web-qa` owns this file. Other suite
skills link it as `../web-qa/references/evidence-contract.md`. Use it whenever you assign a
check status, count coverage, record evidence, or write a verdict.

## Contents

1. Check record
2. Check statuses
3. Source authority
4. Page-ready conditions
5. Evidence rules
6. Repeats and intermittent behavior
7. Regression and fix labels
8. Severity and confidence
9. Coverage accounting
10. Budget ledger
11. Overall verdict
12. Report template

## 1. Check record

Every check carries these fields. A missing field is a gap, not a detail to fill in later.

| Field | Content |
|---|---|
| id | short stable id, for example `SMOKE-03` |
| scope | page, flow, or component under check |
| expected | the required result, quoted or paraphrased, plus the source name and version or date |
| observed | what the run actually produced |
| status | `Pass`, `Fail`, `Unknown`, `Blocked`, or `Not run` |
| environment | build id or commit, base URL, profile, viewport, theme, run start time |
| evidence | absolute paths to screenshots and artifact directories, plus the returned structured output |
| attempts | attempts made and the result of each, for example `3 attempts, failed 1 of 3` |
| severity | impact if real, judged separately from confidence |
| confidence | how strongly the evidence supports the finding |

## 2. Check statuses

| Status | Use when |
|---|---|
| `Pass` | the evidence shows the expected result from a named source |
| `Fail` | the evidence contradicts the expected result from a named source |
| `Unknown` | the check ran but the evidence does not settle it, or the sources disagree |
| `Blocked` | the check could not run because authority, access, tooling, or credentials were missing |
| `Not run` | the check was in scope and applicable but was never attempted, including budget cutoff |

Keep all five statuses in the report. Do not convert `Unknown`, `Blocked`, or `Not run` into
`Pass` because nothing visibly broke. Absence of a finding is not evidence of correctness.

A run that ends in an error does not erase what it already evidenced. Keep every check that
already has evidence at the status that evidence supports, whether `Pass` or `Fail`. Apply
`Unknown` and `Blocked` only to the checks the failed run left unevidenced.

Missing evidence is never a pass. An empty result, a zero count, an empty sample set, a missing
measurement, a null field, or a truthy return value with nothing behind it makes the check
`Unknown`, or `Not run` when it was never attempted. Do not substitute a default such as zero,
an empty list, or "no errors found" for a measurement you do not hold, and do not let a check
pass because a helper returned successfully without producing the evidence the check needs.

A requirement the named reference does not state is out of scope. Report it as out of scope, or
ask whether it belongs in scope. Do not invent a `Fail` for it, and do not read its absence as a
`Pass`.

## 3. Source authority

1. A finding needs a named source that states the expected behavior. A source can be a spec,
   ticket, requirement, design file, test contract, a platform or accessibility invariant the
   project has declared, a promise the product itself advertises, or behavior the user names as
   the accepted baseline. Record an identity another person can open, such as a file path, URL,
   node id, or ticket id, together with its revision, version, or date. A bare name is not an
   identity.
2. The browser run supplies the observed result. It never supplies the expected result, and the
   browser model's opinion that something looks wrong is not a source.
3. Text displayed by the app can be a source or an outcome, not both in the same check. It is a
   source when it states a rule or a promise, for example a plan limit, a stated delivery time,
   or a documented validation message. It is an outcome when it is the result under check.
   Quote a source string exactly, with the page and location where it appeared, and keep it
   separate from the observed result it is compared against.
4. With no baseline, report measured observations and any general constraint the user stated.
   Do not write "matches the design", do not invent a requirement, and do not promote a
   preference into an expected value.
5. When two sources disagree, mark the check `Unknown`, quote both, and ask the user which one
   governs. Do not pick the reading that makes the check pass.
6. Quote or cite the exact source text for each `Fail`.

## 4. Page-ready conditions

A ready condition names a specific visible state: a required text string, a selector that must
exist, a data value that must appear, or an accessibility state such as a control becoming
enabled. Navigation completion, a successful screenshot, a fixed sleep, and network idle are
not ready conditions. Account for streaming responses, polling, and hydration by naming the
settled state you expect.

When a ready condition is not met, decide the status from what the evidence supports.

| Situation | Status |
|---|---|
| the check needed evidence the run never produced | `Unknown` |
| later checks could not run because the flow never reached that state | `Blocked`, naming the blocker |
| a named source states a requirement that the evidence contradicts, for example results must appear within three seconds and none appeared in thirty | `Fail`, quoting the source |

A harness limit is not a product verdict. A `timeout_ms` stop, a `max_steps` stop, or a runner
error is `Unknown` or `Blocked` for the affected checks unless a named product requirement was
actually contradicted by the evidence you hold.

## 5. Evidence rules

1. `browser_use.run` saves one screenshot per successful run. It is the final state of that
   run, not a video and not a per-action trace.
2. Keep a before-and-after comparison inside one run. A new call starts a new Chrome process.
   A named profile keeps cookies, localStorage, and IndexedDB. It does not keep open tabs or
   unsaved page state.
3. For extra images, ask for them in the task text and give an absolute path inside an
   evidence directory the caller created before the run. Request the paths back in the schema.
4. After the run, confirm each file exists on disk. If a requested file is missing, mark the
   evidence incomplete and say which capture is missing. Never describe a screenshot that only
   exists as a filename or a history entry.
5. Load an image with `attach_image` before you state any visual fact about it. A path in a
   message is not an attachment. A child agent sends paths to its parent, and the parent
   attaches and views them.
6. Screenshots and artifacts are not redacted. They can contain private page content and
   visible account data. Do not publish them and do not paste credentials into task text.
7. State what the evidence proves and where the proof stops. A visible UI state is not proof that
   a request completed, that a write is durable, that an async job finished, or that a second
   client sees the same data. Name the boundary in the finding instead of writing "it saved".
8. Record how the evidence was produced, for example an emulated viewport at a stated size in
   Chrome, and name what stayed untested. A rendered viewport proves layout, not a gesture, a
   real device, or an assistive technology.

## 6. Repeats and intermittent behavior

1. Three attempts in total is the default ceiling, counting the first observation. One
   observation plus at most two deliberate repeats. Record what changed between attempts: fresh
   profile, reload, different data, different viewport.
2. Report attempts as observed over total, for example `failed 2 of 3`.
3. Write each attempt's evidence to its own path, for example `check-07-attempt-1.png`. Never
   overwrite a failing attempt's screenshot or artifact directory with a later passing attempt.
4. Keep the original observation after a later attempt passes. Report it as intermittent, with
   the artifacts from the failing attempt. Do not require one hundred percent recurrence.
5. Reproducibility and validity are separate. A defect observed once is still a defect if a
   named source says the behavior is wrong. Say that the repeat rate is low.
6. Do not repeat a task that may have already submitted a form or changed data.

## 7. Regression and fix labels

A regression or fix label is a comparison, so it needs a comparable baseline: the same
requirement, the same state and data, and recorded environment identifiers on both sides.

| Label | Requires |
|---|---|
| fixed | the same requirement re-checked in the same state after the change, with new evidence that now satisfies it |
| still failing | the same requirement re-checked with new evidence that still contradicts it |
| new regression | a named baseline where this requirement passed, plus new evidence that it fails now |
| `Unknown` | the requirement was not re-checked, was never covered before, or the baseline state is not comparable |

Not observed in this session is not fixed. Not previously covered is not a regression. Keep the
prior finding and its artifacts alongside the new evidence so both sides stay inspectable.

## 8. Severity and confidence

| Scale | Values | Meaning |
|---|---|---|
| severity | blocker, major, minor, trivial | impact on the user if the finding is real |
| confidence | high, medium, low | how strongly this evidence supports the finding |

Report both. Low confidence does not lower severity, and high severity does not raise
confidence. A blocker with low confidence stays a blocker with low confidence.

## 9. Coverage accounting

Report four counts with an honest denominator: planned, tested, excluded, unknown. The
denominator is every check that was in scope, not only the checks that ran. List the scope that
was never covered, with the reason. Risk weighting can order the work. It cannot convert a
failed check or an unknown required check into a pass, and it cannot be reported as a score.

## 10. Budget ledger

Record the agreed limits and the spend after each browser call.

| Field | Content |
|---|---|
| limits | wall-clock minutes, browser calls, total steps, aggregate USD cap, and the per-call `max_steps`, `timeout_ms`, and `max_cost_usd` |
| spent | elapsed minutes, calls made, steps used, dollars used |
| remaining | minutes, calls, steps, and dollars left, updated after every call |
| stop reason | no safe allowance left, scope complete, blocked, unsafe scope, or environment failure |

Set each call's limits to the smaller of the per-call default and what remains in the aggregate.
Stop when the remainder cannot cover another safe call, and report the uncovered scope as
`Not run`. Cost caps are approximate and checked between model turns, so a single call can
exceed its cap; keep the aggregate cap above the sum you expect to need. Do not extend a budget
without asking. Do not loop until the result turns green.

## 11. Overall verdict

| Verdict | Condition |
|---|---|
| `Fail` | any required check is `Fail` |
| `Incomplete` | no required `Fail`, but a required check is `Unknown`, `Blocked`, or `Not run` |
| `Pass for the stated scope` | every required check is `Pass` with evidence, and the scope is stated in the same sentence |

Never average check results. Never publish a readiness percentage, a quality score, or a
production-ready rating. State the scope and the uncovered scope next to the verdict.

## 12. Report template

```markdown
## Verdict
<Fail | Incomplete | Pass for the stated scope: ...>

## Environment
Build or commit, base URL, profile, viewport, theme, run window, the browser model the run
reported, how the evidence was produced, and what stayed untested.

## Reference
Named source and version. State "no baseline" when there is none.

## Checks
| id | scope | expected (source) | observed | status | attempts | severity | confidence | evidence |

## Findings
One entry per Fail or intermittent observation: expected with source quote, observed, the user
impact in one sentence, steps to reproduce, attempts, severity, confidence, evidence paths, and
the regression or fix label when the finding is compared against a prior run. Report one repeated
defect as a single systemic finding with its instances listed, not as many duplicates.

## Coverage
Planned / tested / excluded / unknown. Uncovered scope and why.

## Budget
Limits, spent, remaining, stop reason.

## Open questions
Contradictory sources, missing baselines, blocked access, decisions needed from the user.
```
