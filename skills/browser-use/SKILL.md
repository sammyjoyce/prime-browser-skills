---
name: browser-use
description: Run whole browser tasks with browser-use-pi from the Prime Agent Python kernel. Use for browsing, extracting structured page data, checking local app UI, and tasks that need a saved login. Includes headed manual login and a subagent delegation recipe.
compatibility: macOS or Linux, Python 3.11+, Node 22.19+, installed Google Chrome or Chromium, and OPENAI_API_KEY for the default model.
---

# Browser use

## Setup

This Python-backed skill is installed globally at `~/.prime/agent/skills/browser-use/`.
Prime Agent loads `browser_use` automatically in new sessions. Restart the kernel or
start a new session after installation. Do not install another `browser_use` package.

The Node dependency is pinned to `@browser_use/pi` **0.1.0** with a lockfile. To restore it:

```sh
cd ~/.prime/agent/skills/browser-use
npm ci --ignore-scripts --no-audit --no-fund
```

Use Node 22.19+ and an installed Chrome or Chromium. No browser download is required.
Set `OPENAI_API_KEY` in the environment inherited by Prime Agent. Never print its
value. The runner honors `OPENAI_BASE_URL` when set, while retaining the exact
`openai/gpt-6-astra` model selector. OpenRouter credentials are only needed if you
explicitly choose an `openrouter/...` model. The default browser model is exactly `openai/gpt-6-astra`, as requested.
The original POC used `openrouter/anthropic/claude-opus-5`; it is no longer the default.
`BROWSER_USE_MODEL` can select another provider-qualified SDK model, but its provider
must have valid credentials. The browser model is independent of the parent or child
Prime Agent model. There is no silent model fallback.

Telemetry is disabled with `telemetry: false`, `DO_NOT_TRACK=1`, and
`ANONYMIZED_TELEMETRY=false`. A new Node process owns each browser call. Python keeps
no live browser objects or model sessions between calls.

## Jev companion

The separate `jev` skill is available for defined navigation, form, and multi-step
interaction tasks. Read its SKILL.md before calling `jev.run(task, url, ...)`.
Use this Astra-backed skill for structured extraction and tasks outside Jev's supported
action set. A handoff must inspect current state first; never replay an uncertain
submission automatically. The default here remains `openai/gpt-6-astra`.

## Run a browser task

```python
result = await browser_use.run(
    "Open https://news.ycombinator.com and return the titles of the top 3 stories in order.",
    schema={
        "type": "object",
        "properties": {"titles": {"type": "array", "items": {"type": "string"},
                                  "minItems": 3, "maxItems": 3}},
        "required": ["titles"],
        "additionalProperties": False,
    },
    profile="default",
    max_steps=25,
    timeout_ms=180_000,
    max_cost_usd=1.0,
)
print(result["output"])
print(result["screenshot_path"])
```

`schema` may be a JSON Schema dictionary, a Pydantic model class, or `None` for text.
All limits must be positive. Cost is in US dollars and is approximate. The SDK checks
its cost cap between turns, so a response can exceed it. `timeout_ms` bounds the model
run. Startup, screenshot capture, and cleanup have a separate bounded allowance.

Successful results are dictionaries with `status="completed"`, `output`, `text`,
`steps`, `cost`, `screenshot_path`, and `artifact_dir`. Run results also include usage,
model, duration, history and event paths, warnings, and any partial result. Artifact
paths are absolute. A completed run must have a screenshot; a screenshot failure raises
an `artifact_error` rather than pretending the full skill call succeeded.

Every non-completed status raises `browser_use.BrowserUseError`. The error keeps the
status and result dictionary, including any partial output and artifacts. Provider
errors come from `agent.events()` and the SDK error field, not the generic status.
Do not blindly retry a task that might already have submitted a form or changed data.

```python
try:
    result = await browser_use.run("Inspect https://example.com", max_steps=10)
except browser_use.BrowserUseError as error:
    print(str(error))  # Real provider or limit message; known environment secrets are redacted.
    print(error.status)
    print(error.result)
```

## View screenshots in the main session

Every successful browser run saves `screenshot.png` before Chrome closes. The returned
`screenshot_path` is an absolute path on the same machine as Prime Agent. A child can
send this path and the task result to its parent:

```python
result = await browser_use.run("Open https://example.com and describe the page.")
await agent_message.send(
    json.dumps({key: result[key] for key in
                ("status", "output", "steps", "cost", "screenshot_path", "artifact_dir")}),
    receiver_role="parent",
)
```

Import `json` before that example. Once the parent receives the path, it loads the
actual image into its own model context with the native `attach_image` skill:

```python
print(await attach_image("/absolute/path/from/the/child/screenshot.png"))
```

A path in a message is not itself an image attachment. The parent's `attach_image`
call is the step that lets the main session see it. Do not send base64 through chat.
The PNG remains available after the child and Chrome exit. This works for local
Prime Agent sessions sharing the filesystem; remote agents need a separate file
transfer. Screenshots can contain private page content and are not redacted.

## One-time manual login

Tell the user Chrome will open and that they must close every window for this profile
when finished. Then call:

```python
await browser_use.login("work", "https://your-app.example/login")
# Optional timeout_ms=600_000; default is ten minutes.
```

This opens headed Chrome. The user signs in, including MFA, then closes its windows.
No model runs during login and no API key is required. The method returns after Chrome
closes. It reports `authenticated=None` because closing a window does not prove login
succeeded. It does not capture a screenshot of credentials. A later read-only browser
task should verify the signed-in state.

```python
result = await browser_use.run(
    "Open https://your-app.example and report whether I am signed in. Do not change anything.",
    profile="work",
)
```

Cookies, localStorage, and IndexedDB persist under
`~/.prime/agent/browser-use/profiles/<profile>/`. Set `BROWSER_USE_HOME` to move both
profiles and artifacts. Profile names allow letters, digits, underscores, and hyphens,
starting with a letter or digit, up to 64 characters. Use different profiles for
parallel tasks. The same profile has one owner across Prime Agent sessions; a second
caller fails rather than queueing or sharing Chrome.

A hard crash can leave the SDK's `.bu-pi.lock`. Do not delete it blindly. Confirm that
its recorded PID and every Chrome process using that profile have exited before
removing that file. Do not point the skill at your daily Chrome user-data directory.

## Delegate a whole browser task

Prefer one child for one complete browser objective. Do not delegate individual clicks.
Choose an available provider-qualified Prime Agent model with `rlm.find_models` and
follow the session's model-selection rules. For example, after confirming availability:

```python
child = await rlm.spawn(
    "Read the browser-use SKILL.md. Use await browser_use.run to inspect "
    "http://localhost:3000/login. Report every form field, button, and link. "
    "Do not fill credentials, submit, sign in, or change application data. "
    "Use profile='login-inspect', max_steps=25, timeout_ms=180000, max_cost_usd=1. "
    "Reply with output, steps, cost, and absolute screenshot/artifact paths via "
    "await agent_message.send(..., receiver_role='parent'). "
    "If it fails, report the BrowserUseError status and actual message. Do not retry actions.",
    name="browser-inspector",
    model="openai/gpt-6-astra",
    thinking="max",
)
```

Spawn returns at admission. End the turn while the child works; its explicit message
contains the result. Use a unique profile if another browser call may be active.
Give the child the exact URL, success condition, output schema, limits, and prohibited
actions. Get user approval before purchases, messages, deletion, or other consequential
submissions. For a task involving authentication, complete `login` before delegating.

## Trust and artifacts

Browser-generated JavaScript has host filesystem and network access. This is not a
sandbox. Page content can be hostile. Use an isolated machine for untrusted tasks.
Navigation policies are not filesystem or network isolation.

Profiles and artifacts are private local data. Each call writes a separate directory
under `~/.prime/agent/browser-use/artifacts/`, including `result.json`, `screenshot.png`
for runs, SDK history/events, cell outputs, and runner stderr. Known environment secret
values are redacted from returned text and SDK transcripts, but screenshots and
agent-written files are not guaranteed to be sanitized. Do not publish these artifacts
without review. Do not put credentials in task text. There is no automatic retention
policy; remove old artifact directories when no longer needed.

## Validation

Run deterministic packaging and protocol tests from the skill directory:

```sh
npm test
uv run python -m unittest discover -s tests -p 'test_*.py' -v
```

From a **fresh `prime-agent` session in another working directory**, read this skill and
confirm that `browser_use` is pre-imported. Check `help(browser_use)` and call the API
without modifying `sys.path` or manually importing the source file.

1. Run the HN example above. Require three ordered nonempty titles, `completed`, and a
   valid PNG at the returned absolute path. Compare titles with the live front page.
2. Run a read-only inspection of a local app login page, for example
   `http://localhost:3000/login`. Require accurate fields, buttons and links, a valid
   PNG, and no form submission. Do not edit or commit in the app under test. The app
   must already be running.
3. Exercise a provider failure and a step/timeout limit. Require `BrowserUseError` with
   the original message and partial result. Do not print any credential value.
4. Exercise headed login without credentials on a harmless local page. Close the profile
   window and verify zero model steps/cost and profile reuse. A real signed-in account
   still needs the user's manual login and a separate read-only check.

The installation handoff and the live validation records stay in the private
implementation project and are not published in this repository.
