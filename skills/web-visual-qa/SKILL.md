---
name: web-visual-qa
description: Check a web UI against a named visual reference and record measured layout, color, and state evidence from real browser runs. Use when asked to compare a page with a design or written spec, verify responsive mobile-web layout, theme or component states, or investigate a suspected visual regression. Report-only, and not for native iOS or Android apps.
compatibility: Needs the installed browser-use skill (Python browser_use), Chrome or Chromium, and OPENAI_API_KEY. Part of the web QA suite and reads ../web-qa/references/evidence-contract.md.
---

# Web visual QA

Compare a rendered web UI with a named reference, measure what you claim, and report.
Do not edit application code, data, or files under test. Do not file issues.

## Read before running

| Open when you need to... | Read |
|---|---|
| apply the suite status, evidence, budget, and reporting rules | `../web-qa/references/evidence-contract.md` |
| set viewport, device pixel ratio, fonts, motion, crop, theme, or masks and prove they applied | `references/render-controls.md` |
| pick metrics, units, and tolerances before any result exists | `references/measurement-protocol.md` |
| write the run task, output schema, verification code, and report rows | `references/evidence-examples.md` |

If the shared contract file is not installed, write `shared evidence contract missing` in the
report header and use these check statuses: Pass, Fail, Unknown, Blocked, Not run.

## Preconditions

Ask only for the items marked indispensable. For the rest, use the scope the user supplied or
the stated default, record the choice as unverified metadata, and continue.

| Item | Class | Behavior when missing |
|---|---|---|
| approved URL and environment, report-only authority | indispensable | stop and ask |
| absolute evidence directory | indispensable | create it yourself, or stop when the path is not writable |
| named reference with version or date | recordable | run observation-only, mark comparison checks Unknown, record `reference missing` |
| profile name | recordable | use a dedicated name such as `visual-qa` and record it |
| budget: wall clock, browser calls and steps, soft USD cap | recordable | apply a stated bounded default, record it, report the spend |
| variant list: viewports, theme, locale, component states | recordable | use the user scope or a stated default, record what you chose |

Use local or staging targets and test accounts. Never invent a reference name, build id, or
version. Write `unverified` beside metadata you could not confirm.

## Browser call contract

```python
result = await browser_use.run(
    task_text,              # one whole scenario, including every capture step
    schema=output_schema,   # require measurements and absolute image paths back
    profile="visual-qa",
    max_steps=25,
    timeout_ms=180_000,
    max_cost_usd=1.0,
)
```

- These arguments are the whole Python API for a run. There is no resize, follow-up, pause, or
  download option. Express viewport changes, actions, waits, and captures inside `task_text`.
- The default browser model is exactly `openai/gpt-6-astra`. An explicit environment override can
  select a different model. Report `result["model"]`, the model that actually ran, in the header,
  and never substitute a model silently or describe a run as a model it did not use.
- Any non-completed run raises `browser_use.BrowserUseError`. Keep `error.status`, the message,
  and `error.result` as evidence. Do not retry a run that already acted on the page until you
  know what it did.
- Each call starts and closes its own Chrome process. A profile keeps cookies, localStorage, and
  IndexedDB, not open tabs, scroll position, or unsaved page state. Keep a before and after pair
  inside one run.
- Run variants in parallel only under different profile names. One profile has one owner, and a
  second caller fails instead of queueing.

## Evidence capture

The shared contract holds the general evidence rules. These points are specific to visual work:

- `result["screenshot_path"]` is the final state of that run, so capture each variant and each
  intermediate state explicitly with `page.cdp('Page.captureScreenshot', {format:'png'})`, write
  each file into your evidence directory, and return the absolute paths through the schema.
- Name each file for its variant, such as `pricing-390-light.png`, so a report row cites one
  image without ambiguity.
- Call `attach_image(path)` in the session that judges the image, after checking the file exists.
  Never describe an image you did not view.
- A mask hides a region from comparison. It does not remove private content from the PNG.
- A missing capture makes the dependent check Unknown, with `capture missing` in the report.

## Run plan

1. Write the check list first. Each row names the reference item, the expected value with its
   unit, the tolerance, and the variant.
2. Fix tolerances before any measurement exists. If you later change one, report the original
   value, the new value, and the reason.
3. Choose variants deliberately: viewport sizes, theme, locale, and component states. Keep the
   list inside the budget.
4. Run one scenario per browser call. Require measured render conditions and measured values
   back, not adjectives.
5. Verify the run applied each requested condition. A mismatch makes that variant Unknown.
6. Attach and read every image you cite, then compare each measurement with its tolerance.
7. Write the report, including scope nobody covered and budget left.

## Verdict rules

- One status per check. No aggregate similarity score, no pixel-diff percentage, no weighted
  risk index, and no average as the release gate.
- A quantitative claim needs a value, a unit, and a tolerance fixed in advance.
- A qualitative check is valid when you state its criterion before the run and cite viewed
  evidence, such as `heading text not clipped at 390 px`. Never invent a number for one.
- A check that depends on a missing reference is Unknown, never Pass.
- A statistic over an empty set is not evidence. Zero measurements is Not run, never Pass.
- A stale build or a cached asset is a deployment defect, not visual evidence. Confirm the build
  identity before judging the pixels.
- Compare the observed value with the reference value. A before-and-after delta is valid only
  when the reference states a delta, otherwise a no-op passes and a real fix fails.
- A property the reference does not specify is out of scope. Record it as an observation, not a
  Fail.
- A real defect outranks any global match figure. A 99% pixel match with the primary button
  outside the viewport is a Fail.
- Status assignment, ready-condition failures, repeat attempts, severity and confidence, coverage
  counts, and the overall verdict come from the shared contract. Do not restate them differently
  here.

## Responsive scope

- Responsive work here is mobile web in an emulated viewport in desktop Chrome. Report the
  measured viewport size, device pixel ratio, and user agent string.
- Emulation does not prove native device behavior. Real touch input, device fonts, platform
  browser chrome, safe-area insets, and on-device rendering stay out of scope.
- A request to test a native iOS or Android app is Blocked. Say this suite has no native runner,
  send the capability question to the web-qa preflight, and do not invent device tooling.

## Anti-patterns

| Seen | Required behavior |
|---|---|
| "looks correct" with no stated criterion | state the criterion first, then cite a measured value with its unit or the viewed evidence |
| similarity score used as the gate | per-check verdicts only |
| screenshot path quoted without viewing | attach the image first, or do not describe it |
| tolerance picked after the measurement | keep the planned tolerance and report any change |
| no design file, report says "matches design" | Unknown plus observations against stated constraints |
| masked region called sanitized | a mask excludes a region from comparison, not from the PNG |

## Report shape

Use the report template in the shared contract and add these visual fields:

- Header: reference name and version, variants, and the measured render conditions per variant.
- Checks table: add variant, expected with unit, observed with unit, and tolerance columns.
- Findings: add the measurement that failed and the capture that shows it.
- Coverage: add the variants nobody rendered, such as an untested theme or viewport.

Maintenance contract: `SPEC.md`. Provenance and source decisions: `SOURCES.md`.
