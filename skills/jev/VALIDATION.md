# Native Jev validation

Validation date: 2026-09-21. Host: macOS with installed Chrome. Wrapper runtime tested
on Python 3.11 and 3.13; the separate browser runtime uses Python 3.12.13.

Exact-value binding landed later, on 2026-09-22. Every count in the next table is from
the 2026-09-21 run against the pre-fork tree. The suites have grown since. See
"Exact-value binding (not live-validated)" for what that change has and has not proven,
and "Declared DOM checks" for the later `checks` argument, which does have real
headless-browser evidence.

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

Date: 2026-09-22. Scope: the `checks` argument on `jev.run`, the shared contract file
`src/jev/checks.py`, `runner.verify_declared_checks`, and the new `result["verification"]`
object. This did not change the agent loop, the vendored fork, the provider path, the
lifecycle or any existing argument.

Unlike exact-value binding, this change has live browser evidence, because a declared
check is deterministic: it needs a page, not a model. The `checks` group starts its own
headless Chrome with its own profile and its own browser-harness daemon, serves a local
fixture page, and runs the same `verify_declared_checks` the runner calls. It makes no
model request and needs no API key.

| Check | Result |
|---|---|
| Wrapper suite, `tests/` (72 fake-runner cases plus 3 real-runtime cases) | 75 tests passed |
| Runtime unit group | 273 checks passed |
| Runtime `checks` group, real headless Chrome and one real runner process | 49 checks passed |
| Vendor fork tests, `tests/test_agent.py` (unchanged by this work) | 52 tests passed |
| Installer tests, repository `tests/` | 10 tests passed |

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

It reports 25 findings and exits 1. The same command over the same files taken from the
commit this branch starts at reports the same 25 findings, in the same files under the
same rules: pre-existing long lines and the deliberate mid-file imports in
`runtime/tests/run_tests.py`, plus one unused import in the repository's own
`tests/test_install.py`. `src/jev/checks.py` reports nothing. This change adds no new
finding; it also does not clean up the old ones.

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

- Both boundaries reject the same 30 invalid shapes, and the runtime launch test runs
  the real runtime interpreter to confirm it loaded the wrapper's own `checks.py` and
  produced byte-identical normalized output and identical rejection messages.
- A failed or unknown check leaves the run status `completed`, leaves
  `output["verification"]` at `"not_performed"`, and only adds a warning.
- A completed result whose verification is missing, short, mis-scoped, mis-bounded,
  invalid, `not_run` with declared checks, or present with no declared check is a
  protocol error in the wrapper.
- Declared-check evidence is redacted for known secret environment values before it
  reaches the caller, and `result.json` carries the same object.

Not established by any of this:

- No live model run has used `checks` yet. The binding of a model-driven form fill to a
  declared check has not been exercised end to end.
- A passing check is DOM evidence at one instant. It is not proof of backend
  persistence, and the two earlier live form failures below are not affected by it.
- The group ran on macOS only, against a loopback fixture, in headless Chrome.

## Re-run deterministic checks

From the installed Jev skill directory:

```sh
uv sync --project runtime --frozen
uv run python -m unittest discover -s tests -v
uv run --project runtime --frozen python runtime/tests/run_tests.py --group unit
```

These commands require no model key and make no paid model calls. The three
real-runtime wrapper tests skip if runtime setup has not been completed.

`uv sync --project runtime --frozen` installs the vendored `jev-ultrafast` package
non-editably from `runtime/vendor/jev-ultrafast`. Nothing in the declared-check work
touches that package, so no reinstall is needed for it. If you do change a vendored
file, force the copy in the runtime environment to be rebuilt:

```sh
uv sync --project runtime --frozen --reinstall-package jev-ultrafast
```

The wrapper package is installed editably from `src/`, so `src/jev/checks.py` is picked
up without a reinstall. The runner loads that same file by path, so an installed copy
must always contain both `src/` and `runtime/`; `install.py` copies them together and a
test in the repository's `tests/test_install.py` checks that.

The declared-check group starts its own headless Chrome and its own browser-harness
daemon on a temporary profile. It opens no window and makes no model call:

```sh
uv run --project runtime --frozen python runtime/tests/run_tests.py --group checks
```

The following additional groups open real Chrome windows and use a loopback fixture.
They make no model calls. Run them only on a host where opening Chrome is appropriate:

```sh
uv run --project runtime --frozen python runtime/tests/run_tests.py --group browser
uv run --project runtime --frozen python runtime/tests/run_tests.py --group login
```

`--group all` ran all 146 runtime checks on 2026-09-21, before the unit group grew. The
unit group is now 273 checks and the new `checks` group is 49. The browser and login
groups were not re-run on 2026-09-22, so no new all-groups total is claimed. Raw local
screenshots, browser profiles, provider logs and Prime Agent transcripts are not
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
