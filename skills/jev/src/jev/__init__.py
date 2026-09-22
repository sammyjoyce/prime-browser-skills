"""Prime Agent's Jev-first browser skill.

The standard-library wrapper owns profiles and bounded process cleanup. Browser
execution and declared checks run in the separate locked Python 3.12 runtime.
``completed`` remains an execution claim, not proof of an entire user objective.
See result["verification"] for checks of explicitly declared postconditions.

Use ``options`` for exact values, action permissions, confidence gates, render
controls, evidence collection and milestone checks. The runtime validates the
same options before starting Chrome. Browser-use's API/default remain unchanged.
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

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None  # type: ignore[assignment]

__version__ = "0.2.0"
__all__ = ["run", "login", "JevError", "JevValidationError", "JevTimeoutError",
           "JevProtocolError", "JevProfileInUseError", "DEFAULT_HOME", "VERIFICATION"]
DEFAULT_HOME = "~/.prime/agent/jev"
VERIFICATION = "not_performed"
_CLEANUP_ALLOWANCE_S = 45.0
_SIGTERM_GRACE_S = 10.0
_SIGKILL_GRACE_S = 5.0
_SPAWN_GRACE_S = 5.0
_LOGIN_NEUTRAL_LIMIT = 1_000_000
_MAX_TASK_CHARS = 20_000
_MAX_URL_CHARS = 2_048
_MAX_STEPS = 500
_MAX_TIMEOUT_MS = 86_400_000
_MAX_COST_USD = 100.0
_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SECRET_NAME_RE = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)
_REDACTED = "[REDACTED]"
_STDOUT_SNIPPET_CHARS = 2000
_STDERR_SNIPPET_CHARS = 1500
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_DROPPED_ENV_VARS = ("BU_CDP_URL", "BU_CDP_WS", "BROWSER_USE_CDP_URL", "CDP_URL", "CHROME_CDP_URL")
_DROPPED_ENV_PREFIXES = ("BH_",)
_FORCED_ENV = {"DO_NOT_TRACK": "1", "ANONYMIZED_TELEMETRY": "false", "BH_TELEMETRY": "0"}
_OWNED_RESULT_KEYS = ("status", "error", "artifact_dir", "profile_dir", "stderr_path")


class JevError(Exception):
    """Typed failure retaining status, real message and partial result."""
    def __init__(self, status: str, message: str, result: dict | None = None) -> None:
        super().__init__(message)
        self.status, self.message, self.result = status, message, result

    def __str__(self) -> str:
        return f"jev error [{self.status}]: {self.message}"


class JevValidationError(JevError, ValueError):
    """Invalid public API arguments."""


class JevTimeoutError(JevError):
    """Runner exceeded its bounded time allowance."""


class JevProtocolError(JevError):
    """Runner output violated the result contract."""


class JevProfileInUseError(JevError):
    """A different process owns the requested profile."""


def _redact(text: str) -> str:
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


def _invalid(message: str) -> NoReturn:
    raise JevValidationError("invalid_input", _redact(message), None)


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
    if not isinstance(url, str):
        _invalid(f"url must be an http:// or https:// string, got {url!r}")
    candidate = url.strip()
    if not candidate:
        _invalid("url must be a nonempty http:// or https:// URL")
    if len(candidate) > _MAX_URL_CHARS:
        _invalid(f"url must be at most {_MAX_URL_CHARS} characters, got {len(candidate)}")
    if any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7F for c in candidate):
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
        parts.port
    except ValueError:
        _invalid(f"url has an invalid port, got {url!r}")
    return candidate


def _validate_number(value: Any, name: str, maximum: float, whole: bool = False) -> float:
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


def _home_dir() -> Path:
    return Path(os.environ.get("JEV_HOME") or DEFAULT_HOME).expanduser().resolve()


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _runtime_dir() -> Path:
    return _skill_root() / "runtime"


def _runner_path() -> Path:
    return _runtime_dir() / "jev_runner.py"


def _runtime_python() -> Path:
    return _runtime_dir() / ".venv" / "bin" / "python"


def _launch_command() -> list[str]:
    runner, python = _runner_path(), _runtime_python()
    setup = f"run `uv sync --project {_runtime_dir()} --frozen` to install it"
    if not runner.is_file():
        raise JevError("launch_error", f"jev runtime runner not found at {runner}; {setup}", None)
    if not os.access(python, os.X_OK):
        raise JevError("launch_error", f"jev runtime interpreter not found at {python}; {setup}", None)
    return [str(python), str(runner)]


def _child_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if key not in _DROPPED_ENV_VARS and not key.startswith(_DROPPED_ENV_PREFIXES)}
    env.update(_FORCED_ENV)
    return env


def _reject_symlink(path: Path, what: str) -> None:
    if path.is_symlink():
        raise JevError("profile_error", f"{what} must be a real directory, not a symlink: {path}", None)


def _ensure_private_dir(path: Path) -> None:
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


def _acquire_profile_lock(lock_path: Path, profile: str) -> int:
    if fcntl is None:
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
    try:
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
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _probe(send, target: int) -> bool:
    try:
        send(target, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _alive(pid: int) -> bool:
    return _probe(os.kill, pid)


def _group_alive(proc: asyncio.subprocess.Process) -> bool:
    return _probe(os.killpg, proc.pid)


async def _shutdown(proc: asyncio.subprocess.Process) -> None:
    # Always sweep the group, including after its leader has exited.
    _signal_group(proc, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), timeout=_SIGTERM_GRACE_S)
    except asyncio.TimeoutError:
        pass
    _signal_group(proc, signal.SIGKILL)
    try:
        await asyncio.wait_for(proc.wait(), timeout=_SIGKILL_GRACE_S)
    except asyncio.TimeoutError:
        pass
    _close_proc_streams(proc)


async def _spawn_runner(argv: list[str], stderr_fh, env: dict) -> asyncio.subprocess.Process:
    create = asyncio.ensure_future(asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=stderr_fh, env=env, start_new_session=True,
    ))
    try:
        return await asyncio.shield(create)
    except asyncio.CancelledError:
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
                continue
            except Exception:
                break
        if create.done():
            try:
                proc = create.result()
            except BaseException:
                proc = None
        else:
            create.cancel()
        await _terminate_guarded(proc)
        raise


async def _terminate_guarded(proc: asyncio.subprocess.Process | None) -> None:
    if proc is None:
        return
    cleanup = asyncio.ensure_future(_shutdown(proc))
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if cleanup.done() and not cleanup.cancelled():
        cleanup.exception()


def _base_result(status: Any, artifact_dir: Path, profile_dir: Path, stderr_path: Path) -> dict:
    return {
        "status": status, "output": None, "text": "", "steps": None,
        "cost": None, "cost_detail": None, "usage": None, "model": None,
        "resolved_model": None, "helper_model": None, "duration_ms": None,
        "stop_reason": None, "warnings": [], "screenshot_path": None,
        "artifact_dir": str(artifact_dir), "profile_dir": str(profile_dir),
        "stderr_path": str(stderr_path),
    }


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


_FIELD_RULES = {
    "text": (lambda v: isinstance(v, str), "a string"),
    "steps": (lambda v: isinstance(v, int) and not isinstance(v, bool), "an integer"),
    "cost": (lambda v: _is_number(v) and math.isfinite(v) and v >= 0, "a finite non-negative number"),
    "duration_ms": (_is_number, "a number"),
    "output": (lambda v: isinstance(v, dict), "an object"),
    "warnings": (lambda v: isinstance(v, list) and all(isinstance(i, str) for i in v), "a list of strings"),
    "screenshot_path": (lambda v: isinstance(v, str) and os.path.isabs(v), "an absolute path"),
    "model": (lambda v: isinstance(v, str), "a string"),
    "resolved_model": (lambda v: isinstance(v, str), "a string"),
    "helper_model": (lambda v: isinstance(v, str), "a string"),
    "stop_reason": (lambda v: isinstance(v, str), "a string"),
}


def _finish_result(op: str, stdout: bytes | None, returncode: int | None,
                   artifact_dir: Path, profile_dir: Path, stderr_path: Path) -> dict:
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
    result.update({key: value for key, value in obj.items() if key not in _OWNED_RESULT_KEYS})
    status, output, cost = obj["status"].strip(), obj.get("output"), obj.get("cost")
    result.update(
        status=status, text=_redact(obj.get("text") or ""), steps=obj.get("steps"),
        cost=float(cost) if cost is not None else None,
        output=dict(output) if output is not None else None,
        warnings=[_redact(item) for item in obj.get("warnings") or []],
        screenshot_path=obj.get("screenshot_path"), artifact_dir=str(artifact_dir),
        profile_dir=str(profile_dir), stderr_path=str(stderr_path),
    )
    if status != "completed":
        error = obj.get("error")
        error = error.strip() if isinstance(error, str) else ""
        result["error"] = _redact(error or f"run ended with status '{status}'")
        error_class = JevTimeoutError if status == "timeout" else JevError
        raise error_class(status, result["error"], result)
    _check_completed(op, obj, result, protocol_error)
    return result


def _check_completed(op: str, obj: dict, result: dict, protocol_error) -> None:
    # Backward-compatible honesty: no unscoped claim of whole-goal verification.
    if obj.get("verified"):
        protocol_error("runner claimed goal verification; jev never verifies the goal")
    raw_output = result["output"]
    output = dict(raw_output) if isinstance(raw_output, dict) else {}
    verification = output.get("verification", VERIFICATION)
    if verification != VERIFICATION:
        protocol_error(f"output.verification must be {VERIFICATION!r}, got {verification!r}")
    output["verification"] = VERIFICATION
    if op == "login":
        if result["screenshot_path"] is not None:
            protocol_error("login must not return a screenshot (it can show credentials)")
        if result["cost"] != 0:
            protocol_error(f"completed login must report cost 0, got {result['cost']!r}")
        if result["steps"] != 0:
            protocol_error(f"completed login must report steps 0, got {result['steps']!r}")
        if output.get("authenticated") is not None:
            protocol_error(f"login must report authenticated=null, got {output.get('authenticated')!r}")
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
        protocol_error("a completed run must claim completion, got "
                       f"completion_claimed={output['completion_claimed']!r}")
    result["output"] = output
    problem = _png_problem(result["screenshot_path"])
    if problem is not None:
        message = _redact(f"completed run did not produce a usable PNG screenshot: {problem}")
        result.update(status="artifact_error", error=message)
        raise JevError("artifact_error", message, result)


def _png_problem(path: Any) -> str | None:
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


async def _invoke_runner(op: str, task: str | None, url: str, profile: str,
                         max_steps: int, timeout_ms: int, max_cost_usd: float,
                         options: dict | None = None) -> dict:
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

        stderr_fh, proc = None, None
        try:
            try:
                argv = _launch_command()
            except JevError as exc:
                fail(exc.status, exc.message)
            request = {
                "op": op, "run_id": run_id, "profile": profile, "task": task, "url": url,
                "profile_dir": str(profile_dir), "artifact_dir": str(artifact_dir),
                "max_steps": max_steps, "timeout_ms": timeout_ms, "max_cost_usd": max_cost_usd,
            }
            if options is not None:
                request["options"] = options
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
                    pass
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
                result = _finish_result(op, stdout, proc.returncode, artifact_dir, profile_dir, stderr_path)
                leftovers = _group_alive(proc)
                await _terminate_guarded(proc)
                if leftovers:
                    result["warnings"].append(
                        "runner left processes running after it exited; they were "
                        "terminated before the profile lock was released"
                    )
                return result
            except BaseException:
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


async def run(task: str, url: str, profile: str = "default", max_steps: int = 25,
              timeout_ms: float = 120_000, max_cost_usd: float = 0.5, *,
              options: dict | None = None) -> dict:
    """Execute a bounded Jev-first task. See references/runtime-api.md for options.

    No schema or arbitrary JavaScript is accepted. Exact values bypass the text
    helper. Declared checks have scoped evidence, not whole-objective proof.
    """
    task = _validate_task(task)
    url = _validate_url(url)
    profile = _validate_profile(profile)
    max_steps = _validate_number(max_steps, "max_steps", _MAX_STEPS, whole=True)
    timeout_ms = _validate_number(timeout_ms, "timeout_ms", _MAX_TIMEOUT_MS, whole=True)
    max_cost_usd = _validate_number(max_cost_usd, "max_cost_usd", _MAX_COST_USD)
    if options is not None:
        if not isinstance(options, dict):
            _invalid("options must be an object")
        try:
            encoded = json.dumps(options, allow_nan=False)
            if len(encoded) > 100_000:
                _invalid("options exceeds the 100000-character limit")
            options = json.loads(encoded)  # snapshot: caller mutation cannot race execution
        except (TypeError, ValueError, RecursionError):
            _invalid("options must contain finite JSON values")
    return await _invoke_runner("run", task, url, profile, max_steps, timeout_ms,
                                max_cost_usd, options)


async def login(profile: str = "default", url: str = "https://example.com",
                timeout_ms: float = 600_000) -> dict:
    """Open headed Chrome for manual sign-in. No model, screenshot or auth claim."""
    profile = _validate_profile(profile)
    url = _validate_url(url)
    timeout_ms = _validate_number(timeout_ms, "timeout_ms", _MAX_TIMEOUT_MS, whole=True)
    return await _invoke_runner("login", None, url, profile, _LOGIN_NEUTRAL_LIMIT,
                                timeout_ms, float(_LOGIN_NEUTRAL_LIMIT))
