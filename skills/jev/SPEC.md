# Jev skill maintenance contract

Class: workflow-process plus Python integration. Shape: one callable executor with a
small subprocess protocol. A separate runtime is necessary because upstream needs
Python 3.12 while Prime Agent kernels may use 3.11. Do not install upstream into the kernel.

## Invariants

- Keep Astra's browser_use API and exact default openai/gpt-6-astra unchanged.
- Require an explicit HTTP(S) URL. No schema argument or invented extraction support.
- Preserve provider error messages, typed noncompleted errors and partial artifacts.
- A returned completed status is an executor claim, not independent verification.
- Persist named login profiles with exclusive ownership and bounded full-tree cleanup.
- Native PNG from CDP, absolute paths and main-session attachment. No silent JPEG conversion.
- Telemetry off. No personal Chrome attachment. No unrelated dotenv loading.
- Null cost remains unknown; account for both model roles; stop when successful calls
  cannot be costed. No silent fallback or replay after uncertain side effects.

## Trigger cases

Should trigger: navigate through a known site; fill an approved test form; complete a
specified booking in staging; run a bounded browser interaction with screenshot return;
use a persistent Jev login profile; delegate a whole action-heavy browser task.

Should not trigger: typed HN title extraction without actions; explain arbitrary source
code; native iOS/Android testing; filesystem editing; requests for visual acceptance with
no reference; implicit authorization to pay or send a message.

## Required validation cases

Native loader in a fresh session; successful local navigation; approved form checked
against server state; native PNG capture and parent viewing; same-profile lock conflict;
cancel during spawn and during work, cleanup and reuse; timeout; malformed JSON protocol;
provider401 with real message; missing screenshot; missing cost; login with no key and
cookie/localStorage persistence after browser restart; absent Chrome/runtime dependency
reported clearly; explicit unsupported-task handoff with no action replay.

Do not claim every case passed unless VALIDATION.md points to its evidence. Changes to
runtime/provider/source pin require both deterministic checks and bounded live smoke.
