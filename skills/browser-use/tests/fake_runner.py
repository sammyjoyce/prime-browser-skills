"""Fake @browser_use/pi runner used by the browser_use Python unit tests.

Run as `<python> fake_runner.py` through the patched _node_bin/_runner_path
seams, so the real spawn/session/stdin/stdout/stderr/kill/lock machinery is
exercised without node, Chrome, or paid model calls.

Protocol: read exactly one JSON request from stdin, then behave according to
FAKE_RUNNER_MODE (default "ok"). LEAK_TEST_TOKEN is echoed by the modes that
exist to prove secret redaction.

This file is a real .py module (never an inline string) so a syntax error
shows up immediately instead of as a mysterious subprocess failure.
"""

import json
import os
import signal
import sys
import time


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def register_pid(art, name):
    """Publish this process's pid atomically: a reader never sees a partial file."""
    path = os.path.join(art, name)
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        handle.write(str(os.getpid()))
        handle.flush()
        os.fsync(handle.fileno())
    os.rename(tmp, path)


def main():
    raw = sys.stdin.read()
    try:
        req = json.loads(raw)
    except Exception:
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
            time.sleep(2)          # survive SIGTERM long enough to observe the lock
            os._exit(0)

        signal.signal(signal.SIGTERM, slow_term)
        register_pid(art, "runner.pid")
        time.sleep(30)
        return
    if mode == "grandchild":
        pid = os.fork()
        if pid == 0:
            # SIGTERM-ignoring descendant that outlives the leader and holds no
            # stdout pipe (redirected to devnull) so the leader exit is visible.
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
            register_pid(art, "grandchild.pid")
            time.sleep(60)
            os._exit(0)
        time.sleep(0.2)            # let the grandchild register
        sys.exit(0)                # leader exits without emitting JSON
    if mode == "garbage":
        sys.stdout.write("junk preamble with secret " + leak + "\n")
        sys.stdout.flush()
        sys.stderr.write("stderr noise " + leak + "\n")
        sys.stderr.flush()
        time.sleep(0.1)
        return
    if mode == "partial":
        sys.stdout.write("junk line before json\n")
        emit({"status": "completed", "output": {"via": "line-scan"}, "text": "t",
              "steps": 2, "cost": 0.01, "screenshot_path": None})
        return
    if mode == "exit1":
        emit({"status": "completed", "output": None, "text": "looks fine",
              "steps": 1, "cost": 0.01, "screenshot_path": None})
        sys.exit(1)
    if mode == "error":
        emit({"status": "error", "error": "boom " + leak, "text": "saw " + leak,
              "steps": 1, "cost": 0.01, "screenshot_path": None})
        return
    if mode == "runner_timeout":
        emit({"status": "timeout", "error": "task exceeded its timeout",
              "text": "", "steps": 2, "cost": 0.01, "screenshot_path": None})
        return
    if mode == "maxsteps":
        emit({"status": "max_steps", "text": "stopped early"})
        return
    if mode == "relshot":
        emit({"status": "completed", "output": None, "text": "fine",
              "steps": 1, "cost": 0.01, "screenshot_path": "relative/shot.png"})
        return
    if mode == "stderrnoise":
        sys.stderr.write("progress noise " + leak + "\n")
        sys.stderr.flush()

    shot = os.path.join(art, "final.png")
    with open(shot, "wb") as handle:
        handle.write(b"\x89PNG fake")
    emit({
        "status": "completed",
        "output": {
            "request": req,
            "pgid_is_self": os.getpgid(0) == os.getpid(),
            "model_env": os.environ.get("BROWSER_USE_MODEL"),
            "do_not_track": os.environ.get("DO_NOT_TRACK"),
        },
        "text": "all done",
        "steps": 4,
        "cost": 0.05,
        "duration_ms": 1234,
        "screenshot_path": shot,
    })


main()
