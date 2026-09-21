'''browser_use — Prime Agent skill that drives Chrome via the @browser_use/pi Node runner.

Public API (stdlib only; no third-party imports):

    result = await browser_use.run(
        task,                  # nonempty instruction string
        schema=None,           # JSON-schema dict OR pydantic model class (duck-typed
                               # via model_json_schema()) OR None
        profile="default",     # [A-Za-z0-9][A-Za-z0-9_-]{0,63}
        max_steps=25,          # positive int (bools rejected)
        timeout_ms=180_000,    # positive finite number, bools rejected
        max_cost_usd=1.0,      # positive finite number, bools rejected
    )
    result = await browser_use.login(
        profile="default",
        url="https://example.com",   # http/https URL; headed window, no model needed
        timeout_ms=600_000,
    )

Both return the runner result dict with at least:

    status            "completed" on success
    output            schema-validated answer (or None)
    text              final agent text (secret-redacted)
    steps             step count (int or None)
    cost              USD cost (float or None)
    screenshot_path   absolute PNG path or None
    artifact_dir      absolute per-run artifact directory
    stderr_path       absolute runner stderr log (extra key)
    error             present on every non-completed result

Failure mode: every non-completed status raises a typed error instead of returning:
    BrowserUseError(status, message, result)
        .status / .message / .result attributes; .result is the partial dict.
    BrowserUseValidationError   — bad arguments (also a ValueError)
    BrowserUseTimeoutError      — runner exceeded timeout_ms (or self-reported timeout)
    BrowserUseProtocolError     — runner stdout was not one JSON result object
    BrowserUseProfileInUseError — another run holds the profile lock

Storage layout (BROWSER_USE_HOME overrides, default ~/.prime/agent/browser-use):
    profiles/<profile>/          Chrome profile dir (persisted logins)
    profiles/<profile>.lock      cross-session flock held for the whole operation;
                                 auto-released by the OS if this process dies
    artifacts/<op>-<utc>-<id>/   per-run artifacts incl. runner.stderr.log
All created directories are chmod 0700 and files 0600.

Process model: `node runner.mjs` (skill root, resolved relative to __file__) is
spawned with start_new_session=True, no shell. Exactly one JSON request goes to
its stdin; exactly one JSON result object is read from stdout. stderr goes to a
file in the artifact dir, never a pipe. The child env gets DO_NOT_TRACK=1 and
BROWSER_USE_MODEL (default openai/gpt-6-astra). On timeout or
cancellation the whole process group gets SIGTERM, then bounded SIGKILL, then a
reap before the profile lock is released. Importing this module has no side
effects; nothing is created on disk until run()/login() is called.

Secret hygiene: values of env vars whose names match API_KEY/TOKEN/SECRET/PASSWORD
(length >= 8) are replaced with "[REDACTED]" in error messages, the error/text
result fields, and any stdout/stderr diagnostics. The environment is never
dumped into diagnostics.
'''

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import signal
import time
import uuid
from pathlib import Path
from typing import Any, NoReturn

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None  # type: ignore[assignment]

__version__ = "0.1.0"

__all__ = [
    "run",
    "login",
    "BrowserUseError",
    "BrowserUseValidationError",
    "BrowserUseTimeoutError",
    "BrowserUseProtocolError",
    "BrowserUseProfileInUseError",
    "DEFAULT_MODEL",
]

DEFAULT_MODEL = "openai/gpt-6-astra"
DEFAULT_HOME = "~/.prime/agent/browser-use"

# Extra seconds beyond timeout_ms before the outer watchdog SIGTERMs the runner
# process group (covers runner startup plus its own timeout handling/teardown).
_CLEANUP_ALLOWANCE_S = 45.0
_SIGTERM_GRACE_S = 10.0
_SIGKILL_GRACE_S = 5.0
_SPAWN_GRACE_S = 5.0
# login never uses the model; neutral no-op limits sent to keep the request shape.
_LOGIN_NEUTRAL_LIMIT = 1_000_000

_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SECRET_NAME_RE = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)
_REDACTED = "[REDACTED]"
_STDOUT_SNIPPET_CHARS = 2000
_STDERR_SNIPPET_CHARS = 1500


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class BrowserUseError(Exception):
    """Typed failure. Attributes: status (str), message (str), result (dict|None)."""

    def __init__(self, status: str, message: str, result: dict | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.result = result

    def __str__(self) -> str:  # keep repr/str free of secrets
        return f"browser-use error [{self.status}]: {self.message}"


class BrowserUseValidationError(BrowserUseError, ValueError):
    """Invalid arguments to run()/login(). Also catchable as ValueError."""


class BrowserUseTimeoutError(BrowserUseError):
    """Runner exceeded timeout_ms (outer watchdog) or self-reported timeout."""


class BrowserUseProtocolError(BrowserUseError):
    """Runner stdout was not exactly one JSON result object with a status."""


class BrowserUseProfileInUseError(BrowserUseError):
    """Another session/process currently holds this profile's flock."""


# --------------------------------------------------------------------------
# Redaction and diagnostics helpers
# --------------------------------------------------------------------------

def _secret_env_values() -> list[str]:
    values = []
    for name, value in os.environ.items():
        if not isinstance(value, str) or len(value) < 8:
            continue
        if _SECRET_NAME_RE.search(name):
            values.append(value)
    return values


def _redact(text: str) -> str:
    """Replace known env secret values (len >= 8) with a placeholder."""
    if not text:
        return text
    for value in set(_secret_env_values()):
        if value in text:
            text = text.replace(value, _REDACTED)
    return text


def _snippet(text: str, limit: int = _STDOUT_SNIPPET_CHARS) -> str:
    if not text:
        return ""
    return text[-limit:]


def _read_tail(path: Path, limit: int = _STDERR_SNIPPET_CHARS) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-limit:].decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _validate_task(task: Any, what: str = "task") -> str:
    if not isinstance(task, str) or not task.strip():
        raise BrowserUseValidationError(
            "invalid_input", f"{what} must be a nonempty string, got {task!r}", None
        )
    return task


def _validate_profile(profile: Any) -> str:
    if not isinstance(profile, str) or not _PROFILE_NAME_RE.match(profile):
        raise BrowserUseValidationError(
            "invalid_input",
            "profile must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}, got " + repr(profile),
            None,
        )
    return profile


def _validate_positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserUseValidationError(
            "invalid_input", f"{name} must be a positive finite number, got {value!r}", None
        )
    if not math.isfinite(value) or value <= 0:
        raise BrowserUseValidationError(
            "invalid_input", f"{name} must be a positive finite number, got {value!r}", None
        )
    return value


def _validate_positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BrowserUseValidationError(
            "invalid_input", f"{name} must be a positive integer, got {value!r}", None
        )
    return value


def _validate_timeout_ms(value: Any) -> int:
    """Positive whole milliseconds (the runner requires a safe integer)."""
    number = _validate_positive_number(value, "timeout_ms")
    if isinstance(number, float):
        if not number.is_integer():
            raise BrowserUseValidationError(
                "invalid_input",
                f"timeout_ms must be a whole number of milliseconds, got {value!r}",
                None,
            )
        number = int(number)
    if number > 2**53 - 1:
        raise BrowserUseValidationError(
            "invalid_input", f"timeout_ms is too large, got {value!r}", None
        )
    return number


def _validate_login_url(url: Any) -> str:
    if not isinstance(url, str) or not url.strip().lower().startswith(("http://", "https://")):
        raise BrowserUseValidationError(
            "invalid_input", f"url must be an http:// or https:// URL, got {url!r}", None
        )
    return url.strip()


def _coerce_schema(schema: Any) -> dict | None:
    """Accept None, a JSON-schema dict, or any class/instance exposing
    model_json_schema() (pydantic models work without importing pydantic)."""
    if schema is None:
        return None
    if isinstance(schema, dict):
        converted = schema
    else:
        method = getattr(schema, "model_json_schema", None)
        if not callable(method):
            raise BrowserUseValidationError(
                "invalid_input",
                "schema must be a dict or a pydantic model class "
                "(anything with model_json_schema()), got " + repr(schema),
                None,
            )
        converted = method()
        if not isinstance(converted, dict):
            raise BrowserUseValidationError(
                "invalid_input", "schema.model_json_schema() must return a dict", None
            )
    try:
        json.dumps(converted, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise BrowserUseValidationError(
            "invalid_input", f"schema is not JSON-serializable: {exc}", None
        ) from exc
    return converted


# --------------------------------------------------------------------------
# Paths and permissions
# --------------------------------------------------------------------------

def _home_dir() -> Path:
    raw = os.environ.get("BROWSER_USE_HOME") or DEFAULT_HOME
    return Path(raw).expanduser().resolve()


def _runner_path() -> Path:
    # src/browser_use/__init__.py -> <skill root>/runner.mjs
    return Path(__file__).resolve().parents[2] / "runner.mjs"


def _node_bin() -> str:
    return os.environ.get("BROWSER_USE_NODE") or shutil.which("node") or "node"


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


# --------------------------------------------------------------------------
# Profile lock (flock, cross-process and cross-session)
# --------------------------------------------------------------------------

def _acquire_profile_lock(lock_path: Path, profile: str) -> int:
    if fcntl is None:  # pragma: no cover - non-POSIX
        raise BrowserUseError(
            "launch_error", "profile locking requires fcntl (POSIX)", None
        )
    _ensure_private_dir(lock_path.parent)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        raise BrowserUseProfileInUseError(
            "profile_in_use",
            _redact(
                f"profile '{profile}' is in use by another run "
                f"(lock held: {lock_path})"
            ),
            {"profile": profile, "lock_path": str(lock_path)},
        ) from exc
    try:  # best-effort holder info for debugging
        os.ftruncate(fd, 0)
        os.write(fd, f"pid={os.getpid()} time={time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}\n".encode())
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


# --------------------------------------------------------------------------
# Subprocess lifecycle
# --------------------------------------------------------------------------

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
    """Signal the child's whole process group. The child is a session leader
    (start_new_session=True), so pgid == pid; killpg(proc.pid) still reaches
    descendants even after the leader itself has exited."""
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


async def _shutdown(proc: asyncio.subprocess.Process) -> None:
    """Tear down the runner's whole process group. The leader may already have
    exited (returncode set) while descendants such as Chrome still hold the
    profile, so the group is always signaled: SIGTERM, bounded wait, then an
    unconditional group SIGKILL to clear SIGTERM-ignoring stragglers."""
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


async def _spawn_runner(
    node: str, runner: Path, stderr_fh, env: dict
) -> asyncio.subprocess.Process:
    """Spawn the runner so cancellation cannot leak it: the creation future is
    shielded; if the caller is cancelled mid-creation and the process was
    nevertheless created, it is adopted and terminated before propagating.
    OSError (node missing, etc.) propagates to the caller."""
    create = asyncio.ensure_future(
        asyncio.create_subprocess_exec(
            node,
            str(runner),
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
    """Kill and reap the runner even if the caller keeps getting cancelled.

    The profile lock must not be released while the runner may still hold the
    profile, so repeated CancelledErrors are absorbed until _shutdown finishes.
    _shutdown is already bounded end to end (SIGTERM, a grace window, an
    unconditional group SIGKILL, then a reap window), so no second deadline is
    imposed here: a competing deadline could cancel _shutdown while it is still
    inside the SIGTERM grace window, i.e. before SIGKILL is ever delivered,
    stranding a SIGTERM-ignoring process group that still holds the profile.
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
            break  # shutdown itself failed; its error is collected below
    if cleanup.done() and not cleanup.cancelled():
        cleanup.exception()  # retrieve so asyncio never logs it as unhandled


# --------------------------------------------------------------------------
# Result parsing / normalization
# --------------------------------------------------------------------------

def _base_result(status: Any, artifact_dir: Path, stderr_path: Path) -> dict:
    return {
        "status": status,
        "output": None,
        "text": "",
        "steps": None,
        "cost": None,
        "screenshot_path": None,
        "artifact_dir": str(artifact_dir),
        "stderr_path": str(stderr_path),
    }


def _finish_result(
    stdout: bytes | None, returncode: int | None, artifact_dir: Path, stderr_path: Path
) -> dict:
    """Parse and normalize the runner's single stdout JSON result object."""
    raw = (stdout or b"").decode("utf-8", "replace")
    result = _base_result("protocol", artifact_dir, stderr_path)

    def protocol_error(message: str) -> NoReturn:
        message = _redact(message)
        result["error"] = message
        raise BrowserUseProtocolError("protocol", message, result)

    try:
        obj = json.loads(raw.strip())
    except ValueError:
        obj = None
    if not isinstance(obj, dict) or not isinstance(obj.get("status"), str) or not obj["status"].strip():
        message = f"runner stdout was not one JSON result object (exit code {returncode})"
        message += f"; stdout tail: {_snippet(raw)!r}"
        stderr_tail = _read_tail(stderr_path)
        if stderr_tail:
            message += f"; stderr tail: {_snippet(stderr_tail)!r}"
        protocol_error(message)
    if returncode != 0:
        protocol_error(f"runner exited with code {returncode}; stdout tail: {_snippet(raw)!r}")

    status = obj["status"].strip()
    text = obj.get("text")
    if text is None:
        text = ""
    if not isinstance(text, str):
        protocol_error(f"text must be a string, got {type(text).__name__}")
    shot = obj.get("screenshot_path")
    if shot is not None and not (isinstance(shot, str) and os.path.isabs(shot)):
        protocol_error(f"screenshot_path must be an absolute path or null, got {shot!r}")
    steps = obj.get("steps")
    if steps is not None and (isinstance(steps, bool) or not isinstance(steps, int)):
        protocol_error(f"steps must be an integer or null, got {steps!r}")
    cost = obj.get("cost")
    if cost is not None and (isinstance(cost, bool) or not isinstance(cost, (int, float))):
        protocol_error(f"cost must be a number or null, got {cost!r}")

    # Preserve runner-provided extras (usage, model, warnings, ...) but own the
    # normalized keys.
    result.update({k: v for k, v in obj.items() if k not in ("error", "artifact_dir")})
    result["status"] = status
    result["artifact_dir"] = str(artifact_dir)
    result["stderr_path"] = str(stderr_path)
    result["text"] = _redact(text)
    result["screenshot_path"] = shot
    result["steps"] = steps
    result["cost"] = cost

    if status != "completed":
        error = obj.get("error")
        error = error.strip() if isinstance(error, str) else ""
        result["error"] = _redact(error or f"run ended with status '{status}'")
        exc_class = BrowserUseTimeoutError if status == "timeout" else BrowserUseError
        raise exc_class(status, result["error"], result)
    return result


# --------------------------------------------------------------------------
# Core invocation
# --------------------------------------------------------------------------

async def _invoke_runner(
    op: str,
    task: str,
    schema: dict | None,
    profile: str,
    max_steps: int,
    timeout_ms: float,
    max_cost_usd: float,
) -> dict:
    home = _home_dir()
    profiles_root = home / "profiles"

    lock_path = profiles_root / f"{profile}.lock"
    lock_fd = _acquire_profile_lock(lock_path, profile)
    try:
        profile_dir = profiles_root / profile
        _ensure_private_dir(profile_dir)

        run_id = (
            f"{op}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
        )
        artifact_dir = home / "artifacts" / run_id
        _ensure_private_dir(artifact_dir)
        stderr_path = artifact_dir / "runner.stderr.log"

        stderr_fh = None
        proc = None
        try:
            request = {
                "op": op,
                "schema": schema,
                "profile_dir": str(profile_dir),
                "artifact_dir": str(artifact_dir),
                "max_steps": max_steps,
                "timeout_ms": timeout_ms,
                "max_cost_usd": max_cost_usd,
            }
            # The runner's contract: run reads `task`, login reads `url`.
            request["url" if op == "login" else "task"] = task
            runner = _runner_path()
            node = _node_bin()
            if not runner.is_file():
                raise BrowserUseError(
                    "launch_error",
                    f"runner script not found at {runner}",
                    _base_result("launch_error", artifact_dir, stderr_path),
                )

            fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            stderr_fh = os.fdopen(fd, "wb")

            env = dict(os.environ)
            env["DO_NOT_TRACK"] = "1"
            env.setdefault("BROWSER_USE_MODEL", DEFAULT_MODEL)

            try:
                try:
                    proc = await _spawn_runner(node, runner, stderr_fh, env)
                except OSError as exc:
                    raise BrowserUseError(
                        "launch_error",
                        _redact(f"failed to launch runner via {node}: {exc}"),
                        _base_result("launch_error", artifact_dir, stderr_path),
                    ) from exc

                payload = (json.dumps(request, allow_nan=False) + "\n").encode("utf-8")
                try:
                    proc.stdin.write(payload)
                    await proc.stdin.drain()
                    proc.stdin.close()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # runner died before reading; reported via exit code

                budget_s = timeout_ms / 1000.0 + _CLEANUP_ALLOWANCE_S
                try:
                    stdout, _ = await asyncio.wait_for(
                        proc.communicate(), timeout=budget_s
                    )
                except asyncio.TimeoutError:
                    await _terminate_guarded(proc)
                    message = _redact(
                        f"runner did not finish within timeout_ms={timeout_ms} "
                        f"(plus {_CLEANUP_ALLOWANCE_S:g}s cleanup allowance); "
                        "process group was terminated"
                    )
                    result = _base_result("timeout", artifact_dir, stderr_path)
                    result["error"] = message
                    raise BrowserUseTimeoutError("timeout", message, result) from None
                except asyncio.CancelledError:
                    await _terminate_guarded(proc)
                    raise

                return _finish_result(stdout, proc.returncode, artifact_dir, stderr_path)
            except BaseException:
                # Cancellation during spawn/drain, a launch error, or any other
                # failure: the runner must be dead and reaped before the profile
                # lock is released in the outer finally.
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


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

async def run(
    task: str,
    schema: Any = None,
    profile: str = "default",
    max_steps: int = 25,
    timeout_ms: float = 180_000,
    max_cost_usd: float = 1.0,
) -> dict:
    """Run one agentic browser task and return the runner result dict.

    Args:
        task: Nonempty natural-language instruction for the browser agent.
        schema: None, a JSON-schema dict, or a pydantic model class (detected
            via model_json_schema(), no pydantic import needed here). The
            runner returns a schema-validated dict under "output".
        profile: Profile name [A-Za-z0-9][A-Za-z0-9_-]{0,63}. Persisted logins
            live under <home>/profiles/<profile>/.
        max_steps: Positive int step cap.
        timeout_ms: Positive whole-milliseconds wall-clock budget (integral floats OK).
        max_cost_usd: Positive finite USD cost cap.

    Returns:
        dict with status, output, text, steps, cost, screenshot_path,
        artifact_dir (plus stderr_path and any extra runner keys).

    Raises:
        BrowserUseValidationError: bad arguments (also a ValueError).
        BrowserUseProfileInUseError: profile locked by another session.
        BrowserUseTimeoutError: budget exceeded.
        BrowserUseProtocolError: malformed runner output.
        BrowserUseError: any other non-completed status or launch failure.
    """
    task = _validate_task(task)
    profile = _validate_profile(profile)
    max_steps = _validate_positive_int(max_steps, "max_steps")
    timeout_ms = _validate_timeout_ms(timeout_ms)
    max_cost_usd = _validate_positive_number(max_cost_usd, "max_cost_usd")
    schema_dict = _coerce_schema(schema)
    return await _invoke_runner(
        "run", task, schema_dict, profile, max_steps, timeout_ms, max_cost_usd
    )


async def login(
    profile: str = "default",
    url: str = "https://example.com",
    timeout_ms: float = 600_000,
) -> dict:
    """Open a headed Chrome window on url using profile and wait for the user
    to close it, persisting cookies/localStorage into the profile. No model or
    API key is used. Same result dict and error semantics as run().
    """
    profile = _validate_profile(profile)
    url = _validate_login_url(url)
    timeout_ms = _validate_timeout_ms(timeout_ms)
    return await _invoke_runner(
        "login",
        url,
        None,
        profile,
        _LOGIN_NEUTRAL_LIMIT,
        timeout_ms,
        float(_LOGIN_NEUTRAL_LIMIT),
    )
