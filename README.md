# prime-browser-skills

Seven Prime Agent skills for browser work: two runtime skills that drive a real Chrome,
and five report-only QA workflow skills that use them.

| Skill | Type | What it does |
|---|---|---|
| `skills/browser-use` | Python skill | Runs a whole browser task with `browser-use-pi`. Structured extraction, open-ended pages, saved logins. |
| `skills/jev` | Python skill | Runs navigation, forms, and defined multi-step interactions with the pinned Jev runtime. |
| `skills/web-qa` | Markdown skill | Routes a QA request and runs the smoke pass. |
| `skills/web-dogfood` | Markdown skill | Bounded exploratory testing against real user goals. |
| `skills/web-visual-qa` | Markdown skill | Compares a UI with a named visual reference. |
| `skills/web-accessibility-qa` | Markdown skill | Keyboard, accessibility tree, and contrast evidence. |
| `skills/web-interaction-qa` | Markdown skill | Checks that a UI action really changes backend state. |

The QA skills are instruction-shaped. They ship no scripts and no packages.

## Requirements

- macOS or Linux.
- Prime Agent with its Python skill loader.
- Installed Google Chrome or Chromium. Neither skill downloads a browser.
- `browser-use`: Python 3.11+, Node 22.19+, `OPENAI_API_KEY`.
- `jev`: `uv`, Python 3.12+ for its separate runtime, `OPENROUTER_API_KEY`.

## Install

Prime Agent loads skills from `~/.prime/agent/skills/<name>/`. Copy or link the
directories you want:

```sh
git clone https://github.com/sammyjoyce/prime-browser-skills
cd prime-browser-skills
python3 install.py --dry-run            # show what would happen
python3 install.py                      # copy into ~/.prime/agent/skills
```

As alternatives, use `--link` to symlink instead of copying, or
`--only browser-use jev` to select specific skills. Existing destinations are skipped.
`--force` replaces an existing destination and removes its contents; review local changes
before using it and repeat runtime setup afterwards.

`install.py` uses the standard library only. `--dest` installs somewhere else, which is
useful for a test install. The destination may not be the repository `skills/` directory
or anything inside it, because that would overwrite or recurse into the source. The copy
drops local state: caches, virtual environments, `node_modules`, artifacts, profiles,
sessions, logs, and every `.env` file except `.env.example`. Plain
`cp -R skills/<name> ~/.prime/agent/skills/` works too.

Start a new Prime Agent session, or restart the Python kernel, after installing.
`browser_use` and `jev` are then pre-imported in the kernel. Do not install another
package named `browser_use`.

## Runtime setup

`browser-use` pins its Node runner to `@browser_use/pi` 0.1.0 with a lockfile:

```sh
cd ~/.prime/agent/skills/browser-use
npm ci --ignore-scripts --no-audit --no-fund
```

`jev` installs its own locked Python 3.12 runtime. It never installs into the kernel:

```sh
cd ~/.prime/agent/skills/jev
uv sync --project runtime --frozen
```

A missing dependency is a setup error. Neither skill installs anything in the
background.

## Models and credentials

- The `browser-use` default model is exactly `openai/gpt-6-astra`. The runner honors
  `OPENAI_BASE_URL` when it is set, and keeps that exact model selector.
- `BROWSER_USE_MODEL` can select another provider-qualified SDK model. That provider
  needs its own valid credentials.
- `jev` is a separate action executor. It uses `OPENROUTER_API_KEY` for both the Jev
  decision model and the `inception/mercury-2.5` text helper. It does not change the
  `browser_use` default.
- An Astra result reports the model as `result["model"]`. A `browser_use` result has no
  `resolved_model` field.
- A Jev result reports `result["model"]` for the requested decision model and
  `result["resolved_model"]` for the version OpenRouter returned. The text helper has
  `result["helper_model"]` and `result["resolved_helper_model"]`. Report the model the
  run returned, not the default.
- There is no silent model or provider fallback, and no automatic replay of a task that
  may already have submitted a form.
- Never print a key value. Set credentials in the environment that Prime Agent inherits.

## Results and screenshots

Every completed run saves a PNG and returns absolute paths. `jev` captures the PNG
directly through Chrome CDP.

A path in a message is not an image. The session that must see the screenshot calls the
native `attach_image` skill:

```python
print(await attach_image(result["screenshot_path"]))
```

A Jev result nests its completion fields under `output`:

```python
result["output"]["verification"]        # always "not_performed"
result["output"]["completion_claimed"]  # True when Jev chose DONE
result["output"]["final_url"]           # with final_title and page_text
result["verification"]                  # scoped DOM checks, "not_run" by default
```

`jev.run` also takes `values` and `generation` for exact form values:

```python
result = await jev.run(task, url=start_url, profile="work",
                       values={"reviewer_name": "Ada Lovelace"})
result["actions"][0]["value_key"]       # supplied key, or None
result["actions"][0]["value_source"]    # "supplied", "helper", "skipped", or None
```

Values are typed byte for byte, and an empty string clears the field. `generation` is
`"helper"` or `"disabled"`. It decides whether the text helper may write a value when
none is bound, and it defaults to `"disabled"` when you pass `values` and to `"helper"`
when you do not. The typed text never appears in the result. `skills/jev/SKILL.md` holds
the full rules.

`jev.run` also takes `checks`, a list of read-only DOM assertions about the page the
browser ends on:

```python
result = await jev.run(task, url=start_url, profile="work", checks=[
    {"id": "landed", "kind": "url", "contains": "/thanks"},
    {"id": "banner", "kind": "text", "selector": "#status", "equals": "Thank you"},
    {"id": "errors", "kind": "count", "selector": ".field-error", "equals": 0},
])
result["verification"]["status"]     # passed, failed, unknown or not_run
result["verification"]["checks"][0]  # id, status, reason, observed evidence, fingerprint
```

The kinds are `url`, `title`, `text`, `value` and `count`, with `equals` or `contains`.
They run once after execution, read only, with no model call and no arbitrary
JavaScript. `result["verification"]["scope"]` is always `declared_dom_checks_only`, and
this is a different field from `result["output"]["verification"]`, which stays
`"not_performed"`. Only an observed mismatch is `failed`; missing, ambiguous or refused
evidence is `unknown`. A failed check does not change the run status, and passing DOM
evidence is not proof that a server stored anything. Your declaration is not echoed
back: each row carries the SHA-256 `fingerprint` of the check it answers, and a result
whose ordered fingerprints are not the declared ones raises `jev.JevProtocolError`.

`jev.run` also takes `confidence`, an optional dict of cutoffs for three independent
gates. The numbers are illustrative, not a recommendation: they are caller policy, and
there is no default:

```python
result = await jev.run(task, url=start_url, profile="work",
                       confidence={"operation": 0.8, "target": 0.85, "binding": 0.9})
```

Below a declared cutoff Jev withholds the input, dispatches nothing, and stops with
status `needs_review`, which raises `jev.JevError` carrying the partial result. Read
`error.result["handoff"]` for the allowlisted record of what it was about to do, and
`error.result["side_effects"]` for `"none_observed"` or `"uncertain"`, which is never
`"confirmed"`. `result["observation"]` reports whether the page's visible text or its
action list was truncated. Inspect the page; never replay the decision.

A completed status means the executor claimed the task was done, the screenshot was
saved, and cleanup succeeded. It is not independent proof. Check the real postcondition,
and for writes check the saved state rather than a success message. A DONE claimed on a
truncated observation is not accepted as completed unless declared DOM checks were run
and every one of them passed.

Every non-completed status raises a typed error that keeps the real provider message and
any partial result.

## Profiles

Logins persist in named profiles:

- `browser-use`: `~/.prime/agent/browser-use/profiles/<profile>/`, moved with
  `BROWSER_USE_HOME`.
- `jev`: `$JEV_HOME/profiles/<profile>/`, default `~/.prime/agent/jev`.

The two skills keep separate profile trees. The same name in both does not share a
login. One process owns a profile at a time; a second caller fails instead of queueing.
Use different profile names for parallel tasks. Do not point either skill at your daily
Chrome user-data directory.

## Capability limits

- Jev chooses code-owned actions from the observed DOM. It takes no output schema and
  writes no free-form answer. Use `browser_use` with Astra for typed extraction and
  open-ended reasoning. `checks` returns evidence for assertions you declare yourself;
  it is not an extraction API, and it reads only the current page's DOM.
- Shadow DOM, iframes, canvas, upload, popups, and arbitrary keyboard input are not
  established capabilities. Verify or report the task as blocked.
- Jev's text helper writes free-text values. It can change a value, for example by
  adding punctuation. Pass exact strings in `values` instead, which are typed byte for
  byte, and set `generation="disabled"` to stop the helper writing anything. Read the
  saved value back before you report success either way.
- Keys and 80-character previews go to OpenRouter in the decision request, but that
  preview is not a privacy bound. Once a value is typed, the full value is visible too,
  in the observed field value and recent actions, and to the text helper when
  `generation="helper"` runs. Never put a credential or private data in `values`.
- Native iOS and Android apps are out of scope for both skills.
- Cost limits are soft. Jev now checks the budget after every model call and before any
  input, so an uncosted or over-budget call cannot bind a value, call the text helper or
  type; what can still overshoot is the one request already in flight, including the
  retries the client makes inside it. Missing usage data is unknown, never free.
- A natural-language prohibition in a task is not a sandbox. Page content can be hostile,
  and browser-driven JavaScript has host filesystem and network access. Use an isolated
  machine for untrusted browsing.
- Artifacts, profiles, page text, and screenshots can hold private data. Known
  environment secret values are redacted from returned text, but screenshots are not
  sanitized. Review artifacts before publishing them.

## Validation status

Each runtime skill ships deterministic tests. The commands below need no key and no paid
call, and only the optional Jev groups need Chrome:

Run each command from the repository root. None of them changes the working
directory:

```sh
npm --prefix skills/browser-use ci --ignore-scripts --no-audit --no-fund
npm --prefix skills/browser-use test
uv run --project skills/browser-use python -m unittest discover -s skills/browser-use/tests -v
uv sync --project skills/jev/runtime --frozen
uv run --project skills/jev python -m unittest discover -s skills/jev/tests -v
uv run --project skills/jev/runtime --frozen python skills/jev/runtime/tests/run_tests.py
python3 -m unittest discover -s tests -v
```

The last command tests `install.py` and needs no browser and no dependency install.
The Jev runtime suite also takes `--group checks`, `--group guards`, `--group browser`
and `--group login`. All four start a real Chrome and still make no model call.
`checks` and `guards` are headless, on a throwaway profile with a private
browser-harness daemon: `checks` exercises the declared DOM checks against a local
fixture, and `guards` measures the snapshot's truncation and action-cap metadata:

```sh
uv run --project skills/jev/runtime --frozen python skills/jev/runtime/tests/run_tests.py --group checks
uv run --project skills/jev/runtime --frozen python skills/jev/runtime/tests/run_tests.py --group guards
```

Add `--reinstall-package jev-ultrafast` to the `uv sync` line after any change to the
vendored tree; the runtime installs that package non-editably.

`uv` and `npm` create `.venv` and `node_modules` inside the skill directories. Both are
ignored by git.

On 2026-09-21, run from this public checkout with provider credentials removed, these
suites reported 98 Jev runtime checks, 50 Jev wrapper tests, 33 browser-use Node tests,
35 browser-use Python tests, and 9 installer tests, with no failures. The Jev suites
have grown since: exact-value binding, declared DOM checks, the confidence cutoffs and
truncation honesty, and a protocol-consistency follow-up have each landed in turn. The
first declared-DOM-checks landing measured 273 Jev runtime unit checks, 49 Jev runtime
`checks`-group checks against real headless Chrome, 75 Jev wrapper tests, 52 Jev vendor
tests, and 10 installer tests; its own protocol-consistency follow-up remeasured 288
runtime unit checks, 51 `checks`-group checks, and 94 wrapper tests, with vendor and
installer untouched. The confidence, truncation and handoff work measured 514 runtime
unit checks and 85 wrapper tests on its own base, and 522 runtime unit checks, 49
`checks`-group checks, 23 `guards`-group checks, 96 wrapper tests, 90 vendor tests, and
10 installer tests once stacked on the declared-DOM-checks layer, before that layer's
own protocol-consistency follow-up. Those figures are historical. With every layer
combined in the tree, including the protocol-consistency follow-up and the four
confidence-safety review fixes, the current Jev counts are 605 runtime unit checks, 51
`checks`-group checks and 23 `guards`-group checks against real headless Chrome, 104
wrapper tests, 95 vendor tests, and 10 installer tests. The browser-use counts are still
the 2026-09-21 measurements. None of these suites makes a model call. All except the
`checks` and `guards` groups use fake runners or offline runtime paths; those two groups
drive real headless Chrome against a loopback fixture. None of them establishes
live task success.

Live validation of the native `jev` package is still in progress. A live navigation task
passed. A live form task has failed in two different ways, and both failures are kept on
record. Exact-value binding has deterministic tests with mocked model responses only and
no live run at all. Declared DOM checks and the snapshot truncation flags do have real
headless-browser evidence, because they need a page and not a model, but no live model
run has used `checks` or `confidence` yet. Do not read these deterministic results, or
the benchmark below, as proof that form tasks are validated.
`skills/jev/VALIDATION.md` holds the live record and is not allowed to mark a planned
check as passed.

## Benchmark summary

An early comparison ran 18 attempts over three local HTML fixture tasks, nine per
engine. Jev passed 9/9 independently verified checks; Astra passed 8/9. Over the eight
attempt pairs where both engines passed, summed wall time was 75.5 s for Jev against
511.0 s for Astra, a 6.76x ratio.

The two engines do not account for cost the same way. Jev uses OpenRouter per-request
costs; Astra uses the SDK catalog estimate. Treat any cost ratio as approximate. This is
a small local-fixture sample. It supports the executor split for action-heavy HTML
tasks. It is not evidence of production reliability or native app coverage. The raw
benchmark artifacts are not published here.

## License

MIT, see `LICENSE`. Third-party code and attribution are listed in `THIRD_PARTY.md`.
