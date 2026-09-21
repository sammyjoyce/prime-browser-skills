# Browser task recipes

Open this when you need to turn a check into one `browser_use.run` call: task text, output
schema, ready condition, extra screenshots, limits, or error handling.

## Contents

1. What the API accepts
2. Task template
3. Output schema pattern
4. Ready conditions
5. Before and after in one run
6. Extra screenshots
7. Errors
8. Profiles and parallel runs
9. Anti-pattern and correction

## 1. What the API accepts

```python
result = await browser_use.run(
    task,                    # required, nonempty instruction string
    schema=None,             # JSON Schema dict, Pydantic model class, or None
    profile="default",       # [A-Za-z0-9][A-Za-z0-9_-]{0,63}
    max_steps=25,
    timeout_ms=180_000,
    max_cost_usd=1.0,
)
```

`await browser_use.login(profile, url, timeout_ms=600_000)` opens headed Chrome for a
user-driven sign-in. No model runs and no API key is needed. It returns after the user closes
the window and it cannot confirm that the sign-in worked, so verify with a read-only run.

A completed result is a dict with `status`, `output`, `text`, `steps`, `cost`,
`screenshot_path`, `artifact_dir`, plus usage, model, and history and event paths. Artifact
paths are absolute. The browser model defaults to exactly `openai/gpt-6-astra`, and the
environment variable `BROWSER_USE_MODEL` can override it. Read `result.get("model")` and report
that value. Do not state the default as fact when an override may be set.

Set `max_steps`, `timeout_ms`, and `max_cost_usd` on each call to the smaller of the per-call
default and the remaining budget. Stop calling when the remainder cannot cover a safe call.

There is no follow-up, pause, resize, download, viewport, or model parameter. Express a
viewport change, a device emulation, or any other browser action as an instruction inside the
task text. Raw SDK and CDP calls run inside the browser model's own JavaScript, not in the
Python kernel.

## 2. Task template

Write all six parts. Keep them concrete.

```text
1. Target      Open <absolute URL> in this profile.
2. Precondition Confirm <named signed-in or seeded state> before continuing.
3. Steps       Do <numbered user actions, in order>.
4. Ready       Wait until <specific visible text, selector, data value, or enabled control>.
5. Evidence    Report <exact fields>. Write extra PNGs to <absolute paths> if requested.
6. Prohibited  Do not <submit, pay, message, delete, change settings, sign out, retry a submit>.
```

Prohibitions belong in the task text for every run, including read-only ones. The task text
steers the browser model. It is not a sandbox and not an allowlist.

## 3. Output schema pattern

Ask for the observed facts and the ready condition, never for a verdict. The QA judgment
happens in the Prime Agent session against the named source.

```python
schema = {
    "type": "object",
    "properties": {
        "url_after": {"type": "string"},
        "ready_condition_met": {"type": "boolean"},
        "observed": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "check_id": {"type": "string"},
                    "value": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["check_id", "value"],
                "additionalProperties": False,
            },
        },
        "capture_paths": {"type": "array", "items": {"type": "string"}},
        "blocked_reason": {"type": "string"},
    },
    "required": ["url_after", "ready_condition_met", "observed"],
    "additionalProperties": False,
}
```

## 4. Ready conditions

| Weak | Use instead |
|---|---|
| "wait for the page to load" | "wait until the text Order history is visible and the table has at least one row" |
| "wait a few seconds" | "wait until the Save button is enabled" |
| "wait for network idle" | "wait until the balance field shows a number instead of an em dash or Loading" |
| "take a screenshot when done" | "wait until the toast Saved is visible, then report its exact text" |

Streaming, polling, and hydration all produce a page that looks finished before it is.
Name the settled state. Report `ready_condition_met: false` instead of guessing.

## 5. Before and after in one run

Each `run` call starts a new Chrome process and closes it at the end. The profile keeps
cookies, localStorage, and IndexedDB. It does not keep open tabs, scroll position, form input,
or unsaved page state. Put the whole before-and-after scenario in a single task.

```text
Open http://localhost:3000/settings. Wait until the Theme control is visible.
Capture the before image to /abs/evidence/theme-before.png.
Click Dark, then wait until the page background is dark and the Theme control reads Dark.
Capture the after image to /abs/evidence/theme-after.png.
Report both absolute paths and the control text before and after.
```

## 6. Extra screenshots

The run's own `screenshot.png` is the final state only. For extra images, create the evidence
directory in Python first, pass absolute paths in the task, and ask for the paths back.

```python
evidence_dir = pathlib.Path("/abs/evidence/run-07")
evidence_dir.mkdir(parents=True, exist_ok=True)
```

Instruction text for the task, using the same CDP call the runner uses for its own screenshot:

```text
To capture an image, run this in the page context, with the absolute path substituted:
  const shot = await page.cdp('Page.captureScreenshot', {format: 'png'});
  await (await import('node:fs/promises')).writeFile('<ABSOLUTE PATH>', Buffer.from(shot.data, 'base64'));
Report every path you wrote in capture_paths.
```

After the run, check that each file exists and has a nonzero size. A returned path is a claim,
not a file. Then view the image with `attach_image` before you describe it.

## 7. Errors

Every non-completed status raises `browser_use.BrowserUseError` with `status`, `message`, and
`result`. `result` can hold partial output and artifact paths. Keep it as evidence.

| Error | Meaning | QA response |
|---|---|---|
| `BrowserUseValidationError` | bad arguments | fix the call, no status change |
| `BrowserUseProfileInUseError` | another session owns the profile | use a different profile name, or wait |
| `BrowserUseTimeoutError` | the run exceeded `timeout_ms` | a harness limit, not a product verdict; keep already-evidenced results, mark unevidenced checks `Unknown` and unexecuted downstream checks `Blocked`, do not retry a state-changing task |
| `BrowserUseProtocolError` | the runner returned malformed output | mark `Unknown`, report the message, check the environment |
| `BrowserUseError` | provider or other failure | record the real message, mark `Blocked` if credentials or access failed |

```python
try:
    result = await browser_use.run(task, schema=schema, profile="web-qa",
                                   max_steps=25, timeout_ms=180_000, max_cost_usd=0.5)
except browser_use.BrowserUseError as error:
    status, message, partial = error.status, error.message, error.result
```

A failed run does not cancel the checks it already evidenced. Keep those statuses, including a
`Fail` observed before the error, and apply `Unknown` or `Blocked` only to the rest. Record a
product `Fail` from an error only when a named requirement was contradicted by evidence you
hold, not from the error itself.

Never print credential values from an error or an artifact.

## 8. Profiles and parallel runs

One profile has one owner at a time across Prime Agent sessions. A second caller fails rather
than sharing Chrome. Use a distinct profile name per concurrent run, for example `web-qa-a`
and `web-qa-b`. Do not point a profile at a personal Chrome user-data directory. A profile used
for a signed-in check must be the one the user signed in to with `browser_use.login`.

## 9. Anti-pattern and correction

Anti-pattern:

```text
Go to the checkout page, test that it works, retry if anything fails, and tell me if it is good.
```

It has no target URL, no source for "works", no ready condition, no prohibition on paying, and
it invites blind retries of a submit. The verdict is delegated to the browser model.

Correction:

```text
Open http://localhost:3000/checkout in this profile with the seeded cart for test account
qa-user-3. Wait until the line item Blue mug and the text Total are both visible.
Report the line item names, the quantity field value, the subtotal, the tax, and the total,
each exactly as shown. Do not click Pay, do not change quantities, and do not retry a submit.
```

The session then compares the reported totals with the named pricing spec and assigns a status.
