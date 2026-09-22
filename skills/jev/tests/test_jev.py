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
# Marker expectation for wrapper-generated unknown-row tests. It must not appear
# in error text: rows are named by fingerprint, and the declaration is not echoed.
UNATTEMPTED_EQUALS = "PIN-4242-DO-NOT-ECHO"
# Every wait in this suite is finite: a hung child fails the test, never the run.
PID_WAIT_S = 10.0
DEAD_WAIT_S = 12.0


def declared_unattempted_checks():
    """Two fresh declarations used to prove wrapper-generated unknown rows."""
    return [
        {"id": "heading", "kind": "text", "selector": "#status",
         "equals": UNATTEMPTED_EQUALS},
        {"id": "rows", "kind": "count", "selector": ".row", "equals": 3},
    ]


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

    def assert_no_browser_or_model(self, result):
        """A local wrapper failure never invents a browser session or a model call."""
        self.assertIsNone(result["model"])
        self.assertIsNone(result["resolved_model"])
        self.assertIsNone(result["helper_model"])
        self.assertIsNone(result["screenshot_path"])
        self.assertIsNone(result["output"])
        self.assertEqual(result["text"], "")

    def assert_not_run_verification(self, result):
        payload = result["verification"]
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["status"], "not_run")
        self.assertEqual(payload["scope"], jev.CHECK_SCOPE)
        self.assertEqual(payload["declared"], 0)
        self.assertEqual(payload["checks"], [])
        self.assertEqual(payload["counts"], {"passed": 0, "failed": 0, "unknown": 0})

    def assert_unattempted_verification(self, result, declared):
        """Same scoped unknown rows the runner emits when the read never ran."""
        payload = result["verification"]
        normalized = jev.normalize_checks(declared)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["status"], "unknown")
        self.assertEqual(payload["scope"], jev.CHECK_SCOPE)
        self.assertEqual(payload["boundary"], "browser_dom")
        self.assertEqual(payload["declared"], len(normalized))
        self.assertEqual(payload["counts"], {
            "passed": 0, "failed": 0, "unknown": len(normalized),
        })
        self.assertEqual(payload["consistency"], "not_read")
        self.assertIsNone(payload["checked_at_url"])
        self.assertIsNone(payload["captured_at_ms"])
        rows = payload["checks"]
        self.assertEqual(len(rows), len(normalized))
        blob = json.dumps(payload)
        self.assertNotIn(UNATTEMPTED_EQUALS, blob)
        for row, check in zip(rows, normalized):
            self.assertEqual(row["id"], check["id"])
            self.assertEqual(row["kind"], check["kind"])
            self.assertEqual(row["status"], "unknown")
            self.assertEqual(row["reason"], "verification_not_attempted")
            self.assertEqual(
                row["fingerprint"], jev.checks.declaration_fingerprint(check),
            )
            self.assertEqual(row["boundary"], jev.CHECK_BOUNDARY)
            self.assertEqual(
                row["observed"],
                {"available": False, "reason": "verification_not_attempted"},
            )
            for echoed in ("equals", "contains", "selector", "check"):
                self.assertNotIn(echoed, row)


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

    def test_rows_name_their_declaration_and_do_not_echo_it(self):
        declared = [{"id": "done", "kind": "url", "equals": "https://example.test/done"},
                    {"id": "rows", "kind": "count", "selector": ".r", "equals": 3}]
        rows = self.go(checks=declared)["verification"]["checks"]
        self.assertEqual(
            [row["fingerprint"] for row in rows],
            [jev.checks.declaration_fingerprint(check)
             for check in jev.normalize_checks(declared)],
        )
        for row in rows:
            self.assertNotIn("check", row, "the declaration is not echoed back")
            self.assertEqual(row["boundary"], jev.CHECK_BOUNDARY)

    def test_a_credential_shaped_declaration_still_completes(self):
        """The runner redacts its whole result, declared text included.

        A row whose id or expectation looks like a credential comes back
        rewritten. The run must still complete, and nothing restores the
        original text.
        """
        literals = ["Bearer YOUR_TOKEN_HERE", "sk-EXAMPLE_PLACEHOLDER_00000000"]
        declared = [
            {"id": "auth", "kind": "text", "selector": "#s", "contains": literals[0]},
            {"id": "key " + literals[1], "kind": "value", "selector": "#k",
             "equals": literals[1]},
        ]
        with env_set(FAKE_REDACT_LITERALS=json.dumps(literals)), \
                self.mode("checks_redacted_transport"):
            result = self.go(checks=declared)
        payload = result["verification"]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(
            [row["fingerprint"] for row in payload["checks"]],
            [jev.checks.declaration_fingerprint(check)
             for check in jev.normalize_checks(declared)],
        )
        self.assertEqual(payload["checks"][1]["id"], "key " + jev._REDACTED)
        blob = json.dumps(result)
        for literal in literals:
            self.assertNotIn(literal, blob)

    def test_a_second_redaction_says_what_it_returned(self):
        """capture_metadata must describe the string the caller receives."""
        declared = [{"id": "saved", "kind": "text", "selector": "#s", "equals": "Saved"}]
        with env_set(LEAK_TEST_TOKEN=SECRET), self.mode("checks_capture_metadata"):
            payload = self.go(checks=declared)["verification"]
        self.assertNotIn(SECRET, json.dumps(payload))
        for key, name in (("checked_at_url", "url"), ("checked_at_title", "title")):
            with self.subTest(field=name):
                field = payload["capture_metadata"][name]
                self.assertIn(jev._REDACTED, payload[key])
                self.assertTrue(field["redacted"])
                self.assertEqual(field["returned_length"], len(payload[key]))
                # length stays the runtime's own measurement, and says so.
                self.assertNotEqual(field["length"], field["returned_length"])
                self.assertFalse(field["truncated"])

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

    FORGED_TWISTS = (
        ("foreign_declaration", ".fingerprint does not name the check"),
        ("wrong_fingerprint", ".fingerprint does not name the check"),
        ("missing_fingerprint", ".fingerprint is missing"),
        ("malformed_fingerprint", ".fingerprint is missing"),
        ("wrong_kind", ".kind must be the declared kind"),
        ("row_id_type", ".id must be a string label"),
        ("row_boundary", ".boundary must be 'browser_dom'"),
        ("forged_note", "verification.note must be"),
        ("forged_consistency", "verification.consistency must be one of"),
        ("bool_declared", "declared must be the integer"),
        ("bool_counts", "counts must tally"),
        ("wrong_counts", "counts must tally"),
        ("wrong_aggregate", "summarize(rows)"),
        ("row_status", "passed, failed, unknown"),
        ("bare_row", "must be an object"),
    )
    # Twists that need two declared checks to be forgeries at all.
    PAIR_TWISTS = (
        ("dup_rows", ".fingerprint does not name the check"),
        ("swapped_rows", ".fingerprint does not name the check"),
    )

    def _declared_text_check(self):
        return [{"id": "saved", "kind": "text", "selector": "#s", "equals": "Saved"}]

    def test_forged_check_rows_are_protocol_errors(self):
        declared = self._declared_text_check()
        for name, fragment in self.FORGED_TWISTS:
            with self.subTest(twist=name):
                err = self.assert_status("checks_twist_" + name, "protocol", JevProtocolError,
                                         checks=declared)
                self.assertIn(fragment, err.message)
        two = declared + [{"id": "rows", "kind": "count", "selector": ".r", "equals": 3}]
        for name, fragment in self.PAIR_TWISTS:
            with self.subTest(twist=name):
                err = self.assert_status("checks_twist_" + name, "protocol",
                                         JevProtocolError, checks=two)
                self.assertIn(fragment, err.message)

    def test_forged_partial_verification_is_a_protocol_error(self):
        declared = self._declared_text_check()
        for status in ("max_steps", "blocked"):
            for name, fragment in self.FORGED_TWISTS:
                with self.subTest(status=status, twist=name):
                    err = self.assert_status(
                        "partial_twist_" + status + "_" + name, "protocol", JevProtocolError,
                        checks=declared)
                    self.assertIn(fragment, err.message)
                    self.assertEqual(err.result["status"], status)
                    self.assertTrue(err.result.get("screenshot_path"))

    def test_a_blocked_stop_keeps_its_check_evidence(self):
        declared = self._declared_text_check()
        err = self.assert_status("checks_blocked", "blocked", checks=declared)
        payload = err.result["verification"]
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["checks"][0]["id"], "saved")
        self.assertEqual(payload["scope"], jev.CHECK_SCOPE)
        self.assertEqual(err.result["status"], "blocked")

    def test_a_capture_failure_keeps_legitimate_check_rows(self):
        declared = self._declared_text_check()
        err = self.assert_status("noshot", "artifact_error", checks=declared)
        payload = err.result["verification"]
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(len(payload["checks"]), 1)
        self.assertEqual(payload["checks"][0]["id"], "saved")
        self.assertEqual(payload["checks"][0]["kind"], "text")
        self.assertEqual(payload["scope"], jev.CHECK_SCOPE)

    def test_a_capture_failure_does_not_accept_forged_rows(self):
        declared = self._declared_text_check()
        err = self.assert_status("checks_noshot_corrupt", "protocol", JevProtocolError,
                                 checks=declared)
        self.assertIn(".fingerprint does not name the check", err.message)
        self.assertEqual(err.result["status"], "completed")

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
        declared = declared_unattempted_checks()
        frozen = json.loads(json.dumps(declared))
        with mock.patch.object(jev, "_launch_command", REAL_LAUNCH_COMMAND), \
             mock.patch.object(jev, "_runtime_dir", return_value=missing):
            with self.assertRaises(JevError) as ctx:
                self.go(checks=declared)
        err = ctx.exception
        self.assertEqual(err.status, "launch_error")
        self.assertIn("uv sync", err.message)
        self.assertTrue(Path(err.result["artifact_dir"]).is_dir())
        self.assertNotIn(UNATTEMPTED_EQUALS, err.message)
        self.assertEqual(declared, frozen)
        self.assert_unattempted_verification(err.result, frozen)
        self.assert_no_browser_or_model(err.result)

    def test_launch_error_when_the_interpreter_is_missing(self):
        declared = declared_unattempted_checks()
        frozen = json.loads(json.dumps(declared))
        with mock.patch.object(jev, "_launch_command",
                               return_value=["/nonexistent/python-bin"]):
            with self.assertRaises(JevError) as ctx:
                self.go(checks=declared)
        err = ctx.exception
        self.assertEqual(err.status, "launch_error")
        self.assertNotIn(UNATTEMPTED_EQUALS, err.message)
        self.assertEqual(declared, frozen)
        self.assert_unattempted_verification(err.result, frozen)
        self.assert_no_browser_or_model(err.result)

    def test_launch_error_without_declared_checks_is_not_run(self):
        missing = self.tmp / "runtime-missing"
        with mock.patch.object(jev, "_launch_command", REAL_LAUNCH_COMMAND), \
             mock.patch.object(jev, "_runtime_dir", return_value=missing):
            with self.assertRaises(JevError) as ctx:
                self.go()
        err = ctx.exception
        self.assertEqual(err.status, "launch_error")
        self.assert_not_run_verification(err.result)
        self.assert_no_browser_or_model(err.result)

    def test_login_launch_error_keeps_verification_none(self):
        missing = self.tmp / "runtime-missing"
        with mock.patch.object(jev, "_launch_command", REAL_LAUNCH_COMMAND), \
             mock.patch.object(jev, "_runtime_dir", return_value=missing):
            with self.assertRaises(JevError) as ctx:
                asyncio.run(login(url="https://acme.test/login"))
        err = ctx.exception
        self.assertEqual(err.status, "launch_error")
        self.assertIsNone(err.result["verification"])
        self.assert_no_browser_or_model(err.result)

    def test_protocol_error_on_garbage_stdout_reports_declared_checks(self):
        declared = declared_unattempted_checks()
        frozen = json.loads(json.dumps(declared))
        with env_set(LEAK_TEST_TOKEN=SECRET):
            err = self.assert_status("garbage", "protocol", JevProtocolError,
                                     checks=declared)
        self.assertNotIn(SECRET, err.message)
        self.assertIn(jev._REDACTED, err.message)
        self.assertNotIn(UNATTEMPTED_EQUALS, err.message)
        self.assertEqual(declared, frozen)
        self.assert_unattempted_verification(err.result, frozen)
        self.assert_no_browser_or_model(err.result)

    def test_nonzero_exit_with_declared_checks_is_unknown_not_attempted(self):
        # exit 1 is refused before runner fields are adopted, so the partial
        # result is the local unknown fallback. The protocol message may still
        # quote a stdout tail; the structured verification object must not.
        declared = declared_unattempted_checks()
        frozen = json.loads(json.dumps(declared))
        err = self.assert_status("exit1", "protocol", JevProtocolError, checks=declared)
        self.assertEqual(declared, frozen)
        self.assert_unattempted_verification(err.result, frozen)

    def test_runner_omitted_verification_is_not_replaced_with_unknown(self):
        """A parsed runner payload that returned no object stays a protocol error.

        The wrapper must not overwrite that None with synthesized unknown rows:
        missing verification after a real stdout object is a contract break, not
        a local pre-read failure.
        """
        declared = declared_unattempted_checks()
        err = self.assert_status("checks_missing", "protocol", JevProtocolError,
                                 checks=declared)
        self.assertIn("no verification object", err.message)
        self.assertIsNone(err.result["verification"])

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


class VerificationContractTests(unittest.TestCase):
    """Direct _finish_result probes: the gate the reviewer called, not the fake runner."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jev-verif-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.art = self.tmp / "art"
        self.art.mkdir()
        self.prof = self.tmp / "prof"
        self.prof.mkdir()
        self.stderr = self.art / "runner.stderr.log"
        self.stderr.write_text("")
        self.png = self.art / "final.png"
        self.png.write_bytes(jev._PNG_MAGIC + b"\x00" * 16)
        self.one = jev.normalize_checks(
            [{"id": "saved", "kind": "text", "selector": "#s", "equals": "Saved"}]
        )
        self.two = jev.normalize_checks([
            {"id": "saved", "kind": "text", "selector": "#s", "equals": "Saved"},
            {"id": "rows", "kind": "count", "selector": ".r", "equals": 3},
        ])

    def _png_path(self):
        return str(self.png)

    def _honest(self, checks, *, failed=False, unknown=False):
        from jev.checks import verification_payload
        rows = []
        for check in checks:
            if check["kind"] == "count":
                value = 0 if failed else check["equals"]
            elif failed:
                value = "a value the page never showed"
            elif "equals" in check:
                value = check["equals"]
            else:
                value = "saw " + check["contains"]
            if unknown:
                rows.append({"available": False, "reason": "page_unavailable"})
            else:
                rows.append({"available": True, "value": value})
        return verification_payload(checks, {
            "url": "https://example.test/done", "title": "Done", "at": 1, "rows": rows,
        })

    def _obj(self, verification, status="completed", **extra):
        obj = {
            "status": status,
            "output": {
                "final_url": "https://example.test/done",
                "final_title": "Done",
                "page_text": "ok",
                "completion_claimed": True,
                "verification": "not_performed",
            },
            "text": "done",
            "steps": 1,
            "cost": 0.01,
            "screenshot_path": self._png_path(),
            "verification": verification,
            "warnings": [],
        }
        obj.update(extra)
        return obj

    def _finish(self, obj, checks):
        return jev._finish_result(
            "run", json.dumps(obj).encode(), 0, self.art, self.prof, self.stderr, checks,
        )

    def _protocol(self, obj, checks, fragment):
        with self.assertRaises(JevProtocolError) as ctx:
            self._finish(obj, checks)
        self.assertIn(fragment, ctx.exception.message)
        return ctx.exception

    def test_reviewer_forged_completed_payloads_are_rejected(self):
        import fake_runner
        pair = {name for name, _fragment in FailurePathTests.PAIR_TWISTS}
        cases = FailurePathTests.FORGED_TWISTS + FailurePathTests.PAIR_TWISTS
        for name, fragment in cases:
            with self.subTest(twist=name):
                checks = self.two if name in pair else self.one
                base = self._honest(checks)
                twisted = fake_runner.twist_verification(base, name)
                self._protocol(self._obj(twisted), checks, fragment)

    def test_reviewer_forged_partial_payloads_are_rejected(self):
        import fake_runner
        for status in ("max_steps", "blocked"):
            for name, fragment in FailurePathTests.FORGED_TWISTS:
                with self.subTest(status=status, twist=name):
                    twisted = fake_runner.twist_verification(self._honest(self.one), name)
                    err = self._protocol(self._obj(twisted, status=status), self.one, fragment)
                    self.assertEqual(err.result["status"], status)
                    self.assertEqual(err.result["screenshot_path"], self._png_path())

    def test_valid_failed_and_unknown_aggregates_are_accepted(self):
        failed = self._honest(self.one, failed=True)
        result = self._finish(self._obj(failed), self.one)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["verification"]["status"], "failed")
        self.assertEqual(result["verification"]["counts"]["failed"], 1)
        unknown = self._honest(self.one, unknown=True)
        result = self._finish(self._obj(unknown), self.one)
        self.assertEqual(result["verification"]["status"], "unknown")
        self.assertEqual(result["verification"]["counts"]["unknown"], 1)
        mixed = self._honest(self.two, failed=True)
        mixed["checks"][1]["status"] = "unknown"
        mixed["checks"][1]["reason"] = "page_unavailable"
        mixed["counts"] = {"passed": 0, "failed": 1, "unknown": 1}
        mixed["status"] = "failed"
        result = self._finish(self._obj(mixed), self.two)
        self.assertEqual(result["verification"]["status"], "failed")

    def test_zero_checks_only_allows_not_run_and_empty_rows(self):
        empty = self._honest([])
        result = self._finish(self._obj(empty), [])
        self.assertEqual(result["verification"]["status"], "not_run")
        self.assertEqual(result["verification"]["checks"], [])
        none = self._obj(None)
        result = self._finish(none, [])
        self.assertIsNone(result["verification"])
        claimed = dict(empty, status="passed", counts={"passed": 0, "failed": 0, "unknown": 0})
        self._protocol(self._obj(claimed), [], "not_run")
        false_declared = dict(empty, declared=False)
        self._protocol(self._obj(false_declared), [], "declared must be the integer")

    def test_bool_declared_count_is_not_accepted_as_one(self):
        payload = self._honest(self.one)
        payload["declared"] = True
        self._protocol(self._obj(payload), self.one, "declared must be the integer 1")

    def _transported(self, payload, literals):
        """The payload as a transport that rewrites text would deliver it.

        The runner emits redact(json.dumps(result)), so one redaction pass
        reaches every string in the result, the caller's own declared text
        included. The literals come from the test: nothing here copies the
        runtime's patterns and no real environment value is involved.
        """
        blob = json.dumps(payload)
        for literal in literals:
            blob = blob.replace(literal, jev._REDACTED)
        return json.loads(blob)

    def test_a_missing_or_malformed_fingerprint_is_rejected(self):
        for name, mutate in (("missing", lambda row: row.pop("fingerprint")),
                             ("null", lambda row: row.update(fingerprint=None)),
                             ("short", lambda row: row.update(fingerprint="abc123")),
                             ("not_hex", lambda row: row.update(
                                 fingerprint="z" * jev.checks.FINGERPRINT_CHARS)),
                             ("nested", lambda row: row.update(fingerprint={"v": 1}))):
            with self.subTest(shape=name):
                payload = self._honest(self.one)
                payload["checks"][0] = dict(payload["checks"][0])
                mutate(payload["checks"][0])
                self._protocol(self._obj(payload), self.one, ".fingerprint is missing")

    def test_a_row_must_fingerprint_the_declaration_at_its_position(self):
        """A changed selector, expectation, id, kind or order is a mismatch."""
        others = [
            [{"id": "saved", "kind": "text", "selector": "#s", "equals": "Other"}],
            [{"id": "saved", "kind": "text", "selector": "#other", "equals": "Saved"}],
            [{"id": "saved", "kind": "text", "selector": "#s", "contains": "Saved"}],
            [{"id": "another-id", "kind": "text", "selector": "#s", "equals": "Saved"}],
            [{"id": "saved", "kind": "value", "selector": "#s", "equals": "Saved"}],
        ]
        for other in others:
            with self.subTest(declared=repr(other[0])[:70]):
                checks = jev.normalize_checks(other)
                err = self._protocol(self._obj(self._honest(checks)), self.one,
                                     ".fingerprint does not name the check")
                # The message names the position and the kind, never a value.
                self.assertNotIn("Saved", err.message)
                self.assertNotIn("Other", err.message)
                self.assertNotIn("#s", err.message)
        swapped = self._honest(self.two)
        swapped["checks"] = [swapped["checks"][1], swapped["checks"][0]]
        self._protocol(self._obj(swapped), self.two, ".fingerprint does not name the check")

    def test_a_redacted_declaration_still_verifies_on_every_row_status(self):
        """The blocker: credential-shaped declared text is rewritten in transit.

        The row still names its declaration, because the fingerprint is a hex
        digest computed before transport, so an honest result is not turned
        into a protocol error.
        """
        literals = ["Bearer YOUR_TOKEN_HERE", "sk-EXAMPLE_PLACEHOLDER_00000000"]
        checks = jev.normalize_checks([
            {"id": "auth " + literals[0], "kind": "text", "selector": "#s",
             "contains": literals[0]},
            {"id": "key", "kind": "value", "selector": "#k", "equals": literals[1]},
        ])
        for kwargs, expected in ((dict(), "passed"), (dict(failed=True), "failed"),
                                 (dict(unknown=True), "unknown")):
            with self.subTest(status=expected):
                payload = self._transported(self._honest(checks, **kwargs), literals)
                self.assertEqual(payload["checks"][0]["id"], "auth " + jev._REDACTED)
                result = self._finish(self._obj(payload), checks)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["verification"]["status"], expected)
                blob = json.dumps(result["verification"])
                for literal in literals:
                    self.assertNotIn(literal, blob)

    def test_a_forged_row_is_still_rejected_after_redaction(self):
        """Redaction tolerance is not a hole: the fingerprint still decides."""
        literal = "Bearer YOUR_TOKEN_HERE"
        checks = jev.normalize_checks(
            [{"id": "auth", "kind": "text", "selector": "#s", "contains": literal}])
        other = jev.normalize_checks(
            [{"id": "auth", "kind": "text", "selector": "#s", "contains": literal + "-x"}])
        payload = self._transported(self._honest(other), [literal])
        self._protocol(self._obj(payload), checks, ".fingerprint does not name the check")


class LifecycleTests(FakeRunnerTestCase):
    def test_timeout_kills_the_process_group_and_releases_the_lock(self):
        declared = declared_unattempted_checks()
        frozen = json.loads(json.dumps(declared))
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                with self.assertRaises(JevTimeoutError) as ctx:
                    await run("t", "https://example.test", timeout_ms=1000, max_steps=1,
                              checks=declared)
                return ctx.exception

            err = asyncio.run(scenario())
        self.assertEqual(err.status, "timeout")
        self.assertIn("timeout_ms=1000", err.result["error"])
        self.assertNotIn(UNATTEMPTED_EQUALS, err.message)
        self.assertNotIn(UNATTEMPTED_EQUALS, err.result["error"])
        self.assertEqual(declared, frozen)
        self.assert_unattempted_verification(err.result, frozen)
        self.assert_no_browser_or_model(err.result)
        wait_pid_dead(self.wait_pidfile())
        self.assertEqual(self.go()["status"], "completed")

    def test_timeout_without_declared_checks_is_not_run(self):
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                with self.assertRaises(JevTimeoutError) as ctx:
                    await run("t", "https://example.test", timeout_ms=1000, max_steps=1)
                return ctx.exception

            err = asyncio.run(scenario())
        self.assertEqual(err.status, "timeout")
        self.assert_not_run_verification(err.result)
        wait_pid_dead(self.wait_pidfile())

    def test_login_timeout_keeps_verification_none(self):
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                with self.assertRaises(JevTimeoutError) as ctx:
                    await login(url="https://acme.test/login", timeout_ms=1000)
                return ctx.exception

            err = asyncio.run(scenario())
        self.assertEqual(err.status, "timeout")
        self.assertIsNone(err.result["verification"])
        wait_pid_dead(self.wait_pidfile())

    def test_cancellation_kills_and_propagates(self):
        declared = declared_unattempted_checks()
        frozen = json.loads(json.dumps(declared))
        with self.mode("hang"), self.fast_cleanup():
            async def scenario():
                task = asyncio.ensure_future(run("t", "https://example.test",
                                                 timeout_ms=60000, checks=declared))
                await self.await_pidfile(task)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

            asyncio.run(scenario())
        self.assertEqual(declared, frozen)
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

    def test_empty_stdout_with_declared_checks_is_unknown_not_attempted(self):
        declared = declared_unattempted_checks()
        frozen = json.loads(json.dumps(declared))
        with self.mode("grandchild"), self.fast_cleanup():
            with self.assertRaises(JevProtocolError) as ctx:
                self.go(timeout_ms=30000, checks=declared)
        err = ctx.exception
        self.assertNotIn(UNATTEMPTED_EQUALS, err.message)
        self.assertEqual(declared, frozen)
        self.assert_unattempted_verification(err.result, frozen)
        wait_pid_dead(self.wait_pidfile("grandchild.pid"))

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
