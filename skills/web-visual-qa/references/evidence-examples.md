# Evidence examples

Templates for one visual check cycle. Values inside angle brackets are placeholders. Do not copy
these numbers or paths into a report; only real run output belongs there.

## Contents

1. Plan rows
2. Task text
3. Output schema
4. Result handling after the run
5. Report rows
6. Anti-pattern and correction

## Plan rows

| Check | Variant | Reference item | Expected | Tolerance | Method |
|---|---|---|---|---|---|
| primary button height | 390x844, light | `<design v3.2, Button/Primary>` | 44 px | 0 px | `getBoundingClientRect().height` |
| card gap | 390x844, light | `<design v3.2, spacing-4>` | 16 px | plus or minus 1 px | rect edge difference |
| header background | 390x844, dark | `<design v3.2, surface-900>` | `#0B1020` | exact | `getComputedStyle` |

## Task text

```text
Open <https://staging.example.test/pricing> in a fresh tab.
1. Before loading, emulate a 390x844 viewport with device scale factor 3 and mobile enabled.
2. Load the page and wait until the element #pricing-grid is visible and contains 3 cards.
   Do not treat navigation completion or network idle as ready.
3. Await document.fonts.ready. Then inject a style that sets animation-duration and
   transition-duration to 0s for all elements.
4. Measure and return: window.innerWidth, window.innerHeight, window.devicePixelRatio,
   navigator.userAgent, document.fonts.status, the injected rule count,
   the bounding rect of button.cta-primary, the gap between the first and second card rect,
   and getComputedStyle(header).backgroundColor.
5. Capture a PNG with page.cdp('Page.captureScreenshot', {format:'png'}) and write it to
   /abs/evidence/<run-id>/pricing-390-light.png. Return that absolute path.
6. Do not click, submit, sign in, or change any data.
```

## Output schema

```python
output_schema = {
    "type": "object",
    "properties": {
        "conditions": {
            "type": "object",
            "properties": {
                "inner_width_css_px": {"type": "number"},
                "inner_height_css_px": {"type": "number"},
                "device_pixel_ratio": {"type": "number"},
                "user_agent": {"type": "string"},
                "fonts_status": {"type": "string"},
                "motion_rules_injected": {"type": "integer"},
                "ready_condition_met": {"type": "boolean"},
            },
            "required": ["inner_width_css_px", "inner_height_css_px", "device_pixel_ratio",
                         "fonts_status", "motion_rules_injected", "ready_condition_met"],
            "additionalProperties": False,
        },
        "measurements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "number"},
                    "unit": {"type": "string"},
                    "selector": {"type": "string"},
                },
                "required": ["name", "value", "unit", "selector"],
                "additionalProperties": False,
            },
        },
        "computed_styles": {"type": "object", "additionalProperties": {"type": "string"}},
        "captures": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["conditions", "measurements", "captures"],
    "additionalProperties": False,
}
```

## Result handling after the run

```python
from pathlib import Path

conditions = result["output"]["conditions"]
requested = {"inner_width_css_px": 390, "inner_height_css_px": 844, "device_pixel_ratio": 3}
condition_mismatch = {k: (v, conditions.get(k)) for k, v in requested.items()
                      if conditions.get(k) != v}

missing_captures = [p for p in result["output"]["captures"]
                    if not (Path(p).is_file() and Path(p).stat().st_size > 0)]

# Only after this check may the judging session describe an image:
for path in result["output"]["captures"]:
    if path not in missing_captures:
        print(await attach_image(path))
```

- `condition_mismatch` non-empty: every check for that variant is Unknown.
- `missing_captures` non-empty: the dependent checks are Unknown and the report says
  `capture missing`.
- `result["screenshot_path"]` is the final-state PNG from the runner. Cite it as final state,
  not as the state of step 3.

## Report rows

```text
Header
  scope: pricing page, mobile web, light and dark
  reference: <design v3.2>, exported 2026-09-10
  build/url: <https://staging.example.test/pricing>, commit <abc1234>
  profile: visual-qa   evidence: /abs/evidence/<run-id>/
  conditions measured: 390x844 CSS px, DPR 3, fonts loaded, 412 motion rules injected
  budget: 2 of 4 browser calls, $0.13 of $1.00, 6 of 20 minutes

Checks
  | check | variant | expected | observed | tolerance | status | evidence |
  | primary button height | 390x844 light | 44 px | 40 px | 0 px | Fail | pricing-390-light.png |
  | card gap | 390x844 light | 16 px | 16 px | 1 px | Pass | pricing-390-light.png |
  | header background | 390x844 dark | #0B1020 | Unknown | exact | Unknown | dark variant not run |

Findings
  F1 primary button 4 px short of spec
     expected source: <design v3.2, Button/Primary height 44 px>
     actual: measured 40.0 CSS px, button.cta-primary, /abs/evidence/<run-id>/pricing-390-light.png
     severity: medium   confidence: high   attempts: 2 of 2 reproduced

Coverage
  planned 6, tested 4, failed 1, unknown 1, not run 2 (dark variant, 768 px viewport)
```

## Anti-pattern and correction

Wrong:

```text
Visual match 97%. Page looks consistent with the design. Screenshot saved at
/abs/evidence/run/home.png. Pass.
```

Problems: an aggregate score used as the gate, no reference version, no measured value, no unit,
and an image cited without attaching it.

Corrected:

```text
Checks 5 planned, 4 measured, 1 not run.
  nav height: expected 64 px, observed 64 px, tolerance 0 px, Pass, home.png (attached)
  hero title size: expected 32 px, observed 28 px, tolerance 0 px, Fail, home.png (attached)
  footer link color: reference value not supplied, Unknown
  dark variant: Not run, budget stopped after 3 browser calls
Overall: Fail for the stated scope. One required check is Unknown.
```
