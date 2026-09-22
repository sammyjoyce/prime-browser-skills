# Native Jev validation

Validation date: 2026-09-21. Host: macOS with installed Chrome. Wrapper runtime tested
on Python 3.11 and 3.13; the separate browser runtime uses Python 3.12.13.

Exact-value binding landed later, on 2026-09-22. Every count in the next table is from
the 2026-09-21 run against the pre-fork tree. The suites have grown since. See
"Exact-value binding (not live-validated)" for what that change has and has not proven,
"Declared DOM checks" for the later `checks` argument, and "Confidence cutoffs,
truncation honesty and handoff" for the `confidence` argument and the `needs_review`
status. The last two have real headless-browser evidence; none of the three has been
exercised by a live model run.

## Package and lifecycle checks

| Check | Result | Scope |
|---|---|---|
| Python wrapper suite | 50 tests passed | 48 fake-runner cases, 2 real-runtime launch/no-key cases |
| Runtime unit group | 98 checks passed | Request/status contracts, cost accounting, response-shape diagnostics, redaction, direct PNG |
| Runtime browser group | 25 checks passed | Group ownership, cleanup, profile contention/reuse, cancellation and credentials |
| Runtime login group | 23 checks passed | Two headed launches; cookie/localStorage persistence; no model calls |
| Native API lifecycle validation | Six suites passed | Manual-login simulation, cross-process contention, login/run cancellation, real 401, CDP harness check |
| Fresh Prime Agent discovery | Passed | `jev` pre-imported without a manual source import; Astra default unchanged |

The lifecycle checks verified that owned Chrome and daemon processes exited after
cancellation and that the same profile could be reused. Login returned zero steps/cost,
no screenshot and `authenticated=None`. A real invalid-credential request returned the
provider's 401 message in `JevError`, retained unknown cost as null, and did not expose
the credential. These checks do not establish that any real account was signed in.

Production calls launch `runtime/.venv/bin/python` directly with a new process group.
The setup command uses uv, but `uv run` is not the production launcher. A test verified
that runner PID, process-group ID and session ID match. The runtime rejects an unsafe
launch before starting Chrome.

Direct PNG capture is covered by a test that checks the CDP request has `format='png'`
and that the output bytes match the returned bytes. A PNG signature alone would not
exclude JPEG-to-PNG conversion. The completed navigation image was also loaded and
viewed in both its fresh session and the orchestrating session.

## Live task results, including failures

The local fixtures use synthetic data and independent server-state checks. Executor
`completed` is never the independent pass condition.

| Attempt | Executor result | Independent result | Notes |
|---|---|---|---|
| Navigation | completed, 4 actions, $0.00038451 | Pass | Correct route and section feedback; native PNG reviewed |
| Form, initial wording | protocol_error, 2 actions, $0.00058821 | Fail | Text helper returned no valid field value; two fields filled, zero submissions |
| Form, deliberate repeat with same wording | completed, 9 actions, $0.001747608 | Fail | Exactly one submission, but a free-text value gained a trailing period |
| Form, explicitly quoted values | Pending | Pending | One final bounded control, different wording; not a reproduction of the prior failures |

The first failure's response body was not recorded. Its exact cause and selected target
remain unknown. Token count and cost cannot establish what the helper returned.
Metadata-only diagnostics were then added without changing the request or validator.
They report JSON/type/length facts, not values or arbitrary key names.

The passing executor result on the repeat did not override the exact-match failure.
The fixture expectation was not relaxed. The historical failures remain in the record;
there is no automatic retry or fallback. Explicitly quoted field values reduce ambiguity,
but independent readback is still required.

This is a narrow integration check, not evidence of production reliability. The earlier
18-attempt Jev-versus-Astra benchmark used a prototype and different task wording. Its
9/9 Jev result must not be substituted for these native-package outcomes.

## Exact-value binding (not live-validated)

Date: 2026-09-22. Scope: `values` and `generation` on `jev.run`, the vendor fork, and
the `value_key` and `value_source` fields in `result["actions"]`.

This change was tested with mocked model responses and the local HTML fixture only. The
tests mock the model HTTP layer, so they need no API key and make no paid model call.
Every model answer in them is a fixed fake, so they show the wiring, the byte-for-byte
copy and the skip path. They do not show that a real decision model binds the right
value to the right field on a real page.

| Check | Result |
|---|---|
| Wrapper suite with the fake runner, `tests/test_jev.py` | 60 tests passed |
| Runtime unit group | 148 checks passed |
| Vendor fork tests, `tests/test_agent.py` | 52 tests passed |
| Vendor `scripts/check_guards.py` | 22 checks passed |

Wrapper and runtime commands, run from `skills/jev`:

```sh
uv run python -m unittest discover -s tests -v
uv run --project runtime --frozen python runtime/tests/run_tests.py --group unit
```

Vendor commands, run from `skills/jev/runtime/vendor/jev-ultrafast` in the vendor's own
environment:

```sh
uv run pytest
uv run python scripts/check_guards.py
```

`check_guards.py` opens a local browser and makes no model call. Run it only where
opening a browser is appropriate.

Live validation is still owed. Three runs are outstanding:

- A form filled from supplied values against the local fixture, with independent
  readback of every saved field, including punctuation, a trailing space and Unicode.
- A field cleared with an empty string, checked against the saved server state.
- A run with `generation="disabled"` where one field has no bound value, to confirm the
  skip is recorded, nothing is typed, and the rest of the form still completes.

The two earlier form failures stay in the record above. A free-text value that gained a
trailing period, and a protocol_error on an invalid helper value, are the reason this
change exists. Neither is marked fixed. Deterministic tests do not retire them.

## Declared DOM checks (deterministic, including real headless Chrome)

Date: 2026-09-22, remeasured after the row-fingerprint follow-up. Scope: the
`checks` argument on `jev.run`, the shared contract file `src/jev/checks.py`,
`runner.verify_declared_checks`, and the new `result["verification"]` object. This did
not change the agent loop, the vendored fork, the provider path, the lifecycle or any
existing argument. The 2026-09-22 landing measured 75 wrapper tests and 273 unit
checks; the follow-up that correlates returned rows with declarations, validates
non-completed verification objects, and records URL/title truncation remeasured 86
wrapper tests and 281 unit checks. The row-fingerprint follow-up, which stopped the
correspondence gate from comparing the runner's redacted echo of the declaration,
measures 94 wrapper tests, 288 unit checks and 51 `checks`-group checks. Historical
2026-09-21 package counts stay in the table above.

Unlike exact-value binding, this change has live browser evidence, because a declared
check is deterministic: it needs a page, not a model. The `checks` group starts its own
headless Chrome with its own profile and its own browser-harness daemon, serves a local
fixture page, and runs the same `verify_declared_checks` the runner calls. It makes no
model request and needs no API key.

| Check | Result |
|---|---|
| Wrapper suite, `tests/` (89 methods in `test_jev.py` plus 5 real-runtime cases) | 94 tests passed |
| Runtime unit group | 288 checks passed |
| Runtime `checks` group, real headless Chrome and one real runner process | 51 checks passed |
| Vendor fork tests, `tests/test_agent.py` (unchanged by this follow-up) | 52 tests passed (2026-09-22; vendor tree not edited) |
| Installer tests, repository `tests/` | 10 tests passed (2026-09-22; installer not edited) |

Commands, exit code 0 for each, run on 2026-09-22 from this checkout:

```sh
cd skills/jev
uv run python -m unittest discover -s tests -v
uv run --project runtime --frozen python runtime/tests/run_tests.py --group unit
uv run --project runtime --frozen python runtime/tests/run_tests.py --group checks
cd runtime/vendor/jev-ultrafast && uv run pytest -q
cd ../../../../.. && python3 -m unittest discover -s tests -v
```

Lint, with the vendor's own ruff and its 120-character line length, over every file this
change touched:

```sh
cd skills/jev/runtime/vendor/jev-ultrafast
uv run ruff check --isolated --line-length 120 --select E,F,I   ../../../src/jev/checks.py ../../../src/jev/__init__.py ../../../runtime/runner.py   ../../../runtime/tests/run_tests.py ../../../runtime/tests/fixture_server.py   ../../../tests/test_jev.py ../../../tests/fake_runner.py   ../../../tests/test_runtime_launch.py
```

That command lists eight files. It reports 24 findings and exits 1, all of them in
`runtime/runner.py` and `runtime/tests/run_tests.py`: 16 pre-existing long lines, 6
deliberate mid-file imports (E402) and the 2 unsorted import blocks those cause. Run
over the same eight files taken from the previous commit on this branch, it reports the
same 24, in the same files under the same rules, so this change adds no new finding and
cleans up none of the old ones. `src/jev/checks.py`, `src/jev/__init__.py` and the
three test modules report nothing.

An earlier revision of this section said 25. That count included one unused import in
the repository's own `tests/test_install.py`, which the command above does not lint;
that file still reports its single F401.

The `checks` group runs two tests. The first starts the real runner process with
declared checks and no `OPENROUTER_API_KEY`: the run stops before Chrome starts, and the
result plus `result.json` report both declared checks as `unknown` with reason
`verification_not_attempted`, never as passed and never dropped. A second request in the
same test carries an unsupported check kind and comes back `invalid_request` from the
runner itself, which is the re-validation the wrapper does not get to skip.

The second test is the browser one. What it proved, on the local fixture at
`runtime/tests/fixture_server.py`:

- Every kind against a real page: exact and substring `url` and `title`, `text` on a
  visible element, `value` on an input, a textarea, a select and a contenteditable
  element, and `count` on 0, 2 and 3 matches.
- A mismatch is `failed` for each kind that can fail.
- Unknown, never failed, for: a selector matching two elements, a selector matching
  none, a `display:none` element, a password input (both `value` and `text`), a
  `type=hidden` input, a file input, an element that holds no value, and two invalid
  selectors.
- The password and hidden-field values in the fixture never appear in any observed
  evidence. They appear in the result only where the test itself declared them as
  expectations, which is the caller's own input.
- The read changes nothing: a document-level capture listener for click, input, change,
  submit, keydown and pointerdown counted zero events, and the field value and element
  count were unchanged afterwards.
- One read per call: every row carries the same `captured_at_ms`, and
  `checked_at_url`/`checked_at_title` describe the document that was read.
- After a navigation, a second call reports the new URL and different outcomes, which is
  why the checks are documented as an end-state snapshot rather than a per-action
  assertion.
- After the page was closed, every row is `unknown` and nothing raised.

Mocked and unmocked contract evidence in the unit group and the wrapper suite:

- Both boundaries reject the same 29 invalid shapes (the `invalid` list in
  `test_declared_check_contract`, asserted against `normalize_checks` and against
  `runner.normalize`). The wrapper-only list in
  `test_checks_must_follow_the_declared_schema` is 30 shapes; it is not the same set.
  The runtime launch test runs the real runtime interpreter to confirm it loaded the
  wrapper's own `checks.py` and produced byte-identical normalized output and identical
  rejection messages.
- A failed or unknown check leaves the run status `completed`, leaves
  `output["verification"]` at `"not_performed"`, and only adds a warning.
- A result whose verification is missing, short, mis-scoped, mis-bounded, invalid,
  `not_run` with declared checks, present with no declared check, carrying a forged
  `note` or `consistency`, whose rows do not fingerprint the ordered declarations or
  disagree with them on kind or row boundary, whose `declared` count is not the integer
  length, or whose counts/aggregate disagree with the rows is a protocol error in the
  wrapper. The same correspondence check runs on completed results and on non-completed
  results (`max_steps`, `blocked`, missing screenshot). The 14 single-row twists and
  the 2 two-row twists in `fake_runner.twist_verification` are each asserted twice:
  through the fake runner subprocess and directly against `_finish_result`.
- A row names its declaration with a SHA-256 fingerprint computed before transport, so
  the runner's single redaction pass over its whole result cannot break the match. Two
  tests prove it with real code rather than a stand-in. A real runner process with no
  `OPENROUTER_API_KEY` returns `credentials_error` for `contains="Saved"` and for the
  synthetic placeholders `Bearer YOUR_TOKEN_HERE` and
  `sk-EXAMPLE_PLACEHOLDER_00000000` alike, never a protocol error. The runtime
  interpreter also builds a passing, a failed and an unknown payload with its own
  contract and writes exactly the bytes `emit()` would write, redaction included; the
  wrapper parses those bytes and returns `completed` for each, with the redacted row id
  left redacted. Mutating the gate to bind identity to the row `id` again fails those
  tests.
- Declared-check evidence is redacted for known secret environment values before it
  reaches the caller, and `result.json` carries the same object. When the wrapper
  redacts `checked_at_url` or `checked_at_title` a second time, `capture_metadata`
  records `returned_length` beside the runtime's own `length` and `truncated`, so the
  metadata never describes a string the caller did not receive.

Not established by any of this:

- No live model run has used `checks` yet. The binding of a model-driven form fill to a
  declared check has not been exercised end to end.
- A passing check is DOM evidence at one instant. It is not proof of backend
  persistence, and the two earlier live form failures below are not affected by it.
- The group ran on macOS only, against a loopback fixture, in headless Chrome.

## Confidence cutoffs, truncation honesty and handoff (deterministic, including real headless Chrome)

Date: 2026-09-22. Scope: the `confidence` argument on `jev.run`, the shared contract file
`src/jev/confidence.py`, the three gates and the budget callback inside the vendored
agent, `text_truncated` in `snapshot.js`, the `needs_review` status, and the new
`observation`, `side_effects`, `handoff` and `confidence_policy` result keys. Profiles,
the lifecycle, native PNG capture, login and the exact-value binding rules were not
changed.

No live model run exercised any of this. Every case below is deterministic: mocked model
answers, or a real headless Chrome with no model call at all.

These counts are for this work as it stood on the declared-DOM-check layer before
that layer's row-fingerprint follow-up and before the four review fixes, so every
figure in the table below is historical; "Re-run deterministic checks" states the
current combined totals for this tree. On its own base the same work measured 85
wrapper tests and 514 unit checks.

| Check | Result |
|---|---|
| Wrapper suite, `skills/jev/tests/` (92 methods in `test_jev.py` plus 4 real-runtime cases) | 96 tests passed |
| Runtime unit group, including the new `run_operation` integration tests | 522 checks passed |
| Runtime `checks` group, real headless Chrome and one real runner process | 49 checks passed |
| Runtime `guards` group, real headless Chrome, snapshot metadata | 23 checks passed |
| Vendor fork tests, `tests/test_agent.py` | 90 tests passed |
| Installer tests, repository `tests/`, run alone | 10 tests passed |

Commands, exit code 0 for each, run on 2026-09-22 from this checkout, in this order:

```sh
cd skills/jev
uv sync --project runtime --frozen --reinstall-package jev-ultrafast
uv run python -m unittest discover -s tests -v
uv run --project runtime --frozen python runtime/tests/run_tests.py --group unit
uv run --project runtime --frozen python runtime/tests/run_tests.py --group checks
uv run --project runtime --frozen python runtime/tests/run_tests.py --group guards
cd runtime/vendor/jev-ultrafast && uv run --frozen pytest -q
uv run --frozen ruff check jev_ultrafast tests scripts
cd ../../../../.. && python3 -m unittest discover -s tests -v
```

`--reinstall-package jev-ultrafast` matters here: this work changes vendored files, and
the runtime installs that package non-editably. The vendor ruff run reports
`All checks passed!` and exits 0. The installer tests ran alone, because that suite
fingerprints the whole `skills/` tree and another suite writing a `.pyc` at the same time
makes it fail.

Lint over every file this change touched outside the vendored tree, with the vendor's own
ruff and its 120-character line length:

```sh
cd skills/jev/runtime/vendor/jev-ultrafast
uv run --frozen ruff check --isolated --line-length 120 --select E,F,I \
  ../../../src/jev/checks.py ../../../src/jev/confidence.py ../../../src/jev/__init__.py \
  ../../../runtime/runner.py ../../../runtime/tests/run_tests.py \
  ../../../runtime/tests/fixture_server.py ../../../tests/test_jev.py \
  ../../../tests/fake_runner.py ../../../tests/test_runtime_launch.py \
  ../../../../../tests/test_install.py ../../../../../install.py
```

It reports 25 findings and exits 1: 16 E501, 6 E402, 2 I001, 1 F401. That is the same
count, in the same files under the same rules, as the previous change measured on the
same file list, and `src/jev/confidence.py` reports nothing. The old findings were not
cleaned up here.

### What the real browser proved: `--group guards`

The new group starts its own headless Chrome on a throwaway profile with its own
browser-harness daemon and a loopback fixture page, exactly like the `checks` group. It
makes no model call, needs no API key, opens no window, and never attaches to the user's
Chrome. `snapshot.js` decides truncation, so a Python-side guess is not evidence:

- A normal page reports `text_truncated: false`, `omitted_actions: 0`, and viewport
  `w`/`h` of 1120x780, which is the size the vendored `Browser` emulates.
- 20 visible characters: not truncated, text length 20.
- Exactly 6000 visible characters: not truncated, text length 6000.
- 7000 visible characters: truncated, text length 6000.
- 6000 characters plus one more in-view text node: truncated.
- 6000 characters plus `display:none` and `hidden` trailing nodes: not truncated.
- 6000 characters plus a node positioned below the fold: not truncated.
- 251 in-viewport controls: `omitted_actions` is 1, the element list is capped at 250,
  and the wait and scroll sentinels are added outside that cap.
- `runner.observation_of()` over those real snapshots returns exactly the four
  allowlisted keys with the measured values.
- After the group, the owned Chrome process is gone and the harness daemon count is back
  to its pre-test value.

The vendored `scripts/check_guards.py` carries the same snapshot cases, but it needs a
browser daemon it does not own and was not executed. The owned group above is the
evidence.

### What the runner integration proved: unit group

Three of the new unit tests drive the real `run_operation` with the real vendored agent
loop, a fake browser and fake model answers. No Chrome, no daemon, no provider request,
no key. They are integration tests of the parts that only meet inside `run_operation`:

- Each gate withholds on its own. A low operation score stops before the bind call, the
  text helper and any input; a low target score does the same; a low binding score binds
  once and types nothing. A low-confidence "no value fits" answer is withheld, not
  recorded as a skip.
- The same low scores with no policy still type the supplied value byte for byte and
  complete, and the scores are still recorded on the action row.
- An unbound field with `generation="disabled"` still skips, and a skip leaves the run
  `none_observed`.
- An uncosted successful provider attempt stops the run before the bind, before the
  helper and before input; so does an uncosted bind and an uncosted helper answer. Cost
  stays `null`, never `0.0`. Over the cap, the next decision cannot act.
- An interrupted `Browser.act` is `needs_review` with `dispatch="unknown"`, the history
  row survives, and nothing is retried.
- A freshness failure before input re-observes and chooses again: no input was
  dispatched, no row was recorded, and the run stays `none_observed`.
- DONE on a truncated observation with no declared check is `needs_review` with reason
  `truncated_done` and `completion_claimed: false`.
- The same DONE with declared checks is `completed` only when every declared check
  passed, with a warning that says this is scoped page evidence and not proof the task
  finished. When the checks failed, and when they could not be read, the status is
  `needs_review` with reason `truncated_done_checks_not_passed`, the completion claim is
  cleared, and the check evidence is still reported.
- BLOCKED with omitted actions is `needs_review`; a truncated page still accepts a click
  and still completes.
- An untruncated DONE with no declared check is still a plain `completed`.
- The task string, a supplied value, a field label that contains a value, and the page
  text are all absent from every handoff, and the handoff has exactly the allowlisted
  keys.

### Contract and wrapper evidence

- The wrapper rejects 18 invalid confidence policies before any process starts, and
  accepts `{}`, a boundary cutoff of 1.0 and the three-gate form.
- `test_runtime_launch.py` runs the real runtime interpreter and confirms it loaded the
  wrapper's own `src/jev/confidence.py`, normalized 13 policies identically, rejected the
  invalid ones with byte-identical messages, and left `confidence` null for `login`.
- A `needs_review` result raises `jev.JevError` with the partial result, the handoff, the
  action rows and `completion_claimed: false`.
- A completed result carrying a handoff is a protocol error, and
  `side_effects: "confirmed"` is rejected outright, as is any value outside
  `none_observed` / `uncertain`.
- A runner result without the new keys still parses, so an older runner is not a
  protocol error.
- `classify()` maps the vendored `NeedsReview` to `needs_review`, not to
  `browser_error`, and a `StalePage` is still `browser_error`.

### Not established by any of this

- No live model run has used `confidence`, and no live run has hit a truncated page and
  reported `needs_review`. The gates, the budget callback and the truncation rule have
  deterministic evidence only.
- The cutoffs are caller policy. Nothing here calibrates a score against a success rate,
  and no default cutoff exists anywhere in the code.
- `side_effects: "none_observed"` is measured from dispatched input, not from a server. A
  page can call an endpoint while loading.
- The `guards` group ran on macOS only, against a loopback fixture, in headless Chrome.
- The browser and login groups were not re-run for this change.

## Re-run deterministic checks

From the installed Jev skill directory:

```sh
uv sync --project runtime --frozen
uv run python -m unittest discover -s tests -v
uv run --project runtime --frozen python runtime/tests/run_tests.py --group unit
```

These commands require no model key and make no paid model calls. The four
real-runtime wrapper tests skip if runtime setup has not been completed.

`uv sync --project runtime --frozen` installs the vendored `jev-ultrafast` package
non-editably from `runtime/vendor/jev-ultrafast`. The confidence, truncation and
dispatch work does change that package, so its copy in the runtime environment must be
rebuilt before the runtime tests mean anything:

```sh
uv sync --project runtime --frozen --reinstall-package jev-ultrafast
```

The wrapper package is installed editably from `src/`, so `src/jev/checks.py` and
`src/jev/confidence.py` are picked up without a reinstall. The runner loads both files by
path, so an installed copy must always contain both `src/` and `runtime/`; `install.py`
copies them together and a test in the repository's `tests/test_install.py` checks that.

The declared-check group and the snapshot guard group each start their own headless
Chrome and their own browser-harness daemon on a temporary profile. They open no window
and make no model call:

```sh
uv run --project runtime --frozen python runtime/tests/run_tests.py --group checks
uv run --project runtime --frozen python runtime/tests/run_tests.py --group guards
```

The following additional groups open real Chrome windows and use a loopback fixture.
They make no model calls. Run them only on a host where opening Chrome is appropriate:

```sh
uv run --project runtime --frozen python runtime/tests/run_tests.py --group browser
uv run --project runtime --frozen python runtime/tests/run_tests.py --group login
```

`--group all` ran all 146 runtime checks on 2026-09-21, before the unit group grew. On
2026-09-22 the unit group was 273 checks and the `checks` group 49; the declared-check
follow-up that validates every result path took the unit group to 281, and the
confidence, truncation and handoff work measured 514 on its own base. The
row-fingerprint correspondence follow-up, on the declared-check layer alone, took the
unit group to 288 checks and the `checks` group to 51. With confidence, truncation and
handoff stacked on the declared-check layer, before that follow-up, the unit group was
522 checks, the `checks` group unchanged at 49, and the new `guards` group 23. Those
five figures are historical. With every layer combined in this tree, including the
row-fingerprint correspondence fix and the four confidence-safety review fixes below,
the unit group is 605 checks, the `checks` group is 51, and the `guards` group is 23;
those three figures are historical too. With the three landing repairs in "Combined
landing-repair validation" below (binding-identity cache, wrapper failure-path evidence,
dispatch correlation), measured on 2026-09-22, the unit group is 640 checks, the
`checks` group is still 51, and the `guards` group is still 23. The browser and login
groups have not been re-run since 2026-09-21, so no new all-groups total is claimed. Raw
local screenshots, browser profiles, provider logs and Prime Agent transcripts are not
included in the public repository.

## Remaining limits

- Exact field fidelity is not guaranteed by a model completion claim. Supplied values
  are copied byte for byte once bound, but no live run has yet checked a bound value,
  a cleared field or a skipped field against server state.
- A declared DOM check is browser evidence inside the scope the caller declared. It is
  not a verified goal, not a backend readback, and a `completed` status still means the
  executor claimed completion. The two form failures above are not retired by it.
- No production accounts, native mobile devices, uploads, complex iframe or shadow-DOM
  flows, or broad real-site reliability test was performed.
- Model costs are soft limits, checked between calls. Unknown usage stops execution.
- Browser screenshots and page text may contain private data and are not sanitized.
- Linux support follows the code paths, but these live checks ran on macOS only.

## B review-fix validation (isolated archive of `b121a46`)

Date: 2026-09-22. Scope: the four final-review findings on
`771e3bc..b121a46` only. This record is from an isolated archive of `b121a46`
plus the review-fix patch; it does not replace the stacked counts in the table
above, because follow-up A is still adding tests in the live tree.

The source-level gate claims that this patch changes:

- `run_operation` re-reads `safe_snapshot(agent)` after the loop or an
  exception, so `result["observation"]` and `handoff["observation"]` describe
  the page the executor stopped on. The generator yield is used only if that
  in-memory snapshot cannot be read. No extra CDP observation is added.
- The target gate applies from `action["kind"] not in {"wait", "scroll"}`. A
  click, fill or select with `target is None` is withheld when the target
  cutoff is on. `choose()` is unchanged: targeted operations still always
  carry a target.
- Truncated DONE is accepted only through the `checks` seam. There is no
  `allow_truncated_done` constructor flag.
- `handoff` is null on a completed run, on a failure before the agent observed
  a page, and on a DONE that later failed only at screenshot capture or
  cleanup. It is not invented after DONE. An unresolved decision still carries
  the allowlisted record and the no-replay resume policy.

Commands, all exit 0, run in the isolated archive after
`uv sync --project runtime --frozen --reinstall-package jev-ultrafast`:

```sh
cd skills/jev
uv run python -m unittest discover -s tests -v
# Ran 96 tests in 20.304s, OK
uv run --project runtime --frozen python runtime/tests/run_tests.py --group unit
# 598 checks, 0 failed
uv run --project runtime --frozen python runtime/tests/run_tests.py --group checks
# 49 checks, 0 failed
uv run --project runtime --frozen python runtime/tests/run_tests.py --group guards
# 23 checks, 0 failed
cd runtime/vendor/jev-ultrafast && uv run --frozen pytest -q
# 95 passed
uv run --frozen ruff check jev_ultrafast tests scripts
# All checks passed!
cd ../../../../.. && python3 -m unittest discover -s tests -v
# Ran 10 tests, OK (installer, run alone)
```

Relative to the `b121a46` table above (96 / 522 / 49 / 23 / 90 / 10), this
isolated patch measured 96 wrapper, 598 unit, 49 checks, 23 guards, 95 vendor,
10 installer. The unit group grew by the live-observation and null-target
`run_operation` checks; the vendor group grew by the kind-based target-gate
and `choose()` invariant cases. Combined live-tree totals are left to parent
integration with A's tests.

## Combined landing-repair validation

Date: 2026-09-22. Scope: the three approved landing repairs, combined in this tree on
`feat/jev-decision-safety`.

1. Binding-identity cache fix, in vendor `agent.py`.
2. Wrapper failure-path verification-evidence fix, in `src/jev/__init__.py`.
3. Dispatch-correlation fix, in the runtime `agent.py` and `runner.py`.

All three repairs are now committed (`72e4590`, `a4ceb59`, `fe2a70d`); the third was
still uncommitted in the working tree when these commands ran. Each repair was probed
on its own before this
run; those reports are `/tmp/jev-landing-fix-2.md`, `-3.md` and `-4.md`. Every command
and count below is a fresh run against the combined tree. None of it copies those
isolated numbers.

Commands, all exit 0, run from `feat/jev-decision-safety`:

```sh
cd skills/jev
uv sync --project runtime --frozen --reinstall-package jev-ultrafast
uv run --frozen python -m unittest discover -s tests -v
# Ran 112 tests in 40.976s, OK (0 skipped)
uv run --project runtime --frozen python runtime/tests/run_tests.py --group unit
# 640 checks, 0 failed
uv run --project runtime --frozen python runtime/tests/run_tests.py --group checks
# 51 checks, 0 failed
uv run --project runtime --frozen python runtime/tests/run_tests.py --group guards
# 23 checks, 0 failed
cd runtime/vendor/jev-ultrafast && uv run --frozen pytest -q
# 106 passed
uv run --frozen ruff check .
# All checks passed!
cd ../../../../.. && python3 -m unittest discover -s tests -v
# Ran 10 tests in 1.149s, OK (installer, run alone after every suite above finished)
```

The pre-repair origin tip `0175169` measured 104 wrapper, 605 unit, 51 `checks`, 23
`guards`, 95 vendor and 10 installer tests (see "Re-run deterministic checks" above).
The combined tree adds 8 wrapper tests, 35 unit checks and 11 vendor tests. `checks`,
`guards` and installer stay the same, because none of the three repairs touch
`checks.py`, snapshot truncation or `install.py`.

Each new-test claim was checked by name, not just by count:

| Repair | New tests | Where confirmed | Result |
|---|---|---|---|
| Cache fix | 5 vendor tests | Re-selected with `pytest -k`, e.g. `test_stale_retry_does_not_reuse_a_binding_on_another_field` | All 5 pass |
| Wrapper fix | 8 wrapper tests | `git diff 0175169..HEAD` on `tests/test_jev.py`: 8 new `def test_`, 0 removed | Ran inside the 112-test pass |
| Dispatch-correlation fix | 6 vendor tests | `git show fe2a70d -- skills/jev/runtime/vendor/jev-ultrafast/tests/test_agent.py`: 6 new `def test_`, 0 removed; re-selected with `pytest -k` | All 6 pass |
| Dispatch-correlation fix | 35 unit checks | `git show fe2a70d -- skills/jev/runtime/tests/run_tests.py`: 37 new `check()` calls, 2 rename existing checks onto the new contract, so 35 are net new | All 32 `dispatch_correlation.*` and 5 `safety.dispatch_*` checks pass |

The installed runtime copy of `jev-ultrafast` matches the source. After the reinstall,
`runtime/.venv/lib/python3.12/site-packages/jev_ultrafast/agent.py` is byte-identical to
`runtime/vendor/jev-ultrafast/jev_ultrafast/agent.py`. It carries both `binding_identity`
and `decision_seq`/`latest_dispatch`.

No source file changed to reach these results. Only `README.md` and this file changed.
No live model call ran, and no headed browser ran. `--group browser` and `--group
login` did not run, so this entry says nothing about those two groups or about live
provider behaviour. The `checks` and `guards` groups start and stop their own headless
Chrome. Their own `snapshot.owned_chrome_is_gone` and `snapshot.no_daemon_was_left_behind`
checks confirmed a clean exit. A process check after the run found no leftover Chrome
or daemon process. No nested delegation ran this validation.
