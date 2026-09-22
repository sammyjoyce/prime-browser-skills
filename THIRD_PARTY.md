# Third-party material

This repository is MIT licensed, see `LICENSE`. The items below have their own terms.

## Vendored source

| Item | Value |
|---|---|
| Project | `browser-use/jev-ultrafast` |
| Upstream | https://github.com/browser-use/jev-ultrafast |
| Pinned commit | `1231850a0bf1a0c0341fe408ef1668dbbfdfac46` |
| Archive sha256 | `3bed2171ef064135c5192bad354b4a187f71ec397639d5ab676d02be37822211` |
| License | MIT, retained at `skills/jev/runtime/vendor/jev-ultrafast/LICENSE` |
| Path here | `skills/jev/runtime/vendor/jev-ultrafast/` |
| Local changes | Seven files, listed in `skills/jev/runtime/vendor/PROVENANCE.md` |

The vendored tree is a maintained fork of that pinned archive, not a plain copy. Seven
files carry local changes: `jev_ultrafast/agent.py`, `jev_ultrafast/model.py`,
`jev_ultrafast/snapshot.js`, `jev_ultrafast/questions.py`, `jev_ultrafast/browser.py`,
`scripts/check_guards.py` and `tests/test_agent.py`. They add exact-value binding, let a
null text-helper answer skip a field instead of ending the run, clear a field with a
Delete key event, report whether the snapshot's visible text was truncated and tell the
decision and binding calls, withhold input for a low confidence score, an unpaid budget
or an uncertain dispatch, and add the matching fixture and snapshot checks. Every other
retained file is byte-identical to the archive. The MIT license and upstream copyright
notice are kept with the source. `skills/jev/runtime/vendor/PROVENANCE.md` lists the
seven files and gives both ways to reproduce that list.

This published copy omits two upstream paths:

- `docs/`, which holds images, a video, and upstream measurement JSON.
- `AGENTS.md`, which holds upstream agent instructions. This project does not execute
  them.

Upstream `README.md` links into `docs/`, so those links resolve only upstream.
`skills/jev/runtime/vendor/PROVENANCE.md` records the same facts, names each local
change with its reason, and gives the exact command to diff the tree against the pinned
archive.

The `jev` skill also adapts upstream behaviour at runtime. Each runtime adaptation is
listed in the `DEVIATIONS` constant in `skills/jev/runtime/runner.py` and is returned
with each result under `deviations`. That list carries a `fork:` entry naming the in-tree
behaviour changes as well.

## Dependencies

Dependencies are not vendored. They are pinned by lockfiles and fetched from public
registries at install time. Each dependency keeps its own license.

| Lockfile | Scope |
|---|---|
| `skills/browser-use/package-lock.json` | Node runner, `@browser_use/pi` 0.1.0 |
| `skills/browser-use/uv.lock` | `browser-use` skill package |
| `skills/jev/uv.lock` | `jev` skill package |
| `skills/jev/runtime/uv.lock` | isolated Jev runtime, including `browser-harness==0.1.13` |
| `skills/jev/runtime/vendor/jev-ultrafast/uv.lock` | upstream lockfile, kept with its source |

## QA skills

`skills/web-qa`, `skills/web-dogfood`, `skills/web-visual-qa`,
`skills/web-accessibility-qa`, and `skills/web-interaction-qa` are written for this
project. No upstream text, table, schema, script, or file layout was copied or
near-paraphrased.

Each skill has a `SOURCES.md` that records the prior art that was read, its pinned
commit, its license, and whether an idea was adopted or rejected. Adopted items are
ideas, rewritten independently. One prior-art repository declares no license, so it is
treated as all rights reserved and used for ideas only.

`skills/jev/SKILL.md` is an original Prime Agent workflow. It does not copy upstream
skill text.
