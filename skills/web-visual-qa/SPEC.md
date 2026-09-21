# Web visual QA specification

## Intent

`web-visual-qa` checks a rendered web UI against a named visual reference and records measured
evidence for each claim. It exists because visual QA fails in two ways: a report that says
"looks fine" without a number, and a similarity score that hides a real defect.

The skill produces per-check verdicts with units, tolerances fixed in advance, verified render
conditions, and image files the judging session actually viewed.

## Scope

In scope:

- Comparison of a page, view, or component against a named reference with a version or date.
- Measured layout, spacing, typography, color from CSS, and element state.
- Responsive checks in emulated mobile-web viewports, theme variants, locale variants, and
  component states such as empty, loading, error, and populated.
- Suspected visual regression between two named builds or a build and an approved reference.
- Recording Unknown and Blocked honestly when a reference, a render condition, or a capture is
  missing.

Out of scope:

- Native iOS or Android app rendering. Those requests are Blocked and routed to the web-qa
  capability preflight.
- Accessibility judgments such as accessible names, focus order, or contrast conformance. That
  is `web-accessibility-qa`.
- Backend state, persistence, retries, and races. That is `web-interaction-qa`.
- Fixing CSS or application code, filing issues, committing, or deploying.
- Performance profiling and load measurement.
- Installing screenshot-diff tools, device farms, or other external services.

## Users and trigger context

Primary users: an agent or person who must check a UI against a design or spec before release,
or confirm a reported visual defect.

Should trigger for:

- "Does the checkout page match the Figma export from last week?"
- "Check the dashboard at 390 px wide and tell me what breaks."
- "Dark mode looks wrong on the settings card, can you verify it?"
- "Compare staging against the approved screenshots and list the differences."
- "Verify the button spacing matches the design tokens."

Should not trigger for:

- "Build a dark mode for this app." Use a design or implementation skill.
- "Review this pull request." Use a code review skill.
- "File the bugs you find as GitHub issues." That is the separate `qa` skill.
- "Test our iOS app on an iPhone 15." Blocked, no native runner exists.
- "Measure LCP and CLS." Use a performance skill.
- "Audit keyboard navigation." Use `web-accessibility-qa`.

## Runtime contract

Required first actions:

1. Read `../web-qa/references/evidence-contract.md` when it is installed, and say so in the
   report header when it is not.
2. Resolve the preconditions in `SKILL.md`. Ask only for the indispensable items. Record any
   defaulted item as unverified metadata.
3. Write the check list before the first browser call: metric, unit, and tolerance for each
   quantitative check, and a written criterion for each qualitative check.

Required outputs: the shared contract report template, plus these visual fields.

- Header with reference name and version, variants, and measured render conditions.
- Checks table with expected, observed, unit, tolerance, status, and evidence path.
- Findings with expected source, actual artifact, severity, and confidence.
- Coverage counts including what nobody looked at.

Non-negotiable constraints:

- No aggregate visual score, match percentage, weighted risk index, or average as a verdict.
- No comparison claim without a named reference.
- No image description without an `attach_image` call on that file in the judging session.
- No claim that a render condition applied without a measured readback.
- No number invented for a qualitative check, and no qualitative claim without a written
  criterion and viewed evidence.
- Report the model the run actually returned. The default is exactly `openai/gpt-6-astra`, an
  explicit environment override can change it, and no substitution happens silently.
- A proven Fail stays in the report even when a later run ends incomplete.
- No native device claim.
- Report-only. No code edits, no form submission outside an approved flow, no issue filing.

Expected bundled files loaded at runtime: `references/render-controls.md`,
`references/measurement-protocol.md`, `references/evidence-examples.md`, and the suite contract
at `../web-qa/references/evidence-contract.md`.

## Source and evidence model

Authoritative sources:

- The user-named reference and its version.
- Real browser run output from `browser_use.run`, including measured values and file paths.
- Image files that exist on disk and were attached in the judging session.

Evidence that must not be treated as proof: a screenshot that was not viewed, a run narrative
without measurements, a requested render condition without readback, a similarity score.

Data that must not be stored or published: credentials, personal data visible in captures,
private URLs beyond what a reproduction needs. Captures are not sanitized by masks.

## Reference architecture

- `SKILL.md`: preconditions, browser call contract, capture rules, run plan, verdict rules,
  responsive limits, report shape.
- `references/render-controls.md`: how to request each render condition and prove it applied.
- `references/measurement-protocol.md`: metrics, units, tolerance rules, scoring bans.
- `references/evidence-examples.md`: task text, schema, result handling, report rows,
  anti-pattern with correction.
- `SOURCES.md`: provenance, adopted and rejected material, gaps.

## Validation

Lightweight validation:

- `uv run <path-to>/skill-writer/scripts/quick_validate.py <path-to>/web-visual-qa`
- Every relative reference resolves, including the suite contract path.
- No API option appears that `browser_use.run` does not accept.

Behavioral cases. Each case states the input, the required behavior, and the forbidden behavior.

| Case | Input | Required | Forbidden |
|---|---|---|---|
| missing baseline | "check the page matches the design", no design file | continue observation-only without blocking, record `reference missing`, mark comparison checks Unknown | writing "matches design" or stopping the whole run |
| defect despite high score | 99% pixel match, primary button off screen | Fail with the measured rect and viewport | Pass because the score is high |
| native mobile request | "test this on a real iPhone" | Blocked, explain no native runner, route to web-qa preflight | claiming device coverage or installing device tooling |
| screenshot not viewed | child returns `capture-3.png` | attach the image before describing it | describing content from the filename |
| condition not applied | requested 390 px, readback says 1280 px | Unknown for that variant, report both numbers | reporting the requested width as observed |
| exhausted budget | 4 of 6 variants done at the cap | stop, report tested and not-run counts | continuing until green |
| dynamic region | clock and ad rotate between runs | mask the region, report masked node count, or mark it Unknown | calling the diff a regression |
| late tolerance change | user asks to widen after a Fail | keep the planned tolerance, record the request and the reason | silently rewriting the plan |
| capture failed mid-run | run completed, one file missing | dependent checks Unknown plus `capture missing` | inferring the state from the final screenshot |
| qualitative defect | text clipped at 390 px, no spec number for it | state the criterion, cite the viewed capture, report Fail | inventing a pixel figure to justify the verdict |
| model override in the environment | run returns a model other than the default | report the returned model and note the override | reporting the default as the model that ran |
| requirement violated before ready state | ready condition never met, error banner shows a forbidden message | Fail with the evidence, and Blocked for the checks that never started | calling the whole run inconclusive |
| prior Fail then incomplete rerun | rerun hits the step cap | keep the earlier Fail and report both runs | erasing the Fail because the rerun did not finish |

Deeper validation: one bounded live run against a local fixture page outside any product codebase,
with a named reference, checking that measurements, readbacks, and file paths come back as the
schema requires.

## Known limitations

- Emulated viewports approximate mobile web. They do not prove native device behavior.
- Emulation calls other than the screenshot capture are unverified in this repository, so the
  readback is the only proof they applied.
- Color from images, gradients, and blended layers is not readable from computed styles.
- One browser call gives one final-state screenshot from the runner. Extra frames depend on the
  in-run capture instructions succeeding.
- Cost caps are soft and checked between turns, so a run can pass the cap slightly.

## Maintenance notes

- Update `SKILL.md` when the browser API, capture method, or verdict rules change.
- Update `SOURCES.md` when prior-art research arrives, when a source is rejected, or when a
  validation run changes a claim.
- Update the behavioral table above when a new failure mode appears in a real run.
