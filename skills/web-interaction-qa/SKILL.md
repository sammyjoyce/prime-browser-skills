---
name: web-interaction-qa
description: Verify that a web UI action really changes backend state, using approved test data and an authoritative readback. Use when asked to check that a form saves, a submit persists, a retry or double submit stays safe, concurrent edits behave, or a partial failure leaves correct state. Needs an approved non-production environment and readback access, and reports Unknown or Blocked instead of guessing.
compatibility: Needs the installed browser-use skill (Python browser_use), Chrome or Chromium, and OPENAI_API_KEY. Part of the web QA suite and reads ../web-qa/references/evidence-contract.md. Write actions need explicit user authorization.
---

# Web interaction QA

Check what a UI action does to stored state. Use approved test data, read the result back from an
authoritative source, and report. A success message in the UI is not persistence evidence.

## Read before running

| Open when you need to... | Read |
|---|---|
| apply the suite status, evidence, budget, and reporting rules | `../web-qa/references/evidence-contract.md` |
| record authorization, pick test data, and set mutation limits | `references/authorization-and-test-data.md` |
| choose a readback channel and decide Unknown against Blocked | `references/persistence-readback.md` |
| design retry, duplicate submit, race, and partial-failure checks | `references/failure-mode-protocol.md` |
| write the run task, output schema, verification code, and report rows | `references/evidence-examples.md` |

If the shared contract file is not installed, write `shared evidence contract missing` in the
report header and use these check statuses: Pass, Fail, Unknown, Blocked, Not run.

## Preconditions

Ask only for the items marked indispensable. For the rest, use the scope the user supplied or a
stated default, record the choice, and continue with the limits it forces.

| Item | Class | Behavior when missing |
|---|---|---|
| approved environment and URL, named as safe to mutate | indispensable | stop and ask, and never default to production |
| explicit list of actions the run may perform | indispensable | stop and ask |
| explicit test data values, or permission to generate marked test values | indispensable | stop and ask |
| absolute evidence directory | indispensable | create it yourself, or stop when the path is not writable |
| authoritative readback channel | recordable | run UI-level checks only, mark every persistence check Unknown, and say which channel is missing |
| request or server-side instrumentation | recordable | mark duplicate, retry, and race checks Unknown or Blocked, never Pass |
| named reference for expected behavior | recordable | record observations, mark expectation checks Unknown |
| profile name and budget | recordable | use a dedicated profile such as `interaction-qa` and a stated bounded default, and record both |

Never perform a write on production, a payment, a message to a real person, a deletion, or any
third-party side effect without explicit written authorization for that exact action.

## Browser call contract

```python
result = await browser_use.run(
    task_text,              # one whole flow: preconditions, action, in-page evidence
    schema=output_schema,   # require ids, counts, request evidence, and absolute paths back
    profile="interaction-qa",
    max_steps=25,
    timeout_ms=180_000,
    max_cost_usd=1.0,
)
```

- These arguments are the whole Python API for a run. There is no resize, follow-up, pause, or
  download option. Express every click, entry, wait, and capture inside `task_text`.
- The default browser model is exactly `openai/gpt-6-astra`. An explicit environment override can
  select a different model. Report `result["model"]`, the model that actually ran.
- Any non-completed run raises `browser_use.BrowserUseError`. A failed run may already have
  submitted. Treat its state as unknown, read the store before any retry, and record what you
  found.
- Each call starts and closes its own Chrome process. A profile keeps cookies, localStorage, and
  IndexedDB, not open tabs or unsaved form input. Keep one flow in one run, and use a second run
  as a fresh-session readback.
- Concurrency needs different profile names. One profile has one owner and a second caller fails.
  Exact interleaving is not controllable, so report observed timestamps, not intended ordering.

## Evidence model

| Evidence | What it proves |
|---|---|
| success toast, redirect, or optimistic row in the UI | the client rendered a result, nothing about stored state |
| authoritative readback: store query, API read, admin view, or server log the user gives you | the record exists with those values at that time |
| fresh-session reload in a second run that reads the record | the value survived the session and the client cache |
| record count before and after | whether the action created one row, none, or duplicates |
| in-page request instrumentation installed before the action | how many requests the client sent, with headers you captured |
| unique marker inside the test data | which run and attempt created a record |

A persistence claim needs an authoritative readback. Without one, the check is Unknown. Name the
proof boundary each claim reaches, from `references/persistence-readback.md`, and join the
action, the request, and the record by identifier rather than by clock time.

## Run plan

1. Write the checks first: action, approved data with its unique marker, expected stored result,
   readback channel, and rollback or cleanup plan.
2. Capture the before state: record count, existing ids, and any value you will compare.
3. Run the action in one browser call. Return the created or changed identifier, the visible
   result, the request evidence, and capture paths.
4. Read the result back through the authoritative channel. A second browser run counts as a
   fresh-session readback, not as the authoritative store.
5. Run the failure-mode checks the user approved, one at a time, inside the agreed attempt cap.
6. Clean up or report exactly what test data remains, with ids.
7. Write the report with per-check statuses, coverage, leftover data, and budget left.

## Verdict rules

- One status per check. No aggregate pass rate, no weighted risk index, no averaging.
- UI echo alone is never Pass for persistence. It is Unknown.
- Missing instrumentation makes a duplicate, retry, or race check Unknown. A check you could not
  start at all is Blocked.
- A flag the run reports about itself is not evidence. A gate needs independent measurements:
  record ids, counts, request records with timestamps, or a store readback.
- A gate over an empty evidence list is not a Pass. Zero requests recorded or zero records
  compared is Not run or Unknown.
- Behavior the named reference does not cover is out of scope. Record it as an observation, not a
  Fail.
- Status assignment, ready-condition failures, repeat attempts, severity and confidence, coverage
  counts, and the overall verdict come from the shared contract. Do not restate them differently
  here.

## Anti-patterns

| Seen | Required behavior |
|---|---|
| "saved successfully" taken as persistence | read the record back, or mark Unknown |
| blind retry after a failed run | read the store first, then decide |
| duplicate check with no request or row counts | Unknown, and say which instrumentation is missing |
| test data with no unique marker | mark records with the run id so cleanup and duplicates are provable |
| production form submitted to "see what happens" | stop, ask for written authorization for that action |
| intermittent failure dropped after a passing retry | keep it, report attempts and conditions |
| cleanup skipped and unreported | list every remaining record with its id |

## Report shape

Use the report template in the shared contract and add these interaction fields:

- Header: authorization reference and the test data markers used.
- Checks table: add action, expected stored result, readback channel, and proof boundary columns.
- Findings: add the affected record ids and the request evidence.
- State left behind: every record created or changed, with id, marker, and cleanup status.

Maintenance contract: `SPEC.md`. Provenance and source decisions: `SOURCES.md`.
