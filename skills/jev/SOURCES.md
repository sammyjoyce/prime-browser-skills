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
