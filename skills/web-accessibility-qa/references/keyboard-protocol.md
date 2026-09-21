# Keyboard and focus protocol

Use this for tab order, activation, traps, skip links, dialogs, and composite widgets. Keep one
sequence inside one browser run, because a new run is a new Chrome process with no page state.

## Contents

1. Plan the sequence first
2. Real input requirement
3. Focus descriptor
4. Sequence templates
5. Trap and escape rules
6. Incomplete sequences

## Plan the sequence first

Write these before the run: the start element, the ordered keys, the expected focus at each
step from the named reference, the stop condition, and the maximum number of presses. Without an
expected order, record the observed order as an observation and mark order checks Unknown.

## Real input requirement

- Use real key input, such as `page.cdp('Input.dispatchKeyEvent', ...)` or the agent key action.
- `element.dispatchEvent(new KeyboardEvent('keydown', ...))` does not move focus and does not
  trigger browser defaults. A sequence built that way proves nothing about keyboard operation.
- Prove each press with a focus readback taken after the press. If the focus readback is missing,
  that step is Unknown.

## Focus descriptor

Return this for every step:

| Field | Source |
|---|---|
| tag, id, class | `document.activeElement` |
| role and computed name | accessibility node for that element, when available |
| rect | `getBoundingClientRect()` |
| container | nearest dialog, menu, or landmark ancestor |
| is body | `document.activeElement === document.body` |
| visible indicator | attached capture at that step, when the check needs it |

Two traps for the readback itself: focus inside a shadow root needs
`document.activeElement.shadowRoot.activeElement`, and focus inside an iframe reports the iframe
element from the top document. Record which one applied.

## Sequence templates

| Check | Keys | Stop condition |
|---|---|---|
| forward order | Tab repeated | the planned count, or focus returns to the first control |
| reverse order | Shift+Tab repeated | focus returns to the start element |
| skip link | Tab once from the top of the page | the first focused element is read and reported |
| activation | Enter, then Space on the same control | the expected state change is observed and recorded |
| dialog entry | activate the trigger, then read focus | focus is inside the dialog |
| dialog exit | Escape, then read focus | focus returns to the trigger |
| menu, tabs, listbox, grid | Arrow keys, Home, End, and Escape as the pattern defines | the expected roving focus behavior is observed |
| form error | submit with invalid data only when the user approved that action | focus or an error association is observed |

Do not submit a form, send a message, or change data unless the user approved that exact action.
Activation checks default to controls that do not mutate data.

## Trap and escape rules

- A focus cycle inside a modal dialog is expected behavior, not a trap.
- A trap is a recorded sequence where focus cannot leave a container by Tab, Shift+Tab, or
  Escape, with the readback for each attempt.
- Report the attempt count and the exact keys tried. "Seems trapped" is not a finding.
- If focus lands on `body` unexpectedly, record it. That is a common sign of a removed element or
  a closed overlay, and it needs a separate check rather than a conclusion.

## Incomplete sequences

1. Steps that produced readbacks stay as evidence with their statuses.
2. Steps never executed are Blocked, with the reason: step cap, timeout, cost cap, or an error.
3. Report the press count reached against the planned count.
4. Re-running repeats the whole sequence from a fresh browser. Say so, and do not merge two runs
   into one order claim unless both used the same start state and both readbacks agree.
