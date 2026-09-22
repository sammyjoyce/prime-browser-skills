"""Declared DOM checks: one contract, shared by the wrapper and the runtime.

A check is a caller-declared, read-only assertion about the page the browser
ends on. Nothing in this module clicks, types, navigates or writes. The only
browser work is one synchronous JavaScript read that returns observed values;
every comparison happens in this process, so a declared expectation is never
sent into the page.

Honesty rules, in one place:

- Scope is exactly what the caller declared: `scope` is always
  "declared_dom_checks_only". A passing check says the browser DOM said so at
  one instant, after execution finished. It is not proof that a server stored
  anything, and it never turns an executor completion claim into a verified
  goal.
- A row names the declaration it answers with declaration_fingerprint(), not
  with a copy of the declaration. The caller keeps the only copy of its own
  expectation, and the fingerprint survives a transport that rewrites text.
- "failed" is only an observed mismatch. Missing, ambiguous, invisible,
  refused or unreadable evidence is "unknown", never "failed".
- No declared check at all is "not_run", which is not a pass.

Validation runs at both boundaries. The wrapper calls normalize_checks()
before any process is launched, and the runtime calls the same function again
on the request it receives, because a runner never trusts its caller. The two
cannot drift because this is one module in one file, copied as a unit by
install.py.

Standard library only, no import side effects, and no dependency on the rest
of the jev package: the runtime loads this same file directly.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Iterable

__all__ = [
    "CheckError",
    "SCOPE",
    "BOUNDARY",
    "ROW_STATUSES",
    "STATUSES",
    "KINDS",
    "MAX_CHECKS",
    "NOTE",
    "CONSISTENCY",
    "FINGERPRINT_CHARS",
    "declaration_fingerprint",
    "normalize_checks",
    "read_expression",
    "summarize",
    "tally",
    "verification_payload",
]

SCOPE = "declared_dom_checks_only"
BOUNDARY = "browser_dom"
ROW_STATUSES = ("passed", "failed", "unknown")
STATUSES = ROW_STATUSES + ("not_run",)
# The closed vocabulary for `consistency`: the rows came from one synchronous
# read of one document, or no read happened at all.
NOT_READ = "not_read"
SINGLE_READ = "single_synchronous_read"
CONSISTENCY = (NOT_READ, SINGLE_READ)
NOTE = (
    "browser DOM observation taken after execution, inside the declared scope only; "
    "not evidence that a server stored anything and not a verification of the task goal"
)

KINDS = ("url", "title", "text", "value", "count")
SELECTOR_KINDS = ("text", "value", "count")
CHECK_KEYS = ("id", "kind", "selector", "equals", "contains")

MAX_CHECKS = 20
MAX_ID_CHARS = 100
MAX_SELECTOR_CHARS = 1_000
MAX_EXPECTED_CHARS = 2_000
MAX_COUNT = 100_000
# Longest value the page may hand back for one check. A longer one is reported
# unknown rather than compared, because a truncated compare could invent a
# failure that the page never showed.
MAX_READ_CHARS = 20_000
# Longest observed string copied into the result and into result.json.
MAX_REPORTED_CHARS = 2_000
MAX_REPORTED_URL_CHARS = 2_048
# A declaration fingerprint is a SHA-256 hex digest: 64 lowercase hex
# characters. Hex holds no whitespace and no "sk-" or "bearer" literal, so a
# credential-shaped redaction pattern cannot rewrite one in transit.
FINGERPRINT_CHARS = 64

# Every reason a row can be unknown. A reason outside this set is not reported.
REASONS = (
    "missing_or_ambiguous",          # the selector matched zero or several elements
    "sensitive_field",               # a password input is never read
    "hidden_field",                  # type=hidden is not readable evidence
    "unsupported_control",           # the element has no value this layer can read
    "not_a_field",                   # the element holds no value at all
    "not_visible",                   # a text check needs a visible element
    "value_too_large",               # over MAX_READ_CHARS, so never compared
    "unreadable_or_invalid_selector",  # the selector or the read itself threw
    "evidence_unavailable",          # the page returned nothing usable for this row
    "evidence_type_mismatch",        # the page returned the wrong type of evidence
    "page_unavailable",              # the read could not run at all
    "browser_unavailable",           # the browser was gone before the read
    "verification_not_attempted",    # the run ended before checks could run
)


class CheckError(ValueError):
    """An invalid declared check.

    Messages carry indexes, key names, types and lengths. They never carry an
    expectation, an observed value or a selector body.
    """


def _bad(message: str) -> None:
    raise CheckError(message)


def _short(value: Any) -> str:
    """A bounded repr for small enum-like fields (kind), never for expectations."""
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


def normalize_checks(value: Any) -> list:
    """Validate declared checks and return a normalized, private snapshot.

    None or [] means no checks. The result is itself valid input, so the
    wrapper can send its snapshot and the runtime can validate it again.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes, dict)) or not isinstance(value, list):
        _bad(f"checks must be a list of check objects or None, got {type(value).__name__}")
    if len(value) > MAX_CHECKS:
        _bad(f"checks must hold at most {MAX_CHECKS} checks, got {len(value)}")

    normalized = []
    seen: dict = {}
    for index, item in enumerate(value):
        label = f"checks[{index}]"
        if not isinstance(item, dict):
            _bad(f"{label} must be an object, got {type(item).__name__}")
        unknown = sorted((key for key in item if key not in CHECK_KEYS), key=repr)
        if unknown:
            names = ", ".join(repr(key)[:60] for key in unknown)
            _bad(f"{label} has unsupported key(s) {names}; a check accepts only "
                 + ", ".join(CHECK_KEYS))

        identifier = item.get("id", f"check[{index}]")
        if not isinstance(identifier, str) or not identifier.strip():
            _bad(f"{label}.id must be a nonempty string, got {type(identifier).__name__}")
        if len(identifier) > MAX_ID_CHARS:
            _bad(f"{label}.id must be at most {MAX_ID_CHARS} characters, got {len(identifier)}")
        if identifier in seen:
            _bad(f"{label}.id duplicates the id declared at checks[{seen[identifier]}]")
        seen[identifier] = index

        kind = item.get("kind")
        if kind not in KINDS:
            _bad(f"{label}.kind must be one of " + ", ".join(KINDS) + f", got {_short(kind)}")

        selector = item.get("selector")
        if kind in SELECTOR_KINDS:
            if not isinstance(selector, str) or not selector.strip():
                _bad(f"{label}.selector must be a nonempty CSS selector string for kind "
                     f"'{kind}', got {type(selector).__name__}")
            if len(selector) > MAX_SELECTOR_CHARS:
                _bad(f"{label}.selector must be at most {MAX_SELECTOR_CHARS} characters, "
                     f"got {len(selector)}")
        elif selector is not None:
            _bad(f"{label}.kind '{kind}' reads the page itself and accepts no selector")

        has_equals = "equals" in item
        has_contains = "contains" in item
        if has_equals == has_contains:
            _bad(f"{label} needs exactly one of 'equals' or 'contains'")
        key = "equals" if has_equals else "contains"
        expected = item[key]
        if kind == "count":
            if has_contains:
                _bad(f"{label}.kind 'count' compares a number, so it needs 'equals'")
            # bool is not a count: True == 1 must never satisfy an element count.
            if isinstance(expected, bool) or not isinstance(expected, int):
                _bad(f"{label}.equals must be a whole finite number for kind 'count', "
                     f"got {type(expected).__name__}")
            if not 0 <= expected <= MAX_COUNT:
                _bad(f"{label}.equals must be between 0 and {MAX_COUNT} for kind 'count'")
        else:
            if not isinstance(expected, str):
                _bad(f"{label}.{key} must be a string for kind '{kind}', "
                     f"got {type(expected).__name__}")
            if len(expected) > MAX_EXPECTED_CHARS:
                _bad(f"{label}.{key} must be at most {MAX_EXPECTED_CHARS} characters, "
                     f"got {len(expected)}")
            if has_contains and not expected:
                # An empty substring matches every page, so it asserts nothing.
                _bad(f"{label}.contains must not be empty")

        normalized.append({
            "id": identifier,
            "kind": kind,
            "selector": selector if kind in SELECTOR_KINDS else None,
            key: expected,
        })
    return normalized


# One synchronous read. Read-only by construction: it calls querySelectorAll,
# reads location, document.title, innerText, value and visibility, and nothing
# else. It never writes a property, never dispatches an event, and never
# navigates. Each check is wrapped in its own try/catch, so one invalid
# selector cannot erase the rows around it.
READ_SCRIPT = r"""(specs => {
  const LIMIT = %d;
  const visible = element => {
    if (typeof element.checkVisibility === 'function')
      return element.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
    const box = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return !!(box.width && box.height) && style.visibility !== 'hidden' &&
      style.display !== 'none' && style.opacity !== '0';
  };
  const rows = specs.map(spec => {
    try {
      if (spec.kind === 'url') return {available: true, value: location.href};
      if (spec.kind === 'title') return {available: true, value: document.title};
      const nodes = [...document.querySelectorAll(spec.selector)];
      if (spec.kind === 'count') return {available: true, value: nodes.length};
      if (nodes.length !== 1)
        return {available: false, reason: 'missing_or_ambiguous', matches: nodes.length};
      const element = nodes[0];
      const type = String(element.type || element.getAttribute('type') || '').toLowerCase();
      if (type === 'password') return {available: false, reason: 'sensitive_field'};
      if (spec.kind === 'value') {
        if (type === 'hidden') return {available: false, reason: 'hidden_field'};
        if (type === 'file') return {available: false, reason: 'unsupported_control'};
        const holder = ('value' in element) ? element.value : (element.isContentEditable ? element.innerText : null);
        if (typeof holder !== 'string') return {available: false, reason: 'not_a_field'};
        return {available: true, value: holder};
      }
      if (!visible(element)) return {available: false, reason: 'not_visible'};
      return {available: true, value: String(element.innerText)};
    } catch (error) {
      return {available: false, reason: 'unreadable_or_invalid_selector'};
    }
  }).map(row => (typeof row.value === 'string' && row.value.length > LIMIT)
    ? {available: false, reason: 'value_too_large', length: row.value.length}
    : row);
  return {url: location.href, title: document.title, at: Date.now(), rows: rows};
})""" % MAX_READ_CHARS


def read_expression(checks: Iterable[dict]) -> str:
    """The JavaScript expression that reads evidence for these checks.

    Only the kind and the selector cross into the page. The expectation stays
    in this process, so a hostile page cannot learn what is being asserted.
    json.dumps escapes every non-ASCII character, including U+2028 and U+2029,
    so the embedded literal is always a valid JavaScript expression.
    """
    specs = [{"kind": check["kind"], "selector": check["selector"]} for check in checks]
    return READ_SCRIPT + "(" + json.dumps(specs, ensure_ascii=True, allow_nan=False) + ")"


def summarize(rows: list) -> str:
    """passed only when every row passed; failed beats unknown; [] is not_run."""
    if not rows:
        return "not_run"
    statuses = {row.get("status") for row in rows}
    if "failed" in statuses:
        return "failed"
    return "passed" if statuses == {"passed"} else "unknown"


def tally(rows: list) -> dict:
    """Count passed/failed/unknown rows. Other statuses do not increment a bucket."""
    counts = {name: 0 for name in ROW_STATUSES}
    for row in rows:
        status = row.get("status") if isinstance(row, dict) else None
        if status in counts:
            counts[status] += 1
    return counts


def declaration_fingerprint(check: Any) -> str:
    """The fingerprint of one declared check: SHA-256 over canonical JSON.

    Both boundaries compute this from the same normalized declaration, before
    anything is serialized for transport, so the wrapper can match a returned
    row to the check it declared at that position without the row carrying a
    copy of the expectation. normalize_checks() runs first, so the input is
    validated and the digest cannot depend on key order, on a caller's extra
    key, or on a value the contract would have rejected.

    It detects a declaration that does not correspond to the caller's own, by
    accident or by a runner that mixed rows up. It is not a signature and it
    proves nothing about a runner that decides to lie: a deliberately
    dishonest runner holds the declaration and can recompute the digest.

    Raises CheckError when `check` is not a valid declaration.
    """
    canonical = json.dumps(
        normalize_checks([check])[0],
        sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _clean_text(value: str, redact: Callable[[str], str] | None, limit: int) -> dict:
    """Reported evidence: redacted first, then bounded, and honest about both."""
    text = redact(value) if redact is not None else value
    observed: dict = {"available": True, "value": text[:limit]}
    if len(text) > limit:
        observed["truncated"] = True
        observed["length"] = len(text)
    return observed


def _capture_text(value: str, redact: Callable[[str], str] | None, limit: int) -> tuple:
    """A page URL or title: truncated copy plus length/truncated/redacted flags.

    The stored string is never longer than limit. Metadata talks about the
    redacted text (the value that was considered for storage), not a discarded
    original, so an overlong raw value is not leaked. `length` is therefore
    what this process measured; the returned string is min(length, limit)
    characters unless a later pass redacts it again, and that pass adds its
    own `returned_length`.
    """
    text = redact(value) if redact is not None else value
    meta = {"length": len(text), "truncated": len(text) > limit}
    if redact is not None and text != value:
        meta["redacted"] = True
    return text[:limit], meta


def _unknown(row: dict, reason: str, extra: dict | None = None) -> dict:
    reason = reason if reason in REASONS else "evidence_unavailable"
    row["status"] = "unknown"
    row["reason"] = reason
    row["observed"] = {"available": False, "reason": reason}
    if extra:
        row["observed"].update(extra)
    return row


def _row(check: dict, fingerprint: Any, evidence: Any, fallback: str,
         captured_at_ms, redact) -> dict:
    row = {
        "id": check["id"],
        "kind": check["kind"],
        "status": "unknown",
        "reason": None,
        "boundary": BOUNDARY,
        # Which declaration this row answers. The declaration itself is never
        # echoed: the caller already has it, and a second copy would be a
        # second source of truth that a transport can rewrite.
        "fingerprint": fingerprint,
        "observed": None,
        "captured_at_ms": captured_at_ms,
    }
    if not isinstance(evidence, dict):
        return _unknown(row, fallback)
    if evidence.get("available") is not True or "value" not in evidence:
        extra = {}
        for field in ("matches", "length"):
            value = evidence.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                extra[field] = value
        return _unknown(row, str(evidence.get("reason")), extra)

    value = evidence["value"]
    if check["kind"] == "count":
        if isinstance(value, bool) or not isinstance(value, int):
            return _unknown(row, "evidence_type_mismatch")
        row["observed"] = {"available": True, "value": value}
        row["status"] = "passed" if value == check["equals"] else "failed"
        return row
    if not isinstance(value, str):
        return _unknown(row, "evidence_type_mismatch")
    # Compare the value the page returned; report a redacted, bounded copy.
    if "equals" in check:
        matched = value == check["equals"]
    else:
        matched = check["contains"] in value
    row["observed"] = _clean_text(value, redact, MAX_REPORTED_CHARS)
    row["status"] = "passed" if matched else "failed"
    return row


def verification_payload(
    checks: Iterable[dict],
    payload: Any = None,
    reason: str = "evidence_unavailable",
    redact: Callable[[str], str] | None = None,
) -> dict:
    """The result's `verification` object for these checks and this read.

    payload is the object returned by read_expression's script, or None when
    the read could not run; then every declared check is reported unknown with
    `reason`. No declared check at all is "not_run".
    """
    checks = list(checks or [])
    url = title = None
    url_meta = title_meta = None
    captured_at_ms = None
    consistency = NOT_READ
    evidence: list = [None] * len(checks)

    if checks and isinstance(payload, dict):
        rows = payload.get("rows")
        if isinstance(rows, list) and len(rows) == len(checks):
            evidence = rows
            consistency = SINGLE_READ
            raw_at = payload.get("at")
            if isinstance(raw_at, (int, float)) and not isinstance(raw_at, bool):
                captured_at_ms = int(raw_at)
            else:
                captured_at_ms = round(time.time() * 1000)
            if isinstance(payload.get("url"), str):
                url, url_meta = _capture_text(
                    payload["url"], redact, MAX_REPORTED_URL_CHARS)
            if isinstance(payload.get("title"), str):
                title, title_meta = _capture_text(
                    payload["title"], redact, MAX_REPORTED_CHARS)

    rows = []
    for check, item in zip(checks, evidence):
        try:
            fingerprint = declaration_fingerprint(check)
        except Exception:  # not a declaration this contract can name
            fingerprint = None
        try:
            rows.append(_row(check, fingerprint, item, reason, captured_at_ms, redact))
        except Exception:  # one malformed row never erases the others
            rows.append({
                "id": check.get("id"), "kind": check.get("kind"), "status": "unknown",
                "reason": "evidence_unavailable", "boundary": BOUNDARY,
                "fingerprint": fingerprint,
                "observed": {"available": False, "reason": "evidence_unavailable"},
                "captured_at_ms": captured_at_ms,
            })
    capture_metadata = None
    if url_meta is not None or title_meta is not None:
        capture_metadata = {"url": url_meta, "title": title_meta}
    return {
        "status": summarize(rows),
        "scope": SCOPE,
        "boundary": BOUNDARY,
        "declared": len(checks),
        "counts": tally(rows),
        "checked_at_url": url,
        "checked_at_title": title,
        "capture_metadata": capture_metadata,
        "captured_at_ms": captured_at_ms,
        # Every row comes from one synchronous read of one document, so the
        # rows agree with each other and with checked_at_url. They are a
        # snapshot after execution, not a per-action assertion: a later
        # navigation or script can change the page they describe.
        "consistency": consistency,
        "note": NOTE,
        "checks": rows,
    }
