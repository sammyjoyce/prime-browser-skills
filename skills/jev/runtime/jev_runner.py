#!/usr/bin/env python3
"""Jev-first entry point, reusing the tested runner's process/profile lifecycle.

runner.py remains the lifecycle compatibility module and historical executor.
The native skill launches this entry point; no upstream action policy is patched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

import runner as lifecycle
from jev_runtime.contracts import Halt, normalize_options
from jev_runtime.providers import Provider


def environment(config, owned):
    runtime_dir = Path(tempfile.mkdtemp(prefix="jv", dir="/tmp"))
    owned.runtime_dir = runtime_dir
    artifact_dir = config["artifact_dir"]
    os.environ.update({
        "BU_NAME": f"jev-{uuid.uuid4().hex[:12]}", "BH_HOME": str(artifact_dir / "harness"),
        "BH_RUNTIME_DIR": str(runtime_dir), "BH_TMP_DIR": str(artifact_dir / "harness-tmp"),
        "BH_AGENT_WORKSPACE": str(artifact_dir / "harness-workspace"), "BH_TELEMETRY": "0",
        "BROWSER_HARNESS_TELEMETRY": "0", "ANONYMIZED_TELEMETRY": "false", "DO_NOT_TRACK": "1",
    })
    for key in ("BU_CDP_WS", "BU_CDP_URL", "BU_BROWSER_ID"):
        os.environ.pop(key, None)


def main():
    config, result, lock, browser = None, None, None, None
    owned = lifecycle.OwnedProcesses()
    status, stop_reason, error = "internal_error", "exception", None
    try:
        raw = sys.stdin.read(150_001)
        if len(raw) > 150_000:
            raise Halt("invalid_request", "request exceeds 150000 characters")
        try:
            request = json.loads(raw)
        except ValueError:
            raise Halt("invalid_request", "stdin must contain one JSON request") from None
        if not isinstance(request, dict):
            raise Halt("invalid_request", "stdin JSON must be an object")
        lifecycle.register_secrets()
        config = lifecycle.normalize(request)
        if config["op"] == "run":
            config["options"] = normalize_options(request.get("options"), config["url"])
            if config["max_steps"] > 500 or config["timeout_ms"] > 86_400_000 or config["max_cost_usd"] > 100:
                raise Halt("invalid_request", "run limits exceed the public API limits")
        artifact_dir = config["artifact_dir"]
        artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(artifact_dir, 0o700)
        result = lifecycle.base_result(config)
        result["executor"] = "jev-first"
        result["helper_model"] = None
        result["deviations"] = [
            "Project-owned decision, observation, permission and verification modules; vendor remains unchanged.",
            "The existing lifecycle module owns Chrome, daemon, watchdog and profile locks.",
            "Exact values only; no text helper, provider fallback or automatic input replay.",
        ]
        lifecycle.require_process_group_leadership()
        lifecycle.install_signal_handlers()
        lock = lifecycle.ProfileLock(config["profile_dir"]).acquire()
        if config["op"] == "login":
            lifecycle.start_watchdog(config, owned, result)
            stop_reason, error = lifecycle.login_operation(config, owned, result)
            status = "completed" if stop_reason == "closed" else stop_reason
        else:
            settings = config["options"]["provider"]
            result["model"] = settings["model"]
            result["provider"] = settings["name"]
            provider = Provider(settings, attempts=lifecycle.HTTP_ATTEMPTS, logical_calls=lifecycle.LOGICAL_CALLS, check_stop=lifecycle.check_stop)
            lifecycle.start_watchdog(config, owned, result)
            environment(config, owned)
            lifecycle.keep_daemon_in_process_group()
            port = lifecycle.launch_chrome(config["profile_dir"], artifact_dir, headless=True, owned=owned)
            os.environ["BU_CDP_URL"] = f"http://127.0.0.1:{port}"
            lifecycle.check_stop()
            lifecycle.start_private_daemon(owned, artifact_dir, os.environ["BU_NAME"])
            lifecycle.check_stop()
            from jev_runtime.browser import ObservedBrowser
            from jev_runtime.engine import Engine
            browser = ObservedBrowser(config["url"], config["options"])
            engine = Engine(browser, provider, config, result, check_stop=lifecycle.check_stop)
            stop_reason = engine.run()
            status = "completed"
    except Halt as exc:
        status, stop_reason, error = exc.status, exc.status, str(exc)
    except lifecycle.RequestError as exc:
        status, stop_reason, error = "invalid_request", "invalid_request", str(exc)
    except lifecycle.LaunchError as exc:
        status, stop_reason, error = "launch_error", "launch_error", str(exc)
    except lifecycle.ProfileBusy as exc:
        status, stop_reason, error = "profile_busy", "profile_busy", str(exc)
    except lifecycle.Stopped as exc:
        status = "cancelled" if str(exc) == "cancelled" else "timeout"
        stop_reason, error = status, str(exc)
    except Exception as exc:
        status, stop_reason, error = "browser_error", "exception", f"{type(exc).__name__}: {exc}"
    finally:
        if result is None:
            result = {"op": None, "warnings": [], "steps":0,"cost":None,"usage":None,
                      "output":{},"screenshot_path":None}
        if browser is not None and owned.chrome is not None and owned.chrome.poll() is None:
            try:
                result["screenshot_path"] = lifecycle.capture_png(browser.session, config["artifact_dir"] / "final.png")
            except Exception as exc:
                result["warnings"].append(f"final screenshot failed: {type(exc).__name__}")
                if status == "completed":
                    status, error = "artifact_error", "completed execution produced no final PNG"
        # An unsafe launch has not started any owned child. Never signal the caller's group.
        if lock is not None:
            cleanup_ok, cleanup_ms = owned.cleanup()
        else:
            cleanup_ok, cleanup_ms = owned.chrome is None and owned.daemon is None, 0
        lifecycle.FINISHED.set()
        if lock is not None:
            lock.release()
        result["warnings"].extend(owned.warnings)
        result.update(cleanup_ok=cleanup_ok, cleanup_ms=cleanup_ms)
        if status == "completed" and not cleanup_ok:
            status, error = "cleanup_error", "owned browser processes survived cleanup"
        if status == "completed" and config["op"] == "run" and not lifecycle.valid_png(result.get("screenshot_path")):
            status, error = "artifact_error", "completed execution produced no final PNG"
        if lifecycle.STOP["reason"]:
            status = "cancelled" if lifecycle.STOP["reason"] == "cancelled" else "timeout"
            stop_reason, error = status, "operation stopped; inspect partial evidence before retrying"
        result.update(status=status, stop_reason=stop_reason, error=error)
        if config is not None:
            result = lifecycle.finalize(result, config)
        lifecycle.emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
