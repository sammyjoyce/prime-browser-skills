---
name: web-dogfood
description: Bounded exploratory testing of a running web app to find unknown defects, using real user goals instead of a fixed check list. Use when asked to dogfood a build, explore a feature like a user, hunt for problems without a written test plan, or stress a flow before release. Reports observations with evidence and never fixes code, files issues, or invents a defect count.
compatibility: Prime Agent with the browser-use Python skill (await browser_use.run), Chrome or Chromium, and an approved local, staging, or explicitly authorized target.
---

# Web dogfood

Use the product the way a user would, inside a fixed budget, and report what the evidence shows.
A finding needs a named source, so exploration without one produces observations and open
questions. This skill reports only. It does not edit code, file issues, or commit.

## Step 1: preconditions

Take what the request gives you and start. Ask only for a gap that blocks the work, in one message.

| Item | Accept | When the request does not say |
|---|---|---|
| Target | one base URL that is local, staging, or explicitly authorized | ask, this is the one gap that blocks every run |
| Build, profile, viewport | build id or commit, named profile, pixel viewport | record `build unknown`, then choose and announce a reproducible default: profile `web-dogfood`, 1280x800 |
| Sources | specs, tickets, docs, declared platform or accessibility invariants, or promises the product advertises, with versions | continue, and label each finding `observation, source unknown` |
| Authority | read-only, or named test accounts and test data you may create or modify | stay read-only and skip charters that write data |
| Budget | minutes, calls, total steps, aggregate USD cap | announce the default below, record it, and start |
| Safety | which actions are forbidden: payments, messages, deletions, settings changes, sign-outs | treat all of them as forbidden |

Default budget, announced rather than negotiated: 25 minutes, 6 browser calls, 150 steps in
total, and 3.00 USD in total, with `max_steps=25`, `timeout_ms=180_000`, and
`max_cost_usd=0.5` on each call. Set each call's limits to the smaller of the per-call default
and what remains. Stop when the remainder cannot cover another safe call.

Production targets: read-only navigation, only with explicit user approval in this session.
Never submit a form, place an order, or send a message on production.

## Step 2: write charters

A charter is one user goal with its own limits. Write three to five before the first run. Cover the
flows the user named, then the transitions around them: entry, empty state, invalid input,
interruption, back navigation, reload, second attempt, duplicate submit, a late response arriving
after a newer one, cancellation, expired session.

```text
Charter D-2
Goal        Sign up with an email that already exists, then recover.
Entry       http://localhost:3000/signup
Data        qa-user-3@example.test, password from the qa profile, already registered
Budget      1 browser call, max_steps 25, timeout_ms 180000, max_cost_usd 0.5
Evidence    error text, field states, resulting URL, final screenshot
Prohibited  do not create a new account, do not reset a password, do not email anyone
```

Charters bound the work. They are not a bug quota. A charter that ends with no finding is a
valid result, and an early defect neither ends the session nor buys extra charters.

## Step 3: run one charter per call

1. Put the whole charter in one `browser_use.run` task. Each call starts a new Chrome process, so
   open tabs and unsaved page state do not carry over. The profile keeps cookies and storage.
2. Name a ready condition for every stop in the flow: a specific visible text, a selector, a data
   value, or an enabled control. Page load, a fixed sleep, and network idle do not count.
3. Ask for observed facts in the schema, not a verdict. The judgment happens here.
4. For a before-and-after comparison, keep both states in one run and ask for extra captures to
   absolute paths in an evidence directory you made first.
5. After each call, record `steps`, `cost`, elapsed minutes, and the returned paths, then
   update the remaining minutes, calls, steps, and dollars.
6. Confirm each evidence file exists, and view an image with `attach_image` before describing it.
   A child agent sends paths to its parent, which attaches them.

```python
result = await browser_use.run(
    "Open http://localhost:3000/signup in this profile. "
    "Enter qa-user-3@example.test and the password, then submit the form once. "
    "Wait until either an error message or a confirmation heading is visible. "
    "Report the exact error or heading text, the state of each field, and the final URL. "
    "Do not create a second account, do not reset a password, and do not retry the submit.",
    schema={
        "type": "object",
        "properties": {
            "message_text": {"type": "string"},
            "field_states": {"type": "array", "items": {"type": "string"}},
            "url_after": {"type": "string"},
            "ready_condition_met": {"type": "boolean"},
        },
        "required": ["message_text", "field_states", "url_after", "ready_condition_met"],
        "additionalProperties": False,
    },
    profile="web-dogfood",
    max_steps=25,
    timeout_ms=180_000,
    max_cost_usd=0.5,
)
```

Every non-completed status raises `browser_use.BrowserUseError`. Record `error.status` and
`error.message`, and keep `error.result` as partial evidence. Keep whatever the run evidenced,
including a failure seen before the error. Mark the unevidenced part `Unknown` and steps that
never ran `Blocked`. A timeout or step-cap stop is a limit of the run, not a product defect. Do
not repeat a task that may have already changed data.

The browser model defaults to exactly `openai/gpt-6-astra`, and `BROWSER_USE_MODEL` can override
it, so report `result.get("model")` rather than the default. `run` accepts only the parameters
shown above. Task text steers the browser model; it is not a sandbox, and that model can run host
JavaScript. Never put a credential in task text, and have the user run `browser_use.login`.

## Step 4: judge each observation

1. Find the source that states the intended behavior. With no design or spec you can still use a
   platform or accessibility invariant the project declared, a promise the product advertises, a
   documented rule, or behavior the same app shows elsewhere. Quote it with its version or date.
2. Text in the app is a source or an outcome, not both in one finding. It is a source when it
   states a rule or a promise, such as a plan limit or a stated delivery time, and an outcome
   when it is the result under check. Record where each one appeared.
3. The browser model's opinion is not a source, and neither is your preference or an invention.
4. With a source, report a finding: expected with the quote, observed, evidence, severity, and
   confidence. With no source, report `observation, source unknown` and ask the user.
5. When two sources disagree, mark it `Unknown`, quote both, and ask which one governs. A
   requirement no source states is out of scope, not a defect and not a pass.
6. Judge severity and confidence on separate scales. Low confidence does not lower severity.

## Step 5: repeats and intermittent behavior

1. Three attempts in total is the ceiling, counting the first observation. Change and record one
   thing at a time: reload, fresh profile, different data, different viewport.
2. Report attempts as observed over total, for example `failed 1 of 3`.
3. Write each attempt's evidence to its own path. Never overwrite a failing screenshot with a later
   passing one, and never delete a finding because the last attempt was clean.
4. Call something fixed or regressed only after re-checking the same requirement in the same
   state with new evidence. Not re-checked or never covered before is `Unknown`.
5. Do not repeat an action that may have already changed data.

## Step 6: stop and report

Stop when the charters are done, the remaining budget cannot cover another safe call, access or
authority is missing, the scope is unsafe, or the environment fails. Never stop at a chosen number
of bugs, and never keep going because too few appeared.

Report with `../web-qa/references/evidence-contract.md`. Without that file, use this minimal form:
per-charter status from `Pass`, `Fail`, `Unknown`, `Blocked`, `Not run`, findings with expected
source, observed, attempts, severity, confidence and evidence paths, coverage as planned, tested,
excluded and unknown, then the budget ledger and the stop reason.

State the uncovered scope next to the result. Report a session with no findings as "no defects
found in the charters run", never as a pass for the product, never as an averaged or scored result.

## Prohibitions

- Do not edit application code, revert changes, create branches, commit, or file issues.
- Do not create, modify, or delete data outside the authorized test data, and do not pay,
  message a real person, delete content, or change account settings.
- Do not call an observation a defect without a named source, and do not report a charter as
  clean on empty evidence. Missing evidence is `Unknown` or `Not run`.
- Do not describe a screenshot you have not viewed, or a file you have not confirmed exists.
- Do not drop an intermittent observation after a passing retry.
- Do not claim native iOS or Android coverage from a browser viewport.
