"""Unit tests for the jev skill wrapper (the Python half of the skill).

They run the real subprocess machinery against a fake runtime runner (a real
.py file executed through the patched _launch_command seam), so spawn,
session, stdin/stdout/stderr, kill, sweep and lock behaviour are exercised
without uv, Chrome, a provider key, or any paid model call.

    cd skills/jev   # or ~/.prime/agent/skills/jev once installed
    uv run python -m unittest discover -s tests -v
"""

import asyncio
import json
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

import jev
from jev import (
    JevError,
    JevProfileInUseError,
    JevProtocolError,
    JevTimeoutError,
    JevValidationError,
    login,
    run,
)

# The fake runner lives in a real .py file next to this module: an inline
# source string silently produced an unparsable child (literal newlines inside
# quoted strings, a non-ASCII byte inside a b"..." literal) that failed as an
# opaque subprocess error. Compiling it here fails loudly instead.
FAKE_RUNNER_PATH = Path(__file__).resolve().parent / "fake_runner.py"
FAKE_RUNNER_SOURCE = FAKE_RUNNER_PATH.read_text()
if not FAKE_RUNNER_SOURCE.isascii():
    raise AssertionError("fake_runner.py must be plain ASCII")
compile(FAKE_RUNNER_SOURCE, str(FAKE_RUNNER_PATH), "exec")

# Captured before any patching so the launch seam can be restored in one test.
REAL_LAUNCH_COMMAND = jev._launch_command

SECRET = "supersecrettoken123"
# Every wait in this suite is finite: a hung child fails the test, never the run.
PID_WAIT_S = 10.0
DEAD_WAIT_S = 12.0


def wait_pid_dead(pid, timeout=DEAD_WAIT_S):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not jev._alive(pid):
            return
        time.sleep(0.05)
    raise AssertionError(f"pid {pid} still alive after {timeout}s")


@contextmanager
def env_set(**kv):
    """Set env vars for the duration of the block; None removes the variable."""
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
    """Base: temp JEV_HOME plus the fake runner behind the launch seam."""

    def setUp(self):
        # resolve(): macOS hands out /var/folders/... which is a symlink to
        # /private/var/..., and _home_dir() resolves, so compare like for like.
        self.tmp = Path(tempfile.mkdtemp(prefix="jev-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.fake_runner = self.tmp / "fake_runner.py"
        self.fake_runner.write_text(FAKE_RUNNER_SOURCE)

        patchers = [
            mock.patch.object(
                jev, "_launch_command",
                return_value=[sys.executable, str(self.fake_runner)],
            ),
            mock.patch.dict(
                os.environ,
                {"JEV_HOME": str(self.home), "FAKE_RUNNER_MODE": "ok"},
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def mode(self, name):
        return mock.patch.dict(os.environ, {"FAKE_RUNNER_MODE": name})

    def fast_cleanup(self):
        # Shrink the outer watchdog allowance so hang tests stay fast.
        return mock.patch.object(jev, "_CLEANUP_ALLOWANCE_S", 0.3)

    def find_pidfiles(self, name="runner.pid"):
        return list((self.home / "artifacts").glob(f"*/{name}"))

    def wait_pidfile(self, name="runner.pid", timeout=PID_WAIT_S):
        """Read a pid the fake runner registered. Never waits forever."""
        deadline = time.monotonic() + timeout
        while not self.find_pidfiles(name):
            if time.monotonic() >= deadline:
                raise AssertionError(f"timeout waiting for {name} after {timeout}s")
            time.sleep(0.05)
        return int(self.find_pidfiles(name)[0].read_text())

    async def await_pidfile(self, task=None, name="runner.pid", timeout=PID_WAIT_S):
        """Async form: wait until the spawned fake runner registers a pid.

        Fails fast when the task that should have spawned it already finished
        (a runner that cannot start would otherwise hang the suite here), and
        always gives up at a finite deadline.
        """
        deadline = time.monotonic() + timeout
        while not self.find_pidfiles(name):
            if task is not None and task.done():
                detail = "cancelled" if task.cancelled() else repr(task.exception())
                raise AssertionError(f"run task finished before {name} appeared: {detail}")
            if time.monotonic() >= deadline:
                raise AssertionError(f"timeout waiting for {name} after {timeout}s")
            await asyncio.sleep(0.05)
        return int(self.find_pidfiles(name)[0].read_text())

    def assert_private_dir(self, path):
        mode_ = stat.S_IMODE(os.stat(path).st_mode)
        self.assertEqual(mode_, 0o700, f"{path} has mode {oct(mode_)}")

    def go(self, task="do the thing", url="https://example.test/start", **kwargs):
        return asyncio.run(run(task, url, **kwargs))


class ValidationTests(FakeRunnerTestCase):
    def _assert_invalid(self, coro_factory):
        with self.assertRaises(JevValidationError) as ctx:
            asyncio.run(coro_factory())
        err = ctx.exception
        self.assertIsInstance(err, ValueError)
        self.assertEqual(err.status, "invalid_input")
        self.assertIsNone(err.result)
        return err

    def test_task_must_be_nonempty_string(self):
        for bad in ["", "   ", 123, None, b"x", "x" * (jev._MAX_TASK_CHARS + 1)]:
            with self.subTest(task=type(bad)):
                self._assert_invalid(lambda: run(bad, "https://example.test"))

    def test_url_is_required_and_must_be_http(self):
        bad_urls = [
            "", "   ", "example.test", "ftp://example.test", "file:///etc/passwd",
            "javascript:alert(1)", "https://", "http:///path", "https://exa mple.test",
            "https://example.test:99999", "https://exa\nmple.test/x", 123, None,
            "https://" + "a" * jev._MAX_URL_CHARS,
        ]
        for bad in bad_urls:
            with self.subTest(url=bad):
                self._assert_invalid(lambda: run("t", bad))
                self._assert_invalid(lambda: login(url=bad))

    def test_real_urls_are_accepted(self):
        for good in ["http://localhost:8080/app",
                     "https://example.test/path?q=1#frag",
                     "https://user:pw@example.test/x",
                     "http://127.0.0.1:3000"]:
            with self.subTest(url=good):
                result = self.go(url=good)
                self.assertEqual(result["output"]["request"]["url"], good)

    def test_url_is_stripped_not_rewritten(self):
        result = self.go(url="  https://example.test/x  ")
        self.assertEqual(result["output"]["request"]["url"], "https://example.test/x")

    def test_profile_name_rules(self):
        for bad in ["", " leading", "-dash", ".dot", "a/b", "a b", "x" * 65, 5, None]:
            with self.subTest(profile=bad):
                self._assert_invalid(lambda: run("t", "https://example.test", profile=bad))
                self._assert_invalid(lambda: login(profile=bad))

    def test_numeric_limits_are_positive_and_finite(self):
        cases = [
            dict(max_steps=True), dict(max_steps=0), dict(max_steps=-3),
            dict(max_steps=2.5), dict(max_steps="5"), dict(max_steps=jev._MAX_STEPS + 1),
            dict(timeout_ms=0), dict(timeout_ms=-1), dict(timeout_ms=True),
            dict(timeout_ms=float("nan")), dict(timeout_ms=float("inf")),
            dict(timeout_ms=2.5), dict(timeout_ms=jev._MAX_TIMEOUT_MS + 1),
            dict(max_cost_usd=0), dict(max_cost_usd=-0.5), dict(max_cost_usd=True),
            dict(max_cost_usd=float("nan")), dict(max_cost_usd=float("inf")),
            dict(max_cost_usd="1"), dict(max_cost_usd=jev._MAX_COST_USD + 0.1),
        ]
        for kwargs in cases:
            with self.subTest(**kwargs):
                self._assert_invalid(lambda: run("t", "https://example.test", **kwargs))

    def test_login_timeout_is_validated(self):
        for bad in [0, -1, True, float("inf"), jev._MAX_TIMEOUT_MS + 1]:
            with self.subTest(timeout_ms=bad):
                self._assert_invalid(lambda: login(timeout_ms=bad))

    def test_limits_at_the_boundary_are_accepted(self):
        result = self.go(max_steps=jev._MAX_STEPS, max_cost_usd=jev._MAX_COST_USD,
                         timeout_ms=30000.0)
        request = result["output"]["request"]
        self.assertEqual(request["max_steps"], jev._MAX_STEPS)
        self.assertEqual(request["max_cost_usd"], jev._MAX_COST_USD)
        self.assertEqual(request["timeout_ms"], 30000)  # integral float accepted

    def test_values_must_be_a_short_map_of_strings(self):
        bad = [
            [], "x", 5, True, {"email": 5}, {"email": None}, {"email": True},
            {"email": b"x"}, {"1bad": "x"}, {"": "x"}, {"a-b": "x"}, {"a" * 65: "x"},
            {5: "x"}, {"email": "x" * (jev._MAX_VALUE_CHARS + 1)},
            {f"k{i}": "x" for i in range(jev._MAX_VALUES + 1)},
        ]
        for values in bad:
            with self.subTest(values=repr(values)[:40]):
                self._assert_invalid(lambda: run("t", "https://example.test", values=values))

    def test_value_limits_at_the_boundary_are_accepted(self):
        values = {f"k{i}": "x" * jev._MAX_VALUE_CHARS for i in range(jev._MAX_VALUES - 1)}
        values["a" * 64] = ""
        request = self.go(values=values)["output"]["request"]
        self.assertEqual(request["values"], values)
        self.assertEqual(len(request["values"]), jev._MAX_VALUES)

    def test_an_invalid_value_is_never_echoed(self):
        error = self._assert_invalid(
            lambda: run("t", "https://example.test", values={"pin": 123456})
        )
        self.assertNotIn("123456", error.message)
        self.assertIn("'pin'", error.message)

    def test_value_key_with_trailing_newline_is_rejected(self):
        # Python's `$` also matches just before a trailing newline. The wrapper
        # regex must anchor with \A and \Z so a key like "abc\n" is rejected
        # here, before any runner process starts, not by the runner later with
        # a generic invalid_request error.
        error = self._assert_invalid(
            lambda: run("t", "https://example.test", values={"abc\n": "x"})
        )
        self.assertIn("abc", error.message)
        self.assertFalse((self.home / "artifacts").exists())
        self.assertFalse((self.home / "profiles").exists())

    def test_value_key_none_is_reserved(self):
        # "NONE" is the bind_value sentinel for "no supplied value belongs
        # here"; a caller key of "NONE" would be silently overwritten and
        # could never be bound, so the wrapper rejects it up front.
        error = self._assert_invalid(
            lambda: run("t", "https://example.test", values={"NONE": "x"})
        )
        self.assertIn("NONE", error.message)
        self.assertFalse((self.home / "artifacts").exists())
        self.assertFalse((self.home / "profiles").exists())

    def test_generation_must_be_helper_or_disabled(self):
        for bad in ["auto", "", "HELPER", 1, True, ["helper"], {"mode": "helper"}]:
            with self.subTest(generation=bad):
                self._assert_invalid(lambda: run("t", "https://example.test", generation=bad))

    def test_checks_must_follow_the_declared_schema(self):
        bad = [
            {"id": "a", "kind": "url", "equals": "x"},              # an object, not a list
            "url", 5, True, ["h1"], [None],
            [{"kind": "url"}],                                      # no expectation
            [{"kind": "url", "equals": "x", "contains": "x"}],      # both expectations
            [{"kind": "url", "contains": ""}],                      # matches every page
            [{"kind": "url", "equals": 3}],                         # type coercion
            [{"kind": "url", "equals": "x" * (jev.checks.MAX_EXPECTED_CHARS + 1)}],
            [{"kind": "attribute", "selector": "a", "equals": "x"}],  # unsupported kind
            [{"kind": "text", "equals": "x"}],                      # selector required
            [{"kind": "text", "selector": "  ", "equals": "x"}],
            [{"kind": "text", "selector": "d" * (jev.checks.MAX_SELECTOR_CHARS + 1),
              "equals": "x"}],
            [{"kind": "url", "selector": "h1", "equals": "x"}],     # no selector allowed
            [{"kind": "count", "selector": ".r", "equals": True}],  # a bool is not a count
            [{"kind": "count", "selector": ".r", "equals": 3.0}],
            [{"kind": "count", "selector": ".r", "equals": float("inf")}],
            [{"kind": "count", "selector": ".r", "equals": float("nan")}],
            [{"kind": "count", "selector": ".r", "equals": -1}],
            [{"kind": "count", "selector": ".r", "contains": "3"}],
            [{"kind": "url", "equals": "x", "script": "alert(1)"}],   # unknown key
            [{"kind": "url", "equals": "x", "__proto__": {"kind": "url"}}],
            [{"kind": "url", "equals": "x", "constructor": "boom"}],
            [{"id": 7, "kind": "url", "equals": "x"}],
            [{"id": "  ", "kind": "url", "equals": "x"}],
            [{"id": "i" * (jev.checks.MAX_ID_CHARS + 1), "kind": "url", "equals": "x"}],
            [{"id": "a", "kind": "url", "equals": "x"},
             {"id": "a", "kind": "title", "equals": "y"}],          # duplicate id
            [{"kind": "url", "equals": "x"}] * (jev.checks.MAX_CHECKS + 1),
        ]
        for checks in bad:
            with self.subTest(checks=repr(checks)[:60]):
                self._assert_invalid(lambda: run("t", "https://example.test", checks=checks))

    def test_check_limits_at_the_boundary_are_accepted(self):
        checks = [{"id": "i" * jev.checks.MAX_ID_CHARS, "kind": "url",
                   "equals": "x" * jev.checks.MAX_EXPECTED_CHARS},
                  {"kind": "count", "selector": "d" * jev.checks.MAX_SELECTOR_CHARS,
                   "equals": 0}]
        checks += [{"id": "pad%d" % i, "kind": "title", "contains": "x"}
                   for i in range(jev.checks.MAX_CHECKS - len(checks))]
        request = self.go(checks=checks)["output"]["request"]
        self.assertEqual(len(request["checks"]), jev.checks.MAX_CHECKS)

    def test_an_invalid_check_never_echoes_the_expectation(self):
        error = self._assert_invalid(
            lambda: run("t", "https://example.test",
                        checks=[{"id": "pin", "kind": "count", "selector": "#p",
                                 "equals": "123456-" + SECRET}])
        )
        self.assertNotIn(SECRET, error.message)
        self.assertNotIn("123456", error.message)
        self.assertIn("checks[0]", error.message)

    def test_no_run_starts_for_invalid_checks(self):
        with self.assertRaises(JevValidationError):
            asyncio.run(run("t", "https://example.test", checks=[{"kind": "nope"}]))
        self.assertFalse((self.home / "artifacts").exists())
        self.assertFalse((self.home / "profiles").exists())

    def test_no_run_starts_for_invalid_input(self):
        with self.assertRaises(JevValidationError):
            asyncio.run(run("t", "nope"))
        self.assertFalse((self.home / "artifacts").exists())
        self.assertFalse((self.home / "profiles").exists())


class SuccessPathTests(FakeRunnerTestCase):
    def test_result_shape_and_request(self):
        result = self.go()
        for key in ("status", "output", "text", "steps", "cost", "cost_detail", "usage",
                    "model", "resolved_model", "helper_model", "duration_ms",
                    "stop_reason", "warnings", "screenshot_path", "artifact_dir",
                    "profile_dir", "stderr_path"):
            self.assertIn(key, result)
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["steps"], 4)
        self.assertEqual(result["cost"], 0.0123)
        self.assertEqual(result["model"], "jev-latest")
        self.assertEqual(result["resolved_model"], "typesafe/jev-latest-2026-09")
        self.assertEqual(result["helper_model"], "inception/mercury-2.5")
        self.assertEqual(result["duration_ms"], 4321)
        self.assertEqual(result["stop_reason"], "done")
        self.assertEqual(result["warnings"], ["viewport override applied"])
        self.assertEqual(result["usage"], {"decision": {"logical_requests": 2}})

        request = result["output"]["request"]
        self.assertEqual(request["op"], "run")
        self.assertEqual(request["profile"], "default")
        self.assertTrue(request["run_id"].startswith("run-"))
        self.assertIn(request["run_id"], result["artifact_dir"])
        self.assertEqual(request["task"], "do the thing")
        self.assertEqual(request["url"], "https://example.test/start")
        self.assertEqual(request["max_steps"], 25)
        self.assertEqual(request["timeout_ms"], 120000)
        self.assertEqual(request["max_cost_usd"], 0.5)
        self.assertNotIn("schema", request)
        self.assertTrue(os.path.isabs(request["profile_dir"]))
        self.assertTrue(os.path.isabs(request["artifact_dir"]))
        self.assertEqual(request["profile_dir"], str(self.home / "profiles" / "default"))
        self.assertEqual(request["artifact_dir"], result["artifact_dir"])
        self.assertEqual(result["profile_dir"], request["profile_dir"])
        self.assertTrue(Path(result["artifact_dir"]).is_dir())
        self.assertTrue(Path(result["stderr_path"]).exists())

    def test_defaults_match_the_documented_contract(self):
        result = self.go()
        request = result["output"]["request"]
        self.assertEqual((request["max_steps"], request["timeout_ms"],
                          request["max_cost_usd"]), (25, 120000, 0.5))

    def test_supplied_values_reach_the_request_unchanged(self):
        values = {"email": "dana@example.test", "note": " keep  spacing. ", "blank": ""}
        request = self.go(values=values)["output"]["request"]
        self.assertEqual(request["values"], values)
        self.assertEqual(request["values"]["note"], " keep  spacing. ")
        self.assertEqual(request["generation"], "disabled")

    def test_generation_defaults_and_overrides(self):
        plain = self.go()["output"]["request"]
        self.assertIsNone(plain["values"])
        self.assertEqual(plain["generation"], "helper")
        self.assertEqual(self.go(values={})["output"]["request"]["generation"], "helper")
        bound = self.go(values={"a": "b"}, generation="helper")["output"]["request"]
        self.assertEqual(bound["generation"], "helper")
        self.assertEqual(self.go(generation="disabled")["output"]["request"]["generation"], "disabled")

    def test_login_request_is_unchanged_by_the_binding_fields(self):
        with self.mode("login_ok"):
            request = asyncio.run(login())["output"]["request"]
        self.assertNotIn("values", request)
        self.assertNotIn("generation", request)

    def test_actions_report_which_value_was_used(self):
        result = self.go(values={"email": "dana@example.test"})
        self.assertEqual(
            [(a["value_key"], a["value_source"]) for a in result["actions"]],
            [("email", "supplied"), (None, "skipped"), (None, None), (None, None)],
        )
        self.assertNotIn("text", result["actions"][0])
        self.assertNotIn("dana@example.test", result["text"])

    def test_declared_checks_reach_the_request_normalized(self):
        request = self.go(checks=[
            {"kind": "text", "selector": "#status", "equals": "Saved"},
            {"id": "rows", "kind": "count", "selector": ".row", "equals": 3},
        ])["output"]["request"]
        self.assertEqual(request["checks"], [
            {"id": "check[0]", "kind": "text", "selector": "#status", "equals": "Saved"},
            {"id": "rows", "kind": "count", "selector": ".row", "equals": 3},
        ])

    def test_declared_checks_return_a_scoped_verification_object(self):
        result = self.go(checks=[{"id": "done", "kind": "url",
                                  "equals": "https://example.test/done"}])
        payload = result["verification"]
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["scope"], jev.CHECK_SCOPE)
        self.assertEqual(payload["scope"], "declared_dom_checks_only")
        self.assertEqual(payload["boundary"], "browser_dom")
        self.assertEqual(len(payload["checks"]), 1)
        self.assertEqual(payload["checks"][0]["id"], "done")
        # The structured object never changes the two honesty fields.
        self.assertEqual(result["output"]["verification"], "not_performed")
        self.assertTrue(result["output"]["completion_claimed"])
        self.assertEqual(result["status"], "completed")

    def test_no_declared_check_is_not_run_and_changes_nothing(self):
        result = self.go()
        self.assertEqual(result["verification"]["status"], "not_run")
        self.assertEqual(result["verification"]["checks"], [])
        self.assertEqual(result["output"]["request"]["checks"], [])
        self.assertEqual(result["status"], "completed")

    def test_failed_or_unknown_checks_never_change_the_status(self):
        for mode, status in (("checks_failed", "failed"), ("checks_unknown", "unknown")):
            with self.subTest(mode=mode), self.mode(mode):
                result = self.go(checks=[{"id": "saved", "kind": "text",
                                          "selector": "#s", "equals": "Saved"}])
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["verification"]["status"], status)
                self.assertEqual(result["verification"]["checks"][0]["status"], status)
                self.assertEqual(result["output"]["verification"], "not_performed")
                self.assertTrue(result["output"]["completion_claimed"])

    def test_check_evidence_is_redacted(self):
        with env_set(LEAK_TEST_TOKEN=SECRET), self.mode("checks_leak"):
            result = self.go(checks=[{"id": "t", "kind": "text",
                                      "selector": "#s", "equals": "page said x"}])
        payload = result["verification"]
        self.assertNotIn(SECRET, json.dumps(payload))
        self.assertIn(jev._REDACTED, payload["checks"][0]["observed"]["value"])
        self.assertIn(jev._REDACTED, payload["checked_at_url"])

    def test_login_declares_no_check(self):
        with self.mode("login_ok"):
            result = asyncio.run(login(url="https://acme.test/login"))
        self.assertIsNone(result["verification"])
        self.assertNotIn("checks", result["output"]["request"])

    def test_screenshot_is_an_existing_absolute_png(self):
        result = self.go()
        path = result["screenshot_path"]
        self.assertTrue(os.path.isabs(path))
        self.assertTrue(Path(path).is_file())
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(8), jev._PNG_MAGIC)

    def test_verification_is_never_claimed(self):
        result = self.go()
        self.assertEqual(result["output"]["verification"], "not_performed")
        self.assertEqual(jev.VERIFICATION, "not_performed")
        self.assertTrue(result["output"]["completion_claimed"])
        self.assertNotIn("verified", result)
        self.assertEqual(result["output"]["final_url"], "https://example.test/done")
        self.assertEqual(result["output"]["final_title"], "Done")

    def test_child_environment_is_isolated(self):
        with env_set(BU_CDP_URL="http://127.0.0.1:9222", BH_HOME="/tmp/user-harness",
                     DO_NOT_TRACK=None, ANONYMIZED_TELEMETRY=None):
            probe = self.go()["output"]["env_probe"]
            # the user's own Chrome / harness state can never leak into a run
            self.assertIsNone(probe["bu_cdp_url"])
            self.assertIsNone(probe["bh_home"])
            self.assertEqual(probe["do_not_track"], "1")
            self.assertEqual(probe["anonymized_telemetry"], "false")
            self.assertEqual(probe["bh_telemetry"], "0")
            self.assertTrue(probe["pgid_is_self"],
                            "runner must lead its own process group")
            # the parent environment itself is untouched
            self.assertEqual(os.environ["BU_CDP_URL"], "http://127.0.0.1:9222")
            self.assertEqual(os.environ["BH_HOME"], "/tmp/user-harness")
            self.assertNotIn("DO_NOT_TRACK", os.environ)

    def test_provider_key_is_passed_through_but_never_returned(self):
        with env_set(OPENROUTER_API_KEY=SECRET, LEAK_TEST_TOKEN=SECRET):
            result = self.go()
        self.assertTrue(result["output"]["env_probe"]["openrouter_key_present"])
        self.assertNotIn(SECRET, result["output"]["page_text"])
        self.assertIn(jev._REDACTED, result["output"]["page_text"])

    def test_login_request_shape_and_zero_cost(self):
        with self.mode("login_ok"):
            result = asyncio.run(login(profile="acme", url="https://acme.test/login",
                                       timeout_ms=5432))
        request = result["output"]["request"]
        self.assertEqual(request["op"], "login")
        self.assertEqual(request["profile"], "acme")
        self.assertTrue(request["run_id"].startswith("login-"))
        self.assertIsNone(request["task"])
        self.assertEqual(request["url"], "https://acme.test/login")
        self.assertEqual(request["timeout_ms"], 5432)
        self.assertEqual(request["max_steps"], jev._LOGIN_NEUTRAL_LIMIT)
        self.assertEqual(request["max_cost_usd"], float(jev._LOGIN_NEUTRAL_LIMIT))
        self.assertEqual(request["profile_dir"], str(self.home / "profiles" / "acme"))
        self.assertEqual(result["status"], "completed")
        self.assertIsNone(result["screenshot_path"])
        self.assertEqual(result["cost"], 0)
        self.assertEqual(result["steps"], 0)
        self.assertIsNone(result["output"]["authenticated"])
        self.assertEqual(result["output"]["verification"], "not_performed")

    def test_sequential_runs_reuse_profile_and_get_unique_artifacts(self):
        first = self.go(profile="p")
        second = self.go(profile="p")
        self.assertNotEqual(first["artifact_dir"], second["artifact_dir"])
        self.assertEqual(first["profile_dir"], second["profile_dir"])
        self.assertTrue(Path(first["artifact_dir"]).is_dir())
        self.assertTrue(Path(second["artifact_dir"]).is_dir())

    def test_permissions_are_private(self):
        self.go(profile="sec")
        self.assert_private_dir(self.home)
        self.assert_private_dir(self.home / "profiles")
        self.assert_private_dir(self.home / "profiles" / "sec")
        artifact = Path(self.go(profile="sec")["artifact_dir"])
        self.assert_private_dir(artifact)
        self.assertEqual(stat.S_IMODE(os.stat(artifact / "runner.stderr.log").st_mode), 0o600)
        lock = self.home / "profiles" / "sec.lock"
        self.assertTrue(lock.exists())
        self.assertEqual(stat.S_IMODE(os.stat(lock).st_mode), 0o600)

    def test_stderr_goes_to_a_private_file_not_the_result(self):
        with self.mode("stderrnoise"), env_set(LEAK_TEST_TOKEN=SECRET):
            result = self.go()
        self.assertEqual(result["status"], "completed")
        stderr_text = Path(result["stderr_path"]).read_text()
        self.assertIn("progress noise", stderr_text)
        self.assertIn(SECRET, stderr_text)  # the private on-disk log is verbatim


class FailurePathTests(FakeRunnerTestCase):
    def assert_status(self, mode, status, error_class=JevError, **kwargs):
        with self.mode(mode):
            with self.assertRaises(error_class) as ctx:
                self.go(**kwargs)
        self.assertEqual(ctx.exception.status, status)
        return ctx.exception

    def test_runner_error_is_typed_and_redacted(self):
        with env_set(LEAK_TEST_TOKEN=SECRET):
            err = self.assert_status("error", "error")
        self.assertNotIsInstance(err, JevTimeoutError)
        self.assertIn("boom", err.message)
        self.assertNotIn(SECRET, err.message)
        self.assertIn(jev._REDACTED, err.result["error"])
        self.assertNotIn(SECRET, err.result["text"])
        self.assertTrue(Path(err.result["artifact_dir"]).is_dir())
        self.assertEqual(err.result["profile_dir"], str(self.home / "profiles" / "default"))

    def test_runner_reported_timeout_is_a_timeout_error(self):
        err = self.assert_status("runner_timeout", "timeout", JevTimeoutError,
                                 timeout_ms=1234)
        self.assertIn("1234", err.result["error"])
        self.assertIsNone(err.result["cost"])

    def test_missing_error_message_is_synthesized(self):
        err = self.assert_status("maxsteps", "max_steps", max_steps=2)
        self.assertIn("max_steps", err.result["error"])
        self.assertEqual(err.result["steps"], 2)

    def test_unknown_cost_stays_unknown(self):
        err = self.assert_status("cost_unknown", "cost_unknown")
        self.assertIsNone(err.result["cost"], "unknown cost must never become 0.0")
        self.assertIn("no cost", err.result["cost_detail"]["note"])

    def test_protocol_error_on_garbage_stdout_is_redacted(self):
        with env_set(LEAK_TEST_TOKEN=SECRET):
            err = self.assert_status("garbage", "protocol", JevProtocolError)
        self.assertNotIn(SECRET, err.message)
        self.assertIn(jev._REDACTED, err.message)
        self.assertTrue(Path(err.result["stderr_path"]).exists())

    def test_protocol_errors_for_broken_contracts(self):
        cases = {
            "partial": "one JSON result object",
            "exit1": "exited with code 1",
            "relshot": "screenshot_path",
            "badwarnings": "warnings",
            "badcost": "cost",
            "no_output": "output",
            "missing_claim": "completion_claimed",
            "unclaimed": "claim completion",
            "verification_claim": "verification",
            "verified": "verification",
        }
        for mode, fragment in cases.items():
            with self.subTest(mode=mode):
                err = self.assert_status(mode, "protocol", JevProtocolError)
                self.assertIn(fragment, err.message)

    def test_claimed_verification_keeps_its_evidence(self):
        err = self.assert_status("verified", "protocol", JevProtocolError)
        self.assertTrue(err.result.get("verified"),
                        "contradictory evidence must stay in the partial result")

    def test_broken_verification_contracts_are_protocol_errors(self):
        declared = [{"id": "saved", "kind": "text", "selector": "#s", "equals": "Saved"}]
        cases = {
            "checks_missing": "no verification object",
            "checks_short": "one row per declared check",
            "checks_scope": "verification.scope",
            "checks_boundary": "verification.boundary",
            "checks_status": "verification.status",
            "checks_notrun": "not_run",
            "checks_not_an_object": "verification must be an object",
        }
        for mode, fragment in cases.items():
            with self.subTest(mode=mode):
                err = self.assert_status(mode, "protocol", JevProtocolError, checks=declared)
                self.assertIn(fragment, err.message)

    def test_a_partial_stop_keeps_its_check_evidence(self):
        declared = [{"id": "saved", "kind": "text", "selector": "#s", "equals": "Saved"}]
        err = self.assert_status("checks_partial", "max_steps", checks=declared)
        payload = err.result["verification"]
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(len(payload["checks"]), 1)
        self.assertEqual(payload["checks"][0]["id"], "saved")
        self.assertEqual(payload["scope"], jev.CHECK_SCOPE)

    def test_verification_without_a_declared_check_is_a_protocol_error(self):
        invented = self.assert_status("checks_invented", "protocol", JevProtocolError)
        self.assertIn("one row per declared check", invented.message)
        claimed = self.assert_status("checks_extra", "protocol", JevProtocolError)
        self.assertIn("no declared check", claimed.message)

    def test_login_must_not_claim_verification(self):
        with self.mode("login_verification"):
            with self.assertRaises(JevProtocolError) as ctx:
                asyncio.run(login(url="https://acme.test/login"))
        self.assertIn("login declares no DOM check", ctx.exception.message)

    def test_completed_without_a_real_png_is_an_artifact_error(self):
        for mode, fragment in {"noshot": "null",
                               "missingshot": "not readable",
                               "jpegshot": "not a PNG"}.items():
            with self.subTest(mode=mode):
                err = self.assert_status(mode, "artifact_error")
                self.assertNotIsInstance(err, JevProtocolError)
                self.assertIn(fragment, err.message)
                self.assertEqual(err.result["status"], "artifact_error")
                self.assertTrue(err.result["output"]["completion_claimed"])

    def test_login_contract_violations_are_protocol_errors(self):
        for mode, fragment in {"login_nocost": "cost 0",
                               "login_spent": "cost 0",
                               "login_steps": "steps 0",
                               "login_claims_auth": "authenticated",
                               "login_shot": "screenshot"}.items():
            with self.subTest(mode=mode):
                with self.mode(mode):
                    with self.assertRaises(JevProtocolError) as ctx:
                        asyncio.run(login(url="https://acme.test/login"))
                self.assertIn(fragment, ctx.exception.message)

    def test_launch_error_when_runtime_runner_is_missing(self):
        missing = self.tmp / "runtime-missing"
        with mock.patch.object(jev, "_launch_command", REAL_LAUNCH_COMMAND), \
             mock.patch.object(jev, "_runtime_dir", return_value=missing):
            with self.assertRaises(JevError) as ctx:
                self.go()
        err = ctx.exception
        self.assertEqual(err.status, "launch_error")
        self.assertIn("uv sync", err.message)
        self.assertTrue(Path(err.result["artifact_dir"]).is_dir())

    def test_launch_error_when_the_interpreter_is_missing(self):
        with mock.patch.object(jev, "_launch_command",
                               return_value=["/nonexistent/python-bin"]):
            with self.assertRaises(JevError) as ctx:
                self.go()
        self.assertEqual(ctx.exception.status, "launch_error")

    def test_symlinked_profile_is_refused(self):
        profiles = self.home / "profiles"
        profiles.mkdir(parents=True)
        elsewhere = self.tmp / "daily-chrome"
        elsewhere.mkdir()
        (profiles / "linked").symlink_to(elsewhere)
        with self.assertRaises(JevError) as ctx:
            self.go(profile="linked")
        self.assertEqual(ctx.exception.status, "profile_error")
        self.assertFalse(any(elsewhere.iterdir()), "the linked directory must stay untouched")

    def test_symlinked_profiles_root_is_refused(self):
        elsewhere = self.tmp / "other-profiles"
        elsewhere.mkdir()
        self.home.mkdir(parents=True)
        (self.home / "profiles").symlink_to(elsewhere)
        with self.assertRaises(JevError) as ctx:
            self.go()
        self.assertEqual(ctx.exception.status, "profile_error")

    def test_lock_is_released_after_a_failure(self):
        self.assert_status("error", "error", profile="reuse")
        self.assertEqual(self.go(profile="reuse")["status"], "completed")


class LifecycleTests(FakeRunnerTestCase):
    def test_timeout_kills_the_process_group_and_releases_the_lock(self):
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                with self.assertRaises(JevTimeoutError) as ctx:
                    await run("t", "https://example.test", timeout_ms=1000, max_steps=1)
                return ctx.exception

            err = asyncio.run(scenario())
        self.assertEqual(err.status, "timeout")
        self.assertIn("timeout_ms=1000", err.result["error"])
        wait_pid_dead(self.wait_pidfile())
        self.assertEqual(self.go()["status"], "completed")

    def test_cancellation_kills_and_propagates(self):
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                task = asyncio.ensure_future(run("t", "https://example.test",
                                                 timeout_ms=60000))
                await self.await_pidfile(task)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

            asyncio.run(scenario())
        wait_pid_dead(self.wait_pidfile())
        self.assertEqual(self.go()["status"], "completed")

    def test_repeated_cancel_holds_the_lock_until_termination(self):
        with self.mode("hang_sigterm"), self.fast_cleanup():
            async def scenario():
                task = asyncio.ensure_future(run("t", "https://example.test",
                                                 profile="busy", timeout_ms=60000))
                await self.await_pidfile(task)
                task.cancel()                 # SIGTERM sent; the leader survives ~2s
                await asyncio.sleep(0.3)
                task.cancel()                 # repeated cancel during teardown
                # teardown in progress: the profile lock must still be held
                with self.assertRaises(JevProfileInUseError):
                    await run("t", "https://example.test", profile="busy")
                with self.assertRaises(asyncio.CancelledError):
                    await task
                with self.mode("ok"):
                    return await run("t", "https://example.test", profile="busy")

            result = asyncio.run(scenario())
        self.assertEqual(result["status"], "completed")
        wait_pid_dead(self.wait_pidfile())

    def test_orphan_is_killed_when_the_leader_exits_with_garbage(self):
        # malformed stdout plus exit code 0: the descendant must still die.
        with self.mode("grandchild"), self.fast_cleanup():
            with self.assertRaises(JevProtocolError):
                self.go(timeout_ms=30000)
        wait_pid_dead(self.wait_pidfile("grandchild.pid"))
        self.assertEqual(self.go()["status"], "completed")

    def test_success_path_sweeps_leftovers_before_releasing_the_lock(self):
        with self.mode("leftover"):
            result = self.go()
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any("terminated before the profile lock" in w
                            for w in result["warnings"]), result["warnings"])
        wait_pid_dead(self.wait_pidfile("leftover.pid"))

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
            spawned.append(proc.pid)          # process exists ...
            await asyncio.sleep(1.0)          # ... but creation has not returned
            return proc

        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                with mock.patch.object(asyncio, "create_subprocess_exec", slow_create):
                    task = asyncio.ensure_future(run("t", "https://example.test",
                                                     profile="spawn", timeout_ms=60000))
                    deadline = time.monotonic() + PID_WAIT_S
                    while not spawned:
                        if task.done():
                            raise AssertionError(f"run finished early: {task.exception()!r}")
                        if time.monotonic() >= deadline:
                            raise AssertionError("runner process was never created")
                        await asyncio.sleep(0.02)
                    task.cancel()             # mid-creation, process already forked
                    with self.assertRaises(asyncio.CancelledError):
                        await task

            asyncio.run(scenario())
        self.assertEqual(len(spawned), 1)
        wait_pid_dead(spawned[0])                      # adopted, not leaked
        self.assertEqual(self.find_pidfiles(), [])     # never got to run its task
        self.assertEqual(self.go(profile="spawn")["status"], "completed")

    def test_profile_in_use_fails_promptly(self):
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                first = asyncio.ensure_future(run("t", "https://example.test",
                                                  profile="busy", timeout_ms=60000))
                await self.await_pidfile(first)
                started = time.monotonic()
                with self.assertRaises(JevProfileInUseError) as ctx:
                    await run("t", "https://example.test", profile="busy")
                elapsed = time.monotonic() - started
                first.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await first
                return ctx.exception, elapsed

            err, elapsed = asyncio.run(scenario())
        self.assertEqual(err.status, "profile_in_use")
        self.assertIn("busy", err.message)
        self.assertLess(elapsed, 3.0)
        wait_pid_dead(self.wait_pidfile())
        self.assertEqual(self.go(profile="busy")["status"], "completed")

    def test_different_profiles_run_concurrently(self):
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                hanging = asyncio.ensure_future(run("t", "https://example.test",
                                                    profile="aaa", timeout_ms=60000))
                await self.await_pidfile(hanging)
                with self.mode("ok"):          # only "aaa" hangs
                    other = await run("t", "https://example.test", profile="bbb")
                hanging.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await hanging
                return other

            result = asyncio.run(scenario())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["profile_dir"], str(self.home / "profiles" / "bbb"))


class ResolutionTests(unittest.TestCase):
    def test_runtime_paths_resolve_to_the_skill_root(self):
        root = Path(jev.__file__).resolve().parents[2]
        self.assertEqual(root.name, "jev")
        self.assertEqual(jev._runtime_dir(), root / "runtime")
        self.assertEqual(jev._runner_path(), root / "runtime" / "runner.py")

    def test_launch_command_runs_the_installed_runtime_interpreter(self):
        """No uv at run time: the runner itself must be the process the
        wrapper spawns, so it leads the group that gets killed."""
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            (runtime / ".venv" / "bin").mkdir(parents=True)
            python = runtime / ".venv" / "bin" / "python"
            python.write_text("#!/bin/sh\n")
            python.chmod(0o700)
            runner = runtime / "runner.py"
            runner.write_text("# fake\n")
            with mock.patch.object(jev, "_runtime_dir", return_value=runtime):
                self.assertEqual(jev._launch_command(), [str(python), str(runner)])

    def test_launch_command_reports_setup_for_a_missing_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            runtime.mkdir()
            with mock.patch.object(jev, "_runtime_dir", return_value=runtime):
                with self.assertRaises(JevError) as missing_runner:
                    jev._launch_command()
                (runtime / "runner.py").write_text("# fake\n")
                with self.assertRaises(JevError) as missing_python:
                    jev._launch_command()
        for ctx in (missing_runner, missing_python):
            self.assertEqual(ctx.exception.status, "launch_error")
            self.assertIn("uv sync --project", ctx.exception.message)
        self.assertIn("interpreter", missing_python.exception.message)

    def test_home_dir_is_configurable_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "jev-home"
            with env_set(JEV_HOME=str(home)):
                self.assertEqual(jev._home_dir(), home.resolve())
            self.assertFalse(home.exists(), "reading the home path must not create it")
        with env_set(JEV_HOME=None):
            self.assertEqual(jev._home_dir(), Path(jev.DEFAULT_HOME).expanduser().resolve())

    def test_child_env_drops_browser_attach_variables(self):
        with env_set(BU_CDP_URL="http://127.0.0.1:9222",
                     BU_CDP_WS="ws://127.0.0.1:9222/devtools/browser/x",
                     BROWSER_USE_CDP_URL="http://127.0.0.1:9222",
                     CDP_URL="http://127.0.0.1:9222",
                     CHROME_CDP_URL="http://127.0.0.1:9222",
                     BH_HOME="/tmp/user-harness", BH_RUNTIME_DIR="/tmp/user-runtime",
                     OPENROUTER_API_KEY=SECRET):
            env = jev._child_env()
        for dropped in ("BU_CDP_URL", "BU_CDP_WS", "BROWSER_USE_CDP_URL", "CDP_URL",
                        "CHROME_CDP_URL", "BH_HOME", "BH_RUNTIME_DIR"):
            self.assertNotIn(dropped, env)
        self.assertEqual(env["DO_NOT_TRACK"], "1")
        self.assertEqual(env["ANONYMIZED_TELEMETRY"], "false")
        self.assertEqual(env["BH_TELEMETRY"], "0")
        self.assertEqual(env["OPENROUTER_API_KEY"], SECRET)

    def test_redact_replaces_matching_env_values_only(self):
        with env_set(LEAK_TEST_TOKEN=SECRET, SHORT_TOK="short", SAFE_VAR="notasecretvalue"):
            redacted = jev._redact(f"got {SECRET} and short and notasecretvalue")
        self.assertNotIn(SECRET, redacted)
        self.assertIn("short", redacted)
        self.assertIn("notasecretvalue", redacted)

    def test_error_str_is_typed_and_carries_the_partial_result(self):
        err = JevError("s", "m", {"a": 1})
        self.assertEqual(str(err), "jev error [s]: m")
        self.assertEqual(err.result, {"a": 1})
        self.assertIsInstance(JevValidationError("x", "y"), ValueError)


if __name__ == "__main__":
    unittest.main()
