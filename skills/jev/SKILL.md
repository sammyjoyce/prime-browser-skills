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

Jev selects code-owned actions from the observed DOM. Its text helper supplies field
values when needed. It does not accept an output schema and does not generate a
free-form answer to an extraction question.

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

For exact form values, use quoted strings or a JSON object in the task, and state that
punctuation must not change. Do not put credentials in that object. Independent readback
is still required: a native validation attempt added a period to a free-text field while
the executor reported completed. Another attempt stopped on an invalid helper value.
Neither failure is automatically retried or treated as success.

A successful result has `status="completed"`, `output`, `text`, `steps`, `cost`,
`usage`, `screenshot_path`, `artifact_dir`, `profile_dir`, model identifiers, warnings,
and timing data. Paths are absolute. `output` contains the final URL, title, page text,
`completion_claimed`, and `verification="not_performed"`.

**Completed does not mean independently verified.** It means Jev chose DONE, the
screenshot was saved and cleanup succeeded. Check the actual postcondition before
reporting task success. For writes, verify the saved state, not just a success toast.
The built-in QA skills define evidence requirements when the task is a QA check.

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
- Cost includes Jev and the text helper. Limits are checked between calls/actions and
  may overshoot by one request. Missing usage is unknown, never free; an unaccounted
  successful provider call stops execution rather than continuing without a budget.
- `model` records the requested decision model; `resolved_model` records the returned
  version. The default requests `jev-latest`; the text helper is `inception/mercury-2.5`.
- Telemetry is disabled. Chrome and its browser-harness daemon are private to the run.
  They do not attach to the user's daily Chrome or load an unrelated workspace's dotenv.
- Task data goes to OpenRouter and its selected model providers. Browser content can be
  hostile. Use an isolated host for untrusted browsing.
- Profiles, screenshots, transcripts and page text may contain private data. Known key
  redaction does not sanitize page screenshots. Do not publish raw artifacts by default.
- Cancellation and timeouts stop owned processes before releasing the profile lock.
  No automatic artifact retention or profile deletion is performed.

## Delegate a whole task

Use one child per whole objective, not per click. After confirming model availability:

```python
child = await rlm.spawn(
    "Read the jev SKILL.md. Use jev.run for the approved navigation task at the supplied "
    "URL, with a unique profile and explicit time/step/cost limits. Do not submit forms. "
    "Check the final URL and visible heading, then send the result, verification evidence, "
    "cost, and absolute screenshot path to the parent with agent_message.send. "
    "Report JevError with its actual status/message; do not retry uncertain actions.",
    name="jev-browser-task",
    model="openai/gpt-6-astra",
    thinking="high",
)
```

Replace the task/URL placeholders with the approved objective before spawning. Spawn
returns immediately. Let the child finish and send its reply; the parent loads the
screenshot with `attach_image`. The child Prime Agent model is separate from Jev.

## Validation

From this skill directory, run the deterministic tests documented in `VALIDATION.md`.
That file records commands, evidence and any remaining gaps; it must not label planned
tests as passed. From a fresh Prime Agent session in another directory, verify native
`jev` discovery, run an approved local task, check its independent outcome, and view its
PNG. Also test typed provider failure, profile contention and login persistence.

Source pin, license and local changes: `SOURCES.md`. Maintenance contract: `SPEC.md`.
