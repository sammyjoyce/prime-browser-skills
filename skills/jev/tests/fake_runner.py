"""Fake jev runtime runner used by the jev wrapper unit tests.

Run as `<python> fake_runner.py` through the patched _launch_command seam, so
the real spawn/session/stdin/stdout/stderr/kill/lock machinery is exercised
without uv, Chrome, a provider key, or paid model calls.

Protocol: read exactly one JSON request from stdin, then behave according to
FAKE_RUNNER_MODE (default "ok"). LEAK_TEST_TOKEN is echoed by the modes that
exist to prove secret redaction.

This file is a real ASCII .py module (never an inline string) so a syntax
error shows up immediately instead of as a mysterious subprocess failure.
"""

import json
import os
import signal
import sys
import time

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def register_pid(art, name, pid=None):
    """Publish a pid atomically: a reader never sees a partial file."""
    path = os.path.join(art, name)
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        handle.write(str(os.getpid() if pid is None else pid))
        handle.flush()
        os.fsync(handle.fileno())
    os.rename(tmp, path)


def write_png(art, name="final.png", data=None):
    path = os.path.join(art, name)
    with open(path, "wb") as handle:
        handle.write((PNG_MAGIC + b"\x00\x00\x00\rIHDR fake") if data is None else data)
    return path


def ok_result(req, art, **overrides):
    result = {
        "status": "completed",
        "output": {
            "final_url": "https://example.test/done",
            "final_title": "Done",
            "page_text": "page text " + os.environ.get("LEAK_TEST_TOKEN", ""),
            "completion_claimed": True,
            "verification": "not_performed",
            "request": req,
            "env_probe": {
                "pgid_is_self": os.getpgid(0) == os.getpid(),
                "do_not_track": os.environ.get("DO_NOT_TRACK"),
                "anonymized_telemetry": os.environ.get("ANONYMIZED_TELEMETRY"),
                "bh_telemetry": os.environ.get("BH_TELEMETRY"),
                "bu_cdp_url": os.environ.get("BU_CDP_URL"),
                "bh_home": os.environ.get("BH_HOME"),
                "openrouter_key_present": bool(os.environ.get("OPENROUTER_API_KEY")),
            },
        },
        "text": "jev terminal status=done actions=4",
        "steps": 4,
        "cost": 0.0123,
        "cost_detail": {"basis": "http_attempts", "attempts_with_cost": 2},
        "usage": {"decision": {"logical_requests": 2}},
        "model": "jev-latest",
        "resolved_model": "typesafe/jev-latest-2026-09",
        "helper_model": "inception/mercury-2.5",
        "duration_ms": 4321,
        "stop_reason": "done",
        "warnings": ["viewport override applied"],
        "screenshot_path": write_png(art),
    }
    result.update(overrides)
    return result


def spawn_child(art, name, seconds=60):
    """Fork a long-lived SIGTERM-ignoring descendant in the runner's group."""
    pid = os.fork()
    if pid == 0:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
        register_pid(art, name)
        time.sleep(seconds)
        os._exit(0)
    return pid


def main():
    raw = sys.stdin.read()
    try:
        req = json.loads(raw)
    except ValueError:
        req = {}
    mode = os.environ.get("FAKE_RUNNER_MODE", "ok")
    art = req.get("artifact_dir") or "."
    leak = os.environ.get("LEAK_TEST_TOKEN", "")

    if mode == "hang":
        register_pid(art, "runner.pid")
        time.sleep(30)
        emit({"status": "completed", "output": None, "text": "late"})
        return
    if mode == "hang_sigterm":
        def slow_term(signum, frame):
            time.sleep(2)  # survive SIGTERM long enough to observe the lock
            os._exit(0)

        signal.signal(signal.SIGTERM, slow_term)
        register_pid(art, "runner.pid")
        time.sleep(30)
        return
    if mode == "grandchild":
        # SIGTERM-ignoring descendant in the runner's own process group that
        # outlives the leader: only a group SIGKILL clears it.
        spawn_child(art, "grandchild.pid")
        time.sleep(0.3)
        sys.exit(0)  # leader exits without emitting JSON
    if mode == "leftover":
        # Clean result, but a SIGTERM-ignoring descendant is still running in
        # the runner's process group: the wrapper must kill it anyway.
        spawn_child(art, "leftover.pid")
        time.sleep(0.2)
        emit(ok_result(req, art))
        return
    if mode == "garbage":
        sys.stdout.write("junk preamble with secret " + leak + "\n")
        sys.stdout.flush()
        sys.stderr.write("stderr noise " + leak + "\n")
        sys.stderr.flush()
        time.sleep(0.1)
        return
    if mode == "partial":
        sys.stdout.write("junk line before json\n")
        emit(ok_result(req, art))
        return
    if mode == "exit1":
        emit(ok_result(req, art))
        sys.exit(1)
    if mode == "error":
        emit({"status": "error", "error": "boom " + leak, "text": "saw " + leak,
              "steps": 1, "cost": 0.02, "screenshot_path": None})
        return
    if mode == "runner_timeout":
        emit({"status": "timeout", "error": "wrapper timeout after 1234 ms",
              "text": "", "steps": 2, "cost": None, "screenshot_path": None})
        return
    if mode == "cost_unknown":
        emit({"status": "cost_unknown", "text": "stopped: spend could not be measured",
              "steps": 3, "cost": None,
              "cost_detail": {"note": "a successful provider attempt reported no cost"}})
        return
    if mode == "maxsteps":
        emit({"status": "max_steps", "text": "stopped early", "steps": 2, "cost": 0.03})
        return
    if mode == "relshot":
        emit(ok_result(req, art, screenshot_path="relative/shot.png"))
        return
    if mode == "noshot":
        emit(ok_result(req, art, screenshot_path=None))
        return
    if mode == "missingshot":
        emit(ok_result(req, art, screenshot_path=os.path.join(art, "gone.png")))
        return
    if mode == "jpegshot":
        path = write_png(art, "final.jpg", data=b"\xff\xd8\xff\xe0 jpeg not png")
        emit(ok_result(req, art, screenshot_path=path))
        return
    if mode == "verified":
        emit(ok_result(req, art, verified=True))
        return
    if mode == "verification_claim":
        result = ok_result(req, art)
        result["output"]["verification"] = "verified"
        emit(result)
        return
    if mode == "no_output":
        emit(ok_result(req, art, output=None))
        return
    if mode == "missing_claim":
        result = ok_result(req, art)
        del result["output"]["completion_claimed"]
        emit(result)
        return
    if mode == "unclaimed":
        result = ok_result(req, art)
        result["output"]["completion_claimed"] = False
        emit(result)
        return
    if mode == "badwarnings":
        emit(ok_result(req, art, warnings=["fine", 7]))
        return
    if mode == "badcost":
        emit(ok_result(req, art, cost="0.01"))
        return
    if mode.startswith("login"):
        result = {
            "status": "completed",
            "output": {"authenticated": None, "verification": "not_performed",
                       "request": req},
            "text": "login window closed", "steps": 0, "cost": 0,
            "stop_reason": "window_closed", "screenshot_path": None,
        }
        if mode == "login_nocost":
            result["cost"] = None
        elif mode == "login_spent":
            result["cost"] = 0.07
        elif mode == "login_steps":
            result["steps"] = 3
        elif mode == "login_claims_auth":
            result["output"]["authenticated"] = True
        elif mode == "login_shot":
            result["screenshot_path"] = write_png(art)
        emit(result)
        return
    if mode == "stderrnoise":
        sys.stderr.write("progress noise " + leak + "\n")
        sys.stderr.flush()

    emit(ok_result(req, art))


main()
