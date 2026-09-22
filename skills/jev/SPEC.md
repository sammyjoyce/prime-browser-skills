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
- The vendored tree is a maintained fork, not a copy. Upstream DOM snapshot collection
  and the NEXT_ACTION and TARGET rules stay as pinned; the snapshot may report more
  about itself, and today it adds `text_truncated`. Every in-tree change is listed in
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
  rows with the normalized declarations on completed and non-completed results alike,
  and pins `note` and `consistency` to the contract's own values.
- A row names its declaration with `fingerprint`, the SHA-256 of the normalized check,
  computed at both boundaries before anything is serialized. The declaration itself is
  never echoed back, so there is one source of truth and the runner's single redaction
  pass over its whole result cannot turn an honest run into a protocol error. Identity
  is the fingerprint, not the row `id`, which redaction may legitimately rewrite. The
  fingerprint detects a mismatched declaration; it is not a signature and claims
  nothing about a runner that lies.
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
  `runtime/` together. `src/jev/confidence.py` is the same arrangement for cutoffs.
- Confidence cutoffs are an optional caller policy, never a calibrated success rate and
  never an authority. `operation`, `target` and `binding` are independent gates, each a
  finite number in (0, 1]; `None` and `{}` record the scores and withhold nothing; there
  is no default cutoff in any layer. A score above a cutoff never overrides
  `generation="disabled"`, freshness, the skip-when-unbound rule, the cost stop or the
  truncated-DONE rule.
- A withheld step dispatches nothing, keeps its history row with
  `dispatch="not_dispatched"`, clears `pending_text` and stops the run at
  `needs_review`. `needs_review` is not `blocked`, not `browser_error` and not a retry
  instruction: the caller inspects the page first.
- The snapshot says when its own evidence was cut. `text_truncated` is computed in
  `snapshot.js`, never inferred from `len(text) == 6000`, and the decision and binding
  calls are told `omitted_actions`, `text_truncated` and the viewport. Truncation never
  halts an ordinary click, fill, select, scroll or wait.
- DONE on a truncated observation is not a completion. Without declared checks it is
  `needs_review`; with declared checks the executor may accept it provisionally, and the
  runner still refuses `completed` unless every declared check passed. BLOCKED with
  omitted actions is always `needs_review`: a cut action list is not proof that no
  supported operation exists. Every declared check passing is still scoped DOM evidence,
  never proof that the task finished or that a server stored anything.
- Cost is checked after every model call and before any input, through a callback the
  runner passes into the agent. An uncosted or over-budget call cannot bind, cannot call
  the text helper and cannot type. Unknown cost stays `None`, never `0.0`, and both the
  decision and helper roles keep being accounted.
- `result["side_effects"]` is `none_observed` or `uncertain` and never `confirmed`.
  `none_observed` means no click, fill, select or scroll reached the page after a
  passing freshness check; it is not a claim about a server. Any dispatched or
  interrupted input makes the whole run `uncertain`. A freshness failure before input
  dispatched nothing and stays a safe re-observation, never an uncertain input.
- `handoff["input_dispatched"]` names what the decision the run stopped on sent, and it
  is correlated, never counted. The executor records the answer for the decision it is
  executing before every step that can raise, and names that decision with a monotonic
  internal id the decision record and its history row both carry. Row counts cannot
  answer it: a pre-input `StalePage` consumes a decision without recording a row, so one
  row fewer than decisions describes a dispatched click followed by a budget stop on a
  later decision exactly as it describes a run that sent nothing. A record that is
  missing or names another decision reads `unknown`, never `not_dispatched`.
- `result["handoff"]` is an allowlist: reason, choice, operation, target, the three
  scores, binding key, the observation, `input_dispatched` and the fixed
  `resume_policy` string. No task, values, labels, previews, page text, screenshots,
  `page_key`, guards, marker, credentials, raw provider bodies or CDP identifiers, and
  no nested object other than the observation. It is a record to inspect, never a
  resumable session.

## Trigger cases

Should trigger: navigate through a known site; fill an approved test form; fill a form
with caller-supplied exact values; clear a field; complete a specified booking in
staging; run a bounded browser interaction with screenshot return; use a persistent Jev
login profile; delegate a whole action-heavy browser task.

Should also trigger: assert a final URL, a visible status text, a field value or an
element count on the end page through `checks`; withhold input below a caller-declared
confidence cutoff through `confidence`.

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

Confidence, truncation and dispatch add their own cases: each gate withholding
separately, with no bind and no helper call when an earlier gate already failed; a
low-confidence `NONE` binding withheld rather than skipped; independent gates leaving
the other scores alone; the same low scores typing normally with no policy; a valid and
an invalid policy rejected identically in the wrapper and in the runner; an uncosted or
over-budget decision, bind or helper call stopping before input; an interrupted
`Browser.act` recorded as `dispatch="unknown"` and `needs_review`; a pre-input
`StalePage` re-observed without becoming an uncertain input; that same `StalePage`
followed by a dispatched click and a `max_steps` stop reported as `attempted`, paired
with a budget stop on a newer decision that leaves the identical row and decision counts
and is still reported as `not_dispatched`; DONE on truncated evidence
with no declared check reported `needs_review`; the same DONE accepted only when every
declared check passed and refused when they failed or could not be read; a truncated
page still accepting a click; a click, fill or select whose target field is missing
still withheld when the target gate is on; a later tick that re-observes then stops
reporting the new page in both `observation` and the handoff; a task, a supplied
value, a field label and page text all absent from the handoff; and the real
snapshot's `text_truncated` measured in headless
Chrome at 20, exactly 6000 and over 6000 visible characters, with extra in-view, hidden
and off-screen trailing nodes, plus 251 in-view controls reporting one omitted action.

Declared DOM checks add their own cases: every kind against a real page; a mismatch
reported failed; an ambiguous, missing, invisible, password, hidden, file or non-field
selector reported unknown; an invalid selector reported unknown; a torn-down page
reported unknown for every row; mixed outcomes summarised as failed; no declared check
summarised as not_run; a failed check leaving the run status unchanged; identical
validation and identical messages in the wrapper and in the runner, including unknown
keys, duplicate ids, bool-as-count and non-finite numbers; the observed password and
hidden-field values never returned; and evidence surviving into `result.json` and
through the wrapper.

Correspondence adds its own: a credential-shaped declaration keeping the run's real
outcome through a real runner process and through the exact bytes `emit()` writes; a
passing, failed and unknown result accepted after that redaction pass; and a changed
selector, expectation, id, kind or row order, a missing or malformed fingerprint, a
widened row boundary and a forged note or consistency each rejected as a protocol
error.

Do not claim every case passed unless VALIDATION.md points to its evidence. Changes to
the runtime, the provider, the source pin or the vendor fork require both deterministic
checks and bounded live smoke.
