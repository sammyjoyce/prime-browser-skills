---
name: web-accessibility-qa
description: Audit a web UI for accessibility defects using DOM, accessibility-tree, keyboard, and contrast evidence from real browser runs, with optional source-code review. Use when asked to check keyboard operation, focus order, focus traps, accessible names, roles, labels, ARIA usage, or color contrast on a page or component. Reports evidence-backed findings and coverage, never a WCAG conformance certificate.
compatibility: Needs the installed browser-use skill (Python browser_use), Chrome or Chromium, and OPENAI_API_KEY. Part of the web QA suite and reads ../web-qa/references/evidence-contract.md. No screen reader control is available.
---

# Web accessibility QA

Collect accessibility evidence from a real browser run, state what each piece of evidence can
prove, and report findings with honest coverage. Do not certify conformance. Do not edit
application code or data. Do not file issues.

## Read before running

| Open when you need to... | Read |
|---|---|
| apply the suite status, evidence, budget, and reporting rules | `../web-qa/references/evidence-contract.md` |
| choose an evidence source and know its limits, including contrast method | `references/evidence-sources.md` |
| run a keyboard traversal and record focus evidence | `references/keyboard-protocol.md` |
| write the run task, output schema, verification code, and report rows | `references/evidence-examples.md` |

If the shared contract file is not installed, write `shared evidence contract missing` in the
report header and use these check statuses: Pass, Fail, Unknown, Blocked, Not run.

## Claim limits

| Claim | Allowed when |
|---|---|
| "control X has accessible name Y" | the accessibility tree returned that computed name |
| "tab order is A, B, C" | each step returned the focused element after a real key press |
| "keyboard trap in the dialog" | a recorded key sequence failed to move focus out, with the focus readback |
| "contrast is 3.1 to 1 against the stated 4.5 threshold" | both colors were resolved and the method was recorded |
| "no violations found for the checks run" | the coverage list of checks is in the same report |
| "WCAG 2.2 AA conformant", "accessible", "screen reader friendly" | never from this skill |

Screen reader output is Blocked here. There is no verified screen reader control in this
environment. Do not state what any screen reader announces.

## Preconditions

Ask only for the items marked indispensable. For the rest, use the scope the user supplied or a
stated default, record the choice as unverified metadata, and continue.

| Item | Class | Behavior when missing |
|---|---|---|
| approved URL and environment, report-only authority | indispensable | stop and ask |
| how to reach the page state without changing data | indispensable | stop and ask |
| absolute evidence directory | indispensable | create it yourself, or stop when the path is not writable |
| named reference: written requirements, a design annotation, component docs, or a WCAG criterion the user names | recordable | audit against explicit general constraints, mark reference-dependent checks Unknown, record `reference missing` |
| profile name | recordable | use a dedicated name such as `a11y-qa` and record it |
| budget: wall clock, browser calls and steps, soft USD cap | recordable | apply a stated bounded default, record it, report the spend |

Use local or staging targets and test accounts. Optional source access, when the user grants it,
is read-only.

## Browser call contract

```python
result = await browser_use.run(
    task_text,              # one whole traversal or audit, including every readback
    schema=output_schema,   # require AX nodes, focus steps, computed styles, and paths back
    profile="a11y-qa",
    max_steps=25,
    timeout_ms=180_000,
    max_cost_usd=1.0,
)
```

- These arguments are the whole Python API for a run. There is no resize, follow-up, pause, or
  download option. Express key presses, waits, and captures inside `task_text`.
- The default browser model is exactly `openai/gpt-6-astra`. An explicit environment override can
  select a different model. Report `result["model"]`, the model that actually ran, and never
  substitute a model silently.
- Any non-completed run raises `browser_use.BrowserUseError`. Keep the status, the message, and
  `error.result` as evidence.
- Each call starts and closes its own Chrome process. A profile keeps cookies, localStorage, and
  IndexedDB, not open tabs or unsaved page state. A keyboard sequence and its readbacks must
  stay in one run.
- Do not install axe, Lighthouse, or any other audit tool. Use an automated checker only when
  the user names one that already exists, and record its name, version, and ruleset.

## Evidence capture

The shared contract holds the general evidence rules. These points are specific to accessibility
work:

- Ask for machine-readable evidence, not prose: accessibility nodes, focus steps with the focused
  element after each key, computed colors, and attribute values.
- A screenshot cannot show an accessible name, a role, reading order, a live region
  announcement, or keyboard behavior. Use images for visible focus indicators, visible text, and
  visible state only.
- Capture extra frames with `page.cdp('Page.captureScreenshot', {format:'png'})` into your
  evidence directory, check each path exists, then call `attach_image(path)` before describing
  any image.

## Run plan

1. List the checks first: each row names the target element or flow, the expected behavior, the
   evidence source, and the reference item.
2. Reach the page state without changing data. Name the ready condition, such as a visible
   selector or a rendered item count. Navigation completion and network idle are not readiness.
3. Collect structure evidence: accessibility nodes and relevant DOM attributes for the named
   targets.
4. Run the keyboard traversal with focus readbacks. Keep it inside the same run.
5. Collect contrast evidence only for text whose colors resolve from CSS. Mark the rest Unknown.
6. Optional and only with granted access: review source for the specific defect, and label every
   code finding as not runtime-verified.
7. Write the report with per-check statuses, coverage counts, and scope nobody covered.

## Verdict rules

- One status per check. No accessibility score, no pass percentage, no weighted risk index.
- Evidence class decides what a check can say. A DOM-inferred label is not a computed accessible
  name; mark it as DOM inference.
- A gate over an empty evidence list is not a Pass. Zero focus steps, zero accessibility nodes,
  or a tool summary with no findings list is Not run or Unknown.
- A behavior the named reference does not cover is out of scope. Record it as an observation, not
  a Fail.
- A code fix suggested during review does not close a finding. Only a rerun with the same
  evidence closes it.
- Status assignment, ready-condition failures, repeat attempts, severity and confidence, coverage
  counts, and the overall verdict come from the shared contract. Do not restate them differently
  here.

## Anti-patterns

| Seen | Required behavior |
|---|---|
| "the page is accessible" | list the checks run, their statuses, and the uncovered scope |
| accessible name read from a screenshot | get the computed name from the accessibility tree or mark Unknown |
| focus order claimed from source order | record the focused element after each real key press |
| `dispatchEvent` used to fake a Tab press | use real input, then prove it with a focus readback |
| automated tool pass treated as conformance | report tool, version, ruleset, and what it cannot detect |
| live region "announced correctly" | report the attributes and the DOM change, not an announcement |
| contrast judged by eye from a PNG | resolve both colors and record the method, or mark Unknown |

## Report shape

Use the report template in the shared contract and add these accessibility fields:

- Header: page state audited, and any tool used with its version and ruleset.
- Checks table: add target and evidence-source columns, so each row says what proved it.
- Findings: add affected users. A finding without a stated impact is not reportable.
- Coverage: add every check type not attempted, including screen reader verification as
  Blocked, and name the evidence classes that were unavailable.

Maintenance contract: `SPEC.md`. Provenance and source decisions: `SOURCES.md`.
