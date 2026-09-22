# Jev skill maintenance contract

Class: workflow-process plus Python integration. Shape: one callable executor with a
small subprocess protocol. A separate runtime is necessary because upstream needs
Python 3.12 while Prime Agent kernels may use 3.11. Do not install upstream into the kernel.

## Invariants

- Keep Astra's browser_use API and exact default openai/gpt-6-astra unchanged.
- Require an explicit HTTP(S) URL. No schema argument or invented extraction support.
- Preserve provider error messages, typed noncompleted errors and partial artifacts.
- A returned completed status is an executor claim, not independent verification.
- Persist named login profiles with exclusive ownership and bounded full-tree cleanup.
- Native PNG from CDP, absolute paths and main-session attachment. No silent JPEG conversion.
- Telemetry off. No personal Chrome attachment. No unrelated dotenv loading.
- Null cost remains unknown; account for all model roles, including the value-binding
  call; stop when successful calls cannot be costed. No silent fallback or replay after
  uncertain side effects.
- The vendored tree is a maintained fork, not a copy. Upstream DOM snapshot rules and
  the NEXT_ACTION and TARGET rules stay as pinned. Every in-tree change is listed in
  `runtime/vendor/PROVENANCE.md`, and `runner.py` DEVIATIONS keeps its `fork:` entry.
- A supplied value is copied into the field byte for byte. No strip, no punctuation
  change, no normalisation. An empty string clears the field.
- With `generation="disabled"` the text helper is never called, and a field with no
  bound value is skipped rather than guessed. A skip types nothing.
- Supplied values reach the decision model. The `run` docstring, SKILL.md and README
  must keep saying that credentials never belong in `values`.
- `result["actions"]` carries `value_key` and `value_source` for every action. The
  typed text itself stays out of the result.
- Declared DOM checks are scoped evidence, never a verdict. `result["verification"]`
  keeps `scope="declared_dom_checks_only"` and per-row `boundary="browser_dom"`, and it
  is a different field from `output["verification"]`, which stays `"not_performed"`.
  A failed or unknown check never changes the run status, and a passing check never
  claims backend persistence or goal verification. The wrapper correlates returned
  rows with the normalized declarations on completed and non-completed results alike.
- Only an observed mismatch is `failed`. Missing, ambiguous, invisible, refused or
  unreadable evidence is `unknown`; no declared check is `not_run`.
- Checks are read-only and run once, after execution and before teardown, including
  after a partial stop while the browser is alive. They never click, type, navigate or
  execute caller-supplied JavaScript, and only the kind and selector reach the page.
- Password, `type=hidden` and file inputs are refused and never return a value. There
  is no attribute kind and no generic hidden-field extraction.
- One contract file, `src/jev/checks.py`, validates checks in the wrapper before launch
  and again inside the runner, which loads that same file by path. Neither boundary may
  keep its own copy of the rules, and install.py must keep shipping `src/` and
  `runtime/` together.

## Trigger cases

Should trigger: navigate through a known site; fill an approved test form; fill a form
with caller-supplied exact values; clear a field; complete a specified booking in
staging; run a bounded browser interaction with screenshot return; use a persistent Jev
login profile; delegate a whole action-heavy browser task.

Should also trigger: assert a final URL, a visible status text, a field value or an
element count on the end page through `checks`.

Should not trigger: typed HN title extraction without actions; explain arbitrary source
code; native iOS/Android testing; filesystem editing; requests for visual acceptance with
no reference; implicit authorization to pay or send a message; passing a password, token
or other credential through `values`.

## Required validation cases

Native loader in a fresh session; successful local navigation; approved form checked
against server state; native PNG capture and parent viewing; same-profile lock conflict;
cancel during spawn and during work, cleanup and reuse; timeout; malformed JSON protocol;
provider401 with real message; missing screenshot; missing cost; login with no key and
cookie/localStorage persistence after browser restart; absent Chrome/runtime dependency
reported clearly; explicit unsupported-task handoff with no action replay.

Exact-value binding adds its own cases: a supplied value typed byte for byte, including
punctuation, a trailing space and Unicode; an empty string that clears a field; no
supplied value bound with `generation="disabled"`, which skips and makes no helper call;
the same case with `generation="helper"`, which calls the helper; a `{"text": null}`
helper answer that skips instead of erroring; three skips in a row ending as blocked;
a StalePage retry that does not bind twice; the binding call costed through `post_json`;
and rejection of a bad key, a non-string value, more than 20 entries or a value over
2000 characters.

Declared DOM checks add their own cases: every kind against a real page; a mismatch
reported failed; an ambiguous, missing, invisible, password, hidden, file or non-field
selector reported unknown; an invalid selector reported unknown; a torn-down page
reported unknown for every row; mixed outcomes summarised as failed; no declared check
summarised as not_run; a failed check leaving the run status unchanged; identical
validation and identical messages in the wrapper and in the runner, including unknown
keys, duplicate ids, bool-as-count and non-finite numbers; the observed password and
hidden-field values never returned; and evidence surviving into `result.json` and
through the wrapper.

Do not claim every case passed unless VALIDATION.md points to its evidence. Changes to
the runtime, the provider, the source pin or the vendor fork require both deterministic
checks and bounded live smoke.
