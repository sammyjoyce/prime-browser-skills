# Evidence sources and their limits

Use this to pick an evidence source for a check and to know what sentence that evidence
supports. Every row is about proof, not about effort.

## Contents

1. Source table
2. Contrast method
3. Zoom and reflow
4. Code review and automated checkers
5. Claim mapping

## Source table

| Source | Collect it by | Proves | Cannot prove |
|---|---|---|---|
| accessibility tree | asking the run to read the accessibility snapshot for the named selectors, for example through `page.cdp('Accessibility.getFullAXTree')` or the agent accessibility snapshot | computed role, computed name, computed state for the nodes returned | how any screen reader presents or announces the node |
| DOM and attributes | `getAttribute`, `labels`, `tabindex`, `hidden`, `disabled`, `aria-*` values | what the markup declares | the browser-computed accessible name, which comes from the accessibility tree |
| computed styles | `getComputedStyle` for color, background-color, outline, font-size, font-weight | resolved CSS values for that element | the rendered result of stacked images, gradients, or blends |
| real keyboard input | key events sent as real input, then a focus readback after each key | focus movement, activation, traps, and escape behavior | what a screen reader user hears |
| element geometry | `getBoundingClientRect()` | target size and spacing in CSS px | whether a touch target is comfortable in real use |
| media emulation | emulate reduced motion or forced colors, then read `matchMedia(...).matches` | that the page responded to the setting | operating-system-level assistive behavior |
| final screenshot | `result["screenshot_path"]` | visible focus indicator, visible text, visible error state at the end of the run | names, roles, reading order, announcements, keyboard behavior |
| extra captures | `page.cdp('Page.captureScreenshot', {format:'png'})` written into the evidence directory | the visible state at that checkpoint | anything not visible |
| source code | read-only review when the user grants access | what the code declares | runtime behavior, until a run confirms it |
| existing automated checker | only a tool the user names as already available, with its version and ruleset | the rule set that tool covers | conformance, and every issue outside its rules |
| screen reader | not available here | nothing | Blocked, state this in coverage |

## Contrast method

1. Resolve the text color and the effective background color from computed styles.
2. Compute the ratio with the standard relative-luminance formula and report it to one decimal.
3. Take the threshold from the reference the user named, and record where the threshold came
   from, including the text size and weight it depends on.
4. Mark the sample Unknown when the background comes from an image, a gradient, a video, a
   translucent overlay, or a blend mode, unless the user approves pixel sampling. Then record the
   sampling coordinates and the source image.
5. Report the selector, both colors, the ratio, the threshold, and the method for every sample.
   A ratio without its colors is not evidence.

## Zoom and reflow

- Test reflow with an emulated narrow viewport, such as 320 CSS px wide, and record the measured
  width from the readback.
- Evidence of a reflow defect: `document.documentElement.scrollWidth` greater than
  `clientWidth`, content clipped by a fixed height, or a control moved outside the viewport.
- Browser zoom percentage is not directly controlled here. Report the emulated width you used
  and do not describe it as a zoom level unless the reference defines the mapping.

## Code review and automated checkers

- Do not install axe, Lighthouse, pa11y, or any other tool. Use one only when the user says it
  already exists in the project, and then record name, version, and ruleset.
- Label every automated result as tool output for its rule set. Automated rules catch a subset of
  real defects, so a clean tool run is not a Pass for checks the tool does not cover.
- Keep deterministic output separate from your own judgment, and name the findings you believe
  are false positives, with the reason. An unreviewed tool list is not a finding list.
- Label every source-code finding as `code finding, not runtime verified`. It can explain a
  runtime defect or predict one. It does not close a finding.
- A suggested fix stays open until a rerun reproduces the check with runtime evidence.

## Claim mapping

| Evidence you hold | Sentence you may write |
|---|---|
| accessibility node with `name: "Search"` | the computed accessible name is "Search" |
| DOM only, `aria-label="Search"` present | the markup declares `aria-label="Search"`, computed name not read |
| focus readbacks for 12 Tab presses | the tab order over those 12 steps was ... |
| capture showing a visible outline on the focused control | a visible focus indicator was present in this capture |
| no evidence collected for a criterion | Not run, listed in coverage |
| tool output with version and ruleset | that tool reported N issues under ruleset R |
| any of the above | never "the page is accessible" and never "WCAG conformant" |
