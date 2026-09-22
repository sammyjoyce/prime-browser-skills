---
name: jev
description: Execute browser navigation, forms, and defined multi-step interactions with Jev through OpenRouter. Use for action-heavy web tasks with a clear starting URL and observable completion condition. Returns native PNG screenshots for the main Prime Agent session. Use browser-use with Astra for structured extraction, open-ended reasoning, or unsupported controls.
compatibility: Prime Agent Python skill loader, POSIX host, uv, Python 3.12+ for the separate runtime, Chrome or Chromium, and OPENROUTER_API_KEY for browser tasks.
---

# Jev browser tasks

Jev is an action executor alongside Astra, not a replacement for it. The default
`browser_use` model remains exactly `openai/gpt-6-astra`.

## Setup

Prime Agent discovers this Python-backed skill globally and exposes `jev` in a fresh
kernel. The kernel package uses the standard library. Browser execution runs in a
separate, locked Python 3.12+ environment, not inside the persistent kernel.

From this skill directory, install the runtime once:

```sh
uv sync --project runtime --frozen
```

After setup, the skill launches `runtime/.venv/bin/python` directly in its own process
group. This makes cancellation reach the runner, Chrome and the private daemon.
Missing runtime dependencies produce a setup error rather than a background install.

Set `OPENROUTER_API_KEY` in the environment inherited by Prime Agent. Never print it.
Both the Jev decision model and Mercury text helper use that key through OpenRouter.
No TypeSafe account or key is needed. Chrome or Chromium must already be installed.
There is no silent model/provider fallback or automatic task replay.

## Choose the executor

| Task | Use |
|---|---|
| Follow links, fill ordinary forms, operate native selects, complete a defined flow | `jev.run` |
| Extract a typed JSON answer, inspect a complex page, perform open-ended reasoning | `browser_use.run` with Astra |
| Shadow DOM, iframe, canvas, upload, popup, or arbitrary keyboard interaction | Do not assume Jev supports it; choose a verified alternative or report Blocked |
| Native iOS or Android app | Neither local Chrome executor establishes native-app coverage |

Jev selects code-owned actions from the observed DOM. You can supply the exact field
values; its text helper writes a value only when you allow it to. Jev does not accept an
output schema and does not generate a free-form answer to an extraction question.
`checks=` returns evidence for the assertions you declare yourself; it is not an
extraction API and cannot answer an open question about the page.

## Run one complete task

```python
result = await jev.run(
    "Open the Guides section, then the Returns guide. Stop when that guide is visible.",
    url="https://your-approved-app.example/docs",
    profile="work",
    max_steps=25,
    timeout_ms=120_000,
    max_cost_usd=0.5,
)
print(result["status"], result["steps"], result["cost"])
print(result["output"])
print(await attach_image(result["screenshot_path"]))
```

Give the exact starting URL, required final state, authorized actions and prohibitions.
Do not put credentials in the task. Test on approved local or staging environments.
Purchases, messages, deletion, or other consequential actions need explicit authority.
A natural-language restriction is not a sandbox or a technical action allowlist.

For exact form values, pass `values` (see the next section) instead of describing the
strings in the task. Independent readback is still required: a native validation attempt
added a period to a free-text field while the executor reported completed. Another
attempt stopped on an invalid helper value. Neither failure is automatically retried or
treated as success.

A successful result has `status="completed"`, `output`, `text`, `steps`, `cost`,
`usage`, `screenshot_path`, `verification`, `observation`, `side_effects`, `handoff`,
`confidence_policy`, `artifact_dir`, `profile_dir`, model identifiers, warnings, and
timing data. Paths are absolute. `output` contains the final URL, title, page text,
`completion_claimed`, and `verification="not_performed"`.
`result["verification"]` is a different field: the scoped DOM evidence described in
"Declared DOM checks" below, and `"not_run"` unless you declare checks.
`observation`, `side_effects` and `handoff` are described in "Confidence cutoffs and
stopping for review" below.

**Completed does not mean independently verified.** It means Jev chose DONE, the
screenshot was saved and cleanup succeeded. Check the actual postcondition before
reporting task success. For writes, verify the saved state, not just a success toast.
The built-in QA skills define evidence requirements when the task is a QA check.
`checks=` adds declared DOM evidence to the result, but that is page evidence inside
the scope you declared, not a verified goal and not proof of backend persistence.

Every non-completed result raises `jev.JevError`. Keep the real message and partial
result instead of reducing it to a generic failure:

```python
try:
    result = await jev.run(task, url=start_url, profile="work")
except jev.JevError as error:
    print(error.status, error.message)
    partial = error.result
```

Do not repeat an uncertain submission. Inspect the state first. A switch to Astra is
an explicit handoff, not an automatic restart of the original task.

`status="needs_review"` means Jev withheld the next input on purpose. Read
`error.result["handoff"]` and `error.result["side_effects"]`, look at the page, and
decide yourself. Never replay the same decision, and never assume nothing was sent
when `handoff["input_dispatched"]` is `"unknown"`.

## Exact field values

Pass the exact strings in `values`. Jev then binds one supplied value to each field it
fills, instead of asking the text helper to invent the text.

```python
result = await jev.run(
    "Open the feedback form, fill it from the supplied values, then submit it.",
    url="https://your-approved-app.example/feedback",
    profile="work",
    values={
        "reviewer_name": "Ada Lovelace",
        "comment": "Clear guide. No changes needed.",
        "referral_code": "",
    },
    generation="disabled",
)
for action in result["actions"]:
    print(action["kind"], action["value_key"], action["value_source"])
```

`values` is a dict of up to 20 entries, or None. Keys match
`^[A-Za-z][A-Za-z0-9_]{0,63}$`. Each value is a string of at most 2000 characters.
A bad key, a non-string value, more than 20 entries or an over-long value raises
`jev.JevValidationError` with status `invalid_input`, before the browser starts. An empty
dict is treated as no values.

The string is typed byte for byte. Jev does not strip spaces, change punctuation or
normalise anything. An empty string is allowed and means clear the field.

`generation` decides what happens when no supplied value belongs in a field:

- `"helper"`: the text helper may write a value, as it always has.
- `"disabled"`: the text helper is never called, and the field is skipped.
- Default `None`: resolves to `"disabled"` when you pass `values`, and to `"helper"`
  when you do not. Any other value raises `jev.JevValidationError`.

A skipped field types nothing. Jev records the step, then observes the page and carries
on. Three steps in a row with no page change still end the run as blocked, and three
skips in a row do exactly that.

Each entry in `result["actions"]` carries two more fields:

- `value_key`: the supplied key that was used, or None.
- `value_source`: `"supplied"`, `"helper"`, `"skipped"`, or None for actions that are
  not fills.

Every row also reports `operation_confidence`, `target_confidence` (None for operations
with no target), `binding_confidence` (None when no bind ran) and `dispatch`
(`"not_dispatched"`, `"attempted"` or `"unknown"`). `confidence` keeps its old meaning,
the operation score.

The typed text stays out of the result, as before.

**Supplied values are visible to the decision model, in full, not just as a preview.**
Jev sends each key and an 80-character preview of its value to the model that picks the
next action, but that preview is not a privacy bound. Once a value is typed, the full
string is visible to the decision model too, in the observed field value and the recent
actions, and to the call that binds a value to a field, and to the text helper when
`generation="helper"` runs. All of it leaves the host through OpenRouter and its selected
providers. Never put a password, token, card number or any other credential or private
data in `values`. Sign in with `jev.login` instead.

## Declared DOM checks

`checks` asks for read-only evidence from the page the browser ends on. It changes
nothing else: the run's status, `output["completion_claimed"]` and
`output["verification"]` stay exactly as they were.

```python
result = await jev.run(
    "Open the feedback form, fill it from the supplied values, then submit it.",
    url="https://your-approved-app.example/feedback",
    profile="work",
    values={"reviewer_name": "Ada Lovelace"},
    checks=[
        {"id": "landed", "kind": "url", "contains": "/feedback/thanks"},
        {"id": "banner", "kind": "text", "selector": "#status", "equals": "Thank you"},
        {"id": "name_kept", "kind": "value", "selector": "#reviewer_name",
         "equals": "Ada Lovelace"},
        {"id": "errors", "kind": "count", "selector": ".field-error", "equals": 0},
    ],
)
print(result["verification"]["status"])          # passed | failed | unknown | not_run
for row in result["verification"]["checks"]:
    print(row["id"], row["status"], row["reason"], row["observed"])
```

Each check is an object with an `id`, a `kind`, a `selector` for the kinds that need
one, and exactly one of `equals` or `contains`:

| kind | reads | selector | expectation |
|---|---|---|---|
| `url` | `location.href` | not allowed | `equals` or `contains` |
| `title` | `document.title` | not allowed | `equals` or `contains` |
| `text` | `innerText` of one visible element | required | `equals` or `contains` |
| `value` | value of one input, textarea, select or contenteditable | required | `equals` or `contains` |
| `count` | number of matching elements | required | `equals`, a whole number |

`id` defaults to `check[<index>]` and must be unique. At most 20 checks; ids at most
100 characters, selectors 1000, expectations 2000, counts 0 to 100000. An unknown key,
a missing or duplicate id, a bool or non-finite count, a selector on `url`/`title`,
both or neither of `equals`/`contains`, or an empty `contains` raises
`jev.JevValidationError` before any process starts. The runtime validates the same
request again with the same contract file, `src/jev/checks.py`.

`equals` compares byte for byte, `contains` is a case-sensitive substring, and nothing
is trimmed or normalised. There is no `attribute` kind, no regular expression, no
model call, and no arbitrary JavaScript: only the kind and the selector are sent into
the page, and every comparison happens in the runtime process afterwards, so a page
cannot see what you are asserting.

### What a status means

- `passed`: every declared check matched.
- `failed`: at least one check observed a value that did not match. Only an observed
  mismatch is a failure.
- `unknown`: evidence was missing, ambiguous, invisible, refused or unreadable. A
  selector that matches zero or several elements is `unknown`, not `failed`, with
  `reason` `missing_or_ambiguous` and `observed["matches"]`. So is a page the reader
  could not reach at all, with `reason` `page_unavailable`.
- `not_run`: you declared no check. That is not a pass.

**A check is not a verification of your goal, and `completed` still means the executor
claimed completion.** Nothing in this result promotes one to the other: a failed or
unknown check leaves the status `completed` and only adds a warning, and a passing
check leaves `output["verification"]` at `"not_performed"`.

**DOM evidence is not backend persistence.** `scope` is always
`declared_dom_checks_only` and every row carries `boundary: "browser_dom"`. A green
banner and a filled field prove what the page showed at one instant, not that a server
stored anything. For writes, still read the saved state back through an independent
path, exactly as `web-interaction-qa` requires.

`scope`, `boundary`, `note` and `consistency`, and each row's `boundary`, are the
contract's own constants. A result that widens any of them, for example a row claiming
`boundary: "server_confirmed"`, raises `jev.JevProtocolError` instead of reaching you.

### Evidence sensitivity and timing

- `count` counts every match, so a selector that is not unique inflates or deflates the
  number. Count what you mean: `.row` counts rows, `.field-error` counts errors.
- `text` reads `innerText` of one visible element, which follows the browser's rendered
  whitespace and excludes hidden text. An `equals` on a whole paragraph is brittle;
  `contains` on a stable phrase is usually the honest check.
- `value` reads the live field. The observed value is returned in the result and
  written to `result.json`, redacted for known secret environment values and truncated
  at 2000 characters. A password input is refused and never returns a value, and so are
  `type=hidden` and file inputs. There is no generic hidden-field extraction.
- Your declaration is not echoed back. Each row carries `fingerprint`, the SHA-256 of
  the normalized check it answers, and jev rejects a result whose ordered row
  fingerprints are not the ones it declared. Rows arrive in declaration order, so
  `verification["checks"][i]` answers your check `i`.
- The runner redacts its whole result in one pass, so an `id` or an expectation that
  looks like a credential comes back rewritten. A row `id` is a display label for that
  reason; the fingerprint is what binds a row to a declaration, and a hex digest is
  not something a credential pattern rewrites. The fingerprint detects a mismatched
  declaration. It is not a signature, and it proves nothing about a runner that
  decides to lie.
- The checks run once, after execution and before teardown, in one synchronous read, so
  the rows agree with each other and with `checked_at_url`. They are a snapshot of the
  end state, not a per-action assertion: a page that navigates or updates afterwards is
  not covered, and `captured_at_ms` records when the read happened.
- `checked_at_url` (at most 2048 characters) and `checked_at_title` (at most 2000) stay
  strings. `capture_metadata` records each field's `length` and `truncated` as the
  runtime measured them. When jev redacts one of the two again on the way out, that
  field also gets `redacted: true` and `returned_length`, the length of the string you
  actually receive. The discarded tail is not stored.
- They also run after a partial stop (blocked, max_steps, cost limit, timeout,
  cancellation) whenever the browser is still alive, because that is when the page state
  matters most. They are read-only, so this changes nothing about a failed run.
- A run that ended before the read could happen reports every declared check as
  `unknown` with `reason` `verification_not_attempted`. Wrapper-generated launch,
  protocol, and outer-timeout results do the same, using the same scoped rows
  the runner would, rather than omitting the object.

## Confidence cutoffs and stopping for review

Jev's executor scores each choice it makes. You can declare a cutoff below which it
must not act. The numbers below are an illustrative example, not a recommended
setting: they are your policy, not a measured success rate, and this skill ships no
default.

```python
result = await jev.run(
    "Open the feedback form, fill it from the supplied values, then submit it.",
    url="https://your-approved-app.example/feedback",
    values={"reviewer_name": "Ada Lovelace"},
    confidence={"operation": 0.8, "target": 0.85, "binding": 0.9},  # illustrative
)
```

The three gates are independent and each one is optional:

- `operation`: the score for the chosen operation (CLICK, TYPE_TEXT, SELECT, ...).
- `target`: the score for the chosen element. Operations with no target (WAIT, SCROLL,
  DONE, BLOCKED) skip it.
- `binding`: the score for the supplied value bound to a field, including the answer
  "no supplied value fits". A low-confidence "none" is withheld, not silently skipped.

Each value is a finite number greater than 0 and at most 1. `None` and `{}` both mean
"record the scores and withhold nothing". An absent key leaves that gate off. A bad
value raises `jev.JevValidationError` before any process starts, and the runtime
validates the same policy again.

A cutoff can only withhold. It never grants authority: `generation="disabled"` still
skips, freshness still applies, an unbound field is still skipped, the cost stop still
fires, and `output["verification"]` is still `"not_performed"`. A high score is not
evidence that the action was correct.

When a gate withholds, the run stops with `status="needs_review"` and raises
`jev.JevError`. The partial result is on `error.result`, the step is recorded with
`dispatch="not_dispatched"`, and nothing was typed or clicked for it.

`needs_review` also covers cases that do not need a cutoff, and three of them changed
what earlier versions reported:

- A DONE or a BLOCKED claimed on truncated evidence (was `completed` or `blocked`).
- An interrupted dropdown or any other failure after input was sent, where dispatch
  cannot be confirmed (was `browser_error`).
- A page that went stale while being re-observed after input was sent (was
  `browser_error`).

A freshness failure *before* input is not one of these. Nothing was sent, so Jev simply
observes again and chooses again, exactly as before.

`result["handoff"]` is a small record of the unresolved decision the executor
stopped on, for you to read before re-planning. It is present when a decision was
withheld, a budget stop fired, dispatch was interrupted, truncated DONE or BLOCKED
was refused, or another `needs_review` case left work unfinished. It is `None`
when there is no such decision to describe: a completed run; a failure that
stopped before the agent observed a page; or a DONE that later failed only at
screenshot capture or cleanup. A later capture or cleanup failure does not invent
a withheld decision after DONE.

The record looks like this:

```python
{"reason": "low_binding_confidence", "choice": "e3", "operation": "TYPE_TEXT",
 "operation_confidence": 0.91, "target": "2", "target_confidence": 0.88,
 "binding_key": "email", "binding_confidence": 0.40,
 "observation": {"omitted_actions": 0, "text_truncated": True,
                 "viewport": {"w": 1120, "h": 780}, "fingerprint": "..."},
 "input_dispatched": "not_dispatched",
 "resume_policy": "inspect current state; never replay this decision or any uncertain input"}
```

It carries stable ids, scores and flags only. No task, no supplied value, no field
label, no page text, no screenshot, no browser session id. It is not a resumable
session: a later `jev.run` on the same profile is a new process, a new observation and
a new decision. Never replay the decision, and never replay an input whose dispatch
is uncertain; inspect the current page first.

### What Jev saw, and what it may have changed

`result["observation"]` describes the last page the executor observed:

- `omitted_actions`: in-viewport controls dropped by the 250-action cap. Scrolling does
  not recover them; they were already in view.
- `text_truncated`: the visible text hit the 6000-character cap and more visible text
  existed. The snapshot computes this in the browser; it is not guessed from the length.
- `viewport` and `fingerprint`.

Truncation does not stop ordinary work. Clicks, fills, selects, scrolls and waits still
run on a truncated page. What it does stop is a completion claim built on it: if Jev
reports DONE while `text_truncated` or `omitted_actions` says the evidence was cut, the
run is `needs_review` unless you declared DOM checks and every one of them passed. A
BLOCKED verdict with omitted actions is always `needs_review`, because a cut action list
is not proof that nothing on the page could help.

`result["side_effects"]` is `"none_observed"` or `"uncertain"`, never `"confirmed"`:

- `none_observed`: no click, fill, select or scroll reached the page after a passing
  freshness check. Waits and skipped fills stay in this state.
- `uncertain`: at least one input was dispatched, or one dispatch could not be
  confirmed. A fill whose value reads back correctly is still `uncertain`.

This is about dispatched input, not about a server. A page can call an endpoint while
loading, so `none_observed` is not a promise that nothing happened anywhere, and
`uncertain` is not proof that anything was saved. Read the saved state back yourself.

## Screenshots in the main session

Every completed run captures a native PNG directly through Chrome CDP. It is not a
JPEG converted to PNG. The final image remains available after Chrome exits.

A child sends its absolute `screenshot_path` and result to its parent. The parent must
call `attach_image(path)` before describing the image. A filename in a message does
not attach the image, and base64 does not belong in chat. Local sessions share the
filesystem; remote workers need a separate file-transfer step.

Failure screenshots are best effort. A missing screenshot never replaces the primary
provider or browser error. If Jev finishes but capture fails, the call raises
`artifact_error` rather than reporting a full skill success.

## One-time manual login

```python
await jev.login("work", "https://your-approved-app.example/login")
```

Tell the user to sign in manually, including MFA, then close all Chrome windows for
this profile. Login opens headed Chrome and makes no model calls. It needs no API key.
It returns with zero model steps/cost and `authenticated=None`, not proof of a successful
sign-in. Verify authentication with a later read-only task. Login takes no screenshot.
The default login timeout is ten minutes; pass `timeout_ms` to change it.

`JEV_HOME` defaults to `~/.prime/agent/jev`. Named profiles live under `profiles/` and
keep cookies, localStorage and IndexedDB. Each run gets a new browser process and
artifact directory. Open tabs and unsaved state are not promised across calls.

Profile names use letters, digits, underscores and hyphens, start with a letter or
digit, and have at most 64 characters. One process owns a profile at a time. Use separate
names for parallel tasks. Jev profiles are separate from Astra's `browser_use` profiles;
sharing a name does not transfer authentication or in-progress actions.

## Limits and privacy

- Defaults: 25 actions, 120 seconds, soft model-cost limit $0.50. Upstream safety limits
  can stop a task sooner. The wrapper allows bounded artifact capture and cleanup time.
- Cost includes Jev, the text helper and each value-binding call. The budget is checked
  after every model call and before any input, so an uncosted or over-budget call cannot
  bind a value, call the text helper or type. What can still overshoot is the one
  request already in flight, including the retries the upstream client makes inside it.
  Missing usage is unknown, never free; an unaccounted successful provider call stops
  execution rather than continuing without a budget.
- `model` records the requested decision model; `resolved_model` records the returned
  version. The default requests `jev-latest`; the text helper is `inception/mercury-2.5`.
  With `generation="disabled"` the text helper is never called.
- Telemetry is disabled. Chrome and its browser-harness daemon are private to the run.
  They do not attach to the user's daily Chrome or load an unrelated workspace's dotenv.
- Task data and supplied values go to OpenRouter and its selected model providers.
  Browser content can be hostile. Use an isolated host for untrusted browsing.
- Profiles, screenshots, transcripts and page text may contain private data. Known key
  redaction does not sanitize page screenshots. Do not publish raw artifacts by default.
- Cancellation and timeouts stop owned processes before releasing the profile lock.
  No automatic artifact retention or profile deletion is performed.

## Delegate a whole task

Use one child per whole objective, not per click.

```python
child = await rlm.spawn(
    "Read the jev SKILL.md. Use jev.run for the approved navigation task at the supplied "
    "URL, with a unique profile and explicit time/step/cost limits. Do not submit forms. "
    "Check the final URL and visible heading, then send the result, verification evidence, "
    "cost, and absolute screenshot path to the parent with agent_message.send. "
    "Report JevError with its actual status/message; on needs_review report the handoff "
    "and side_effects instead of retrying; do not retry uncertain actions.",
    name="jev-browser-task",
    thinking="high",
)
```

The child model is your choice. Omit `model` to inherit yours, or pass a selector you
have confirmed with `rlm.find_models`. An unavailable selector fails the spawn. The
child Prime Agent model is separate from Jev's own decision model, which this argument
does not change.

Replace the task/URL placeholders with the approved objective before spawning. Spawn
returns immediately. Let the child finish and send its reply; the parent loads the
screenshot with `attach_image`.

## Validation

From this skill directory, run the deterministic tests documented in `VALIDATION.md`.
The declared-check group runs against real headless Chrome and makes no model call:

```sh
uv run --project runtime --frozen python runtime/tests/run_tests.py --group checks
uv run --project runtime --frozen python runtime/tests/run_tests.py --group guards
```

Both groups start their own headless Chrome on a throwaway profile with a private
browser-harness daemon, and neither touches the user's own Chrome. The `guards` group
measures the snapshot's truncation and action-cap metadata in that browser.

That file records commands, evidence and any remaining gaps; it must not label planned
tests as passed. From a fresh Prime Agent session in another directory, verify native
`jev` discovery, run an approved local task, check its independent outcome, and view its
PNG. Also test typed provider failure, profile contention and login persistence.

Exact-value binding has deterministic tests with mocked model responses only. No live
run has exercised it. Read the saved value back yourself before you report success.

Source pin, license and local changes: `SOURCES.md`. Maintenance contract: `SPEC.md`.
