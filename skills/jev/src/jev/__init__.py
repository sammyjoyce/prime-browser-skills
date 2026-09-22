"""jev - Prime Agent skill that drives a dedicated Chrome with the pinned
jev-ultrafast agent, through a separate Python 3.12 runtime project.

    result = await jev.run(task, url, profile="default", max_steps=25,
                           timeout_ms=120_000, max_cost_usd=0.5,
                           values=None, generation=None, checks=None)
    result = await jev.login(profile="default", url="https://example.com",
                             timeout_ms=600_000)

jev executes browser actions. It does not extract typed answers (no schema
argument) and it never verifies the goal: output["verification"] is always
"not_performed" and an upstream DONE only sets output["completion_claimed"].

Declared DOM checks: checks=[{"id": "saved", "kind": "text",
"selector": "#status", "equals": "Saved"}] asks for read-only evidence from
the page the browser ends on. Each check has an id (defaults to
"check[<index>]"), a kind, a selector for the kinds that need one, and exactly
one of equals or contains:

    kind     reads                               selector   expectation
    url      location.href                       no         equals/contains
    title    document.title                      no         equals/contains
    text     innerText of one visible element    yes        equals/contains
    value    value of one input/textarea/select  yes        equals/contains
    count    number of matching elements         yes        equals (whole number)

At most 20 checks; ids at most 100 characters, selectors 1000, expectations
2000. An unknown key, a missing or duplicate id, a bool or non-finite count, a
selector on url/title, both or neither of equals/contains, or an empty
contains is rejected with JevValidationError before any process starts, and
the runtime validates the same request again. Only the kind and the selector
are sent into the page; the expectation is never sent into it, and every
comparison happens in the runtime process.

The checks run once, after execution and before teardown, in one synchronous
read, and they are read-only: no click, no typing, no navigation. They add
result["verification"], a separate object from output["verification"]:

    {"status": "passed"|"failed"|"unknown"|"not_run",
     "scope": "declared_dom_checks_only", "boundary": "browser_dom",
     "declared": 2, "counts": {"passed": 1, "failed": 0, "unknown": 1},
     "checked_at_url": ..., "checked_at_title": ...,
     "capture_metadata": {"url"|"title": {"length", "truncated", "redacted"?,
                                          "returned_length"?}} | null,
     "captured_at_ms": ...,
     "consistency": "single_synchronous_read", "note": ...,
     "checks": [{"id", "kind", "status", "reason", "boundary", "fingerprint",
                 "observed", "captured_at_ms"}, ...]}

status is "failed" only for an observed mismatch. Missing, ambiguous,
invisible, refused or unreadable evidence is "unknown", and no declared check
is "not_run". A failed or unknown check does not change the run's status:
"completed" still means the executor claimed completion, never a verified
goal, and a passing check is DOM evidence at one instant, not proof that a
server stored anything. A password input is refused (reason
"sensitive_field") and its value is never returned; type=hidden and file
inputs are refused too. Observed values for text, value, count and url checks
are returned, redacted for known secret environment values and truncated at
2000 characters, so a check you declare can put page content in the result.
checked_at_url is truncated at 2048 characters and checked_at_title at 2000;
those two fields stay strings, and capture_metadata records length, whether
either was cut, whether redaction changed the text, and then the
returned_length that redaction produced. The discarded tail is not stored
anywhere in the payload.

Your declaration is not echoed back. Each row carries "fingerprint", the
SHA-256 of the normalized check it answers, and the wrapper rejects a result
whose ordered row fingerprints are not the ones it declared. Rows come back in
declaration order, so row i answers checks[i]. A row "id" is a display label:
it is the id you declared, except that the runner redacts its whole result, so
an id that looks like a credential comes back redacted.

Supplied values: values={"email": "dana@example.test"} binds exact strings to
fields. A bound value is copied into the field byte for byte, with no trimming
and no punctuation added, and "" clears the field. Every key, plus an 80-character
preview of each value, is sent to the decision model in state.supplied_values.
That preview is not a privacy bound: once a value is typed, the full value is
visible to the decision model too, in state.elements[].value and
state.recent_actions[].text. The bind_value() call also sends the field's
current value and recent action text in full, and the text helper sees the same
page text and recent actions when generation="helper". Never pass credentials or
private data in values. generation="helper" lets the small text helper write a
value for a field that no supplied value fits; generation="disabled" skips that
field and types nothing. generation defaults to "disabled" when values is given
and to "helper" otherwise. Each entry in result["actions"] reports value_key
and value_source ("supplied", "helper", "skipped" or null); the text that was
typed is never returned.

Result dict, always with the same keys: status ("completed" on success),
output, text, steps, cost (None means unknown, never a fake 0.0; a completed
login is 0 because it makes no model call), cost_detail, usage, model,
resolved_model, helper_model, duration_ms, stop_reason, warnings,
screenshot_path (run: an existing absolute PNG; login: always None),
verification (run: the declared-check object above, "not_run" when no check
was declared; login: None), artifact_dir, profile_dir, stderr_path. A
completed run's output carries final_url, final_title, page_text,
completion_claimed and verification; a completed login's output carries
authenticated (always None) and verification.
Every non-completed status raises instead of returning:
JevError(status, message, result), plus JevValidationError (bad arguments,
also a ValueError), JevTimeoutError, JevProtocolError (the runner broke the
result contract) and JevProfileInUseError.

Storage (JEV_HOME overrides, default ~/.prime/agent/jev), directories 0700
and files 0600: profiles/<profile>/ is the dedicated Chrome user-data-dir and
persists cookies and localStorage but not open tabs; profiles/<profile>.lock
is a cross-session flock held from before launch until the whole process tree
is gone; artifacts/<op>-<utc>-<id>/ holds per-run artifacts including
runner.stderr.log. A symlinked profile path is refused, because it could aim
the dedicated Chrome at the user's own profile.

Process model: the runtime is a separate uv project with its own Python 3.12
interpreter and pinned upstream code, set up once with

    cd <skill> && uv sync --project runtime --frozen

That interpreter is then launched directly, with no shell and no uv in the
process tree, as `<skill>/runtime/.venv/bin/python <skill>/runtime/runner.py`
with start_new_session=True, so the runner itself leads the process group and
must keep Chrome and the browser-harness daemon inside it. Exactly one JSON
request goes to its stdin; exactly one JSON result object is read from its
stdout; stderr goes to a file, never a pipe. The whole group gets SIGTERM and
then an unconditional SIGKILL on timeout, cancellation or failure, and is
swept again after a clean exit; only then is the profile lock released.
timeout_ms is the runner's own budget: the outer watchdog fires at
timeout_ms + 45s, leaving it a bounded allowance to stop, capture artifacts
and tear the browser down.

Child environment: the parent environment is copied, browser-attach and
browser-harness variables are dropped (a stray BU_CDP_URL must never point
the agent at the user's daily Chrome), and DO_NOT_TRACK=1,
ANONYMIZED_TELEMETRY=false, BH_TELEMETRY=0 are set. os.environ itself is
never modified. OPENROUTER_API_KEY is the only credential the runtime needs,
and values of env vars named like API_KEY/TOKEN/SECRET/PASSWORD (length >= 8)
are replaced with "[REDACTED]" in messages, text, page_text, declared-check
evidence and error fields.
The environment is never dumped anywhere.

Importing this module has no side effects; nothing is created on disk until
run() or login() is called.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import signal
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, NoReturn

from .checks import BOUNDARY as CHECK_BOUNDARY
from .checks import CONSISTENCY as CHECK_CONSISTENCY
from .checks import FINGERPRINT_CHARS, CheckError, declaration_fingerprint, normalize_checks, summarize, tally
from .checks import NOTE as CHECK_NOTE
from .checks import ROW_STATUSES as CHECK_ROW_STATUSES
from .checks import SCOPE as CHECK_SCOPE
from .checks import STATUSES as CHECK_STATUSES

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None  # type: ignore[assignment]

__version__ = "0.1.0"

__all__ = [
    "run",
    "login",
    "JevError",
    "JevValidationError",
    "JevTimeoutError",
    "JevProtocolError",
    "JevProfileInUseError",
    "DEFAULT_HOME",
    "VERIFICATION",
    "CHECK_SCOPE",
    "CHECK_BOUNDARY",
    "CHECK_STATUSES",
]

DEFAULT_HOME = "~/.prime/agent/jev"

# Honest-reporting constant: this wrapper never claims the goal was verified.
VERIFICATION = "not_performed"

# Outer watchdog: extra seconds beyond timeout_ms before the runner's process
# group is torn down (covers interpreter startup and the runner's own
# timeout handling, screenshot capture and browser teardown).
_CLEANUP_ALLOWANCE_S = 45.0
_SIGTERM_GRACE_S = 10.0
_SIGKILL_GRACE_S = 5.0
_SPAWN_GRACE_S = 5.0
# login never calls a model; neutral no-op limits keep the request shape fixed.
_LOGIN_NEUTRAL_LIMIT = 1_000_000

# Finite input limits (a request must never be unbounded).
_MAX_TASK_CHARS = 20_000
_MAX_URL_CHARS = 2_048
_MAX_STEPS = 500
_MAX_TIMEOUT_MS = 86_400_000  # 24 hours
_MAX_COST_USD = 100.0
_MAX_VALUES = 20
_MAX_VALUE_CHARS = 2_000
_GENERATION = ("helper", "disabled")

_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_VALUE_KEY_RE = re.compile(r"\A[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_SECRET_NAME_RE = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)
_REDACTED = "[REDACTED]"
_STDOUT_SNIPPET_CHARS = 2000
_STDERR_SNIPPET_CHARS = 1500
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Dropped from the child environment: an inherited CDP endpoint would attach
# the agent to an already running browser (possibly the user's own Chrome),
# and inherited browser-harness locations would share state between runs.
_DROPPED_ENV_VARS = (
    "BU_CDP_URL", "BU_CDP_WS", "BROWSER_USE_CDP_URL", "CDP_URL", "CHROME_CDP_URL",
)
_DROPPED_ENV_PREFIXES = ("BH_",)
_FORCED_ENV = {
    "DO_NOT_TRACK": "1",
    "ANONYMIZED_TELEMETRY": "false",
    "BH_TELEMETRY": "0",
}

# Result keys this wrapper owns; a runner value never overwrites them.
_OWNED_RESULT_KEYS = ("status", "error", "artifact_dir", "profile_dir", "stderr_path")


# --- Errors ---

class JevError(Exception):
    """Typed failure. Attributes: status (str), message (str), result (dict|None)."""

    def __init__(self, status: str, message: str, result: dict | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.result = result

    def __str__(self) -> str:  # keep repr/str free of secrets
        return f"jev error [{self.status}]: {self.message}"


class JevValidationError(JevError, ValueError):
    """Invalid arguments to run()/login(). Also catchable as ValueError."""


class JevTimeoutError(JevError):
    """Runner exceeded timeout_ms (outer watchdog) or self-reported a timeout."""


class JevProtocolError(JevError):
    """Runner stdout was not exactly one JSON result object obeying the contract."""


class JevProfileInUseError(JevError):
    """Another session/process currently holds this profile's flock."""


# --- Redaction and diagnostics helpers ---

def _redact(text: str) -> str:
    """Replace values of secret-looking env vars (len >= 8) with a placeholder.

    Only values are matched; variable names are never returned or logged.
    """
    if not text:
        return text
    for name, value in os.environ.items():
        if len(value) >= 8 and value in text and _SECRET_NAME_RE.search(name):
            text = text.replace(value, _REDACTED)
    return text


def _snippet(text: str, limit: int = _STDOUT_SNIPPET_CHARS) -> str:
    return text[-limit:] if text else ""


def _read_tail(path: Path) -> str:
    try:
        return path.read_bytes()[-_STDERR_SNIPPET_CHARS:].decode("utf-8", "replace")
    except OSError:
        return ""


# --- Validation ---

def _invalid(message: str) -> NoReturn:
    raise JevValidationError("invalid_input", message, None)


def _validate_task(task: Any) -> str:
    if not isinstance(task, str) or not task.strip():
        _invalid(f"task must be a nonempty string, got {task!r}")
    if len(task) > _MAX_TASK_CHARS:
        _invalid(f"task must be at most {_MAX_TASK_CHARS} characters, got {len(task)}")
    return task


def _validate_profile(profile: Any) -> str:
    if not isinstance(profile, str) or not _PROFILE_NAME_RE.match(profile):
        _invalid("profile must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}, got " + repr(profile))
    return profile


def _validate_url(url: Any) -> str:
    """Require a real, absolute http(s) URL with a host and a usable port."""
    if not isinstance(url, str):
        _invalid(f"url must be an http:// or https:// string, got {url!r}")
    candidate = url.strip()
    if not candidate:
        _invalid("url must be a nonempty http:// or https:// URL")
    if len(candidate) > _MAX_URL_CHARS:
        _invalid(f"url must be at most {_MAX_URL_CHARS} characters, got {len(candidate)}")
    if any(character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
           for character in candidate):
        _invalid(f"url must not contain whitespace or control characters, got {url!r}")
    try:
        parts = urllib.parse.urlsplit(candidate)
    except ValueError as exc:
        _invalid(f"url could not be parsed ({exc}), got {url!r}")
    if parts.scheme.lower() not in ("http", "https"):
        _invalid(f"url must be an http:// or https:// URL, got {url!r}")
    if not parts.netloc or not parts.hostname:
        _invalid(f"url must include a host, got {url!r}")
    try:
        parts.port  # raises ValueError on a malformed port
    except ValueError:
        _invalid(f"url has an invalid port, got {url!r}")
    return candidate


def _validate_values(values: Any) -> dict | None:
    """None, or an exact copy of the caller's field values.

    Nothing is trimmed, reformatted or dropped, and "" is a real value meaning
    clear that field. Error messages carry types and lengths, never the values.
    """
    if values is None:
        return None
    if not isinstance(values, dict):
        _invalid(f"values must be a dict of strings or None, got {type(values).__name__}")
    if len(values) > _MAX_VALUES:
        _invalid(f"values must have at most {_MAX_VALUES} entries, got {len(values)}")
    for key, value in values.items():
        if not isinstance(key, str) or not _VALUE_KEY_RE.match(key):
            _invalid("values keys must match [A-Za-z][A-Za-z0-9_]{0,63}, got " + repr(key))
        if key == "NONE":
            _invalid("values keys must not be 'NONE'; that name is reserved for the no-value choice")
        if not isinstance(value, str):
            _invalid(f"values[{key!r}] must be a string, got {type(value).__name__}")
        if len(value) > _MAX_VALUE_CHARS:
            _invalid(
                f"values[{key!r}] must be at most {_MAX_VALUE_CHARS} characters, got {len(value)}"
            )
    return dict(values)


def _validate_generation(generation: Any, values: dict | None) -> str:
    """Supplied values turn the text helper off unless the caller asks for it."""
    if generation is None:
        return "disabled" if values else "helper"
    if generation not in _GENERATION:
        _invalid(f"generation must be 'helper', 'disabled' or None, got {generation!r}")
    return generation


def _validate_checks(value: Any) -> list:
    """Declared DOM checks, normalized, or []. Rejected before anything starts.

    The contract lives in jev/checks.py and the runtime re-validates the same
    request with the same function, so the two boundaries cannot drift. The
    returned list is a private snapshot: a caller that mutates its own dicts
    afterwards cannot change what the runner receives.
    """
    try:
        return normalize_checks(value)
    except CheckError as exc:
        _invalid(str(exc))


def _validate_number(value: Any, name: str, maximum: float, whole: bool = False) -> float:
    """Positive, finite, bounded; bools are never numbers here."""
    kind = "integer" if whole else "finite number"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _invalid(f"{name} must be a positive {kind}, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        _invalid(f"{name} must be a positive {kind}, got {value!r}")
    if whole and not float(value).is_integer():
        _invalid(f"{name} must be a positive {kind}, got {value!r}")
    if value > maximum:
        _invalid(f"{name} must be at most {maximum:g}, got {value!r}")
    return int(value) if whole else value


# --- Paths, runtime launch command and permissions ---

def _home_dir() -> Path:
    raw = os.environ.get("JEV_HOME") or DEFAULT_HOME
    return Path(raw).expanduser().resolve()


def _skill_root() -> Path:
    # src/jev/__init__.py -> <skill root>
    return Path(__file__).resolve().parents[2]


def _runtime_dir() -> Path:
    return _skill_root() / "runtime"


def _runner_path() -> Path:
    return _runtime_dir() / "runner.py"


def _runtime_python() -> Path:
    return _runtime_dir() / ".venv" / "bin" / "python"


def _launch_command() -> list[str]:
    """argv for the runtime's own installed interpreter.

    Launching it directly (instead of through `uv run`) keeps the runner
    itself the leader of the process group this wrapper signals. `uv sync`
    stays a one-time setup step that creates this interpreter.
    """
    runner = _runner_path()
    python = _runtime_python()
    setup = f"run `uv sync --project {_runtime_dir()} --frozen` to install it"
    if not runner.is_file():
        raise JevError("launch_error", f"jev runtime runner not found at {runner}; {setup}", None)
    if not os.access(python, os.X_OK):
        raise JevError(
            "launch_error", f"jev runtime interpreter not found at {python}; {setup}", None
        )
    return [str(python), str(runner)]


def _child_env() -> dict[str, str]:
    """A private copy of the environment. os.environ is never modified."""
    env = {key: value for key, value in os.environ.items()
           if key not in _DROPPED_ENV_VARS
           and not key.startswith(_DROPPED_ENV_PREFIXES)}
    env.update(_FORCED_ENV)
    return env


def _reject_symlink(path: Path, what: str) -> None:
    """A symlinked profile path could aim the dedicated Chrome at the user's
    own profile, so it is refused instead of followed."""
    if path.is_symlink():
        raise JevError(
            "profile_error", f"{what} must be a real directory, not a symlink: {path}", None
        )


def _ensure_private_dir(path: Path) -> None:
    """Create path (and missing ancestors) with 0700; leave existing dirs alone."""
    missing: list[Path] = []
    cursor = Path(path)
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        try:
            os.chmod(directory, 0o700)
        except OSError:
            pass


# --- Profile lock (flock: cross-process and cross-session) ---

def _acquire_profile_lock(lock_path: Path, profile: str) -> int:
    if fcntl is None:  # pragma: no cover - non-POSIX
        raise JevError("launch_error", "profile locking requires fcntl (POSIX)", None)
    _ensure_private_dir(lock_path.parent)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        raise JevProfileInUseError(
            "profile_in_use",
            _redact(f"profile '{profile}' is in use by another run (lock held: {lock_path})"),
            {"profile": profile, "lock_path": str(lock_path)},
        ) from exc
    try:  # best-effort holder info for debugging
        os.ftruncate(fd, 0)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        os.write(fd, f"pid={os.getpid()} time={stamp}\n".encode())
        os.fsync(fd)
    except OSError:
        pass
    return fd


def _release_profile_lock(fd: int | None) -> None:
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


# --- Subprocess lifecycle ---

def _close_proc_streams(proc: asyncio.subprocess.Process | None) -> None:
    if proc is None:
        return
    for stream in (proc.stdin, proc.stdout):
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def _signal_group(proc: asyncio.subprocess.Process, sig: int) -> None:
    """Signal the runner's whole process group. The runner is a session leader
    (start_new_session=True), so pgid == pid, and killpg still reaches Chrome
    and the browser-harness daemon after the leader itself has exited."""
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _probe(send, target: int) -> bool:
    """True when the pid or process group still exists."""
    try:
        send(target, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # alive, just not ours to signal
    except OSError:
        return False
    return True


def _alive(pid: int) -> bool:
    return _probe(os.kill, pid)


def _group_alive(proc: asyncio.subprocess.Process) -> bool:
    return _probe(os.killpg, proc.pid)


async def _shutdown(proc: asyncio.subprocess.Process) -> None:
    """Tear down the runner's whole process tree. The leader may already have
    exited (returncode set) while Chrome or the harness daemon still hold the
    profile, so the group is always signaled: SIGTERM, a bounded wait, then an
    unconditional group SIGKILL for SIGTERM-ignoring stragglers."""
    _signal_group(proc, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), timeout=_SIGTERM_GRACE_S)
    except asyncio.TimeoutError:
        pass
    _signal_group(proc, signal.SIGKILL)
    try:
        await asyncio.wait_for(proc.wait(), timeout=_SIGKILL_GRACE_S)
    except asyncio.TimeoutError:
        pass  # asyncio's child watcher still reaps
    _close_proc_streams(proc)


async def _spawn_runner(argv: list[str], stderr_fh, env: dict) -> asyncio.subprocess.Process:
    """Spawn the runner so cancellation cannot leak it: the creation future is
    shielded; if the caller is cancelled mid-creation and the process was
    nevertheless created, it is adopted and terminated before propagating.
    OSError (missing interpreter, etc.) propagates to the caller."""
    create = asyncio.ensure_future(
        asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=stderr_fh,
            env=env,
            start_new_session=True,
        )
    )
    try:
        return await asyncio.shield(create)
    except asyncio.CancelledError:
        # Cancelled mid-creation: give the in-flight creation a real, bounded
        # window (enforced by wait_for, not just a loop condition) to hand the
        # process over, so an already-forked runner is killed, never leaked.
        proc = None
        deadline = time.monotonic() + _SPAWN_GRACE_S
        while not create.done():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(asyncio.shield(create), remaining)
            except asyncio.TimeoutError:
                break
            except asyncio.CancelledError:
                continue  # repeated cancel: keep waiting out the window
            except Exception:
                break  # creation failed; nothing to kill
        if create.done():
            try:
                proc = create.result()
            except BaseException:
                proc = None  # creation failed; nothing to kill
        else:
            create.cancel()  # bounded give-up; fork races are pathological
        await _terminate_guarded(proc)
        raise


async def _terminate_guarded(proc: asyncio.subprocess.Process | None) -> None:
    """Kill and reap the runner tree even if the caller keeps getting cancelled.

    The profile lock must not be released while anything may still hold the
    profile, so repeated CancelledErrors are absorbed until _shutdown finishes.
    _shutdown is already bounded end to end (SIGTERM, a grace window, an
    unconditional group SIGKILL, then a reap window), so no second deadline is
    imposed here: a competing deadline could cancel _shutdown while it is
    still inside the SIGTERM grace window, i.e. before SIGKILL is ever
    delivered, stranding a process group that still holds the profile.
    """
    if proc is None:
        return
    cleanup = asyncio.ensure_future(_shutdown(proc))
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            continue  # absorb: the bounded shutdown must run to completion
        except Exception:
            break  # shutdown itself failed; the caller's error still wins
    if cleanup.done() and not cleanup.cancelled():
        cleanup.exception()  # retrieve so asyncio never logs it as unhandled


# --- Result parsing and normalization ---

def _base_result(status: Any, artifact_dir: Path, profile_dir: Path, stderr_path: Path) -> dict:
    return {
        "status": status,
        "output": None,
        "text": "",
        "steps": None,
        "cost": None,
        "cost_detail": None,
        "usage": None,
        "model": None,
        "resolved_model": None,
        "helper_model": None,
        "duration_ms": None,
        "stop_reason": None,
        "warnings": [],
        "screenshot_path": None,
        # Structured, caller-declared DOM evidence. Separate from
        # output["verification"], which stays the honesty constant.
        "verification": None,
        "artifact_dir": str(artifact_dir),
        "profile_dir": str(profile_dir),
        "stderr_path": str(stderr_path),
    }


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


# Runner field -> (accepts, description). Anything may also be null.
_FIELD_RULES = {
    "text": (lambda v: isinstance(v, str), "a string"),
    "steps": (lambda v: isinstance(v, int) and not isinstance(v, bool), "an integer"),
    "cost": (lambda v: _is_number(v) and math.isfinite(v) and v >= 0,
             "a finite non-negative number"),
    "duration_ms": (_is_number, "a number"),
    "output": (lambda v: isinstance(v, dict), "an object"),
    "warnings": (lambda v: isinstance(v, list) and all(isinstance(i, str) for i in v),
                 "a list of strings"),
    "screenshot_path": (lambda v: isinstance(v, str) and os.path.isabs(v),
                        "an absolute path"),
    "model": (lambda v: isinstance(v, str), "a string"),
    "resolved_model": (lambda v: isinstance(v, str), "a string"),
    "helper_model": (lambda v: isinstance(v, str), "a string"),
    "stop_reason": (lambda v: isinstance(v, str), "a string"),
    "verification": (lambda v: isinstance(v, dict), "an object"),
}


def _redact_verification(payload: Any) -> Any:
    """Redact known secret values inside declared-check evidence.

    The runtime redacts the same strings with the same rule; doing it again
    here keeps the wrapper's stated contract true for every text field it
    returns, and redaction is idempotent.

    capture_metadata.length and .truncated are the runtime's measurement of
    the text it considered for storage. When this second pass changes the
    stored string, that measurement no longer describes what the caller
    receives, so the field also records returned_length, the length of the
    string actually in the result.
    """
    if not isinstance(payload, dict):
        return payload
    meta = payload.get("capture_metadata")
    meta = meta if isinstance(meta, dict) else None
    for key, meta_key in (("checked_at_url", "url"), ("checked_at_title", "title")):
        if isinstance(payload.get(key), str):
            before = payload[key]
            payload[key] = _redact(before)
            if payload[key] != before and isinstance(meta, dict):
                field = meta.get(meta_key)
                if isinstance(field, dict):
                    field["redacted"] = True
                    field["returned_length"] = len(payload[key])
    rows = payload.get("checks")
    if isinstance(rows, list):
        for row in rows:
            observed = row.get("observed") if isinstance(row, dict) else None
            if isinstance(observed, dict) and isinstance(observed.get("value"), str):
                observed["value"] = _redact(observed["value"])
    return payload


def _counts_match(got: Any, expected: dict) -> bool:
    """True when counts is exactly the tally, with real ints (not bools)."""
    if not isinstance(got, dict) or set(got) != set(expected):
        return False
    for key, want in expected.items():
        value = got[key]
        if isinstance(value, bool) or not isinstance(value, int) or value != want:
            return False
    return True


def _is_fingerprint(value: Any) -> bool:
    """A SHA-256 hex digest as declaration_fingerprint() writes it."""
    return (isinstance(value, str) and len(value) == FINGERPRINT_CHARS
            and all(character in "0123456789abcdef" for character in value))


def _check_verification(op: str, checks: list, result: dict, protocol_error) -> None:
    """The runner's verification object must describe exactly the declared checks.

    This is protocol consistency, not a proof that the browser told the truth:
    every row must be a dict whose fingerprint is declaration_fingerprint() of
    the normalized declaration at that index, whose kind and boundary are the
    declared kind and "browser_dom", and whose status is passed, failed or
    unknown; declared is the integer length; counts tally the rows; aggregate
    status equals summarize(rows); scope, boundary, note and consistency are
    the contract's own constants. Zero checks allow only a missing object, or
    not_run with empty rows.

    Identity is the fingerprint, not the row's `id`. The runner emits its whole
    result through one redaction pass, so a caller whose id or expectation
    looks like a credential gets a rewritten id back; the fingerprint is a hex
    digest computed before transport and no credential pattern can match it.
    That also means a row `id` is a display label here: a runner that rewrites
    one cannot be told apart from redaction, while a row that answers a
    declaration the caller never made is rejected by its fingerprint.

    _FIELD_RULES already rejects a non-object, non-null verification value, so
    this function does not repeat that type check. It runs for every parsed
    result, including non-completed statuses. A failed or unknown check never
    changes the run's status: `completed` stays an executor claim.
    """
    checks = list(checks or [])
    declared = len(checks)
    payload = result.get("verification")
    if payload is None:
        if declared:
            protocol_error(
                f"run declared {declared} DOM check(s) but returned no verification object"
            )
        return
    status = payload.get("status")
    if status not in CHECK_STATUSES:
        protocol_error(
            "verification.status must be one of " + ", ".join(CHECK_STATUSES) + f", got {status!r}"
        )
    if payload.get("scope") != CHECK_SCOPE:
        protocol_error(f"verification.scope must be {CHECK_SCOPE!r}, got {payload.get('scope')!r}")
    if payload.get("boundary") != CHECK_BOUNDARY:
        protocol_error(
            f"verification.boundary must be {CHECK_BOUNDARY!r}, got {payload.get('boundary')!r}"
        )
    if payload.get("consistency") not in CHECK_CONSISTENCY:
        protocol_error(
            "verification.consistency must be one of " + ", ".join(CHECK_CONSISTENCY)
            + f", got {payload.get('consistency')!r}"
        )
    if payload.get("note") != CHECK_NOTE:
        # Bounded: the note is a sentence, and a forged one may be anything.
        protocol_error(
            "verification.note must be the declared-check contract note, got "
            f"{repr(payload.get('note'))[:80]}"
        )
    rows = payload.get("checks")
    if not isinstance(rows, list) or len(rows) != declared:
        count = len(rows) if isinstance(rows, list) else None
        protocol_error(
            f"verification must report one row per declared check ({declared}), got {count!r}"
        )
    if op == "login" and status != "not_run":
        protocol_error(
            "login declares no DOM check, so verification.status must be 'not_run', "
            f"got {status!r}"
        )
    if declared and status == "not_run":
        protocol_error(f"verification.status is 'not_run' but {declared} check(s) were declared")
    if not declared and status != "not_run":
        protocol_error(
            f"verification.status must be 'not_run' with no declared check, got {status!r}"
        )
    got_declared = payload.get("declared")
    if isinstance(got_declared, bool) or not isinstance(got_declared, int) or got_declared != declared:
        protocol_error(
            f"verification.declared must be the integer {declared}, got {got_declared!r}"
        )
    for index, (row, check) in enumerate(zip(rows, checks)):
        label = f"verification.checks[{index}]"
        if not isinstance(row, dict):
            protocol_error(f"{label} must be an object, got {type(row).__name__}")
        fingerprint = row.get("fingerprint")
        if not _is_fingerprint(fingerprint):
            protocol_error(
                f"{label}.fingerprint is missing or is not a declaration fingerprint"
            )
        if fingerprint != declaration_fingerprint(check):
            protocol_error(
                f"{label}.fingerprint does not name the check declared at that position "
                f"(kind={check['kind']!r})"
            )
        if row.get("kind") != check["kind"]:
            protocol_error(
                f"{label}.kind must be the declared kind {check['kind']!r}, "
                f"got {row.get('kind')!r}"
            )
        if not isinstance(row.get("id"), str):
            # A label, not an identity: redaction may rewrite it, but a
            # redacted string is still a string.
            protocol_error(
                f"{label}.id must be a string label, got {type(row.get('id')).__name__}"
            )
        if row.get("boundary") != CHECK_BOUNDARY:
            protocol_error(
                f"{label}.boundary must be {CHECK_BOUNDARY!r}, got {row.get('boundary')!r}"
            )
        row_status = row.get("status")
        if row_status not in CHECK_ROW_STATUSES:
            protocol_error(
                f"{label}.status must be one of " + ", ".join(CHECK_ROW_STATUSES)
                + f", got {row_status!r}"
            )
    expected_counts = tally(rows)
    got_counts = payload.get("counts")
    if not _counts_match(got_counts, expected_counts):
        protocol_error(
            "verification.counts must tally row statuses "
            f"{expected_counts}, got {got_counts!r}"
        )
    expected_status = summarize(rows)
    if status != expected_status:
        protocol_error(
            f"verification.status must equal summarize(rows) ({expected_status!r}), "
            f"got {status!r}"
        )


def _finish_result(
    op: str,
    stdout: bytes | None,
    returncode: int | None,
    artifact_dir: Path,
    profile_dir: Path,
    stderr_path: Path,
    checks: list | None = None,
) -> dict:
    """Parse, type-check and normalize the runner's single stdout JSON object."""
    raw = (stdout or b"").decode("utf-8", "replace")
    result = _base_result("protocol", artifact_dir, profile_dir, stderr_path)

    def protocol_error(message: str) -> NoReturn:
        message = _redact(message)
        result["error"] = message
        raise JevProtocolError("protocol", message, result)

    try:
        obj = json.loads(raw.strip())
    except ValueError:
        obj = None
    if not isinstance(obj, dict) or not isinstance(obj.get("status"), str) or not obj["status"].strip():
        message = (f"runner stdout was not one JSON result object (exit code "
                   f"{returncode}); stdout tail: {_snippet(raw)!r}")
        stderr_tail = _read_tail(stderr_path)
        if stderr_tail:
            message += f"; stderr tail: {_snippet(stderr_tail)!r}"
        protocol_error(message)
    if returncode != 0:
        protocol_error(f"runner exited with code {returncode}; stdout tail: {_snippet(raw)!r}")

    for field, (accepts, description) in _FIELD_RULES.items():
        value = obj.get(field)
        if value is not None and not accepts(value):
            protocol_error(f"{field} must be {description} or null, got {value!r}")

    # Keep runner extras (metrics, deviations, ...) but own the normalized keys.
    result.update({key: value for key, value in obj.items() if key not in _OWNED_RESULT_KEYS})
    status = obj["status"].strip()
    output = obj.get("output")
    cost = obj.get("cost")
    result.update(
        status=status,
        text=_redact(obj.get("text") or ""),
        steps=obj.get("steps"),
        cost=float(cost) if cost is not None else None,
        output=dict(output) if output is not None else None,
        warnings=[_redact(item) for item in obj.get("warnings") or []],
        screenshot_path=obj.get("screenshot_path"),
        artifact_dir=str(artifact_dir),
        profile_dir=str(profile_dir),
        stderr_path=str(stderr_path),
    )
    result["verification"] = _redact_verification(result.get("verification"))
    # Correspondence runs before the non-completed raise and before the PNG
    # check, so a forged verification cannot hide behind max_steps, blocked,
    # or a missing screenshot, and a legitimate row survives a capture failure.
    _check_verification(op, checks or [], result, protocol_error)

    if status != "completed":
        error = obj.get("error")
        error = error.strip() if isinstance(error, str) else ""
        result["error"] = _redact(error or f"run ended with status '{status}'")
        error_class = JevTimeoutError if status == "timeout" else JevError
        raise error_class(status, result["error"], result)

    _check_completed(op, obj, result, protocol_error)
    return result


def _check_completed(op: str, obj: dict, result: dict, protocol_error) -> None:
    """Enforce the completion contract before a result is called 'completed'."""
    # Honesty: an upstream DONE is a claim, never a verified goal.
    if obj.get("verified"):
        protocol_error("runner claimed goal verification; jev never verifies the goal")
    raw_output = result["output"]
    output = dict(raw_output) if isinstance(raw_output, dict) else {}
    verification = output.get("verification", VERIFICATION)
    if verification != VERIFICATION:
        protocol_error(
            f"output.verification must be {VERIFICATION!r}, got {verification!r}"
        )
    output["verification"] = VERIFICATION

    if op == "login":
        # login opens a headed window only: no model call, no step, no capture.
        if result["screenshot_path"] is not None:
            protocol_error("login must not return a screenshot (it can show credentials)")
        if result["cost"] != 0:
            protocol_error(f"completed login must report cost 0, got {result['cost']!r}")
        if result["steps"] != 0:
            protocol_error(f"completed login must report steps 0, got {result['steps']!r}")
        if output.get("authenticated") is not None:
            protocol_error(
                f"login must report authenticated=null, got {output.get('authenticated')!r}"
            )
        output["authenticated"] = None
        result["output"] = output
        return

    if not raw_output:
        protocol_error("completed run must return a non-empty output object")
    for key in ("final_url", "final_title", "page_text", "completion_claimed"):
        if key not in output:
            protocol_error(f"completed run output is missing {key!r}")
    for key in ("final_url", "final_title"):
        if output[key] is not None and not isinstance(output[key], str):
            protocol_error(f"output.{key} must be a string or null, got {output[key]!r}")
    page_text = output["page_text"]
    if page_text is None:
        page_text = ""
    if not isinstance(page_text, str):
        protocol_error(f"output.page_text must be a string or null, got {page_text!r}")
    output["page_text"] = _redact(page_text)
    if output["completion_claimed"] is not True:
        protocol_error(
            "a completed run must claim completion, got "
            f"completion_claimed={output['completion_claimed']!r}"
        )
    result["output"] = output

    shot = result["screenshot_path"]
    problem = _png_problem(shot)
    if problem is not None:
        message = _redact(f"completed run did not produce a usable PNG screenshot: {problem}")
        result["status"] = "artifact_error"
        result["error"] = message
        raise JevError("artifact_error", message, result)


def _png_problem(path: Any) -> str | None:
    """None when path is an existing absolute file with a real PNG signature."""
    if path is None:
        return "screenshot_path is null"
    if not isinstance(path, str) or not os.path.isabs(path):
        return f"screenshot_path is not absolute: {path!r}"
    try:
        with open(path, "rb") as handle:
            head = handle.read(len(_PNG_MAGIC))
    except OSError as exc:
        return f"screenshot_path is not readable ({exc.__class__.__name__}): {path}"
    if head != _PNG_MAGIC:
        return f"screenshot is not a PNG (bad signature): {path}"
    return None


# --- Core invocation ---

async def _invoke_runner(
    op: str,
    task: str | None,
    url: str,
    profile: str,
    max_steps: int,
    timeout_ms: int,
    max_cost_usd: float,
    values: dict | None = None,
    generation: str | None = None,
    checks: list | None = None,
) -> dict:
    home = _home_dir()
    profiles_root = home / "profiles"
    _reject_symlink(profiles_root, "the profiles directory")
    _reject_symlink(profiles_root / profile, f"the '{profile}' profile directory")

    lock_path = profiles_root / f"{profile}.lock"
    lock_fd = _acquire_profile_lock(lock_path, profile)
    try:
        profile_dir = profiles_root / profile
        _ensure_private_dir(profile_dir)

        run_id = f"{op}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
        artifact_dir = home / "artifacts" / run_id
        _ensure_private_dir(artifact_dir)
        stderr_path = artifact_dir / "runner.stderr.log"

        def fail(status: str, message: str) -> NoReturn:
            message = _redact(message)
            result = _base_result(status, artifact_dir, profile_dir, stderr_path)
            result["error"] = message
            raise JevError(status, message, result)

        stderr_fh = None
        proc = None
        try:
            try:
                argv = _launch_command()
            except JevError as exc:
                fail(exc.status, exc.message)

            request = {
                "op": op,
                "run_id": run_id,
                "profile": profile,
                "task": task,
                "url": url,
                "profile_dir": str(profile_dir),
                "artifact_dir": str(artifact_dir),
                "max_steps": max_steps,
                "timeout_ms": timeout_ms,
                "max_cost_usd": max_cost_usd,
            }
            if op == "run":
                # login opens a window and types nothing, so its request is unchanged.
                request["values"] = values
                request["generation"] = generation
                # Already normalized and bounded; the runner validates it again.
                request["checks"] = checks or []

            fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            stderr_fh = os.fdopen(fd, "wb")

            try:
                try:
                    proc = await _spawn_runner(argv, stderr_fh, _child_env())
                except OSError as exc:
                    fail("launch_error", f"failed to launch the jev runtime interpreter: {exc}")

                payload = (json.dumps(request, allow_nan=False) + "\n").encode("utf-8")
                try:
                    proc.stdin.write(payload)
                    await proc.stdin.drain()
                    proc.stdin.close()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # runner died before reading; reported via exit code

                budget_s = timeout_ms / 1000.0 + _CLEANUP_ALLOWANCE_S
                try:
                    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=budget_s)
                except asyncio.TimeoutError:
                    await _terminate_guarded(proc)
                    message = _redact(
                        f"runner did not finish within timeout_ms={timeout_ms} "
                        f"(plus {_CLEANUP_ALLOWANCE_S:g}s cleanup allowance); "
                        "the process tree was terminated"
                    )
                    result = _base_result("timeout", artifact_dir, profile_dir, stderr_path)
                    result["error"] = message
                    raise JevTimeoutError("timeout", message, result) from None
                except asyncio.CancelledError:
                    await _terminate_guarded(proc)
                    raise

                result = _finish_result(
                    op, stdout, proc.returncode, artifact_dir, profile_dir, stderr_path,
                    checks or [],
                )
                # The runner exited and its result parsed, but Chrome or the
                # harness daemon could still be alive in its group. Nothing may
                # outlive the profile lock, so the same bounded teardown runs
                # on the success path too.
                leftovers = _group_alive(proc)
                await _terminate_guarded(proc)
                if leftovers:
                    result["warnings"].append(
                        "runner left processes running after it exited; they were "
                        "terminated before the profile lock was released"
                    )
                return result
            except BaseException:
                # Cancellation during spawn/drain, a launch error, or any other
                # failure: the runner tree must be dead and reaped before the
                # profile lock is released in the outer finally.
                await _terminate_guarded(proc)
                raise
        finally:
            if stderr_fh is not None:
                try:
                    stderr_fh.close()
                except OSError:
                    pass
            _close_proc_streams(proc)
    finally:
        _release_profile_lock(lock_fd)


# --- Public API ---

async def run(
    task: str,
    url: str,
    profile: str = "default",
    max_steps: int = 25,
    timeout_ms: float = 120_000,
    max_cost_usd: float = 0.5,
    values: dict | None = None,
    generation: str | None = None,
    checks: list | None = None,
) -> dict:
    """Run one agentic browser task from url; see the module docstring.

    max_cost_usd is a soft cap over the jev decision calls, the value-binding
    calls and the text helper calls. status is "completed" only when the runner
    finished, a native PNG exists and cleanup succeeded; every other status
    raises a typed JevError carrying the partial result.

    values maps a key to the exact string to type, at most 20 entries of at most
    2000 characters; "" clears the field. A bound value is typed byte for byte.
    The keys and an 80-character preview of each value are visible to the
    decision model in state.supplied_values, but that preview is not a privacy
    bound: the full value is visible too, once typed, in state.elements[].value
    and state.recent_actions[].text, and to the text helper when
    generation="helper". Never pass credentials or private data in values.
    generation is "helper" (the text helper may write a value no supplied value
    fits), "disabled" (skip that field) or None, which means "disabled" when
    values is given and "helper" otherwise.

    checks is an optional list of up to 20 read-only DOM checks, run once after
    execution and before teardown. They populate result["verification"] and
    change nothing else: status stays an executor claim, and
    output["verification"] stays "not_performed". See the module docstring for
    the check schema and the evidence limits.
    """
    task = _validate_task(task)
    url = _validate_url(url)
    profile = _validate_profile(profile)
    max_steps = _validate_number(max_steps, "max_steps", _MAX_STEPS, whole=True)
    timeout_ms = _validate_number(timeout_ms, "timeout_ms", _MAX_TIMEOUT_MS, whole=True)
    max_cost_usd = _validate_number(max_cost_usd, "max_cost_usd", _MAX_COST_USD)
    values = _validate_values(values)
    generation = _validate_generation(generation, values)
    checks = _validate_checks(checks)
    return await _invoke_runner(
        "run", task, url, profile, max_steps, timeout_ms, max_cost_usd, values, generation,
        checks,
    )


async def login(
    profile: str = "default",
    url: str = "https://example.com",
    timeout_ms: float = 600_000,
) -> dict:
    """Open a headed dedicated Chrome on url and wait for the user to finish.

    The user signs in (including MFA), then closes every window of that
    profile; cookies and localStorage persist, open tabs and page JavaScript
    state do not. No model call, no API key, no screenshot, and no claim that
    the login worked: output["authenticated"] is always None and cost is 0.
    Same result dict and error semantics as run().
    """
    profile = _validate_profile(profile)
    url = _validate_url(url)
    timeout_ms = _validate_number(timeout_ms, "timeout_ms", _MAX_TIMEOUT_MS, whole=True)
    return await _invoke_runner("login", None, url, profile, _LOGIN_NEUTRAL_LIMIT,
                                timeout_ms, float(_LOGIN_NEUTRAL_LIMIT))
