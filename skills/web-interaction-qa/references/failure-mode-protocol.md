# Failure-mode protocol

Use this for idempotency, retries, duplicate submits, concurrency, and partial failures. Each
check needs its own evidence. Without that evidence the check is Unknown, not Pass.

## Contents

1. Runtime constraints that shape these checks
2. Request instrumentation
3. Check designs
4. Attempt rules for intermittent behavior
5. Reporting a partial failure

## Runtime constraints that shape these checks

| Constraint | Consequence for the design |
|---|---|
| one Chrome process per `browser_use.run` call | a whole flow, including the second submit, stays inside one run |
| a profile keeps cookies but not tabs or unsaved input | a second run is a fresh session, useful as a readback, useless as a continuation |
| one owner per profile, a second caller fails | parallel runs need different profile names |
| no Python-side control of timing inside the page | interleaving is approximate, so report observed timestamps |
| failed runs raise and may have already written | read the store before any retry |

## Request instrumentation

Install instrumentation inside the run before the action, and return what it collected:

1. Wrap `window.fetch` and `XMLHttpRequest.prototype.send` to count calls, record method, URL
   path, and any idempotency or request-id header the client sends. Record the wrapper install
   time so nothing earlier is counted.
2. Read `performance.getEntriesByType('resource')` for a cross-check of request count and timing.
3. Ask the user for server-side evidence when the claim depends on what the server received,
   such as access logs, a request-id trace, or a queue count.

Limits to state in the report: a client wrapper sees only requests the page made after install,
it does not see request bodies unless you record them, and it cannot prove what the server
processed. When the claim needs server truth and no server evidence exists, mark it Unknown.

## One gesture against one business change

Keep two identities apart:

- action id: one gesture, such as a single click on submit.
- intent id: one business change, such as one contact created.

A duplicate check asks whether one intent produced more than one effect. Two actions for one
intent are normal in a retry flow, so counting clicks alone proves nothing. Count effects in the
store and tie them to the intent marker.

If the application already sends a correlation header such as a request id, record its value and
use it for the join. Never ask for application changes to make a check possible, and never assume
those headers exist.

## Check designs

| Check | Setup inside one run | Evidence required | Pass condition |
|---|---|---|---|
| single submit creates one record | count records, submit once, read back | before and after counts, record id, request count | exactly one new record with the marker |
| double submit | click the submit control twice quickly, without waiting for the response | request count, both responses, after count | one record, or a documented rejection of the second |
| retry after visible failure | submit, observe the failure, retry once as the user would | both request records, after count | one record, and no partial second record |
| network interruption | interrupt the request through the browser agent, then retry | evidence that the interruption happened, plus the after state | state matches the documented recovery rule |
| concurrent edit | two runs with different profiles, or two tabs in one run, editing the same record | both submitted values, both responses, final stored value, observed timestamps | the documented conflict rule holds, for example last write wins or a conflict error |
| partial failure | a multi-step flow where a later step fails, only with the user approved method | stored state for every step | the documented rule holds, either all steps applied or none |
| idempotency key honored | repeat the same request identity as the client does | the key value on both requests, after count | one record for one key |

For a check whose setup needs fault injection that the environment does not support, record it as
Blocked and name the missing capability.

## Attempt rules for intermittent behavior

The shared contract sets the attempt ceiling, the reporting form, and the rule that a later
passing attempt never erases an earlier failure. These additions are specific to write actions:

1. Use a new data marker for every attempt, so two attempts never share an identity.
2. Record which records each attempt created, including the ones a failed attempt left behind.
3. Record what differed between attempts: timing, data, session, environment load.
4. Never repeat an action that may have already written, until a readback tells you what exists.

## Reporting a partial failure

Report these separately:

- what the UI showed,
- what the client sent,
- what the store holds now,
- which steps of the flow completed,
- what a user would have to do to recover,
- which records remain and with which ids.

A partial failure with no store readback is Unknown. Say which channel was missing rather than
describing the flow as "probably fine".
