# Sources and changes

## Upstream code

- Repository: https://github.com/browser-use/jev-ultrafast
- Pinned commit: `1231850a0bf1a0c0341fe408ef1668dbbfdfac46`.
- License: MIT. The bundled upstream license is retained with its source.
- The vendored tree is a maintained fork of that commit. Local changes sit in
  `jev_ultrafast/agent.py`, `model.py`, `questions.py`, `browser.py`,
  `scripts/check_guards.py` and `tests/test_agent.py`. They add exact-value binding, let
  a null text-helper answer skip a field instead of ending the run, clear a field with a
  Delete key event, and add a fixture check that an empty value clears the field and
  fires an input event.
- The prompt surface changed only for value binding. When the caller supplies values,
  the decision request gains a `supplied_values` state entry holding an 80-character
  preview per key, the TYPE_TEXT label says a supplied value may provide the text, and
  a new `BIND_VALUE` question asks which supplied value belongs in the field.
- Unchanged from upstream: the DOM snapshot rules, the NEXT_ACTION and TARGET rules,
  the request body when no values are supplied, the retry policy and the TypeSafe choice
  validation in `validate_choice`. `field_text()` now accepts `{"text": null}` as a
  no-value answer, so text-helper response validation did change.
  `runtime/vendor/PROVENANCE.md` holds the file-by-file record.
- Native runtime changes outside the vendored tree are provider routing, dedicated
  browser ownership, named-profile lifecycle, execution limits, accounting, direct PNG
  capture and protocol adaptation.
- Browser integration dependency: `browser-harness==0.1.13`, resolved in `runtime/uv.lock`.
- The published copy of the vendored tree omits upstream `docs/` and upstream
  `AGENTS.md`. See `runtime/vendor/PROVENANCE.md` and the repository `THIRD_PARTY.md`.
- OpenRouter System One protocol:
  https://openrouter.ai/docs/guides/community/typesafe-sdk

## Declared DOM checks: adapted from a sibling branch

`src/jev/checks.py` is adapted from work on this repository's own
`codex/jev-first-browser-qa` branch, commit `91c6846fc46576b7665aac9aeb65eb242139380e`
(`git show 91c6846:skills/jev/runtime/jev_runtime/evidence.py` and
`.../contracts.py`). It is first-party code from the same project, not third-party
material, so it needs no separate license entry. Taken from there: the shape of one
batched, read-only DOM read (`evidence.READ`), the pass/fail/unknown summary rule
(`evidence.summarize`), the refusal to read a password input or an ambiguous selector,
and the `{id, kind, selector, equals|contains}` check schema with its bounded,
unknown-keys-rejected validation (`contracts.checks`).

Changed here, deliberately:

- The expectation never reaches the page. Only the kind and the selector are sent;
  every comparison happens in the runner's process. The source sent the whole check
  object, expectation included, into the document.
- One contract file validates both boundaries: the wrapper before it launches anything,
  and the runner on the request it receives. The source validated only inside the
  runtime, after the caller's process had already committed to a subprocess.
- `attribute` checks are not supported. An absent attribute reads as `null`, which the
  source reported as `failed`; that conflates "missing" with "wrong". Hidden and file
  inputs are refused as well as password inputs, so there is no generic hidden-field
  extraction.
- A wrong evidence type, an unreadable page and an unusable row are `unknown` with a
  fixed reason vocabulary, never `failed`.
- The payload records `checked_at_url`, `checked_at_title`, `captured_at_ms`,
  `declared`, `counts` and `consistency`, so a reader can see which document was read
  and when.
- Observed strings are redacted for known secret environment values and truncated at
  2000 characters after comparison, so evidence cannot smuggle a secret into
  `result.json`.
- `id` defaults to `check[<index>]`, and the normalized snapshot is itself valid input,
  so the wrapper can send exactly what it validated.
- Not adopted: the `Engine` loop, the provider adapters, `allow`/`origins`, milestones,
  extractions, collectors, the confidence thresholds, and the new status strings
  (`needs_review`, `policy_blocked`, `verification_failed`). Declared checks never
  change a run's status.

## Local evidence

The initial comparison ran against the unmodified pinned commit, before the fork. It
completed 18 attempts on three local HTML fixture tasks, nine per engine. Jev passed
9/9 independently verified; Astra passed 8/9. Across the eight attempt pairs where
both engines passed, summed whole-process wall time was 75.5 s for Jev and 511.0 s for
Astra, a 6.76x ratio. Recorded model cost favored Jev by a large margin, but the two
engines do not account for cost the same way: Jev uses OpenRouter per-request costs,
Astra uses the SDK catalog estimate, so cost ratios are approximate and not an invoice
comparison. This is a small local-fixture sample. It supports the
executor choice for ordinary action-heavy HTML tasks, not general production
reliability and not native app coverage. The full benchmark report and its raw
artifacts stay in the private implementation project.

The native package needs its own validation after adaptation. Do not treat the
benchmark's JPEG-to-PNG screenshot conversion or fresh-only profiles as proof of the
native PNG and persistent-login requirements. The benchmark predates exact-value
binding and says nothing about it. See VALIDATION.md for actual checks.

This SKILL.md is an original Prime Agent workflow. It does not copy upstream skill text.
