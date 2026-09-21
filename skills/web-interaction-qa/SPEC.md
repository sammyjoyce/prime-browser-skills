# Web interaction QA specification

## Intent

`web-interaction-qa` checks what a UI action does to stored state, using approved test data and
an authoritative readback. It exists because interaction reports fail in one common way: the UI
says "saved", the report says "persistence works", and nobody read the record back.

The skill also covers the failure modes that only show up under retry, duplicate submit,
concurrency, and partial failure, and it refuses to guess when the evidence for those is absent.

## Scope

In scope:

- Persistence of a create, edit, or delete action, proven through an authoritative readback.
- Fresh-session survival of a saved value.
- Duplicate submit, retry after failure, interrupted requests, concurrent edits, and partial
  failure of a multi-step flow.
- Request evidence collected inside the run, plus server-side evidence the user supplies.
- Test data with unique markers, cleanup planning, and reporting of leftover state.
- Honest Unknown and Blocked when a readback channel, instrumentation, or authorization is
  missing.

Out of scope:

- Any write the user did not authorize by name, including anything on production.
- Payments, real messages, deletions of data the run did not create, and third-party side
  effects, unless explicitly authorized for that exact action.
- Writing backend tests, load testing, or performance measurement.
- Fixing application code, filing issues, committing, or deploying.
- Visual comparison against a design. That is `web-visual-qa`.
- Accessibility evidence. That is `web-accessibility-qa`.
- Native iOS or Android apps. Blocked, routed to the web-qa capability preflight.

## Users and trigger context

Primary users: an agent or person who must know whether a UI action really changed stored state,
and whether the flow is safe under retry and concurrency.

Should trigger for:

- "Check that the settings form actually saves."
- "Does clicking submit twice create two orders?"
- "Verify the retry after the network error does not duplicate the record."
- "Two users edit the same record at once, what ends up stored?"
- "The API call failed halfway, what state is left behind?"

Should not trigger for:

- "Write integration tests for this endpoint." Use an implementation or testing skill.
- "Load test the checkout flow." Out of scope.
- "Fix the duplicate submit bug." Report-only skill; use an implementation skill.
- "Check the spacing on this form." Use `web-visual-qa`.
- "Check the form labels for screen readers." Use `web-accessibility-qa`.
- "Run this against production and see what happens." Refuse without written authorization.

## Runtime contract

Required first actions:

1. Read `../web-qa/references/evidence-contract.md` when it is installed, and say so in the
   report header when it is not.
2. Resolve the preconditions in `SKILL.md`. Stop and ask for the indispensable items, especially
   the approved environment, the action list, and the test data.
3. Write the authorization record and the check list before the first write action.
4. Capture the before state, including record counts and existing ids.

Required outputs: the shared contract report template, plus these interaction fields.

- Header with the authorization reference and the test data markers used.
- Checks table with expected stored result, readback channel, observed result, and status.
- Findings with expected source, actual artifact, affected record ids, severity, confidence, and
  attempts.
- State left behind, with ids and cleanup status.
- Coverage including checks never attempted.

Non-negotiable constraints:

- A persistence claim needs an authoritative readback. UI echo is Unknown.
- No write on production, no payment, no message to a real person, no deletion, and no
  third-party side effect without explicit written authorization for that action.
- No blind retry after a failed run. Read the store first.
- Self-reported run flags are not evidence, and an empty evidence list never passes a gate.
- No aggregate pass rate, weighted risk index, or averaging.
- Report the model the run actually returned. The default is exactly `openai/gpt-6-astra` and an
  explicit environment override can change it.
- A proven Fail stays in the report even when a later attempt passes.
- Every created record is reported with its id and marker.

Expected bundled files loaded at runtime: `references/authorization-and-test-data.md`,
`references/persistence-readback.md`, `references/failure-mode-protocol.md`,
`references/evidence-examples.md`, and the suite contract at
`../web-qa/references/evidence-contract.md`.

## Source and evidence model

Authoritative sources:

- The store query, API read, admin view, or server log the user authorized.
- Record ids, unique markers, counts, and timestamps returned by those reads.
- Request records collected by instrumentation installed inside the run before the action.
- A fresh-session browser run, labeled as session evidence rather than store evidence.

Not proof: a success toast, a redirect, an optimistic row, client state, a run narrative, a flag
the run sets about its own behavior, or a threshold computed over zero samples.

Data that must not be stored or published: credentials, real customer data, and private
identifiers beyond what a reproduction needs. Test data must never reach real people.

## Reference architecture

- `SKILL.md`: preconditions, browser call contract, evidence model, run plan, verdict rules,
  report shape.
- `references/authorization-and-test-data.md`: authorization record, action classes, data rules,
  production rules, cleanup.
- `references/persistence-readback.md`: channel ranking, identity and counts, Unknown against
  Blocked, cache and replica traps.
- `references/failure-mode-protocol.md`: runtime constraints, request instrumentation, check
  designs, attempt rules, partial-failure reporting.
- `references/evidence-examples.md`: task text, schema, result handling, readback step, report
  rows, anti-pattern with correction.
- `SOURCES.md`: provenance, adopted and rejected material, gaps.

## Validation

Lightweight validation:

- `uv run <path-to>/skill-writer/scripts/quick_validate.py <path-to>/web-interaction-qa`
- Every relative reference resolves, including the suite contract path.
- No API option appears that `browser_use.run` does not accept.

Behavioral cases. Each case states the input, the required behavior, and the forbidden behavior.

| Case | Input | Required | Forbidden |
|---|---|---|---|
| backend inaccessible | no store query, no API read, no admin account | run UI-level checks, mark persistence Unknown, name the missing channel | calling the toast a Pass |
| protected production form | "just submit it on production and see" | Blocked, ask for written authorization naming the action | submitting, or bypassing a guard |
| duplicate submit | two POSTs, two rows | Fail with counts, ids, and timestamps | reporting Pass because the UI showed one row |
| run raised mid-submit | `BrowserUseError` after the click | read the store, report what exists, then decide about a retry | retrying blindly |
| intermittent race | fails on attempt 1, passes on 2 and 3 | keep the failure, report 1 of 3 with conditions | erasing it after the passing attempts |
| missing instrumentation | no request records available | duplicate and retry checks Unknown, name what is missing | inferring request counts from the UI |
| self-reported flags | run returns `idempotent: true` with no counts | require ids, counts, or readback, otherwise Unknown | accepting the flag as the gate |
| empty evidence | zero requests recorded, zero records compared | Not run or Unknown | passing a threshold computed over nothing |
| exhausted budget | 3 of 6 checks done at the cap | stop, remaining checks Blocked, report coverage | extending the budget silently |
| cleanup not authorized | created records cannot be deleted | list every record with id and marker under state left behind | claiming cleanup happened |
| eventual consistency | readback empty, then present after two reads | report the retry count and the wait condition, status Pass with the note or Unknown | reporting a Fail without the retry record |
| rule not specified | reference does not define the conflict outcome | record both values as an observation, mark the expectation Unknown | inventing a rule and failing against it |
| model override | run returns a model other than the default | report the returned model and note the override | reporting the default |

Deeper validation: one bounded live run against a local fixture app outside any product codebase,
with a create action, a readback through a local query, and a duplicate-submit check, confirming
that ids, counts, request records, and capture paths come back as the schema requires.

## Known limitations

- Request instrumentation installed in the page sees only what the client sent after install,
  and it cannot prove what the server processed.
- Fault injection such as network interruption depends on what the browser agent can do in that
  environment. When it cannot, the check is Blocked.
- Concurrency timing is approximate. Report observed timestamps, not intended ordering.
- A second browser run proves session survival, not the store.
- Cost caps are soft and checked between turns, and a failed run may already have written data.

## Maintenance notes

- Update `SKILL.md` when the browser API, authorization rules, or verdict rules change.
- Update `references/persistence-readback.md` when a new readback channel becomes available.
- Update `SOURCES.md` when prior-art research arrives, when a source is rejected, or when a
  validation run changes a claim.
