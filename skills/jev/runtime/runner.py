#!/usr/bin/env python3
"""Native Jev runtime.

One process per operation. Reads one JSON request on stdin, writes exactly one
JSON result object on stdout, and sends every log line to stderr.

Operations
    run    - drive the vendored jev-ultrafast agent against an http(s) URL.
    login  - open a headed browser on a named profile so a person can sign in.

The package in vendor/jev-ultrafast is a maintained fork of upstream pin
1231850a0bf1a0c0341fe408ef1668dbbfdfac46, not an untouched copy; every local
change to it is listed in vendor/PROVENANCE.md. Six further adaptations are
applied in-process. All seven differences from upstream, the fork included, are
listed in DEVIATIONS.
"""

from __future__ import annotations

import base64
import fcntl
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PROC_T0 = time.perf_counter()

# The declared-check contract lives beside the wrapper, in the skill package,
# and is loaded here from that one file. The wrapper validates a caller's
# checks before this process exists; this runner validates the same request
# again, with the same code, so the two boundaries cannot drift apart.
# install.py copies src/ and runtime/ together, so both are always present.
CHECKS_MODULE_PATH = Path(__file__).resolve().parent.parent / "src" / "jev" / "checks.py"
# The confidence-cutoff contract is the same arrangement: one file, validated in
# the wrapper before this process exists and again here.
CONFIDENCE_MODULE_PATH = Path(__file__).resolve().parent.parent / "src" / "jev" / "confidence.py"


def load_contract_module(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"the contract module {module_name} could not be loaded from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_checks_module(path=CHECKS_MODULE_PATH):
    return load_contract_module("jev_declared_checks", path)


def load_confidence_module(path=CONFIDENCE_MODULE_PATH):
    return load_contract_module("jev_confidence_policy", path)


dom_checks = load_checks_module()
confidence_policy_contract = load_confidence_module()

UPSTREAM_COMMIT = "1231850a0bf1a0c0341fe408ef1668dbbfdfac46"
UPSTREAM_SYSTEMONE_URL = "https://api.typesafe.ai/v1/systemone"
SYSTEMONE_URL = "https://openrouter.ai/api/v1/systemone"
TEXT_BASE_URL = "https://openrouter.ai/api/v1"
DECISION_MODEL = "jev-latest"
HELPER_MODEL = "inception/mercury-2.5"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PROFILE_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
VALUE_KEY_RE = re.compile(r"\A[A-Za-z][A-Za-z0-9_]{0,63}\Z")
MAX_VALUES = 20
MAX_VALUE_CHARS = 2000
GENERATION = ("helper", "disabled")
DIR_MODE = 0o700
FILE_MODE = 0o600

CHROME_START_TIMEOUT_S = 40.0
DAEMON_START_TIMEOUT_S = 45.0
SCREENSHOT_TIMEOUT_S = 30.0
CLEANUP_BUDGET_S = 12.0
HARD_EXIT_GRACE_S = 12.0
LOGIN_POLL_S = 0.5

DEVIATIONS = [
    "transport: jev_ultrafast.model.post_json is wrapped in-process so the hardcoded "
    f"{UPSTREAM_SYSTEMONE_URL} becomes {SYSTEMONE_URL}, and so every provider HTTP attempt is "
    "accounted. Request bodies, headers, retry policy and response validation stay upstream.",
    "process ownership: browser_harness._ipc.spawn_kwargs is emptied on POSIX so the private "
    "daemon starts in this runner's process group. An outer process-group kill then reaches it "
    "instead of leaving a detached daemon behind.",
    "budgets: the wrapper stops the upstream run() generator at the requested max_steps, "
    "timeout_ms and max_cost_usd. Upstream's own budgets stay active underneath and are only "
    "ever reached later than these.",
    "browser: a dedicated Chrome with the named profile directory is launched by this runner and "
    "reached through browser-harness BU_CDP_URL. The user's running Chrome is never attached.",
    "verification: when the caller declares DOM checks, this runner performs one extra read-only "
    "JavaScript read through the upstream Browser.evaluate after the agent generator is closed, "
    "and reports it as result['verification'] with scope 'declared_dom_checks_only'. The page is "
    "never written to, the agent loop never sees it, and no check changes the run's status.",
    "safety: the runner passes the caller's confidence cutoffs and a budget callback into the "
    "vendored agent. The callback runs after every model call and before any input, so an "
    "uncosted or over-budget call stops the run before it binds a value, calls the text helper "
    "or types, and a decision below a declared cutoff is withheld as needs_review. It also "
    "refuses to call a run completed when the executor claimed DONE on an observation the "
    "snapshot reported as truncated and the declared DOM checks did not all pass.",
    "fork: vendor/jev-ultrafast is a maintained fork of the upstream pin, not an untouched copy. "
    "Four behaviours differ from upstream: a caller-supplied value is bound to a field by one "
    "TypeSafe choice and typed byte for byte, a text helper that answers {\"text\": null} now "
    "skips the field instead of ending the run, the snapshot reports whether its visible text was "
    "truncated and the decision and binding calls are told, and the agent withholds input for a "
    "low confidence score, an unpaid budget or an uncertain dispatch instead of continuing. "
    "Every local change is listed in vendor/PROVENANCE.md.",
]

# Statuses. Only "completed" means DONE plus a native PNG plus successful cleanup.
COMPLETED = "completed"
BLOCKED = "blocked"
MAX_STEPS = "max_steps"
TIMEOUT = "timeout"
CANCELLED = "cancelled"
COST_LIMIT = "cost_limit"
COST_UNKNOWN = "cost_unknown"
PROVIDER_ERROR = "provider_error"
BROWSER_ERROR = "browser_error"
ARTIFACT_ERROR = "artifact_error"
CLEANUP_ERROR = "cleanup_error"
PROFILE_BUSY = "profile_busy"
PROTOCOL_ERROR = "protocol_error"
# The executor stopped because the next input was not safe to take. A partial
# result is present, and the caller must inspect the page before any retry.
NEEDS_REVIEW = "needs_review"
CREDENTIALS_ERROR = "credentials_error"
LAUNCH_ERROR = "launch_error"
INTERNAL_ERROR = "internal_error"
PROVIDER_MESSAGE_LIMIT = 500
INVALID_REQUEST = "invalid_request"


SECRET_PATTERNS = [
    re.compile(r"sk-or-v1-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
]
_SECRET_VALUES = []


SECRET_NAME_RE = re.compile(r"(API_KEY|APIKEY|ACCESS_KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)


def register_secrets():
    """Remember every credential-shaped environment value.

    Broad by design: any inherited variable whose name looks like a credential
    is registered, so an unrelated provider key cannot leak through an error
    message or a provider response body.
    """
    for name, value in list(os.environ.items()):
        if not value or len(value) < 8:
            continue
        if not SECRET_NAME_RE.search(name):
            continue
        if value not in _SECRET_VALUES:
            _SECRET_VALUES.append(value)


def redact(text):
    """Replace credential values and key-shaped tokens with a marker."""
    if not isinstance(text, str):
        return text
    for value in _SECRET_VALUES:
        if value in text:
            text = text.replace(value, "[REDACTED]")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def log(message):
    sys.stderr.write(redact(f"[jev {time.strftime('%H:%M:%S')}] {message}") + "\n")
    sys.stderr.flush()


class RequestError(Exception):
    """The request itself is unusable."""


class ProfileBusy(Exception):
    """Another process owns this profile."""


class Stopped(Exception):
    """Timeout or cancellation asked the run to stop."""


class MissingCredentials(RuntimeError):
    """The run path needs OPENROUTER_API_KEY and it is absent."""


class LaunchError(Exception):
    """The runner was started in a way that makes cleanup unverifiable."""


LAUNCH_INSTRUCTION = (
    "start the runner as its own process group leader, for example "
    "subprocess.Popen([<runtime>/.venv/bin/python, <runtime>/runner.py], start_new_session=True). "
    "Do not wrap it in `uv run`: uv remains the group leader, which leaves browser and daemon "
    "teardown unverifiable."
)


def require_process_group_leadership():
    """Refuse to start a browser this runner could not verifiably clean up."""
    try:
        leader = os.getpgid(0) == os.getpid()
    except OSError as exc:
        raise LaunchError(f"process group could not be determined: {exc}") from None
    if not leader:
        raise LaunchError(f"this runner is not its own process group leader; {LAUNCH_INSTRUCTION}")


# --------------------------------------------------------------------------
# single-result stdout contract
# --------------------------------------------------------------------------
_emit_lock = threading.Lock()
_emitted = False


def emit(result):
    global _emitted
    with _emit_lock:
        if _emitted:
            return False
        _emitted = True
        sys.stdout.write(redact(json.dumps(result, default=str)))
        sys.stdout.write("\n")
        sys.stdout.flush()
        return True


# --------------------------------------------------------------------------
# request validation
# --------------------------------------------------------------------------
def positive_int(value, field, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise RequestError(f"{field} must be an integer, got {type(value).__name__}")
    if value <= 0:
        raise RequestError(f"{field} must be greater than 0, got {value}")
    if maximum is not None and value > maximum:
        raise RequestError(f"{field} must be at most {maximum}, got {value}")
    return value


def positive_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RequestError(f"{field} must be a number, got {type(value).__name__}")
    if not math.isfinite(value) or value <= 0:
        raise RequestError(f"{field} must be a finite number greater than 0, got {value}")
    return float(value)


def absolute_dir(value, field):
    if not isinstance(value, str) or not value.strip():
        raise RequestError(f"{field} must be a non-empty string")
    path = Path(value)
    if not path.is_absolute():
        raise RequestError(f"{field} must be an absolute path, got {value!r}")
    return path


def http_url(value, field):
    if not isinstance(value, str) or not value.strip():
        raise RequestError(f"{field} must be a non-empty string")
    if not re.match(r"\Ahttps?://", value, re.IGNORECASE):
        raise RequestError(f"{field} must be an http(s) URL, got {value!r}")
    return value


def supplied_values(value, field="values"):
    """None, or a bounded dict of exact field values. Nothing is normalised here.

    An empty string is a real value: it means clear that field.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RequestError(f"{field} must be an object or null, got {type(value).__name__}")
    if len(value) > MAX_VALUES:
        raise RequestError(f"{field} must have at most {MAX_VALUES} entries, got {len(value)}")
    for key, item in value.items():
        if not isinstance(key, str) or not VALUE_KEY_RE.match(key):
            raise RequestError(f"{field} keys must match [A-Za-z][A-Za-z0-9_]{{0,63}}, got {key!r}")
        if key == "NONE":
            raise RequestError(f"{field} keys must not be 'NONE'; that name is reserved for the no-value choice")
        if not isinstance(item, str):
            raise RequestError(f"{field}[{key!r}] must be a string, got {type(item).__name__}")
        if len(item) > MAX_VALUE_CHARS:
            raise RequestError(f"{field}[{key!r}] must be at most {MAX_VALUE_CHARS} characters, got {len(item)}")
    return dict(value)


def generation_mode(value, values, field="generation"):
    """Supplied values turn the text helper off unless the caller asks for it."""
    if value is None:
        return "disabled" if values else "helper"
    if value not in GENERATION:
        raise RequestError(f"{field} must be 'helper', 'disabled' or null, got {value!r}")
    return value


def declared_dom_checks(value):
    """The caller's read-only DOM checks, normalized, or [].

    The same contract module the wrapper uses. Re-validated here as well as in
    the wrapper: a runner never trusts its caller.
    """
    try:
        return dom_checks.normalize_checks(value)
    except dom_checks.CheckError as exc:
        raise RequestError(str(exc)) from None


def confidence_cutoffs(value):
    """The caller's opt-in confidence cutoffs, or None.

    The same contract module the wrapper uses, re-validated here: a runner
    never trusts its caller. None and {} both mean "record the scores and
    withhold nothing". There is no default cutoff.
    """
    try:
        return confidence_policy_contract.normalize_confidence(value)
    except confidence_policy_contract.ConfidenceError as exc:
        raise RequestError(str(exc)) from None


def normalize(request):
    op = request.get("op")
    if op not in {"run", "login"}:
        raise RequestError("op must be 'run' or 'login'")
    profile = request.get("profile")
    if profile is not None and not PROFILE_NAME_RE.match(str(profile)):
        raise RequestError("profile must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}")
    config = {
        "op": op,
        "profile": str(profile) if profile is not None else None,
        "profile_dir": absolute_dir(request.get("profile_dir"), "profile_dir"),
        "artifact_dir": absolute_dir(request.get("artifact_dir"), "artifact_dir"),
        "url": http_url(request.get("url"), "url"),
        "timeout_ms": positive_int(request.get("timeout_ms", 120000), "timeout_ms"),
        "run_id": str(request.get("run_id") or uuid.uuid4().hex[:12]),
    }
    if op == "run":
        task = request.get("task")
        if not isinstance(task, str) or not task.strip():
            raise RequestError("task must be a non-empty string")
        config["task"] = task.strip()
        config["max_steps"] = positive_int(request.get("max_steps", 25), "max_steps")
        config["max_cost_usd"] = positive_number(request.get("max_cost_usd", 0.5), "max_cost_usd")
        # Re-validated here as well as in the wrapper: a runner never trusts its caller.
        config["values"] = supplied_values(request.get("values"))
        config["generation"] = generation_mode(request.get("generation"), config["values"])
        config["checks"] = declared_dom_checks(request.get("checks"))
        config["confidence"] = confidence_cutoffs(request.get("confidence"))
    else:
        config["task"] = None
        config["max_steps"] = None
        config["max_cost_usd"] = None
        config["values"] = None
        config["generation"] = None
        # login opens a window for a person; it asserts nothing about a page.
        config["checks"] = []
        # login makes no model call and dispatches no agent input, so a cutoff
        # would have nothing to gate.
        config["confidence"] = None
    return config


# --------------------------------------------------------------------------
# provider accounting
# --------------------------------------------------------------------------
HTTP_ATTEMPTS = []  # one record per real HTTP attempt, upstream retries included
LOGICAL_CALLS = []  # one record per upstream post_json call
_ROLE = ["unknown"]


def _read_usage(payload):
    if not isinstance(payload, dict):
        return None, None, None
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
    cost = None
    if usage is not None:
        raw = usage.get("cost", usage.get("total_cost"))
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            cost = float(raw)
    return usage, cost, payload.get("model")


FINISH_REASONS = frozenset({"stop", "length", "content_filter", "tool_calls", "function_call", "error"})


def normalized_finish_reason(value):
    """Known finish reason, or "other". Never free provider text."""
    if not value:
        return None
    return str(value) if str(value) in FINISH_REASONS else "other"


def helper_response_shape(payload):
    """Metadata about a helper response. No values and no key names are kept.

    The vendored fork accepts exactly {"text": "<non-blank string>"}, plus the
    documented {"text": null} for a missing value, which now skips the field
    instead of ending the run. These counts and booleans separate the remaining
    failure modes without capturing any field content: a model-chosen key could
    itself contain field data, so keys are counted and compared, never recorded.
    """
    shape = dict.fromkeys(
        (
            "finish_reason", "native_finish_reason", "content_type", "content_chars",
            "json_top_type", "json_key_count", "text_value_type", "text_value_chars", "text_is_blank",
        )
    )
    shape.update(
        refusal_present=False, content_present=False, content_is_null=False,
        json_parse_ok=False, has_text_key=False, keys_are_exact_text=False, error_present=False,
    )
    if not isinstance(payload, dict):
        return shape
    shape["error_present"] = payload.get("error") is not None
    choices = payload.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
    if choice is None:
        return shape
    # Mapped to a known set, so no free provider text can ride along.
    shape["finish_reason"] = normalized_finish_reason(choice.get("finish_reason"))
    shape["native_finish_reason"] = normalized_finish_reason(choice.get("native_finish_reason"))
    message = choice.get("message")
    if not isinstance(message, dict):
        return shape
    shape["refusal_present"] = message.get("refusal") is not None
    content = message.get("content")
    shape["content_present"] = "content" in message
    shape["content_is_null"] = content is None
    shape["content_type"] = type(content).__name__
    if not isinstance(content, str):
        return shape
    shape["content_chars"] = len(content)
    try:
        parsed = json.loads(content)
    except ValueError:
        return shape
    shape["json_parse_ok"] = True
    shape["json_top_type"] = type(parsed).__name__
    if not isinstance(parsed, dict):
        return shape
    shape["json_key_count"] = len(parsed)
    shape["has_text_key"] = "text" in parsed
    shape["keys_are_exact_text"] = set(parsed) == {"text"}
    if shape["has_text_key"]:
        value = parsed["text"]
        shape["text_value_type"] = type(value).__name__
        if isinstance(value, str):
            shape["text_value_chars"] = len(value)
            shape["text_is_blank"] = not value.strip()
    return shape


class RecordingClient:
    """Proxy over upstream's httpx client that counts every HTTP attempt.

    Upstream retries inside one logical call, so counting logical calls alone
    would understate provider traffic and hide the cost of retried attempts.
    """

    def __init__(self, inner):
        self._inner = inner

    def post(self, url, **kwargs):
        record = {
            "role": _ROLE[0],
            "status_code": None,
            "latency_ms": None,
            "usage": None,
            "cost_usd": None,
            "resolved_model": None,
            "provider_message": None,
            "helper_shape": None,
            "error": None,
        }
        HTTP_ATTEMPTS.append(record)
        started = time.perf_counter()
        try:
            response = self._inner.post(url, **kwargs)
        except Exception as exc:
            record["latency_ms"] = round((time.perf_counter() - started) * 1000)
            record["error"] = type(exc).__name__
            raise
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        record["status_code"] = response.status_code
        ok_status = 200 <= response.status_code < 300
        if not ok_status:
            # Upstream raises a generic "HTTP <code>" and discards the body, so the
            # real provider message would be lost. Capture it here, bounded and
            # redacted. Retry semantics and the vendored code are untouched.
            try:
                record["provider_message"] = redact(response.text or "")[:PROVIDER_MESSAGE_LIMIT]
            except Exception as exc:
                record["provider_message"] = f"<unreadable provider body: {type(exc).__name__}>"
        try:
            payload = response.json()
        except Exception:
            payload = None
        usage, cost, model = _read_usage(payload)
        if record["role"] == "helper" and ok_status:
            # Diagnostics only. Nothing here changes the request, the retry
            # policy or upstream's validation of the response.
            record["helper_shape"] = helper_response_shape(payload)
        record["usage"] = usage
        record["cost_usd"] = cost
        record["resolved_model"] = model
        return response

    def __getattr__(self, name):
        return getattr(self._inner, name)


def successful_attempts_without_cost():
    return [
        a
        for a in HTTP_ATTEMPTS
        if a["cost_usd"] is None
        and isinstance(a["status_code"], int)
        and 200 <= a["status_code"] < 300
    ]


def known_cost():
    return sum(a["cost_usd"] for a in HTTP_ATTEMPTS if isinstance(a["cost_usd"], (int, float)))


def usage_summary():
    if not HTTP_ATTEMPTS:
        return None
    summary = {}
    for role in sorted({a["role"] for a in HTTP_ATTEMPTS}):
        attempts = [a for a in HTTP_ATTEMPTS if a["role"] == role]
        logical = [c for c in LOGICAL_CALLS if c["role"] == role]
        entry = {
            "logical_requests": len(logical),
            "http_attempts": len(attempts),
            "http_attempt_status": [a["status_code"] for a in attempts],
            "resolved_model": next((a["resolved_model"] for a in attempts if a["resolved_model"]), None),
            "latency_ms": [a["latency_ms"] for a in attempts],
        }
        for field in ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens"):
            values = [
                a["usage"].get(field)
                for a in attempts
                if isinstance(a.get("usage"), dict) and isinstance(a["usage"].get(field), (int, float))
            ]
            entry[field] = sum(values) if values else None
        summary[role] = entry
    return summary


def cost_summary():
    """(cost, detail). Unknown is None. Never zero as a stand-in for unknown."""
    detail = {
        "basis": "http_attempts",
        "attempts_total": len(HTTP_ATTEMPTS),
        "attempts_with_cost": sum(1 for a in HTTP_ATTEMPTS if a["cost_usd"] is not None),
        "logical_calls": len(LOGICAL_CALLS),
        "known_subtotal_usd": known_cost(),
        "per_attempt": [
            {"role": a["role"], "status_code": a["status_code"], "cost_usd": a["cost_usd"]} for a in HTTP_ATTEMPTS
        ],
    }
    if not HTTP_ATTEMPTS:
        detail["note"] = "no model requests were made"
        return 0.0, detail
    missing = successful_attempts_without_cost()
    missing_ids = {id(a) for a in missing}
    failed_without_cost = [
        a for a in HTTP_ATTEMPTS if a["cost_usd"] is None and id(a) not in missing_ids
    ]
    detail["successful_attempts_without_cost"] = len(missing)
    detail["failed_attempts_without_cost"] = len(failed_without_cost)
    if missing:
        detail["note"] = (
            f"{len(missing)} successful provider attempt(s) reported no cost; spend is unknown, not zero"
        )
        return None, detail
    if detail["attempts_with_cost"] == 0:
        detail["note"] = "no provider attempt reported a cost; spend is unknown, not zero"
        return None, detail
    if failed_without_cost:
        detail["note"] = (
            f"cost covers all {detail['attempts_with_cost']} attempt(s) that reported one; "
            f"{len(failed_without_cost)} failed attempt(s) reported no cost and are assumed unbilled"
        )
        return detail["known_subtotal_usd"], detail
    detail["note"] = "every provider HTTP attempt reported a cost"
    return detail["known_subtotal_usd"], detail


def install_provider_patch():
    import jev_ultrafast.model as jev_model

    jev_model.CLIENT = RecordingClient(jev_model.CLIENT)
    original = jev_model.post_json

    def post_json(url, key, body):
        is_decision = url == UPSTREAM_SYSTEMONE_URL
        role = "decision" if is_decision else "helper"
        record = {"role": role, "ok": False, "latency_ms": None, "resolved_model": None, "error": None}
        LOGICAL_CALLS.append(record)
        previous, _ROLE[0] = _ROLE[0], role
        started = time.perf_counter()
        try:
            result = original(SYSTEMONE_URL if is_decision else url, key, body)
        except Exception as exc:
            record["latency_ms"] = round((time.perf_counter() - started) * 1000)
            record["error"] = str(exc)
            raise
        finally:
            _ROLE[0] = previous
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        record["ok"] = True
        record["resolved_model"] = result.get("model") if isinstance(result, dict) else None
        return result

    jev_model.post_json = post_json


def last_provider_message():
    """Most recent non-2xx provider body, already bounded and redacted."""
    for attempt in reversed(HTTP_ATTEMPTS):
        if attempt.get("provider_message"):
            return attempt["provider_message"]
    return None


def resolved_model_for(role):
    for attempt in HTTP_ATTEMPTS:
        if attempt["role"] == role and attempt["resolved_model"]:
            return attempt["resolved_model"]
    return None


# --------------------------------------------------------------------------
# owned processes
# --------------------------------------------------------------------------
class OwnedProcesses:
    """Every process this runner started, plus bounded teardown for all of it.

    Chrome and the browser-harness daemon are both started by this runner as
    direct children, so teardown uses the Popen handles this process owns. No
    stored PID is ever signalled, so a reused PID can never be hit, and the
    teardown does not depend on being a process-group leader - which matters
    because `uv run` is the parent process in the documented launch.

    Neither child is given a new session, so both also stay in whatever process
    group the caller placed this runner in. An outer process-group kill
    therefore reaches them too.
    """

    def __init__(self):
        self.chrome = None
        self.daemon = None
        self.daemon_name = None
        self.runtime_dir = None
        self.warnings = []

    @staticmethod
    def owns_process_group():
        try:
            return os.getpgid(0) == os.getpid()
        except OSError:
            return False

    @staticmethod
    def group_members():
        """Live PIDs sharing this runner's process group.

        Excludes this process, the `ps` child used to take the snapshot, and
        any process already reaped or zombied, so a scan can never report
        itself as a leftover.
        """
        try:
            pgid = os.getpgid(0)
        except OSError:
            return []
        try:
            scanner = subprocess.Popen(
                ["ps", "ax", "-o", "pid=,pgid=,stat="],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            listing, _ = scanner.communicate(timeout=5)
        except Exception:
            return []
        ignore = {os.getpid(), scanner.pid}
        members = []
        for line in listing.splitlines():
            parts = line.split()
            if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
                continue
            pid, group, state = int(parts[0]), int(parts[1]), parts[2]
            if group != pgid or pid in ignore or state.startswith("Z"):
                continue
            members.append(pid)
        return members

    def _stop_child(self, process, label, budget_s):
        """Stop a direct child through its own handle."""
        if process is None or process.poll() is not None:
            return True
        for action, wait_s in ((process.terminate, budget_s * 0.6), (process.kill, budget_s * 0.4)):
            try:
                action()
            except OSError:
                return process.poll() is not None
            try:
                process.wait(timeout=max(wait_s, 0.2))
                return True
            except subprocess.TimeoutExpired:
                continue
        self.warnings.append(f"the owned {label} did not exit")
        return False

    def request_daemon_shutdown(self):
        """Ask the private daemon to stop. Clean request only; never a kill."""
        if not self.daemon_name:
            return
        try:
            from browser_harness import _ipc as harness_ipc

            connection, token = harness_ipc.connect(self.daemon_name, timeout=1.5)
            try:
                harness_ipc.request(connection, token, {"meta": "shutdown"})
            finally:
                connection.close()
        except Exception as exc:
            log(f"daemon shutdown request failed: {type(exc).__name__}: {exc}")

    def stop_daemon(self, budget_s=5.0):
        self.request_daemon_shutdown()
        if self.daemon is not None:
            deadline = time.perf_counter() + min(budget_s * 0.3, 1.5)
            while time.perf_counter() < deadline and self.daemon.poll() is None:
                time.sleep(0.05)
        ok = self._stop_child(self.daemon, "daemon", budget_s)
        if self.daemon_name:
            try:
                from browser_harness import _ipc as harness_ipc

                harness_ipc.cleanup_endpoint(self.daemon_name)
            except Exception:
                pass
        return ok

    def stop_chrome(self, budget_s=6.0):
        return self._stop_child(self.chrome, "browser", budget_s)

    def sweep_group(self, budget_s=4.0):
        """SIGTERM this runner's own process group, surviving it deliberately.

        Only reached when this process leads the group, so the signal cannot
        touch the caller's processes. Catches browser helpers that outlive the
        browser handle.
        """
        if not self.owns_process_group():
            return False
        previous = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            os.killpg(os.getpid(), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError) as exc:
            self.warnings.append(f"group teardown signal failed: {type(exc).__name__}: {exc}")
        finally:
            deadline = time.perf_counter() + budget_s
            while time.perf_counter() < deadline and self.group_members():
                time.sleep(0.1)
            try:
                signal.signal(signal.SIGTERM, previous)
            except (ValueError, OSError, TypeError):
                pass
        return True

    def cleanup(self, budget_s=CLEANUP_BUDGET_S):
        """Stop every owned process. Returns (ok, elapsed_ms)."""
        started = time.perf_counter()
        daemon_ok = self.stop_daemon(budget_s=budget_s * 0.35)
        chrome_ok = self.stop_chrome(budget_s=budget_s * 0.35)
        swept = self.sweep_group(budget_s=budget_s * 0.3)
        if not swept:
            # Never claim a clean teardown that was never verified.
            self.warnings.append(
                "group teardown was skipped because this runner does not lead its process group"
            )
            leftovers = []
        else:
            leftovers = self.group_members()
            if leftovers:
                self.warnings.append(
                    f"processes still share this runner's process group after cleanup: {leftovers}"
                )
        if self.runtime_dir:
            shutil.rmtree(self.runtime_dir, ignore_errors=True)
        ok = daemon_ok and chrome_ok and swept and not leftovers
        return ok, round((time.perf_counter() - started) * 1000)


def start_private_daemon(owned, artifact_dir, name):
    """Start this run's browser-harness daemon as an owned child process.

    browser_harness.admin.ensure_daemon() spawns the daemon detached and then
    owns its lifecycle. Starting the same daemon module directly keeps it as a
    direct child, so it can be stopped through its own handle and cannot be
    orphaned. Readiness uses the harness's own liveness check plus one real CDP
    call, which is the same health bar ensure_daemon applies.
    """
    from browser_harness.admin import daemon_alive

    log_path = artifact_dir / "daemon.log"
    handle = open(log_path, "ab")
    try:
        os.chmod(log_path, FILE_MODE)
    except OSError:
        pass
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "browser_harness.daemon"],
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=handle,
        )
    finally:
        handle.close()
    owned.daemon = process
    owned.daemon_name = name
    deadline = time.perf_counter() + DAEMON_START_TIMEOUT_S
    while time.perf_counter() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"the browser-harness daemon exited with code {process.returncode} before it was ready"
            )
        if daemon_alive(name):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError(f"the browser-harness daemon was not ready within {DAEMON_START_TIMEOUT_S:g}s")
    from browser_harness.helpers import cdp

    cdp("Target.getTargets", _response_timeout=10.0)
    log(f"private daemon ready pid={process.pid} name={name}")
    return process


def chrome_binary():
    explicit = os.environ.get("JEV_CHROME_BINARY")
    if explicit:
        if not Path(explicit).exists():
            raise RequestError(f"JEV_CHROME_BINARY does not exist: {explicit}")
        return explicit
    for candidate in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ):
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("no Chrome or Chromium binary was found")


def launch_chrome(profile_dir, artifact_dir, headless, owned, start_url=None):
    """Start a dedicated Chrome on this profile, in this runner's process group."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(profile_dir, DIR_MODE)
    port_file = profile_dir / "DevToolsActivePort"
    if port_file.exists():
        port_file.unlink()
    args = [
        chrome_binary(),
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-search-engine-choice-screen",
    ]
    if headless:
        args.insert(1, "--headless=new")
    args.append(start_url or "about:blank")
    log_path = artifact_dir / "chrome.log"
    handle = open(log_path, "ab")
    try:
        os.chmod(log_path, FILE_MODE)
    except OSError:
        pass
    try:
        # No start_new_session: Chrome stays in this process group so an outer
        # group kill reaches it and cannot leave an orphan browser behind.
        process = subprocess.Popen(args, stdout=handle, stderr=handle)
    finally:
        handle.close()
    owned.chrome = process
    deadline = time.perf_counter() + CHROME_START_TIMEOUT_S
    while time.perf_counter() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Chrome exited with code {process.returncode} before DevTools was ready")
        try:
            lines = port_file.read_text().splitlines()
        except (FileNotFoundError, OSError):
            lines = []
        if lines and lines[0].strip().isdigit():
            port = int(lines[0].strip())
            if devtools_ready(port):
                log(f"chrome ready on 127.0.0.1:{port} pid={process.pid} headless={headless}")
                return port
        time.sleep(0.05)
    raise RuntimeError(f"Chrome DevTools endpoint was not ready within {CHROME_START_TIMEOUT_S:g}s")


def devtools_ready(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as response:
            json.loads(response.read())
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def page_targets(port):
    """Page targets of this Chrome, or None when DevTools is unreachable."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
            targets = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(targets, list):
        return None
    return [t for t in targets if isinstance(t, dict) and t.get("type") == "page"]


# --------------------------------------------------------------------------
# profile lock
# --------------------------------------------------------------------------
class ProfileLock:
    """Exclusive ownership of one profile directory for this runner process.

    The skill wrapper owns the profile-level lock at `.jev-profile.lock`. This
    is a second, runner-level lock on a different file, so the two never fight
    while a directly invoked runner still cannot collide with another runner.
    It is held until every owned process has been cleaned up.
    """

    def __init__(self, profile_dir):
        self.path = Path(profile_dir) / ".jev-runner.lock"
        self.handle = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, DIR_MODE)
        self.handle = open(self.path, "a+")
        try:
            os.chmod(self.path, FILE_MODE)
        except OSError:
            pass
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise ProfileBusy(
                f"profile directory {self.path.parent} is in use by another Jev process"
            )
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"{os.getpid()} {time.time():.0f}\n")
        self.handle.flush()
        return self

    def release(self):
        if self.handle is None:
            return
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self.handle.close()
        except OSError:
            pass
        self.handle = None


# --------------------------------------------------------------------------
# screenshots: direct native PNG, never a converted JPEG
# --------------------------------------------------------------------------
def capture_png(session_id, destination):
    """Capture with CDP Page.captureScreenshot format='png' and write the bytes.

    The bytes are written exactly as Chrome produced them. Nothing is decoded,
    re-encoded or converted, so the artifact is a native PNG rather than a JPEG
    wearing a PNG extension.
    """
    from browser_harness.helpers import cdp

    response = cdp(
        "Page.captureScreenshot",
        session_id=session_id,
        format="png",
        _response_timeout=SCREENSHOT_TIMEOUT_S,
    )
    data = response.get("data") if isinstance(response, dict) else None
    if not data:
        raise RuntimeError("Page.captureScreenshot returned no data")
    raw = base64.b64decode(data)
    if not raw.startswith(PNG_SIGNATURE):
        raise RuntimeError("Page.captureScreenshot did not return PNG bytes")
    destination = Path(destination)
    destination.write_bytes(raw)
    try:
        os.chmod(destination, FILE_MODE)
    except OSError:
        pass
    return str(destination.resolve())


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------
def configure_environment(config, artifact_dir, runtime_dir):
    """Provider credentials plus a private browser-harness identity and state."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise MissingCredentials(
            "OPENROUTER_API_KEY is not set; the run operation needs it for decisions and field text"
        )
    os.environ["TYPESAFE_API_KEY"] = key
    register_secrets()
    os.environ["TYPESAFE_MODEL"] = DECISION_MODEL
    os.environ["TEXT_MODEL_API_KEY"] = key
    os.environ["TEXT_MODEL_BASE_URL"] = TEXT_BASE_URL
    os.environ["TEXT_MODEL"] = HELPER_MODEL
    os.environ["TEXT_MODEL_REASONING"] = "none"
    safe = "".join(c if (c.isalnum() or c in "_-") else "-" for c in config["run_id"])[:48]
    os.environ["BU_NAME"] = f"jev-{safe}" if safe else f"jev-{uuid.uuid4().hex[:12]}"
    os.environ["BH_HOME"] = str(artifact_dir / "harness")
    os.environ["BH_RUNTIME_DIR"] = str(runtime_dir)
    os.environ["BH_TMP_DIR"] = str(artifact_dir / "harness-tmp")
    os.environ["BH_AGENT_WORKSPACE"] = str(artifact_dir / "harness-workspace")
    os.environ["BH_TELEMETRY"] = "0"
    os.environ["BROWSER_HARNESS_TELEMETRY"] = "0"
    os.environ["ANONYMIZED_TELEMETRY"] = "false"
    os.environ["DO_NOT_TRACK"] = "1"
    # Never inherit another session's browser endpoint; this runner sets its own.
    for name in ("BU_CDP_WS", "BU_CDP_URL", "BU_BROWSER_ID"):
        os.environ.pop(name, None)


EXPECTED_SPAWN_KWARGS = {"start_new_session": True}


def keep_daemon_in_process_group():
    """Stop browser-harness detaching its daemon into a new session.

    Fails closed. If the pinned browser-harness no longer exposes the exact
    spawn shape this patch understands, the operation stops instead of running
    with a daemon that a process-group kill cannot reach.
    """
    if os.name != "posix":
        raise RuntimeError("this runtime supports POSIX process-group ownership only")
    from browser_harness import _ipc as harness_ipc

    spawn_kwargs = getattr(harness_ipc, "spawn_kwargs", None)
    if not callable(spawn_kwargs):
        raise RuntimeError(
            "browser_harness._ipc.spawn_kwargs is missing; refusing to start a daemon that "
            "process-group cleanup may not reach"
        )
    observed = spawn_kwargs()
    if observed != EXPECTED_SPAWN_KWARGS:
        raise RuntimeError(
            "browser_harness._ipc.spawn_kwargs returned "
            f"{observed!r}, expected {EXPECTED_SPAWN_KWARGS!r}; refusing to start a daemon whose "
            "detachment behaviour is unknown"
        )
    harness_ipc.spawn_kwargs = lambda: {}


# --------------------------------------------------------------------------
# stop coordination: timeout, cancellation, hard exit
# --------------------------------------------------------------------------
STOP = {"reason": None}
FINISHED = threading.Event()
WAKE = threading.Event()


def request_stop(reason):
    if STOP["reason"] is None:
        STOP["reason"] = reason
    WAKE.set()


def install_signal_handlers():
    def handler(signum, _frame):
        request_stop("cancelled")
        log(f"signal {signum} received; stopping")

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass


def start_watchdog(config, owned, result):
    """Bound the whole operation, then tear every owned process down."""
    deadline = PROC_T0 + config["timeout_ms"] / 1000.0

    def body():
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0 or STOP["reason"] or FINISHED.is_set():
                break
            WAKE.wait(timeout=min(remaining, 0.5))
        if FINISHED.is_set():
            return
        reason = STOP["reason"] or "timeout"
        request_stop(reason)
        log(f"watchdog: {reason}; stopping owned Chrome so the operation unblocks")
        owned.stop_chrome()
        if FINISHED.wait(timeout=HARD_EXIT_GRACE_S):
            return
        log("watchdog: operation did not finish; tearing down and exiting")
        ok, elapsed = owned.cleanup()
        result["status"] = CANCELLED if reason == "cancelled" else TIMEOUT
        result["stop_reason"] = f"{reason}_hard"
        result["error"] = (
            f"operation {reason} after {config['timeout_ms']} ms and did not stop cleanly"
        )
        result.setdefault("warnings", []).extend(owned.warnings)
        result["cleanup_ok"] = ok
        result["cleanup_ms"] = elapsed
        emit(finalize(result, config))
        sys.stderr.flush()
        os._exit(0)

    thread = threading.Thread(target=body, name="watchdog", daemon=True)
    thread.start()
    return thread


def check_stop():
    if STOP["reason"]:
        raise Stopped(STOP["reason"])


# --------------------------------------------------------------------------
# result assembly
# --------------------------------------------------------------------------
def base_result(config):
    return {
        "op": config["op"],
        "status": None,
        "stop_reason": None,
        "text": None,
        "steps": 0,
        "output": {},
        "usage": None,
        "cost": None,
        "cost_detail": None,
        "screenshot_path": None,
        "artifact_dir": str(config["artifact_dir"]),
        "profile_dir": str(config["profile_dir"]),
        "profile": config["profile"],
        "model": DECISION_MODEL,
        "resolved_model": None,
        "helper_model": HELPER_MODEL,
        "resolved_helper_model": None,
        "duration_ms": None,
        "warnings": [],
        "error": None,
        # Declared DOM checks, filled in by run_operation or finalize. Never
        # the same field as output["verification"], which stays "not_performed".
        "verification": None,
        # Safety metadata. observation/side_effects/handoff stay null until the
        # agent exists: a run that failed before launch has nothing to describe
        # and must not invent an observation. confidence_policy is the policy
        # that was applied, known from the request, never a measured accuracy.
        "observation": None,
        "side_effects": None,
        "handoff": None,
        "confidence_policy": config.get("confidence") if config["op"] == "run" else None,
        "upstream_commit": UPSTREAM_COMMIT,
        "deviations": list(DEVIATIONS),
    }


def finalize(result, config):
    if config["op"] == "run":
        # A run that ended before the checks could run still reports them, as
        # unknown rows: silence would read like "nothing was declared".
        if not isinstance(result.get("verification"), dict):
            result["verification"] = dom_checks.verification_payload(
                config.get("checks") or [], reason="verification_not_attempted"
            )
        result["usage"] = usage_summary()
        cost, detail = cost_summary()
        result["cost"] = cost
        result["cost_detail"] = detail
        result["resolved_model"] = resolved_model_for("decision")
        result["resolved_helper_model"] = resolved_model_for("helper")
        shapes = [a["helper_shape"] for a in HTTP_ATTEMPTS if a.get("helper_shape")]
        result["helper_shapes"] = shapes or None
    else:
        result["usage"] = None
        result["cost"] = 0.0
        result["cost_detail"] = {"basis": "no_model_calls", "note": "login makes no model requests"}
    result["e2e_duration_ms"] = round((time.perf_counter() - PROC_T0) * 1000)
    try:
        path = Path(config["artifact_dir"]) / "result.json"
        path.write_text(redact(json.dumps(result, indent=2, default=str)))
        os.chmod(path, FILE_MODE)
    except OSError as exc:
        log(f"could not write result.json: {exc}")
    return result


def valid_png(path):
    """True when path is an absolute, existing file whose bytes are a real PNG."""
    if not path:
        return False
    candidate = Path(path)
    if not candidate.is_absolute() or not candidate.is_file():
        return False
    try:
        with open(candidate, "rb") as handle:
            return handle.read(len(PNG_SIGNATURE)) == PNG_SIGNATURE
    except OSError:
        return False


def classify(exc):
    """Map an upstream failure onto an honest status, preserving its message."""
    message = str(exc)
    name = type(exc).__name__
    if name == "MissingCredentials":
        return CREDENTIALS_ERROR
    if name == "Stopped":
        return CANCELLED if message == "cancelled" else TIMEOUT
    if isinstance(exc, ValueError):
        if "TypeSafe" in message or "Text helper" in message:
            return PROTOCOL_ERROR
        if "budget" in message:
            return MAX_STEPS
        if "TEXT_MODEL_API_KEY" in message:
            return PROVIDER_ERROR
    if isinstance(exc, RuntimeError) and message.startswith("Model "):
        return PROVIDER_ERROR
    # The executor withheld the next input on purpose. It is not a browser
    # failure, and the caller must inspect the page instead of retrying.
    if name == "NeedsReview":
        return NEEDS_REVIEW
    if name == "StalePage":
        return BROWSER_ERROR
    return BROWSER_ERROR


# --------------------------------------------------------------------------
# declared DOM checks: read-only evidence, inside the caller's declared scope
# --------------------------------------------------------------------------
def verify_declared_checks(browser, checks):
    """Read the page once for the caller's declared checks. Never writes.

    One synchronous JavaScript read returns observed values; every comparison
    happens here. The expectation itself is never sent into the page. A read
    that cannot run at all reports every declared check unknown, never failed,
    and never raises: verification is evidence, so it must not be able to
    replace the run's own outcome or its artifacts.

    The exception type is logged, never its message: a CDP error can quote the
    expression, and nothing about a declared check belongs in a log.
    """
    if not checks:
        return dom_checks.verification_payload([])
    try:
        payload = browser.evaluate(dom_checks.read_expression(checks))
    except Exception as exc:
        log(f"declared DOM checks could not be read: {type(exc).__name__}")
        return dom_checks.verification_payload(
            checks, reason="page_unavailable", redact=redact
        )
    return dom_checks.verification_payload(checks, payload=payload, redact=redact)


def note_verification(result):
    """A warning when a declared check did not pass. The status is unchanged."""
    payload = result.get("verification")
    if not isinstance(payload, dict) or payload.get("status") in (None, "passed", "not_run"):
        return
    counts = payload.get("counts") or {}
    result["warnings"].append(
        "declared DOM checks did not all pass: "
        f"{counts.get('passed', 0)} passed, {counts.get('failed', 0)} failed, "
        f"{counts.get('unknown', 0)} unknown; a completed status is still only an "
        "executor claim"
    )


# --------------------------------------------------------------------------
# operations
# --------------------------------------------------------------------------
def run_operation(config, owned, result):
    """Drive the vendored agent. Returns (stop_reason, error)."""
    artifact_dir = config["artifact_dir"]
    runtime_dir = Path(tempfile.mkdtemp(prefix="jv", dir="/tmp"))
    owned.runtime_dir = runtime_dir
    configure_environment(config, artifact_dir, runtime_dir)
    keep_daemon_in_process_group()

    port = launch_chrome(config["profile_dir"], artifact_dir, headless=True, owned=owned)
    os.environ["BU_CDP_URL"] = f"http://127.0.0.1:{port}"
    install_provider_patch()

    from jev_ultrafast import Agent
    from jev_ultrafast.agent import NeedsReview

    check_stop()
    start_private_daemon(owned, artifact_dir, os.environ["BU_NAME"])
    check_stop()

    # Count only: a supplied value is never written to stderr, the result, or an artifact.
    log(f"supplied_values={len(config['values'] or {})} generation={config['generation']}")
    log(f"confidence_policy={sorted(config['confidence'] or {})} checks={len(config['checks'] or [])}")

    def budget_guard():
        """Called inside the agent after each model call and before any input.

        An uncosted or over-budget call therefore cannot bind a value, cannot
        call the text helper and cannot type. The overshoot is what the
        upstream retry policy may already have spent inside the one logical
        call that is in flight, which is up to three HTTP attempts, not a bind
        plus a helper plus a typed field.
        """
        check_stop()
        if successful_attempts_without_cost():
            raise Stopped(COST_UNKNOWN)
        if known_cost() > config["max_cost_usd"]:
            raise Stopped(COST_LIMIT)

    agent = Agent(
        config["url"], config["task"], values=config["values"], generation=config["generation"],
        # None and {} both mean "record the scores, withhold nothing".
        confidence=config["confidence"],
        budget_guard=budget_guard,
        # The A seam. A non-empty list lets the executor take DONE on truncated
        # evidence, provisionally: this runner still refuses to call that run
        # completed unless every declared check actually passed, below.
        checks=config["checks"],
    )
    stop_reason = None
    error = None
    final_state = None
    handoff = None
    review_dispatch = None
    try:
        generator = agent.run()
        for state in generator:
            final_state = state
            steps = len(state["history"])
            log(f"step={steps} status={state['status']} elapsed={state['elapsed_ms']}ms url={state['page']['url'][:80]}")
            check_stop()
            if state["status"] in {"done", "blocked", "needs_review"}:
                stop_reason = state["status"]
                break
            if steps >= config["max_steps"]:
                stop_reason = MAX_STEPS
                break
            # Backstop only: budget_guard already stopped the run before input.
            if successful_attempts_without_cost():
                stop_reason = COST_UNKNOWN
                break
            if known_cost() > config["max_cost_usd"]:
                stop_reason = COST_LIMIT
                break
        generator.close()
    except NeedsReview as exc:
        # The executor refused the next input on purpose. That is not a browser
        # failure, so it must not be classified as one, and the partial history
        # stays exactly as it was recorded.
        stop_reason = NEEDS_REVIEW
        error = None
        handoff = getattr(exc, "handoff", None)
        review_dispatch = getattr(exc, "input_dispatched", None)
        log(f"agent withheld input: {getattr(exc, 'reason', NEEDS_REVIEW)}")
    except Stopped as exc:
        stop_reason = str(exc)
        error = None
    except Exception as exc:  # upstream failure; the message is preserved verbatim
        error = exc
        stop_reason = "exception"
        log(f"agent raised: {type(exc).__name__}: {exc}")

    # The generator yields only at the end of a tick, so a raise leaves
    # final_state describing the previous tick's page. Re-read the agent's
    # in-memory state so observation and handoff describe the page it stopped
    # on. snapshot() does not call CDP; safe_snapshot already swallows failures.
    live_state = safe_snapshot(agent)
    if live_state is not None:
        final_state = live_state
    elif final_state is None:
        final_state = {}

    # Declared DOM checks run here: after execution, before teardown, and
    # before the screenshot, so a capture failure cannot destroy evidence that
    # was already readable. They run after a partial stop too (blocked,
    # max_steps, cost limit, timeout, cancellation), because a stopped run is
    # exactly when a caller needs to know what the page actually shows. They
    # are read-only, so running them after a failure changes nothing.
    if config["checks"]:
        try:
            if owned.chrome is not None and owned.chrome.poll() is None:
                result["verification"] = verify_declared_checks(agent.browser, config["checks"])
            else:
                result["verification"] = dom_checks.verification_payload(
                    config["checks"], reason="browser_unavailable"
                )
        except Exception as exc:  # evidence never breaks the run or its artifacts
            log(f"declared DOM checks failed to run: {type(exc).__name__}")
            result["verification"] = dom_checks.verification_payload(
                config["checks"], reason="page_unavailable"
            )
        note_verification(result)

    # Native PNG while the browser is still alive. Best effort after a failure,
    # and it can never overwrite the primary failure.
    if owned.chrome is not None and owned.chrome.poll() is None:
        try:
            result["screenshot_path"] = capture_png(agent.browser.session, artifact_dir / "final.png")
        except Exception as exc:
            result["warnings"].append(f"screenshot failed: {type(exc).__name__}: {exc}")
    else:
        result["warnings"].append("screenshot skipped: the owned browser was no longer running")

    page = (final_state or {}).get("page") or {}
    history = (final_state or {}).get("history") or []
    elapsed = (final_state or {}).get("elapsed_ms")

    # A DONE taken on an observation the snapshot itself reported as truncated
    # is provisional. Declared checks being present is not evidence; only every
    # declared check actually passing is. A failed, unknown or missing
    # verification keeps the partial result and stops at needs_review, and the
    # completion claim below is cleared with it.
    if stop_reason == "done" and completion_was_provisional(final_state, page):
        if all_declared_checks_passed(result.get("verification")):
            result["warnings"].append(
                "the executor claimed DONE on a truncated observation; every declared DOM check "
                "passed, which is scoped page evidence only, not proof the whole task finished "
                "or that a server stored anything"
            )
        else:
            stop_reason = NEEDS_REVIEW
            # The evidence reason, as an enum. The counts stay where they were
            # measured, in result["verification"].
            handoff = {"reason": "truncated_done_checks_not_passed"}
            review_dispatch = NOT_DISPATCHED
            result["warnings"].append(
                "the executor claimed DONE on a truncated observation and the declared DOM checks "
                "did not all pass; the completion claim was withheld"
            )
            log("truncated DONE withheld: declared checks did not all pass")

    result["steps"] = len(history)
    result["duration_ms"] = elapsed if elapsed else (None if not history else elapsed)
    result["output"] = {
        "final_url": page.get("url"),
        "final_title": page.get("title"),
        "page_text": (page.get("text") or "")[:4000],
        "completion_claimed": stop_reason == "done",
        "verification": "not_performed",
    }
    result["text"] = (
        f"jev finished with upstream status {(final_state or {}).get('status')!r} after {len(history)} action(s); "
        f"final url {page.get('url')}"
    )
    result["actions"] = action_rows(history)

    # Safety metadata on every path that reached the agent, partial results
    # included. Only the last observation, never live browser state. With no
    # page at all there is nothing to describe, and a default observation would
    # be an invention.
    result["observation"] = observation_of(page) if page else None
    result["side_effects"] = side_effects_of(history)
    if stop_reason == "done":
        result["handoff"] = None
    else:
        if error is not None:
            # An unclassified upstream failure does not prove where it stopped.
            dispatched = UNKNOWN_DISPATCH
        elif review_dispatch is not None:
            dispatched = review_dispatch
        else:
            dispatched = stopping_dispatch(final_state)
        reason = (handoff or {}).get("reason") or (
            (final_state or {}).get("review_reason") if stop_reason == NEEDS_REVIEW else stop_reason
        )
        fields = dict(decision_fields(final_state))
        for key in ("choice", "operation", "operation_confidence", "target", "target_confidence",
                    "binding_key", "binding_confidence"):
            if isinstance(handoff, dict) and handoff.get(key) is not None:
                fields[key] = handoff[key]
        result["handoff"] = build_handoff(reason, page, fields, dispatched)
    return stop_reason, error


ACTION_FIELDS = (
    "step", "kind", "action", "operation", "probability", "confidence", "page_changed",
    "value_key", "value_source",
    # confidence stays the operation score, as in the previous release.
    # operation_confidence is the same number under a name that matches the others.
    "operation_confidence", "target_confidence", "binding_confidence", "dispatch",
)


def action_rows(history):
    """Reported actions. Which value was used, never the text that was typed."""
    return [{k: h.get(k) for k in ACTION_FIELDS} for h in history]


# --------------------------------------------------------------------------
# safety metadata: observation, side effects, handoff
# --------------------------------------------------------------------------
NOT_DISPATCHED = "not_dispatched"
ATTEMPTED = "attempted"
UNKNOWN_DISPATCH = "unknown"
DISPATCH_VALUES = (NOT_DISPATCHED, ATTEMPTED, UNKNOWN_DISPATCH)

NONE_OBSERVED = "none_observed"
UNCERTAIN = "uncertain"

RESUME_POLICY = "inspect current state; never replay this decision or any uncertain input"
# Only these keys, in this order. Nothing else is copied into a handoff.
HANDOFF_FIELDS = (
    "reason", "choice", "operation", "operation_confidence", "target", "target_confidence",
    "binding_key", "binding_confidence", "observation", "input_dispatched", "resume_policy",
)
# Stable identifiers the executor produced: action ids, operation names, target
# indexes, supplied-value keys and reason enums. A label, a task, a page string,
# a typed value or anything with whitespace cannot match this.
HANDOFF_ID_RE = re.compile(r"\A[A-Za-z0-9_:.-]{1,120}\Z")


def handoff_id(value):
    """A short stable identifier, or None. Never a label, value or free text."""
    return value if isinstance(value, str) and HANDOFF_ID_RE.match(value) else None


def handoff_score(value):
    """A finite score in [0, 1], or None. Never a bool and never a string."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= 1 else None


def observation_of(page):
    """Allowlisted snapshot metadata for the last page, or None.

    Never page text, element values, page_key, guards or marker: page_key
    carries live field values, and the marker carries the visible text.
    """
    if not isinstance(page, dict):
        return None
    omitted = page.get("omitted_actions")
    viewport = {}
    for key in ("w", "h"):
        size = page.get(key)
        viewport[key] = size if isinstance(size, int) and not isinstance(size, bool) else None
    return {
        "omitted_actions": int(omitted) if isinstance(omitted, int) and not isinstance(omitted, bool) else 0,
        "text_truncated": bool(page.get("text_truncated")),
        "viewport": viewport,
        "fingerprint": handoff_id(page.get("fingerprint")),
    }


def side_effects_of(history):
    """none_observed or uncertain. Never confirmed.

    "none_observed" says no click, fill, select or scroll in this run reached
    Browser.act after a passing freshness check. It is not a promise that the
    page produced no backend effect: a navigation alone can load an endpoint.
    "uncertain" is the answer for anything that reached input, including a fill
    whose value reads back correctly, because typing proves what was typed and
    never what was stored. A row whose dispatch cannot be read is uncertain: an
    unrecognised row is not evidence that nothing was sent.
    """
    if not isinstance(history, list):
        return UNCERTAIN
    for row in history:
        if not isinstance(row, dict) or row.get("dispatch") != NOT_DISPATCHED:
            return UNCERTAIN
    return NONE_OBSERVED


LATEST_DISPATCH = "latest_dispatch"
DECISION_SEQ = "decision_seq"


def stopping_dispatch(final_state):
    """Was input dispatched for the decision this run stopped on?

    The executor answers this itself. It records what the decision it is
    executing has sent in ``latest_dispatch``, before every step that can
    raise, and names that decision with the same monotonic ``decision_seq``
    the decision record and its history row carry. This function only reads
    that record, and only after checking it describes the last decision.

    Row counts cannot answer it. A pre-input StalePage consumes a decision and
    appends no row, because browser.py raises before any CDP input, so "one
    row fewer than decisions" describes a dispatched click followed by a
    budget stop on a later decision exactly as it describes a run that sent
    nothing at all.

    When the record is missing, unreadable, or describes some other decision,
    the answer is "unknown", never "not_dispatched": an unreadable record is
    not proof that nothing was sent.
    """
    if not isinstance(final_state, dict):
        return UNKNOWN_DISPATCH
    decisions = final_state.get("decisions")
    record = final_state.get(LATEST_DISPATCH)
    if not isinstance(decisions, list) or not decisions or not isinstance(record, dict):
        return UNKNOWN_DISPATCH
    seq = record.get(DECISION_SEQ)
    if isinstance(seq, bool) or not isinstance(seq, int) or seq <= 0:
        return UNKNOWN_DISPATCH
    last = decisions[-1]
    if not isinstance(last, dict) or last.get(DECISION_SEQ) != seq:
        return UNKNOWN_DISPATCH
    value = record.get("dispatch")
    return value if value in DISPATCH_VALUES else UNKNOWN_DISPATCH


def decision_fields(final_state):
    """Allowlisted scalars from the last decision. Never its request body."""
    decisions = (final_state or {}).get("decisions") if isinstance(final_state, dict) else None
    last = decisions[-1] if isinstance(decisions, list) and decisions else None
    if not isinstance(last, dict):
        return {}
    return {
        "choice": last.get("choice"),
        "operation": last.get("operation"),
        "operation_confidence": last.get("confidence"),
        "target": last.get("target"),
        "target_confidence": last.get("target_confidence"),
    }


def build_handoff(reason, page, fields=None, input_dispatched=UNKNOWN_DISPATCH):
    """What a parent model may read before it re-plans. Allowlist only.

    Stable ids, an enum reason, scores, the truncation and viewport flags and
    the page fingerprint. No task, no supplied values, no labels (an input
    label can echo a value), no previews, no page text, no screenshot, no
    page_key, guards or marker, no credentials, no raw provider body and no CDP
    session or target id. Scalars are validated here; a nested object other
    than the observation this function builds is never copied in. This is a
    record to inspect, not a session to resume: the profile directory persists,
    but a later jev.run is a new process, a new observation and a new decision.
    """
    fields = fields if isinstance(fields, dict) else {}
    handoff = {
        "reason": handoff_id(reason) or "unknown",
        "choice": handoff_id(fields.get("choice")),
        "operation": handoff_id(fields.get("operation")),
        "operation_confidence": handoff_score(fields.get("operation_confidence")),
        "target": handoff_id(fields.get("target")),
        "target_confidence": handoff_score(fields.get("target_confidence")),
        "binding_key": handoff_id(fields.get("binding_key")),
        "binding_confidence": handoff_score(fields.get("binding_confidence")),
        "observation": observation_of(page),
        "input_dispatched": (
            input_dispatched if input_dispatched in DISPATCH_VALUES else UNKNOWN_DISPATCH
        ),
        "resume_policy": RESUME_POLICY,
    }
    return {key: handoff[key] for key in HANDOFF_FIELDS}


def all_declared_checks_passed(payload):
    """True only when every declared DOM check was read and passed.

    Scope is still the declared DOM only: this says the caller's own assertions
    matched the page, never that the task finished or that a server stored
    anything.
    """
    if not isinstance(payload, dict) or payload.get("status") != "passed":
        return False
    rows = payload.get("checks")
    if not isinstance(rows, list) or not rows or len(rows) != payload.get("declared"):
        return False
    return all(isinstance(row, dict) and row.get("status") == "passed" for row in rows)


def completion_was_provisional(final_state, page):
    """True when the executor took DONE on evidence it reported as truncated."""
    if isinstance(final_state, dict) and final_state.get("provisional_done"):
        return True
    if not isinstance(page, dict):
        return False
    omitted = page.get("omitted_actions")
    return bool(page.get("text_truncated")) or bool(
        isinstance(omitted, int) and not isinstance(omitted, bool) and omitted > 0
    )


def safe_snapshot(agent):
    try:
        return agent.snapshot()
    except Exception:
        try:
            return {k: v for k, v in agent.state.items() if k != "browser"}
        except Exception:
            return None


def login_operation(config, owned, result):
    """Headed sign-in on a named profile. No model calls, no credentials read."""
    port = launch_chrome(
        config["profile_dir"], config["artifact_dir"], headless=False, owned=owned, start_url=config["url"]
    )
    log("headed browser open; sign in, then close every window of this profile")
    deadline = PROC_T0 + config["timeout_ms"] / 1000.0
    seen_page = False
    empty_polls = 0
    stop_reason = "timeout"
    while time.perf_counter() < deadline:
        check_stop()
        if owned.chrome.poll() is not None:
            stop_reason = "closed"
            break
        targets = page_targets(port)
        if targets is None:
            empty_polls += 1 if seen_page else 0
        elif targets:
            seen_page = True
            empty_polls = 0
        elif seen_page:
            empty_polls += 1
        if empty_polls >= 2:
            stop_reason = "closed"
            break
        time.sleep(LOGIN_POLL_S)

    if not seen_page and stop_reason == "closed":
        result["warnings"].append("no page target was ever observed for this profile")
    profile_dir = config["profile_dir"]
    persisted = (profile_dir / "Default").is_dir() or (profile_dir / "Local State").exists()
    if not persisted:
        result["warnings"].append("no Chrome profile state was written to the profile directory")
    result["steps"] = 0
    result["duration_ms"] = round((time.perf_counter() - PROC_T0) * 1000)
    result["screenshot_path"] = None
    result["output"] = {
        "authenticated": None,
        "windows_closed": stop_reason == "closed",
        "profile_state_written": bool(persisted),
        "verification": "not_performed",
    }
    result["text"] = (
        "login session ended after the profile windows closed"
        if stop_reason == "closed"
        else "login session timed out while the profile windows were still open"
    )
    return stop_reason, None


def decide_status(op, stop_reason, error, result, cleanup_ok):
    if error is not None:
        return classify(error)
    if op == "login":
        if stop_reason == "closed":
            return COMPLETED if cleanup_ok else CLEANUP_ERROR
        return CANCELLED if stop_reason == "cancelled" else TIMEOUT
    if stop_reason == "done":
        output = result.get("output") or {}
        if output.get("completion_claimed") is not True or output.get("verification") != "not_performed":
            return INTERNAL_ERROR
        if not valid_png(result.get("screenshot_path")):
            return ARTIFACT_ERROR
        if not cleanup_ok:
            return CLEANUP_ERROR
        return COMPLETED
    return {
        "blocked": BLOCKED,
        MAX_STEPS: MAX_STEPS,
        COST_LIMIT: COST_LIMIT,
        COST_UNKNOWN: COST_UNKNOWN,
        NEEDS_REVIEW: NEEDS_REVIEW,
        "timeout": TIMEOUT,
        "cancelled": CANCELLED,
    }.get(stop_reason, BROWSER_ERROR)


DEFAULT_MESSAGES = {
    BLOCKED: "the agent reported BLOCKED or made no progress for three consecutive actions",
    MAX_STEPS: "stopped at the requested max_steps",
    COST_LIMIT: "stopped at the requested max_cost_usd",
    COST_UNKNOWN: "a successful model request reported no cost, so the budget could not be enforced",
    NEEDS_REVIEW: (
        "the executor withheld the next input; inspect the current page before any retry and do "
        "not replay this decision or any uncertain input (see result['handoff'])"
    ),
    TIMEOUT: "the operation exceeded timeout_ms",
    CANCELLED: "the operation was cancelled",
    ARTIFACT_ERROR: "the agent reported DONE but no valid native PNG screenshot exists at an absolute path",
    CREDENTIALS_ERROR: "OPENROUTER_API_KEY is required for the run operation",
    LAUNCH_ERROR: "the runner must be started as its own process group leader",
    INTERNAL_ERROR: "the result failed its own completion invariants",
    PROTOCOL_ERROR: "the model provider returned a response the upstream validator rejected",
    PROVIDER_ERROR: "the model provider request failed",
    PROFILE_BUSY: "another Jev process owns this profile directory",
    CLEANUP_ERROR: "the operation finished but an owned process survived cleanup",
    BROWSER_ERROR: "the browser session failed",
}


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def main():
    config = None
    result = None
    owned = OwnedProcesses()
    lock = None
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise RequestError("empty stdin; expected one JSON request object")
        try:
            request = json.loads(raw)
        except ValueError as exc:
            raise RequestError(f"stdin is not valid JSON: {exc}") from None
        if not isinstance(request, dict):
            raise RequestError("stdin JSON must be an object")
        register_secrets()
        # Never inherit a browser endpoint from the caller's environment.
        for inherited in ("BU_CDP_WS", "BU_CDP_URL", "BU_BROWSER_ID"):
            os.environ.pop(inherited, None)
        config = normalize(request)
        artifact_dir = config["artifact_dir"]
        artifact_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(artifact_dir, DIR_MODE)
        result = base_result(config)
        install_signal_handlers()
        # Checked before any browser or daemon is started.
        require_process_group_leadership()
        lock = ProfileLock(config["profile_dir"]).acquire()
        start_watchdog(config, owned, result)
        log(f"op={config['op']} run_id={config['run_id']} profile={config['profile']} artifacts={artifact_dir}")
        operation = run_operation if config["op"] == "run" else login_operation
        stop_reason, error = operation(config, owned, result)
    except RequestError as exc:
        FINISHED.set()
        payload = result or {"op": None, "warnings": []}
        payload.update(status=INVALID_REQUEST, stop_reason="invalid_request", error=str(exc))
        if config is None:
            payload.update(cost=None, usage=None, steps=0, screenshot_path=None, output={})
            emit(payload)
            return 0
        emit(finalize(payload, config))
        return 0
    except LaunchError as exc:
        FINISHED.set()
        result.update(status=LAUNCH_ERROR, stop_reason="launch_error", error=str(exc))
        emit(finalize(result, config))
        return 0
    except ProfileBusy as exc:
        FINISHED.set()
        result.update(status=PROFILE_BUSY, stop_reason="profile_busy", error=str(exc))
        emit(finalize(result, config))
        return 0
    except Stopped as exc:
        stop_reason, error = str(exc), None
    except Exception as exc:
        log(f"unexpected failure: {type(exc).__name__}: {exc}")
        traceback.print_exc(file=sys.stderr)
        stop_reason, error = "exception", exc
        if result is None:
            FINISHED.set()
            emit(
                {
                    "op": None,
                    "status": BROWSER_ERROR,
                    "error": f"{type(exc).__name__}: {exc}",
                    "cost": None,
                    "usage": None,
                    "steps": 0,
                    "screenshot_path": None,
                    "output": {},
                    "warnings": [],
                }
            )
            return 0

    # Cleanup owns every process this runner started, and it runs before the
    # profile lock is released so no other Jev process can start too early.
    cleanup_ok, cleanup_ms = owned.cleanup()
    FINISHED.set()
    if lock is not None:
        lock.release()
    result["warnings"].extend(owned.warnings)
    result["cleanup_ok"] = cleanup_ok
    result["cleanup_ms"] = cleanup_ms
    status = decide_status(config["op"], stop_reason, error, result, cleanup_ok)
    result["status"] = status
    result["stop_reason"] = stop_reason
    if error is not None:
        result["error"] = redact(f"{type(error).__name__}: {error}")
        detail = last_provider_message()
        if detail:
            # Upstream discards the provider body; keep its own message first and
            # append what the provider actually said.
            result["provider_detail"] = detail
            result["error"] = f"{result['error']} | provider response: {detail}"
    elif status != COMPLETED and not result.get("error"):
        result["error"] = DEFAULT_MESSAGES.get(status, "the operation did not complete")
    emit(finalize(result, config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
