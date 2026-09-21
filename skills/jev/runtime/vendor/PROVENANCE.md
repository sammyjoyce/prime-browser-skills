# Vendored upstream provenance

`vendor/jev-ultrafast/` is an unmodified copy of the upstream project source.

| Item | Value |
|---|---|
| Project | `browser-use/jev-ultrafast` |
| License | MIT (see `vendor/jev-ultrafast/LICENSE`) |
| Pinned commit | `1231850a0bf1a0c0341fe408ef1668dbbfdfac46` |
| Source archive | `https://codeload.github.com/browser-use/jev-ultrafast/tar.gz/1231850a0bf1a0c0341fe408ef1668dbbfdfac46` |
| Archive sha256 | `3bed2171ef064135c5192bad354b4a187f71ec397639d5ab676d02be37822211` |
| Vendored | 2026-09-21 |

Every retained file is byte-identical to that archive. No upstream file is edited.
`runner.py` adapts behaviour at runtime only, and every adaptation is listed in its
`DEVIATIONS` constant and returned in each result under `deviations`.

This published copy omits two upstream paths: `docs/` (images, video, and upstream
measurement JSON) and `AGENTS.md` (upstream agent instructions, which this project
does not execute). Nothing else is removed. Upstream `README.md` links into `docs/`,
so those links resolve only in the upstream repository.

To re-verify:

```sh
curl -sSL -o /tmp/jev.tar.gz https://codeload.github.com/browser-use/jev-ultrafast/tar.gz/1231850a0bf1a0c0341fe408ef1668dbbfdfac46
mkdir -p /tmp/jev-check && tar xzf /tmp/jev.tar.gz -C /tmp/jev-check --strip-components=1
diff -r -x docs -x AGENTS.md /tmp/jev-check vendor/jev-ultrafast
```
