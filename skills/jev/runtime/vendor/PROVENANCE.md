# Vendored upstream provenance

`vendor/jev-ultrafast/` is a maintained fork of the upstream project source. It began as
a byte-identical copy of the pinned archive below. Six files now carry local changes.
Every other retained file is still byte-identical to that archive.

| Item | Value |
|---|---|
| Project | `browser-use/jev-ultrafast` |
| License | MIT (see `vendor/jev-ultrafast/LICENSE`) |
| Pinned commit | `1231850a0bf1a0c0341fe408ef1668dbbfdfac46` |
| Source archive | `https://codeload.github.com/browser-use/jev-ultrafast/tar.gz/1231850a0bf1a0c0341fe408ef1668dbbfdfac46` |
| Archive sha256 | `3bed2171ef064135c5192bad354b4a187f71ec397639d5ab676d02be37822211` |
| Vendored | 2026-09-21 |
| Forked | 2026-09-22 |

## Local changes

| File | Change |
|---|---|
| `jev_ultrafast/agent.py` | Binds a caller-supplied value to a fill field, caches that bind decision beside the existing text cache, and skips a field with no bound value instead of typing a guess. |
| `jev_ultrafast/model.py` | Adds `bind_value()`, shows supplied keys and 80-character value previews to the decision call, and lets the text helper answer `{"text": null}` without raising. |
| `jev_ultrafast/questions.py` | Adds the `BIND_VALUE` rules text used by the new binding question. |
| `jev_ultrafast/browser.py` | Clears a field with a Delete key event when the supplied value is the empty string. |
| `scripts/check_guards.py` | Adds a fixture check: an empty value clears the field and fires an input event. |
| `tests/test_agent.py` | Adds cases for byte-for-byte typing, clearing, skipping, the null helper answer, the three-skip blocked rule and the bind cache. |

Upstream behaviour that did not change: the DOM snapshot rules, the NEXT_ACTION and
TARGET rules, the operation and target question construction when no values are
supplied, the retry policy and the TypeSafe choice validation in `validate_choice`.
Response validation for the text helper did change: `field_text()` now accepts
`{"text": null}` as a no-value answer instead of raising.

Runtime adaptations outside this tree stay in the `DEVIATIONS` constant in
`runtime/runner.py` and are returned with each result under `deviations`. That list now
carries a `fork:` entry naming the two behaviour changes made here.

## Omitted files

This published copy omits two upstream paths: `docs/` (images, video, and upstream
measurement JSON) and `AGENTS.md` (upstream agent instructions, which this project
does not execute). Nothing else is removed. Upstream `README.md` links into `docs/`,
so those links resolve only in the upstream repository.

## Diff against upstream

Run these from `skills/jev/runtime/`. Expect differences in the six files listed above
and, in a fresh clone, in nothing else:

```sh
curl -sSL -o /tmp/jev.tar.gz https://codeload.github.com/browser-use/jev-ultrafast/tar.gz/1231850a0bf1a0c0341fe408ef1668dbbfdfac46
shasum -a 256 /tmp/jev.tar.gz
mkdir -p /tmp/jev-check && tar xzf /tmp/jev.tar.gz -C /tmp/jev-check --strip-components=1
diff -qr -x docs -x AGENTS.md /tmp/jev-check vendor/jev-ultrafast
diff -u /tmp/jev-check/jev_ultrafast/agent.py vendor/jev-ultrafast/jev_ultrafast/agent.py
```

The third command lists which files differ. The fourth reads one change in full; repeat
it for each other changed file. Check the printed sha256 against the table before you
trust the comparison. In a working checkout, `diff -qr` also lists the untracked local
`.venv/` directory (see `.gitignore:2`); that is a local build artefact, not a source
change.
