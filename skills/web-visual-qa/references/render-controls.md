# Render controls and proof of control

Use this when a visual check depends on a named render condition: viewport, device pixel ratio,
fonts, motion, theme, locale, crop, masks, or page readiness.

Rule for every control: request it inside the browser task, then require a measured readback in
the run output. The readback is the proof. A request without a readback is Unknown.

## Contents

1. Control table
2. Page readiness
3. What you cannot control here
4. When a control cannot be proven

## Control table

| Control | Ask the run to | Require this readback | Unit |
|---|---|---|---|
| viewport size | apply emulated device metrics through its own JavaScript before loading the page | `window.innerWidth`, `window.innerHeight` | CSS px |
| device pixel ratio | set the device scale factor in the same override | `window.devicePixelRatio` | ratio |
| mobile emulation | set the mobile flag and report the user agent actually in use | `navigator.userAgent`, `navigator.maxTouchPoints` | string, count |
| web fonts | await `document.fonts.ready` before any capture | `document.fonts.status` plus resolved `font-family` and `font-size` of one named element | string, px |
| motion | inject a style that sets `animation-duration` and `transition-duration` to `0s` on all elements | the injected rule count plus `matchMedia('(prefers-reduced-motion: reduce)').matches` | count, boolean |
| color scheme | emulate the media feature, then reload or re-evaluate | `matchMedia('(prefers-color-scheme: dark)').matches` and the resolved background color of `<body>` | boolean, rgb |
| locale and timezone | emulate them through its JavaScript | `Intl.DateTimeFormat().resolvedOptions()` locale and timeZone | string |
| crop | compute the rect with `getBoundingClientRect()` and pass it as the capture clip | the exact rect numbers used | CSS px |
| masks | overlay opaque blocks over each named dynamic selector before capture | number of nodes matched and number of overlays added | count |
| scroll position | scroll the target element into view and wait for the named ready condition | `window.scrollY` and the element rect after the wait | CSS px |

Notes:

- `page.cdp('Page.captureScreenshot', {format:'png'})` is the capture call the installed runner
  already uses. Other emulation calls go through the same JavaScript channel in the browser
  agent, so treat their effect as unproven until the readback confirms it.
- A mask hides a region from comparison. It does not sanitize the PNG, and the file can still
  hold private content from elsewhere on the page.
- Record every readback in the report row for that variant, not only in the run log.

## Page readiness before a capture

The shared contract defines what counts as a ready condition. Two additions for captures:

- Capture only after the ready condition and after the motion-freeze readback. An entry
  animation still running makes the image a snapshot of a transition, not of the state.
- Record the ready condition used in the variant row, so a later rerun can wait for the same
  state.

## What you cannot control here

| Not available | Consequence |
|---|---|
| a Python resize, follow-up, or download call | state viewport and capture work inside the task text |
| native device rendering | mobile web only, native app requests are Blocked |
| printer, PDF, or email rendering | out of scope unless the user supplies a verified path |
| video, canvas, and WebGL frames frozen by CSS | mark timing-dependent regions Unknown or mask them |
| screen recordings or per-step frames | capture named checkpoints inside the run instead |

## When a control cannot be proven

1. Record the requested value and the measured value side by side.
2. Mark every check that depended on that condition as Unknown for that variant.
3. Keep any other check in the same run that did not depend on it.
4. Try one alternative method at most, and only when the budget allows it. Record both attempts.
5. Never restate the requested value as the observed value.
