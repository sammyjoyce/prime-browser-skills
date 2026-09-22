"""Confidence cutoffs: one contract, shared by the wrapper and the runtime.

A cutoff is a caller policy, not a measured probability of success. It says
"do not take this input on my behalf when the executor's own score for that
choice is below this number". Nothing here calibrates anything, and no cutoff
grants authority the caller did not already give: `generation="disabled"`,
freshness, the skip-when-unbound rule, `output["verification"]`, the refusal
to claim backend persistence and the cost stop all still apply above any
cutoff.

Three independent, optional gates:

    operation  the score for the chosen operation (CLICK, TYPE_TEXT, ...)
    target     the score for the chosen element, when the operation has one
    binding    the score for the supplied value bound to a field

`None` and `{}` both mean "record the scores, withhold nothing". An absent key
leaves that gate off. A present value must be a finite number in (0, 1]; a
bool is not a number here, and 0 is rejected because a cutoff of 0 would
withhold nothing while looking like a policy.

There are no default cutoffs on purpose. This project has no evaluation set
that would justify one, so an invented default would be an uncalibrated number
presented as a safety property.

Validation runs at both boundaries. The wrapper calls normalize_confidence()
before any process is launched, and the runtime calls the same function again
on the request it receives, because a runner never trusts its caller. The two
cannot drift because this is one module in one file, copied as a unit by
install.py.

Standard library only, no import side effects, and no dependency on the rest
of the jev package: the runtime loads this same file directly.
"""

from __future__ import annotations

import math
from typing import Any

__all__ = ["ConfidenceError", "GATES", "normalize_confidence"]

# One independent gate per decision the executor makes before it dispatches input.
GATES = ("operation", "target", "binding")


class ConfidenceError(ValueError):
    """An invalid confidence policy.

    Messages carry key names, types and numbers the caller supplied for this
    policy. They never carry a task, a supplied value or page content.
    """


def normalize_confidence(value: Any, field: str = "confidence") -> dict | None:
    """None, or a copy of the caller's cutoffs. Nothing is defaulted or rounded.

    Returns None for None and a new dict otherwise, so a caller that mutates
    its own dict afterwards cannot change the policy that was applied.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfidenceError(
            f"{field} must be an object or null, got {type(value).__name__}"
        )
    policy = {}
    for key, cutoff in value.items():
        if not isinstance(key, str) or key not in GATES:
            raise ConfidenceError(
                f"{field} keys must be one of " + ", ".join(GATES) + f", got {key!r}"
            )
        if isinstance(cutoff, bool) or not isinstance(cutoff, (int, float)):
            raise ConfidenceError(
                f"{field}[{key!r}] must be a number greater than 0 and at most 1, "
                f"got {type(cutoff).__name__}"
            )
        if not math.isfinite(cutoff) or not 0 < cutoff <= 1:
            raise ConfidenceError(
                f"{field}[{key!r}] must be a number greater than 0 and at most 1, got {cutoff!r}"
            )
        policy[key] = cutoff
    return policy
