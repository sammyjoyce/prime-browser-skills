# Measurement protocol

Use this before any visual result exists. It fixes what to measure, in what unit, and with what
tolerance, so a later number cannot be reverse-fitted into a Pass.

## Contents

1. Order of work
2. Metric table
3. Tolerance rules
4. Color and contrast limits
5. Scoring rules

## Order of work

1. List the checks from the named reference.
2. For each check, write metric, unit, method, and tolerance.
3. Get the user to confirm any tolerance you had to choose yourself.
4. Only then run the browser task.
5. Compare each measured value with its recorded tolerance.

## Metric table

| Property | Method inside the run | Unit |
|---|---|---|
| position, size | `getBoundingClientRect()` on a named selector | CSS px |
| spacing between elements | difference between two rect edges | CSS px |
| alignment | compare left, right, or center values of several rects | CSS px |
| typography | `getComputedStyle` font-family, font-size, font-weight, line-height | string, px |
| color | `getComputedStyle` color, background-color, border-color | rgb or rgba, converted to hex |
| radius, border, shadow | `getComputedStyle` border-radius, border-width, box-shadow | px, string |
| overflow or clipping | `scrollWidth` against `clientWidth`, rect against viewport rect | CSS px |
| element on top at a point | `document.elementFromPoint(x, y)` at the rect center | selector or tag |
| visible item count | `querySelectorAll` length after the ready condition | count |
| image dimensions | `naturalWidth`, `naturalHeight` against rendered rect | px |

Measure in CSS pixels inside the page. Convert to device pixels only when you must compare with
a screenshot, and record the device pixel ratio used for that conversion.

## Tolerance rules

| Case | Default starting tolerance | Confirm with user |
|---|---|---|
| value derived from a design token or spec number | 0 px exact | yes, if the user expects sub-pixel rounding |
| layout position and spacing | plus or minus 1 CSS px | yes |
| text block height or wrapped text width | plus or minus 2 CSS px | yes |
| color from a named token | exact hex match | yes |
| computed contrast ratio | threshold stated by the reference, no tolerance | yes |

Rules:

1. A tolerance without a unit is invalid.
2. A tolerance chosen after seeing the measurement is invalid. Report the planned value and any
   later change with its reason.
3. Do not widen a tolerance to cover a difference you cannot explain. Mark the check Fail or
   Unknown and say which.
4. A measurement you did not take is Not run, not a Pass.
5. A quantitative claim carries value, unit, and tolerance. A check without those three is
   either a qualitative check with a written criterion or it is not a check.

## Qualitative checks

Some real defects have no natural number. A qualitative check is valid when you write the
criterion before the run and cite evidence you viewed.

| Valid criterion | Evidence |
|---|---|
| heading text is not clipped or truncated at the stated viewport | attached capture plus `scrollWidth` against `clientWidth` when it applies |
| the two cards do not overlap | attached capture plus both rects |
| the primary action is visible without scrolling | attached capture plus rect against viewport height |
| the error state shows the error icon and message together | attached capture plus both selectors present |

Invalid: "looks polished", "feels cramped", "roughly matches", or a number invented to describe
one of these. Ask for the missing reference value instead, and mark the check Unknown until it
arrives.

## Three readings when a layout looks wrong

When the DOM numbers match the reference and the page still looks wrong, take three readings and
say which disagree:

1. the DOM rect of the element,
2. the painted extent visible in a capture you attached,
3. the container a user perceives as the frame, for example the card, not the wrapper.

Report all three values. A mismatch between them is the finding, and it is more useful than a
single number that says the check passed.

## Same spec before and after

A before-and-after pair uses one measurement spec: same selectors, same viewport, same device
pixel ratio, same fonts, same tolerance. Changing any of them between the two runs invalidates
the comparison. Do not compare captures across browsers, operating systems, font sets, zoom
levels, or device pixel ratios without recording the difference and what it does to the numbers.

## Detector outputs

An automated detector is a hint, not a measurement. Confirm every detector output with a DOM
measurement or a viewed capture before it enters a check.

| Detector | Known failure |
|---|---|
| bounding box taken from painted pixels | on a light background the box can select the background instead of the element |
| whitespace or horizontal-rule detection | plain white gaps are reported as rules |
| any threshold computed over zero samples | the empty set passes the threshold |
| screenshot-pixel distance without the device pixel ratio | the numbers are off by the ratio |

Record the device pixel ratio used for any screenshot-pixel conversion. A conversion without a
recorded ratio is Unknown.

## Status mapping for measurements

| Situation | Status |
|---|---|
| measured value inside tolerance | Pass |
| measured value outside tolerance, reference value known | Fail |
| requirement violation you can evidence, even though the page never reached the ready state | Fail |
| reference value missing, measurement taken | Unknown, with the measurement recorded |
| capture or readback missing, unreadable, or ambiguous | Unknown |
| check never started because an earlier step failed or the budget stopped | Blocked |
| check planned but never attempted | Not run |
| statistic computed over zero samples | Not run, never Pass |
| property the reference does not specify | out of scope, recorded as an observation |

## Color and contrast limits

- Read color from computed styles when the color comes from CSS.
- When the visible color comes from an image, a gradient, a blend mode, or a stacked
  translucent layer, computed styles do not give the rendered color. Mark it Unknown unless the
  user approves a pixel-sampling step, and then record the sampling method and coordinates.
- Deep contrast and accessibility judgments belong to `web-accessibility-qa`. Keep contrast work
  here to reference-stated color values.

## Scoring rules

- Report per-check statuses only.
- Do not produce a visual score, a match percentage, a weighted index, or a pass rate that can
  hide a failure.
- Do not average variants. A failure in one viewport stays a failure.
- If the user asks for a single number, give counts instead: checks planned, passed, failed,
  unknown, blocked, not run.
