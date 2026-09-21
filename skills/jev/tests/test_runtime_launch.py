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
