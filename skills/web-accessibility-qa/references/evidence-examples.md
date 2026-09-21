# Evidence examples

Templates for one accessibility audit cycle. Values inside angle brackets are placeholders. Only
real run output belongs in a report.

## Contents

1. Check rows
2. Task text
3. Output schema
4. Result handling after the run
5. Report rows
6. Anti-pattern and correction

## Check rows

| Check | Target | Evidence source | Expected | Reference |
|---|---|---|---|---|
| icon button has a computed name | `button.icon-search` | accessibility tree | name is "Search" | `<component docs v4>` |
| tab order follows the visual order | header, then main | real keys plus focus readback | logo, search, sign in, main heading | `<spec section 3.2>` |
| dialog returns focus | `#filters-dialog` | real keys plus focus readback | Escape returns focus to the trigger | `<spec section 3.4>` |
| body text contrast | `.card p` | computed styles | ratio at or above the stated 4.5 threshold | `<brand tokens v2>` |

## Task text

```text
Open <https://staging.example.test/search> in a fresh tab.
1. Wait until #results-list is visible and contains at least 1 item. Do not treat navigation
   completion or network idle as ready.
2. Read the accessibility nodes for button.icon-search, a.skip-link, and #filters-dialog, and
   return role, computed name, and state for each.
3. Return the DOM attributes aria-label, aria-labelledby, alt, and tabindex for those elements.
4. Focus the document body, then send 12 real Tab key presses. After every press, return the
   focused element as tag, id, class, role, computed name, and bounding rect.
5. Activate button.filters with Enter, read focus, send Escape, and read focus again.
6. Return getComputedStyle color and background-color for .card p, plus its font-size and
   font-weight.
7. Capture PNGs at step 4 press 1 and after step 5 with
   page.cdp('Page.captureScreenshot', {format:'png'}), write them to
   /abs/evidence/<run-id>/focus-step-1.png and /abs/evidence/<run-id>/dialog-escape.png,
   and return both absolute paths.
8. Do not submit forms, sign in, or change any data.
```

## Output schema

```python
output_schema = {
    "type": "object",
    "properties": {
        "ready_condition_met": {"type": "boolean"},
        "ax_nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "role": {"type": "string"},
                    "computed_name": {"type": "string"},
                    "state": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["selector", "role", "computed_name", "source"],
                "additionalProperties": False,
            },
        },
        "focus_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "integer"},
                    "key": {"type": "string"},
                    "focused": {"type": "string"},
                    "role": {"type": "string"},
                    "computed_name": {"type": "string"},
                    "input_method": {"type": "string"},
                },
                "required": ["step", "key", "focused", "input_method"],
                "additionalProperties": False,
            },
        },
        "contrast_samples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "foreground": {"type": "string"},
                    "background": {"type": "string"},
                    "font_size_px": {"type": "number"},
                    "font_weight": {"type": "string"},
                    "method": {"type": "string"},
                },
                "required": ["selector", "foreground", "background", "method"],
                "additionalProperties": False,
            },
        },
        "captures": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ready_condition_met", "ax_nodes", "focus_steps", "captures"],
    "additionalProperties": False,
}
```

`source` on an accessibility node records where the name came from, for example
`accessibility-tree` or `dom-inference`. `input_method` records how the key was sent, for example
`cdp-input` or `agent-key-action`. Both fields decide which sentence the report may use.

## Result handling after the run

```python
from pathlib import Path

out = result["output"]
dom_only = [n for n in out["ax_nodes"] if n["source"] != "accessibility-tree"]
fake_input = [s for s in out["focus_steps"] if s["input_method"] not in
              ("cdp-input", "agent-key-action")]
missing_captures = [p for p in out["captures"]
                    if not (Path(p).is_file() and Path(p).stat().st_size > 0)]

for path in out["captures"]:
    if path not in missing_captures:
        print(await attach_image(path))      # required before describing any capture
```

- `dom_only` entries become DOM-inference observations, not accessible-name claims.
- `fake_input` entries invalidate the keyboard claim for those steps. Mark them Unknown and rerun
  with real input if the budget allows.
- `out["ready_condition_met"]` false makes every later check Unknown or Blocked, except a
  requirement violation you can still evidence from what was captured.

## Report rows

```text
Header
  scope: search page, header and filters dialog
  reference: <component docs v4>, <spec section 3.2 and 3.4>
  build/url: <https://staging.example.test/search>  profile: a11y-qa
  model actually used: <value of result["model"]>
  evidence: /abs/evidence/<run-id>/   tools: none installed
  budget: 2 of 3 browser calls, $0.11 of $1.00, 9 of 25 minutes

Checks
  | check | target | evidence | expected | observed | status |
  | computed name | button.icon-search | accessibility tree | "Search" | "" (empty name) | Fail |
  | tab order | header | 12 focus readbacks, cdp-input | logo, search, sign in | logo, sign in, search | Fail |
  | dialog focus return | #filters-dialog | focus readback after Escape | trigger regains focus | focus on body | Fail |
  | body contrast | .card p | computed styles | at or above 4.5 | 4.9 | Pass |
  | live region announcement | #status | none available | not testable here | Blocked | Blocked |

Findings
  A1 icon-only search button has an empty accessible name
     impact: screen reader and voice control users cannot identify or target the control
     expected source: <component docs v4, "icon buttons need an accessible name">
     actual: accessibility node role "button", computed name "", source accessibility-tree
     severity: high   confidence: high   attempts: 2 of 2 reproduced

Coverage
  planned 12, checked 9, failed 3, unknown 1, blocked 2, not run 1
  not attempted: screen reader verification (Blocked, no verified tool), forced-colors mode
  conformance: not assessed, this report is evidence for the checks listed above only
```

## Anti-pattern and correction

Wrong:

```text
Ran an accessibility review. The page is WCAG 2.2 AA compliant. Buttons have labels and the
focus ring is visible in the screenshot. Score 92/100.
```

Problems: a conformance claim with no criterion-level evidence, labels read from markup or from
an image rather than computed names, keyboard behavior inferred from a static capture, and a
score used as a gate.

Corrected:

```text
Checks: 12 planned, 9 checked with evidence, 3 failed, 1 unknown, 2 blocked, 1 not run.
  button.icon-search: computed name empty (accessibility tree). Fail.
  header tab order: observed logo, sign in, search over 12 recorded presses. Fail against
  <spec section 3.2>.
  .card p contrast: 4.9 against the stated 4.5 threshold, computed styles. Pass.
  Screen reader behavior: Blocked, no verified screen reader in this environment.
Conformance is not assessed. These results cover the listed checks only.
```
