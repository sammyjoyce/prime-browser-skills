"""Integration checks against the real runtime project at <skill>/runtime.

These prove the launch contract itself: that the installed runtime
interpreter is the leader of the process group the wrapper kills, and that
the run path fails typed and early when no provider key is present. No model
request and no paid call happens here: the runner checks OPENROUTER_API_KEY
before it starts a browser, and every call is guarded by an explicit
"no key is set" assertion first.

Skipped automatically until `uv sync --project runtime --frozen` has
installed the runtime interpreter.

    cd skills/jev   # or ~/.prime/agent/skills/jev once installed
    uv run python -m unittest discover -s tests -v
"""

import asyncio
import json
import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import jev
from jev import JevError, run

RUNTIME_AVAILABLE = jev._runner_path().is_file() and os.access(
    jev._runtime_python(), os.X_OK
)

# Printed by the probe below: one JSON line, then a sleep, so the launcher's
# process-group behaviour can be observed while the interpreter is alive.
PROBE_SOURCE = (
    "import json, os, sys, time; "
    "sys.stdout.write(json.dumps({'pid': os.getpid(), 'pgid': os.getpgid(0), "
    "'ppid': os.getppid(), 'sid': os.getsid(0)}) + chr(10)); "
    "sys.stdout.flush(); time.sleep(30)"
)
PROBE_START_S = 60.0  # interpreter startup only; uv is not in this path
DEAD_WAIT_S = 20.0

# Runs inside the real runtime interpreter: reports which file the runner
# loaded the declared-check contract from, and how it validates each case.
# Importing runner has no side effect; nothing is started and no key is read.
CONTRACT_PROBE_SOURCE = """
import json, sys
sys.path.insert(0, sys.argv[1])
import runner

request = {"op": "run", "task": "t", "url": "http://127.0.0.1:9/",
           "profile_dir": "/tmp/jev-contract-probe", "artifact_dir": "/tmp/jev-contract-probe"}
report = {"file": runner.dom_checks.__file__, "results": []}
for checks in json.loads(sys.stdin.read()):
    try:
        normalized = runner.normalize(dict(request, checks=checks))["checks"]
        report["results"].append({"ok": True, "checks": normalized})
    except runner.RequestError as exc:
        report["results"].append({"ok": False, "error": str(exc)})
sys.stdout.write(json.dumps(report))
"""

# Also runs inside the real runtime interpreter: builds a verification payload
# with the runner's own contract and writes exactly the bytes runner.emit()
# would write for it, redaction included. Nothing is started; no key is read.
EMIT_PROBE_SOURCE = """
import json, sys
sys.path.insert(0, sys.argv[1])
import runner

spec = json.loads(sys.stdin.read())
request = {"op": "run", "task": "t", "url": "http://127.0.0.1:9/",
           "profile_dir": "/tmp/jev-emit-probe", "artifact_dir": "/tmp/jev-emit-probe"}
checks = runner.normalize(dict(request, checks=spec["checks"]))["checks"]
wires = []
for case in spec["cases"]:
    payload = runner.dom_checks.verification_payload(
        checks, case["evidence"], redact=runner.redact)
    result = {
        "status": "completed",
        "output": {"final_url": "https://app.test/done", "final_title": "Done",
                   "page_text": "ok", "completion_claimed": True,
                   "verification": "not_performed"},
        "text": "done", "steps": 1, "cost": 0.0, "warnings": [],
        "screenshot_path": spec["screenshot_path"],
        "verification": payload,
    }
    # emit() writes redact(json.dumps(result, default=str)): one redaction
    # pass over the whole blob, row ids and observed evidence included.
    wires.append(runner.redact(json.dumps(result, default=str)))
sys.stdout.write(json.dumps({"wires": wires}))
"""

# Synthetic, credential-shaped and non-secret: no real value is used here.
BEARER_LITERAL = "Bearer YOUR_TOKEN_HERE"
KEY_LITERAL = "sk-EXAMPLE_PLACEHOLDER_00000000"

CONTRACT_CASES = [
    None,
    [],
    [{"kind": "url", "equals": "https://example.test/done"},
     {"id": "rows", "kind": "count", "selector": ".row", "equals": 3},
     {"id": "note", "kind": "value", "selector": "#note", "contains": "line"}],
    [{"kind": "attribute", "selector": "a", "equals": "x"}],
    [{"kind": "count", "selector": ".r", "equals": True}],
    [{"kind": "url", "equals": "x", "__proto__": {"kind": "url"}}],
    [{"id": "a", "kind": "url", "equals": "x"}, {"id": "a", "kind": "title", "equals": "y"}],
    [{"kind": "text", "equals": "x"}],
    [{"kind": "url", "equals": "x"}] * 21,
]


# Same idea for the confidence-cutoff contract: the runtime must load the
# wrapper's own file and reject the same policies with the same messages.
CONFIDENCE_PROBE_SOURCE = """
import json, sys
sys.path.insert(0, sys.argv[1])
import runner

request = {"op": "run", "task": "t", "url": "http://127.0.0.1:9/",
           "profile_dir": "/tmp/jev-contract-probe", "artifact_dir": "/tmp/jev-contract-probe"}
report = {"file": runner.confidence_policy_contract.__file__, "results": []}
for policy in json.loads(sys.stdin.read()):
    try:
        report["results"].append(
            {"ok": True, "confidence": runner.normalize(dict(request, confidence=policy))["confidence"]}
        )
    except runner.RequestError as exc:
        report["results"].append({"ok": False, "error": str(exc)})
report["login_has_no_cutoff"] = runner.normalize(
    {"op": "login", "url": "http://127.0.0.1:9/", "profile_dir": "/tmp/jev-contract-probe",
     "artifact_dir": "/tmp/jev-contract-probe", "confidence": {"operation": 0.8}}
)["confidence"]
sys.stdout.write(json.dumps(report))
"""

CONFIDENCE_CASES = [
    None,
    {},
    {"operation": 1.0},
    {"operation": 0.8, "target": 0.85, "binding": 0.9},
    {"operation": 0},
    {"operation": 1.1},
    {"operation": True},
    {"operation": "0.8"},
    {"operation": None},
    {"op": 0.8},
    {"": 0.8},
    [],
    0.8,
]


def wait_pid_dead(pid, timeout=DEAD_WAIT_S):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not jev._alive(pid):
            return
        time.sleep(0.05)
    raise AssertionError(f"pid {pid} still alive after {timeout}s")


@unittest.skipUnless(RUNTIME_AVAILABLE, "runtime project or uv is not installed")
class RuntimeLaunchTests(unittest.TestCase):
    def test_runner_interpreter_is_the_killed_process_group_leader(self):
        """The spawned process must BE the runtime interpreter: pid == pgid ==
        sid, so killpg(proc.pid) reaches the runner and everything it starts,
        and no launcher process is left in between."""
        argv = jev._launch_command()[:-1] + ["-c", PROBE_SOURCE]

        async def scenario():
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=jev._child_env(),
                start_new_session=True,
            )
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), PROBE_START_S)
                probe = json.loads(line)
                self.assertEqual(probe["pid"], proc.pid,
                                 "the spawned process must be the interpreter itself")
                self.assertEqual(probe["pgid"], proc.pid)
                self.assertEqual(probe["sid"], proc.pid)
                self.assertEqual(os.getsid(proc.pid), proc.pid)
                jev._signal_group(proc, signal.SIGKILL)
                await asyncio.wait_for(proc.wait(), DEAD_WAIT_S)
                return probe
            finally:
                if proc.returncode is None:
                    jev._signal_group(proc, signal.SIGKILL)
                jev._close_proc_streams(proc)

        probe = asyncio.run(scenario())
        wait_pid_dead(probe["pid"])  # the interpreter died with the group kill

    def test_runtime_validates_declared_checks_with_the_wrapper_contract(self):
        """One contract file, loaded by both boundaries, agreeing case by case.

        The runtime runs in its own interpreter and its own project, so this
        is the only place the two validators meet. No browser, no key, no
        model call: the probe only imports the runner and calls normalize().
        """
        with tempfile.TemporaryDirectory(prefix="jev-contract-") as tmp:
            probe = Path(tmp) / "contract_probe.py"
            probe.write_text(CONTRACT_PROBE_SOURCE)
            completed = subprocess.run(
                [str(jev._runtime_python()), str(probe), str(jev._runtime_dir())],
                input=json.dumps(CONTRACT_CASES),
                capture_output=True, text=True, timeout=120, env=jev._child_env(),
            )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        report = json.loads(completed.stdout)
        self.assertEqual(Path(report["file"]).resolve(),
                         Path(jev.checks.__file__).resolve(),
                         "the runtime must load the wrapper's own check contract")
        self.assertEqual(len(report["results"]), len(CONTRACT_CASES))
        for case, outcome in zip(CONTRACT_CASES, report["results"]):
            with self.subTest(case=repr(case)[:60]):
                if outcome["ok"]:
                    self.assertEqual(outcome["checks"], jev._validate_checks(case),
                                     "both boundaries must normalize identically")
                else:
                    with self.assertRaises(jev.JevValidationError) as ctx:
                        jev._validate_checks(case)
                    self.assertEqual(ctx.exception.message, outcome["error"],
                                     "both boundaries must reject with the same message")

    def test_the_wrapper_accepts_the_bytes_the_runner_really_emits(self):
        """Both halves, real code, on one byte string.

        The runtime builds the verification payload with its own contract and
        redacts the whole result the way emit() does; the wrapper then parses
        exactly those bytes. A declaration that looks like a credential is
        rewritten in transit, so this is the case that must not become a
        protocol error. No browser, no key, no model call.
        """
        declared = [
            {"id": "auth " + BEARER_LITERAL, "kind": "text", "selector": "#s",
             "contains": BEARER_LITERAL},
            {"id": "key", "kind": "value", "selector": "#k", "equals": KEY_LITERAL},
        ]
        cases = [
            ("passed", [{"available": True, "value": "sent " + BEARER_LITERAL},
                        {"available": True, "value": KEY_LITERAL}]),
            ("failed", [{"available": True, "value": "no header at all"},
                        {"available": True, "value": KEY_LITERAL}]),
            ("unknown", [{"available": False, "reason": "missing_or_ambiguous"},
                         {"available": False, "reason": "sensitive_field"}]),
        ]
        with tempfile.TemporaryDirectory(prefix="jev-emit-") as tmp:
            root = Path(tmp)
            shot = root / "final.png"
            shot.write_bytes(jev._PNG_MAGIC + b"\x00" * 16)
            probe = root / "emit_probe.py"
            probe.write_text(EMIT_PROBE_SOURCE)
            spec = {
                "checks": declared,
                "screenshot_path": str(shot),
                "cases": [{"evidence": {"url": "https://app.test/done", "title": "Done",
                                        "at": 1737000000000, "rows": rows}}
                          for _status, rows in cases],
            }
            completed = subprocess.run(
                [str(jev._runtime_python()), str(probe), str(jev._runtime_dir())],
                input=json.dumps(spec),
                capture_output=True, text=True, timeout=120, env=jev._child_env(),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            wires = json.loads(completed.stdout)["wires"]
            self.assertEqual(len(wires), len(cases))
            checks = jev._validate_checks(declared)
            fingerprints = [jev.checks.declaration_fingerprint(check) for check in checks]
            for (expected, _rows), wire in zip(cases, wires):
                with self.subTest(status=expected):
                    # The transport really did rewrite the declared text.
                    self.assertIn(jev._REDACTED, wire)
                    self.assertNotIn(BEARER_LITERAL, wire)
                    self.assertNotIn(KEY_LITERAL, wire)
                    result = jev._finish_result(
                        "run", wire.encode(), 0, root, root, root / "missing.log", checks)
                    self.assertEqual(result["status"], "completed")
                    payload = result["verification"]
                    self.assertEqual(payload["status"], expected)
                    self.assertEqual([row["fingerprint"] for row in payload["checks"]],
                                     fingerprints)
                    self.assertEqual(payload["checks"][0]["id"], "auth " + jev._REDACTED)
                    self.assertNotIn(BEARER_LITERAL, json.dumps(payload))

    def test_a_credential_shaped_declaration_keeps_the_real_failure(self):
        """A real runner process, no key: the failure stays credentials_error.

        Three declarations, one plain and two credential-shaped. The runner
        stops before Chrome starts, reports every declared check as unknown,
        and the shape of the declared text must not change that outcome.
        """
        expectations = ("Saved", BEARER_LITERAL, KEY_LITERAL)
        with tempfile.TemporaryDirectory(prefix="jev-shaped-") as tmp:
            home = Path(tmp) / "home"
            with mock.patch.dict(os.environ, {"JEV_HOME": str(home)}):
                os.environ.pop("OPENROUTER_API_KEY", None)
                for expectation in expectations:
                    with self.subTest(expectation=expectation[:12]):
                        self.assertFalse(os.environ.get("OPENROUTER_API_KEY"),
                                         "refusing to run: a provider key is still set")
                        checks = [{"id": "auth", "kind": "text", "selector": "#s",
                                   "contains": expectation}]
                        with self.assertRaises(JevError) as ctx:
                            asyncio.run(run("open the page", "http://127.0.0.1:9/",
                                            profile="shaped", max_steps=1,
                                            timeout_ms=120_000, max_cost_usd=0.01,
                                            checks=checks))
                        err = ctx.exception
                        self.assertEqual(err.status, "credentials_error", err.message)
                        self.assertNotIsInstance(err, jev.JevProtocolError)
                        self.assertIn("OPENROUTER_API_KEY", err.message)
                        row = err.result["verification"]["checks"][0]
                        self.assertEqual(row["status"], "unknown")
                        self.assertEqual(row["reason"], "verification_not_attempted")
                        self.assertEqual(
                            row["fingerprint"],
                            jev.checks.declaration_fingerprint(
                                jev._validate_checks(checks)[0]))

    def test_runtime_validates_confidence_with_the_wrapper_contract(self):
        """One cutoff contract file, loaded by both boundaries, case by case.

        No browser, no key, no model call: the probe imports the runner and
        calls normalize() only.
        """
        with tempfile.TemporaryDirectory(prefix="jev-confidence-") as tmp:
            probe = Path(tmp) / "confidence_probe.py"
            probe.write_text(CONFIDENCE_PROBE_SOURCE)
            completed = subprocess.run(
                [str(jev._runtime_python()), str(probe), str(jev._runtime_dir())],
                input=json.dumps(CONFIDENCE_CASES),
                capture_output=True, text=True, timeout=120, env=jev._child_env(),
            )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        report = json.loads(completed.stdout)
        self.assertEqual(Path(report["file"]).resolve(),
                         Path(jev.confidence.__file__).resolve(),
                         "the runtime must load the wrapper's own cutoff contract")
        self.assertIsNone(report["login_has_no_cutoff"], "login gates nothing")
        self.assertEqual(len(report["results"]), len(CONFIDENCE_CASES))
        for case, outcome in zip(CONFIDENCE_CASES, report["results"]):
            with self.subTest(case=repr(case)[:60]):
                if outcome["ok"]:
                    self.assertEqual(outcome["confidence"], jev._validate_confidence(case),
                                     "both boundaries must normalize identically")
                else:
                    with self.assertRaises(jev.JevValidationError) as ctx:
                        jev._validate_confidence(case)
                    self.assertEqual(ctx.exception.message, outcome["error"],
                                     "both boundaries must reject with the same message")

    def test_run_without_a_key_fails_typed_before_any_model_call(self):
        """No key means no browser and no provider request, twice in a row.

        Every call is guarded by assert_no_key(): if the environment ever
        still held a key, this test fails instead of spending money.
        """
        def attempt(profile):
            self.assertFalse(os.environ.get("OPENROUTER_API_KEY"),
                             "refusing to run: a provider key is still set")
            with self.assertRaises(JevError) as ctx:
                asyncio.run(run("open the page", "http://127.0.0.1:9/",
                                profile=profile, max_steps=1,
                                timeout_ms=120_000, max_cost_usd=0.01))
            self.assertEqual(ctx.exception.status, "credentials_error")
            return ctx.exception

        with tempfile.TemporaryDirectory(prefix="jev-live-") as tmp:
            home = Path(tmp) / "home"
            # patch.dict restores the whole environment on exit, including the
            # key popped inside the block.
            with mock.patch.dict(os.environ, {"JEV_HOME": str(home)}):
                os.environ.pop("OPENROUTER_API_KEY", None)
                err = attempt("nokey")
                self.assertIn("OPENROUTER_API_KEY", err.message)
                self.assertIn(err.result["cost"], (None, 0))
                self.assertIsNone(err.result["screenshot_path"])
                artifacts = Path(err.result["artifact_dir"])
                self.assertTrue(artifacts.is_dir())
                self.assertFalse((artifacts / "chrome.log").exists(),
                                 "no browser may start without a provider key")
                # the profile lock is free again right after the typed failure
                attempt("nokey")
                self.assertTrue(str(home) in err.result["artifact_dir"])


if __name__ == "__main__":
    unittest.main()
