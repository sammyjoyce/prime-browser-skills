'''Unit tests for the browser_use skill Python half.

Runs the real subprocess machinery against a fake "runner" (a Python script
executed via patched _node_bin/_runner_path seams), so spawn/session/stdin/
stdout/stderr/kill/lock behavior is exercised without node, Chrome, or paid
model calls.

    cd skills/browser-use   # or ~/.prime/agent/skills/browser-use once installed
    uv run python -m unittest discover -s tests -v
'''

import asyncio
import importlib.util
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import browser_use
from browser_use import (
    BrowserUseError,
    BrowserUseProfileInUseError,
    BrowserUseProtocolError,
    BrowserUseTimeoutError,
    BrowserUseValidationError,
    login,
    run,
)

try:
    import pydantic

    HAVE_PYDANTIC = True
except ImportError:  # dev dependency; duck-typed schemas still covered below
    HAVE_PYDANTIC = False

# The fake runner lives in a real .py file next to this module: an inline
# source string silently produced an unparsable child (literal newlines inside
# quoted strings, a non-ASCII byte inside a b"..." literal) that failed as an
# opaque subprocess error. Compiling it here fails loudly instead.
FAKE_RUNNER_PATH = Path(__file__).resolve().parent / "fake_runner.py"
FAKE_RUNNER_SOURCE = FAKE_RUNNER_PATH.read_text()
compile(FAKE_RUNNER_SOURCE, str(FAKE_RUNNER_PATH), "exec")

SECRET = "supersecrettoken123"


def wait_pid_dead(pid, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.05)
    raise AssertionError(f"pid {pid} still alive after {timeout}s")


@contextmanager
def env_set(**kv):
    """Set env vars; a value of None removes the variable."""
    saved = {}
    for key, value in kv.items():
        saved[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class FakeRunnerTestCase(unittest.TestCase):
    """Base: temp home, fake runner subprocess via patched seams."""

    def setUp(self):
        # resolve(): macOS hands out /var/folders/... which is a symlink to
        # /private/var/..., and _home_dir() resolves, so compare like for like.
        self.tmp = Path(tempfile.mkdtemp(prefix="bu-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.fake_runner = self.tmp / "fake_runner.py"
        self.fake_runner.write_text(FAKE_RUNNER_SOURCE)

        patchers = [
            mock.patch.object(browser_use, "_runner_path", return_value=self.fake_runner),
            mock.patch.object(browser_use, "_node_bin", return_value=sys.executable),
            mock.patch.dict(
                os.environ,
                {"BROWSER_USE_HOME": str(self.home), "FAKE_RUNNER_MODE": "ok"},
            ),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)

    def mode(self, name):
        return mock.patch.dict(os.environ, {"FAKE_RUNNER_MODE": name})

    def fast_cleanup(self):
        # Shrink the outer watchdog allowance so hang tests stay fast.
        return mock.patch.object(browser_use, "_CLEANUP_ALLOWANCE_S", 0.3)

    def find_pidfiles(self, name="runner.pid"):
        return list((self.home / "artifacts").glob(f"*/{name}"))

    def wait_pidfile(self, name="runner.pid", timeout=10.0):
        """Read the pid the fake runner registered. Never waits forever."""
        deadline = time.monotonic() + timeout
        while not self.find_pidfiles(name):
            if time.monotonic() >= deadline:
                raise AssertionError(f"timeout waiting for {name} after {timeout}s")
            time.sleep(0.05)
        return int(self.find_pidfiles(name)[0].read_text())

    async def await_pidfile(self, task=None, name="runner.pid", timeout=10.0):
        """Async form: wait until the spawned fake runner registers its pid.

        Fails fast when the run task that should have spawned it already
        finished (a runner that cannot start used to hang the whole suite
        here), and always gives up at a finite deadline.
        """
        deadline = time.monotonic() + timeout
        while not self.find_pidfiles(name):
            if task is not None and task.done():
                detail = "cancelled" if task.cancelled() else repr(task.exception())
                raise AssertionError(
                    f"run task finished before {name} appeared: {detail}"
                )
            if time.monotonic() >= deadline:
                raise AssertionError(f"timeout waiting for {name} after {timeout}s")
            await asyncio.sleep(0.05)
        return int(self.find_pidfiles(name)[0].read_text())

    def assert_private_dir(self, path):
        mode_ = stat.S_IMODE(os.stat(path).st_mode)
        self.assertEqual(mode_, 0o700, f"{path} has mode {oct(mode_)}")


class ValidationTests(FakeRunnerTestCase):
    def _assert_invalid(self, coro_factory):
        with self.assertRaises(BrowserUseValidationError) as ctx:
            asyncio.run(coro_factory())
        err = ctx.exception
        self.assertIsInstance(err, ValueError)
        self.assertEqual(err.status, "invalid_input")
        self.assertIsNone(err.result)
        return err

    def test_task_must_be_nonempty_string(self):
        self._assert_invalid(lambda: run(""))
        self._assert_invalid(lambda: run("   "))
        self._assert_invalid(lambda: run(123))
        self._assert_invalid(lambda: run(None))

    def test_profile_name_rules(self):
        for bad in ["", " leading", "-dash", ".dot", "a/b", "a b", "x" * 65, 5]:
            with self.subTest(profile=bad):
                self._assert_invalid(lambda: run("t", profile=bad))

    def test_numeric_limits(self):
        cases = [
            dict(max_steps=True), dict(max_steps=0), dict(max_steps=-3),
            dict(max_steps=2.5), dict(max_steps="5"),
            dict(timeout_ms=0), dict(timeout_ms=-1), dict(timeout_ms=True),
            dict(timeout_ms=float("nan")), dict(timeout_ms=float("inf")),
            dict(timeout_ms=2.5), dict(timeout_ms=2**53),
            dict(max_cost_usd=0), dict(max_cost_usd=-0.5), dict(max_cost_usd=True),
            dict(max_cost_usd=float("nan")), dict(max_cost_usd=float("inf")),
            dict(max_cost_usd="1"),
        ]
        for kwargs in cases:
            with self.subTest(**kwargs):
                self._assert_invalid(lambda: run("t", **kwargs))

    def test_timeout_accepts_integral_float(self):
        result = asyncio.run(run("t", timeout_ms=30000.0))
        self.assertEqual(result["output"]["request"]["timeout_ms"], 30000)

    def test_schema_must_be_dict_or_schema_like(self):
        for bad in ['{"type": "object"}', 5, [1], object(), {"a": float("nan")}]:
            with self.subTest(schema=bad):
                self._assert_invalid(lambda: run("t", schema=bad))

    def test_login_url_must_be_http(self):
        for bad in ["", "ftp://x", "file:///etc", 123, None]:
            with self.subTest(url=bad):
                self._assert_invalid(lambda: login(url=bad))
        self._assert_invalid(lambda: login(timeout_ms=0))


class SuccessPathTests(FakeRunnerTestCase):
    def test_result_shape_and_request(self):
        result = asyncio.run(run("do the thing"))
        for key in ("status", "output", "text", "steps", "cost", "screenshot_path", "artifact_dir"):
            self.assertIn(key, result)
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["text"], "all done")
        self.assertEqual(result["steps"], 4)
        self.assertEqual(result["cost"], 0.05)
        self.assertEqual(result["duration_ms"], 1234)  # extras preserved

        request = result["output"]["request"]
        self.assertEqual(request["op"], "run")
        self.assertEqual(request["task"], "do the thing")
        self.assertIsNone(request["schema"])
        self.assertEqual(request["max_steps"], 25)
        self.assertEqual(request["timeout_ms"], 180000)
        self.assertEqual(request["max_cost_usd"], 1.0)
        self.assertTrue(os.path.isabs(request["profile_dir"]))
        self.assertTrue(os.path.isabs(request["artifact_dir"]))
        self.assertEqual(request["profile_dir"], str(self.home / "profiles" / "default"))
        self.assertEqual(request["artifact_dir"], result["artifact_dir"])

        self.assertTrue(os.path.isabs(result["screenshot_path"]))
        self.assertTrue(Path(result["screenshot_path"]).exists())
        self.assertTrue(Path(result["artifact_dir"]).is_dir())
        self.assertTrue(Path(result["stderr_path"]).exists())

    def test_child_environment(self):
        with env_set(BROWSER_USE_MODEL=None):
            result = asyncio.run(run("t"))
            self.assertEqual(result["output"]["model_env"], browser_use.DEFAULT_MODEL)
        with env_set(BROWSER_USE_MODEL="prov/model-x"):
            result = asyncio.run(run("t"))
            self.assertEqual(result["output"]["model_env"], "prov/model-x")
        result = asyncio.run(run("t"))
        self.assertTrue(result["output"]["pgid_is_self"],
                        "child must be its own process-group leader")
        self.assertEqual(result["output"]["do_not_track"], "1")

    def test_default_model_is_gpt6_astra(self):
        self.assertEqual(browser_use.DEFAULT_MODEL, "openai/gpt-6-astra")

    def test_schema_dict_passthrough(self):
        schema = {"type": "object", "properties": {"titles": {"type": "array"}}}
        result = asyncio.run(run("t", schema=schema))
        self.assertEqual(result["output"]["request"]["schema"], schema)

    def test_schema_duck_typed(self):
        class Duck:
            @classmethod
            def model_json_schema(cls):
                return {"type": "object", "title": "Duck"}

        result = asyncio.run(run("t", schema=Duck))
        self.assertEqual(result["output"]["request"]["schema"],
                         {"type": "object", "title": "Duck"})

    @unittest.skipUnless(HAVE_PYDANTIC, "pydantic not installed")
    def test_schema_pydantic_model(self):
        class Titles(pydantic.BaseModel):
            titles: list[str]

        result = asyncio.run(run("t", schema=Titles))
        self.assertEqual(result["output"]["request"]["schema"], Titles.model_json_schema())

    def test_login_request_shape(self):
        result = asyncio.run(login(profile="acme", url="https://acme.example/login",
                                   timeout_ms=5432))
        request = result["output"]["request"]
        self.assertEqual(request["op"], "login")
        self.assertEqual(request["url"], "https://acme.example/login")
        self.assertNotIn("task", request)
        self.assertIsNone(request["schema"])
        self.assertEqual(request["timeout_ms"], 5432)
        self.assertEqual(request["profile_dir"], str(self.home / "profiles" / "acme"))

    def test_sequential_runs_reuse_profile_and_unique_artifacts(self):
        first = asyncio.run(run("one", profile="p"))
        second = asyncio.run(run("two", profile="p"))
        self.assertNotEqual(first["artifact_dir"], second["artifact_dir"])
        self.assertTrue(Path(first["artifact_dir"]).is_dir())
        self.assertTrue(Path(second["artifact_dir"]).is_dir())

    def test_permissions_are_private(self):
        asyncio.run(run("t", profile="sec"))
        self.assert_private_dir(self.home)
        self.assert_private_dir(self.home / "profiles")
        self.assert_private_dir(self.home / "profiles" / "sec")
        artifact = Path(asyncio.run(run("t", profile="sec"))["artifact_dir"])
        self.assert_private_dir(artifact)
        self.assertEqual(stat.S_IMODE(os.stat(artifact / "runner.stderr.log").st_mode), 0o600)
        lock = self.home / "profiles" / "sec.lock"
        self.assertTrue(lock.exists())
        self.assertEqual(stat.S_IMODE(os.stat(lock).st_mode), 0o600)

    def test_stderr_goes_to_file_not_result(self):
        with self.mode("stderrnoise"), env_set(LEAK_TEST_TOKEN=SECRET):
            result = asyncio.run(run("t"))
        self.assertEqual(result["status"], "completed")
        stderr_text = Path(result["stderr_path"]).read_text()
        self.assertIn("progress noise", stderr_text)
        self.assertIn(SECRET, stderr_text)  # on-disk log keeps original text


class FailurePathTests(FakeRunnerTestCase):
    def test_noncompleted_error_raises_with_result(self):
        with self.mode("error"), env_set(LEAK_TEST_TOKEN=SECRET):
            with self.assertRaises(BrowserUseError) as ctx:
                asyncio.run(run("t"))
        err = ctx.exception
        self.assertNotIsInstance(err, BrowserUseTimeoutError)
        self.assertEqual(err.status, "error")
        self.assertIn("boom", err.message)
        self.assertNotIn(SECRET, err.message)
        self.assertIn(browser_use._REDACTED, err.result["error"])
        self.assertNotIn(SECRET, err.result["text"])
        self.assertTrue(Path(err.result["artifact_dir"]).is_dir())

    def test_runner_reported_timeout_uses_typed_error(self):
        with self.mode("runner_timeout"):
            with self.assertRaises(BrowserUseTimeoutError) as ctx:
                asyncio.run(run("t", timeout_ms=1234))
        err = ctx.exception
        self.assertEqual(err.status, "timeout")
        self.assertEqual(err.result["error"], "task exceeded its timeout")
        self.assertEqual(err.result["artifact_dir"], err.result["artifact_dir"])

    def test_error_synthesized_when_missing(self):
        with self.mode("maxsteps"):
            with self.assertRaises(BrowserUseError) as ctx:
                asyncio.run(run("t", max_steps=2))
        err = ctx.exception
        self.assertEqual(err.status, "max_steps")
        self.assertTrue(err.result["error"])
        self.assertIn("max_steps", err.result["error"])

    def test_protocol_error_on_garbage_stdout_redacted(self):
        with self.mode("garbage"), env_set(LEAK_TEST_TOKEN=SECRET):
            with self.assertRaises(BrowserUseProtocolError) as ctx:
                asyncio.run(run("t"))
        err = ctx.exception
        self.assertEqual(err.status, "protocol")
        self.assertNotIn(SECRET, err.message)
        self.assertIn(browser_use._REDACTED, err.message)
        self.assertTrue(Path(err.result["artifact_dir"]).is_dir())
        self.assertTrue(Path(err.result["stderr_path"]).exists())

    def test_protocol_error_on_extra_json_lines(self):
        with self.mode("partial"):
            with self.assertRaises(BrowserUseProtocolError):
                asyncio.run(run("t"))

    def test_protocol_error_on_nonzero_exit_despite_json(self):
        with self.mode("exit1"):
            with self.assertRaises(BrowserUseProtocolError) as ctx:
                asyncio.run(run("t"))
        self.assertIn("exited with code 1", ctx.exception.message)

    def test_protocol_error_on_relative_screenshot(self):
        with self.mode("relshot"):
            with self.assertRaises(BrowserUseProtocolError) as ctx:
                asyncio.run(run("t"))
        self.assertIn("screenshot_path", ctx.exception.message)

    def test_launch_error_when_runner_missing(self):
        with mock.patch.object(browser_use, "_runner_path",
                               return_value=self.tmp / "nope.mjs"):
            with self.assertRaises(BrowserUseError) as ctx:
                asyncio.run(run("t"))
        self.assertEqual(ctx.exception.status, "launch_error")

    def test_launch_error_when_node_missing(self):
        with mock.patch.object(browser_use, "_node_bin",
                               return_value="/nonexistent/node-bin"):
            with self.assertRaises(BrowserUseError) as ctx:
                asyncio.run(run("t"))
        self.assertEqual(ctx.exception.status, "launch_error")


class LifecycleTests(FakeRunnerTestCase):
    def test_timeout_kills_process_group_and_releases_lock(self):
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                with self.assertRaises(BrowserUseTimeoutError) as ctx:
                    await run("t", timeout_ms=1000, max_steps=1)
                return ctx.exception

            err = asyncio.run(scenario())
        self.assertEqual(err.status, "timeout")
        self.assertIn("timeout_ms=1000", err.result["error"])
        runner_pid = self.wait_pidfile()
        self.assertEqual(len(self.find_pidfiles()), 1)
        wait_pid_dead(runner_pid)
        # lock must be free again
        result = asyncio.run(run("t"))
        self.assertEqual(result["status"], "completed")

    def test_cancellation_kills_and_propagates(self):
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                task = asyncio.ensure_future(run("t", timeout_ms=60000))
                await self.await_pidfile(task)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

            asyncio.run(scenario())
        pidfiles = self.find_pidfiles()
        self.assertEqual(len(pidfiles), 1)
        wait_pid_dead(int(pidfiles[0].read_text()))
        result = asyncio.run(run("t"))
        self.assertEqual(result["status"], "completed")

    def test_repeated_cancel_holds_lock_until_termination(self):
        with self.mode("hang_sigterm"), self.fast_cleanup():
            async def scenario():
                task = asyncio.ensure_future(run("t", profile="busy", timeout_ms=60000))
                await self.await_pidfile(task)
                task.cancel()                       # SIGTERM sent; leader survives ~2s
                await asyncio.sleep(0.3)
                task.cancel()                       # repeated cancel during teardown
                # teardown in progress: the profile lock must still be held
                with self.assertRaises(BrowserUseProfileInUseError):
                    await run("t", profile="busy")
                with self.assertRaises(asyncio.CancelledError):
                    await task
                with self.mode("ok"):
                    return await run("t", profile="busy")

            result = asyncio.run(scenario())
        self.assertEqual(result["status"], "completed")
        wait_pid_dead(self.wait_pidfile())

    def test_grandchild_killed_after_leader_exit(self):
        with self.mode("grandchild"), self.fast_cleanup():
            with self.assertRaises(BrowserUseProtocolError):
                asyncio.run(run("t", timeout_ms=30000))
        grandchild = self.wait_pidfile("grandchild.pid")
        wait_pid_dead(grandchild)
        result = asyncio.run(run("t"))
        self.assertEqual(result["status"], "completed")

    def test_cancel_during_spawn_adopts_and_kills(self):
        """Cancelled mid-creation, the already-forked child must still be killed.

        The child cannot register a pid file here: its stdin is never written,
        so it is still blocked in stdin.read() when cancellation lands. The
        spawn hook records the real child pid instead, which is what must end
        up dead and reaped.
        """
        real_create = asyncio.create_subprocess_exec
        spawned = []

        async def slow_create(*args, **kwargs):
            proc = await real_create(*args, **kwargs)
            spawned.append(proc.pid)               # process exists ...
            await asyncio.sleep(1.0)               # ... but creation has not returned
            return proc

        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                with mock.patch.object(asyncio, "create_subprocess_exec", slow_create):
                    task = asyncio.ensure_future(run("t", profile="spawn", timeout_ms=60000))
                    deadline = time.monotonic() + 10.0
                    while not spawned:
                        if task.done():
                            raise AssertionError(f"run finished early: {task.exception()!r}")
                        if time.monotonic() >= deadline:
                            raise AssertionError("runner process was never created")
                        await asyncio.sleep(0.02)
                    task.cancel()                   # mid-creation, process already forked
                    with self.assertRaises(asyncio.CancelledError):
                        await task

            asyncio.run(scenario())
        self.assertEqual(len(spawned), 1)
        wait_pid_dead(spawned[0])                   # adopted, not leaked
        self.assertEqual(self.find_pidfiles(), [])  # never got to run its task
        result = asyncio.run(run("t", profile="spawn"))   # lock was released
        self.assertEqual(result["status"], "completed")

    def test_profile_in_use_fails_promptly(self):
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                first = asyncio.ensure_future(run("t", profile="busy", timeout_ms=60000))
                await self.await_pidfile(first)
                start = time.monotonic()
                with self.assertRaises(BrowserUseProfileInUseError) as ctx:
                    await run("t", profile="busy")
                elapsed = time.monotonic() - start
                first.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await first
                return ctx.exception, elapsed

            err, elapsed = asyncio.run(scenario())
        self.assertEqual(err.status, "profile_in_use")
        self.assertIn("busy", err.message)
        self.assertLess(elapsed, 3.0)
        wait_pid_dead(self.wait_pidfile())
        result = asyncio.run(run("t", profile="busy"))
        self.assertEqual(result["status"], "completed")

    def test_different_profiles_run_concurrently(self):
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                hanging = asyncio.ensure_future(run("t", profile="aaa", timeout_ms=60000))
                await self.await_pidfile(hanging)
                with self.mode("ok"):               # only "aaa" hangs
                    other = await run("t", profile="bbb")  # different profile: no clash
                hanging.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await hanging
                return other

            result = asyncio.run(scenario())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["output"]["request"]["profile_dir"],
                         str(self.home / "profiles" / "bbb"))


class ResolutionTests(unittest.TestCase):
    def test_runner_path_resolves_to_skill_root(self):
        expected = Path(browser_use.__file__).resolve().parents[2] / "runner.mjs"
        self.assertEqual(browser_use._runner_path(), expected)
        self.assertEqual(expected.parent.name, "browser-use")

    def test_redact_replaces_matching_env_values_only(self):
        with env_set(LEAK_TEST_TOKEN=SECRET, SHORT_TOK="short", SAFE_VAR="notasecretvalue"):
            text = f"got {SECRET} and short and notasecretvalue"
            redacted = browser_use._redact(text)
        self.assertNotIn(SECRET, redacted)
        self.assertIn("short", redacted)
        self.assertIn("notasecretvalue", redacted)

    def test_error_str_is_typed(self):
        err = BrowserUseError("s", "m", {"a": 1})
        self.assertEqual(str(err), "browser-use error [s]: m")
        self.assertEqual(err.result, {"a": 1})


if __name__ == "__main__":
    unittest.main()
