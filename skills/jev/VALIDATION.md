# Native Jev validation

Validation date: 2026-09-21. Host: macOS with installed Chrome. Wrapper runtime tested
on Python 3.11 and 3.13; the separate browser runtime uses Python 3.12.13.

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

## Re-run deterministic checks

From the installed Jev skill directory:

```sh
uv sync --project runtime --frozen
uv run python -m unittest discover -s tests -v
uv run --project runtime --frozen python runtime/tests/run_tests.py --group unit
```

These commands require no model key and make no paid model calls. The two real-runtime
wrapper tests skip if runtime setup has not been completed.

The following additional groups open real Chrome windows and use a loopback fixture.
They make no model calls. Run them only on a host where opening Chrome is appropriate:

```sh
uv run --project runtime --frozen python runtime/tests/run_tests.py --group browser
uv run --project runtime --frozen python runtime/tests/run_tests.py --group login
```

`--group all` runs all 146 runtime checks. Raw local screenshots, browser profiles,
provider logs and Prime Agent transcripts are not included in the public repository.

## Remaining limits

- Exact field fidelity is not guaranteed by a model completion claim.
- No production accounts, native mobile devices, uploads, complex iframe or shadow-DOM
  flows, or broad real-site reliability test was performed.
- Model costs are soft limits, checked between calls. Unknown usage stops execution.
- Browser screenshots and page text may contain private data and are not sanitized.
- Linux support follows the code paths, but these live checks ran on macOS only.
