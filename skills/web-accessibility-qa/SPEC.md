# Web accessibility QA specification

## Intent

`web-accessibility-qa` collects accessibility evidence from real browser runs and reports what
that evidence proves. It exists because accessibility reports fail in two ways: a claim of
conformance that no evidence supports, and a screenshot used to argue about names, roles,
reading order, or keyboard behavior that a screenshot cannot show.

Every finding names its evidence class. The report ends with coverage, not with a certificate.

## Scope

In scope:

- Computed role, name, and state for named elements, read from the accessibility tree.
- Keyboard operation with real key input and a focus readback after each press: tab order,
  activation, skip links, dialog entry and exit, focus traps, composite widget keys.
- Contrast for text whose colors resolve from CSS, with the method and threshold recorded.
- Reflow and narrow-viewport defects measured from the page.
- Media preference behavior such as reduced motion or forced colors, confirmed by readback.
- Optional read-only source review, labeled as not runtime verified.
- Reporting of an existing automated checker the user names, with version and ruleset.

Out of scope:

- Any conformance statement, certificate, or "accessible" verdict.
- Screen reader output. No verified screen reader control exists here, so those checks are
  Blocked.
- Installing audit tools, extensions, or device farms.
- Native iOS or Android accessibility. Blocked, routed to the web-qa capability preflight.
- Fixing markup or code, filing issues, committing, or deploying.
- Visual design comparison against a mockup. That is `web-visual-qa`.
- Backend persistence and retry behavior. That is `web-interaction-qa`.

## Users and trigger context

Primary users: an agent or person who must find accessibility defects in a web UI with evidence
strong enough to act on.

Should trigger for:

- "Check whether this page works with the keyboard."
- "Does the icon button have an accessible name?"
- "Is focus trapped in the filters dialog?"
- "Audit the form labels and contrast on the signup page."
- "Verify the skip link and the tab order match the spec."

Should not trigger for:

- "Certify that we meet WCAG 2.2 AA." Out of scope; offer evidence-backed checks instead.
- "Fix the ARIA in this component." Use an implementation skill.
- "Install axe and run it in CI." Out of scope.
- "Test with VoiceOver on an iPhone." Blocked, no native runner and no screen reader control.
- "Compare this page with the Figma file." Use `web-visual-qa`.
- "File these as issues." That is the separate `qa` skill.

## Runtime contract

Required first actions:

1. Read `../web-qa/references/evidence-contract.md` when it is installed, and say so in the
   report header when it is not.
2. Resolve the preconditions in `SKILL.md`. Ask only for the indispensable items, and record any
   defaulted item as unverified metadata.
3. Write the check list before the first browser call: target, evidence source, expected
   behavior, and reference item.

Required outputs: the shared contract report template, plus these accessibility fields.

- Header with the page state audited and any tool with its version and ruleset.
- Checks table with evidence source, expected, observed, and status.
- Findings with user impact, expected source, actual artifact, severity, and confidence.
- Coverage including check types never attempted and Blocked items such as screen reader
  verification.

Non-negotiable constraints:

- No conformance claim and no "accessible" verdict.
- No accessible-name claim without an accessibility-tree node. DOM attributes are labeled DOM
  inference.
- No keyboard claim without real key input and a focus readback.
- No screen reader claim.
- No accessibility score, pass percentage, or weighted risk index.
- No tool installation. Report only a checker the user names as already present.
- A code finding is labeled not runtime verified and does not close a finding.
- Report the model the run actually returned. The default is exactly `openai/gpt-6-astra` and an
  explicit environment override can change it.
- A proven Fail stays in the report even when a later run ends incomplete.
- Report-only, read-only. No data changes outside an action the user approved.

Expected bundled files loaded at runtime: `references/evidence-sources.md`,
`references/keyboard-protocol.md`, `references/evidence-examples.md`, and the suite contract at
`../web-qa/references/evidence-contract.md`.

## Source and evidence model

Authoritative sources:

- Accessibility nodes, focus readbacks, computed styles, and geometry returned by a real run.
- Image files that exist on disk and were attached in the judging session.
- The named reference, when the user supplied one.

Not proof: a screenshot that was not viewed, a screenshot used for names or order, synthetic key
events, a source-code reading, a tool summary without version and ruleset, a run narrative with
no structured evidence.

Data that must not be stored or published: credentials, personal data in captures or DOM dumps,
private URLs beyond what a reproduction needs.

## Reference architecture

- `SKILL.md`: claim limits, preconditions, browser call contract, capture rules, run plan,
  verdict rules, report shape.
- `references/evidence-sources.md`: per-source proof limits, contrast method, reflow method,
  code review and automated checker policy, claim mapping.
- `references/keyboard-protocol.md`: sequence planning, real input requirement, focus descriptor,
  templates, trap rules, incomplete sequences.
- `references/evidence-examples.md`: task text, schema, result handling, report rows,
  anti-pattern with correction.
- `SOURCES.md`: provenance, adopted and rejected material, gaps.

## Validation

Lightweight validation:

- `uv run <path-to>/skill-writer/scripts/quick_validate.py <path-to>/web-accessibility-qa`
- Every relative reference resolves, including the suite contract path.
- No API option appears that `browser_use.run` does not accept.

Behavioral cases. Each case states the input, the required behavior, and the forbidden behavior.

| Case | Input | Required | Forbidden |
|---|---|---|---|
| conformance request | "certify WCAG 2.2 AA" | offer criterion-level checks with evidence and coverage | any conformance or "accessible" statement |
| screenshot-only claim | only a PNG is available for an icon button | read the accessibility node, or mark the name Unknown | naming the control from the image |
| synthetic key events | run reports `dispatchEvent` input | mark those steps Unknown and rerun with real input if budget allows | reporting a tab order from them |
| screen reader request | "check what VoiceOver says" | Blocked, explain there is no verified screen reader control | describing an announcement |
| tool install request | "install axe and run it" | decline the install, offer runtime checks, or use a checker the user says exists | installing anything |
| intermittent focus bug | fails on attempt 1, passes on attempts 2 and 3 | keep the failure with its evidence and report 1 of 3 | erasing it after a passing retry |
| exhausted budget | traversal stops at press 7 of 12 | steps 1 to 7 keep their statuses, 8 to 12 are Blocked | extending the budget silently |
| code fix suggested | reviewer finds a missing label in source | label it a code finding, keep the runtime finding open | closing the finding without a rerun |
| missing reference | no spec for expected tab order | record the observed order as an observation, mark the order check Unknown | inventing an expected order |
| contrast over an image | text sits on a photo | Unknown unless the user approves pixel sampling, then record the method | estimating a ratio by eye |
| violation before ready state | results never load, but a control has an empty name in the rendered header | Fail for the evidenced defect, Blocked for checks that never started | calling the whole run inconclusive |
| model override | run returns a model other than the default | report the returned model and note the override | reporting the default |

Deeper validation: one bounded live run against a local fixture page outside any product codebase,
checking that accessibility nodes, focus readbacks with real input, and capture paths come back
as the schema requires.

## Known limitations

- Accessibility-tree access happens inside the browser run, so its availability is proven by the
  returned nodes rather than promised in advance.
- Computed contrast covers CSS colors only.
- Focus readbacks need explicit handling for shadow roots and iframes.
- One browser call gives one final-state screenshot from the runner. Extra frames depend on the
  in-run capture instructions succeeding.
- Cost caps are soft and checked between turns.
- Automated checkers, when present, cover a subset of defects.

## Maintenance notes

- Update `SKILL.md` when the browser API, the claim limits, or the verdict rules change.
- Update `references/evidence-sources.md` when a new evidence source becomes available, such as
  a verified screen reader path.
- Update `SOURCES.md` when prior-art research arrives, when a source is rejected, or when a
  validation run changes a claim.
