"""Deterministic tests for the Jev runtime. No model calls, no paid calls.

Usage:
    uv run --frozen python tests/run_tests.py            # unit group
    uv run --frozen python tests/run_tests.py --group checks   # headless Chrome
    uv run --frozen python tests/run_tests.py --group browser  # opens Chrome
    uv run --frozen python tests/run_tests.py --group login    # opens Chrome
"""

import base64
import json
import os
import py_compile
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE.parent
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(HERE))

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
JPEG_HEAD = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    mark = "PASS" if condition else "FAIL"
    print("%-6s %s %s" % (mark, name, detail if not condition else ""))
    return bool(condition)


def expect_raises(name, exception_types, call, message_contains=None):
    try:
        call()
    except exception_types as exc:
        if message_contains and message_contains not in str(exc):
            return check(name, False, "message %r lacks %r" % (str(exc), message_contains))
        return check(name, True)
    except Exception as exc:  # wrong type
        return check(name, False, "raised %s: %s" % (type(exc).__name__, exc))
    return check(name, False, "no exception raised")


# --------------------------------------------------------------------------
def test_validation(runner):
    base = {
        "op": "run",
        "task": "do a thing",
        "url": "http://127.0.0.1:1/",
        "profile_dir": "/tmp/jev-test-profile",
        "artifact_dir": "/tmp/jev-test-artifacts",
    }

    def with_fields(**extra):
        request = dict(base)
        request.update(extra)
        return lambda: runner.normalize(request)

    check("validation.accepts_minimal", runner.normalize(dict(base))["max_steps"] == 25)
    expect_raises("validation.rejects_bool_max_steps", runner.RequestError, with_fields(max_steps=True), "integer")
    expect_raises("validation.rejects_zero_max_steps", runner.RequestError, with_fields(max_steps=0), "greater than 0")
    expect_raises("validation.rejects_str_max_steps", runner.RequestError, with_fields(max_steps="25"), "integer")
    expect_raises("validation.rejects_bool_timeout", runner.RequestError, with_fields(timeout_ms=True), "integer")
    expect_raises("validation.rejects_negative_timeout", runner.RequestError, with_fields(timeout_ms=-1), "greater")
    expect_raises("validation.rejects_bool_cost", runner.RequestError, with_fields(max_cost_usd=True), "number")
    expect_raises("validation.rejects_zero_cost", runner.RequestError, with_fields(max_cost_usd=0), "greater than 0")
    expect_raises("validation.rejects_inf_cost", runner.RequestError, with_fields(max_cost_usd=float("inf")), "finite")
    expect_raises("validation.rejects_file_url", runner.RequestError, with_fields(url="file:///etc/passwd"), "http")
    expect_raises("validation.rejects_relative_dir", runner.RequestError, with_fields(profile_dir="rel/path"), "absolute")
    expect_raises("validation.rejects_empty_task", runner.RequestError, with_fields(task="  "), "task")
    expect_raises("validation.rejects_bad_op", runner.RequestError, with_fields(op="extract"), "op must be")
    expect_raises("validation.rejects_bad_profile", runner.RequestError, with_fields(profile="../escape"), "profile must")
    check("validation.accepts_good_profile", runner.normalize(dict(base, profile="work-1"))["profile"] == "work-1")
    login = runner.normalize(
        {"op": "login", "url": "https://example.com", "profile_dir": "/tmp/p", "artifact_dir": "/tmp/a"}
    )
    check("validation.login_needs_no_task", login["task"] is None and login["max_cost_usd"] is None)
    check("validation.login_has_no_confidence_policy", login["confidence"] is None)

    check("validation.confidence_defaults_to_none", runner.normalize(dict(base))["confidence"] is None)
    check("validation.confidence_copies_the_policy",
          runner.normalize(dict(base, confidence={"operation": 0.8, "binding": 1.0}))["confidence"]
          == {"operation": 0.8, "binding": 1.0})
    check("validation.empty_confidence_is_kept_as_record_only",
          runner.normalize(dict(base, confidence={}))["confidence"] == {})
    policy = {"operation": 0.8}
    copied = runner.normalize(dict(base, confidence=policy))["confidence"]
    policy["operation"] = 0.1
    check("validation.confidence_is_a_private_copy", copied == {"operation": 0.8}, str(copied))
    for name, value, fragment in (
        ("unknown_key", {"speed": 0.8}, "must be one of"),
        ("empty_key", {"": 0.8}, "must be one of"),
        ("zero", {"operation": 0}, "greater than 0"),
        ("above_one", {"operation": 1.1}, "greater than 0"),
        ("bool", {"operation": True}, "greater than 0"),
        ("string", {"operation": "0.8"}, "greater than 0"),
        ("nan", {"operation": float("nan")}, "greater than 0"),
        ("list_value", {"operation": [0.8]}, "greater than 0"),
        ("not_an_object", [0.8], "must be an object"),
        ("number", 0.8, "must be an object"),
    ):
        expect_raises("validation.rejects_confidence_" + name, runner.RequestError,
                      with_fields(confidence=value), fragment)


def test_safety_metadata(runner):
    """The observation, side-effect and handoff builders, on their own."""
    page = {
        "url": "https://app.test/form", "title": "Form", "text": "page body",
        "w": 1120, "h": 780, "omitted_actions": 12, "text_truncated": True,
        "fingerprint": "a" * 64, "page_key": ["live field value"], "guards": {"10": ["x"]},
        "marker": ["page body"],
    }
    observation = runner.observation_of(page)
    check("safety.observation_keys",
          sorted(observation) == ["fingerprint", "omitted_actions", "text_truncated", "viewport"],
          json.dumps(sorted(observation)))
    check("safety.observation_values",
          observation["omitted_actions"] == 12 and observation["text_truncated"] is True
          and observation["viewport"] == {"w": 1120, "h": 780}, json.dumps(observation))
    blob = json.dumps(observation)
    check("safety.observation_omits_page_state",
          all(secret not in blob for secret in ("page body", "live field value", "page_key",
                                                "guards", "marker")), blob)
    empty = runner.observation_of({})
    check("safety.observation_defaults",
          empty == {"omitted_actions": 0, "text_truncated": False,
                    "viewport": {"w": None, "h": None}, "fingerprint": None}, json.dumps(empty))
    check("safety.observation_needs_a_page", runner.observation_of(None) is None)
    check("safety.observation_rejects_junk_sizes",
          runner.observation_of({"w": True, "h": "780", "omitted_actions": True})["viewport"]
          == {"w": None, "h": None})

    check("safety.no_rows_is_none_observed", runner.side_effects_of([]) == "none_observed")
    check("safety.skips_and_waits_are_none_observed",
          runner.side_effects_of([{"dispatch": "not_dispatched"}] * 3) == "none_observed")
    check("safety.one_attempt_is_uncertain",
          runner.side_effects_of([{"dispatch": "not_dispatched"}, {"dispatch": "attempted"}])
          == "uncertain")
    check("safety.unknown_is_uncertain",
          runner.side_effects_of([{"dispatch": "unknown"}]) == "uncertain")
    check("safety.a_row_without_dispatch_is_uncertain",
          runner.side_effects_of([{"step": 1}]) == "uncertain")
    check("safety.junk_history_is_uncertain",
          runner.side_effects_of(None) == "uncertain" and runner.side_effects_of(["x"]) == "uncertain")
    check("safety.confirmed_is_not_a_value",
          "confirmed" not in (runner.NONE_OBSERVED, runner.UNCERTAIN))

    check("safety.dispatch_unknown_without_state", runner.stopping_dispatch(None) == "unknown")
    check("safety.dispatch_not_dispatched_when_the_decision_made_no_row",
          runner.stopping_dispatch({
              "history": [],
              "decisions": [{"choice": "DONE", "decision_seq": 1}],
              "latest_dispatch": {"decision_seq": 1, "dispatch": "not_dispatched"},
          }) == "not_dispatched")
    check("safety.dispatch_reads_the_decision_record",
          runner.stopping_dispatch({
              "history": [{"dispatch": "attempted", "decision_seq": 1}],
              "decisions": [{"choice": "e1", "decision_seq": 1}],
              "latest_dispatch": {"decision_seq": 1, "dispatch": "attempted"},
          }) == "attempted")
    check("safety.dispatch_of_an_unreadable_record_is_unknown",
          runner.stopping_dispatch({
              "history": [{"dispatch": "typed", "decision_seq": 1}],
              "decisions": [{"choice": "e1", "decision_seq": 1}],
              "latest_dispatch": {"decision_seq": 1, "dispatch": "typed"},
          }) == "unknown")
    # The record must name the decision the run stopped on. One that names an
    # earlier decision describes something else and cannot be reported.
    check("safety.dispatch_of_a_stale_record_is_unknown",
          runner.stopping_dispatch({
              "history": [{"dispatch": "attempted", "decision_seq": 1}],
              "decisions": [{"choice": "e1", "decision_seq": 1},
                            {"choice": "e1", "decision_seq": 2}],
              "latest_dispatch": {"decision_seq": 1, "dispatch": "attempted"},
          }) == "unknown")
    # A state with no record at all is legacy or unreadable, never proof that
    # nothing was sent.
    check("safety.dispatch_without_a_record_is_unknown",
          runner.stopping_dispatch({"history": [{"dispatch": "attempted"}],
                                    "decisions": [{"choice": "e1"}]}) == "unknown"
          and runner.stopping_dispatch({"history": [], "decisions": []}) == "unknown"
          and runner.stopping_dispatch({"history": [], "decisions": [{"choice": "DONE"}]})
          == "unknown")
    # The counts are the same shape on both of these and the answers differ, so
    # no count can produce them. One dispatched click then a budget stop on a
    # newer decision; one dispatched click that the run stopped on.
    ambiguous = {"history": [{"dispatch": "attempted", "decision_seq": 1}],
                 "decisions": [{"choice": "e1", "decision_seq": 1},
                               {"choice": "e1", "decision_seq": 2}]}
    check("safety.dispatch_separates_states_the_counts_cannot",
          runner.stopping_dispatch({**ambiguous,
                                    "latest_dispatch": {"decision_seq": 2,
                                                        "dispatch": "not_dispatched"}})
          == "not_dispatched"
          and runner.stopping_dispatch({
              "history": [{"dispatch": "attempted", "decision_seq": 2}],
              "decisions": [{"choice": "e1", "decision_seq": 1},
                            {"choice": "e1", "decision_seq": 2}],
              "latest_dispatch": {"decision_seq": 2, "dispatch": "attempted"},
          }) == "attempted")

    hostile = runner.build_handoff(
        "low_operation_confidence",
        page,
        {
            "choice": "e1",
            # A label, a task, a typed value and a nested object must not survive.
            "operation": "CLICK; user@example.test password=hunter2",
            "operation_confidence": 0.62,
            "target": {"nested": "object"},
            "target_confidence": "0.9",
            "binding_key": "email address",
            "binding_confidence": 1.5,
        },
        "attempted",
    )
    check("safety.handoff_keys_are_exactly_the_allowlist",
          tuple(hostile) == runner.HANDOFF_FIELDS, json.dumps(sorted(hostile)))
    check("safety.handoff_drops_free_text", hostile["operation"] is None, str(hostile["operation"]))
    check("safety.handoff_drops_nested_objects", hostile["target"] is None, str(hostile["target"]))
    check("safety.handoff_drops_string_scores", hostile["target_confidence"] is None)
    check("safety.handoff_drops_out_of_range_scores", hostile["binding_confidence"] is None)
    check("safety.handoff_drops_keys_with_spaces", hostile["binding_key"] is None)
    check("safety.handoff_keeps_valid_ids_and_scores",
          hostile["choice"] == "e1" and hostile["operation_confidence"] == 0.62)
    check("safety.handoff_carries_the_observation",
          hostile["observation"] == observation, json.dumps(hostile["observation"]))
    check("safety.handoff_resume_policy",
          hostile["resume_policy"] == runner.RESUME_POLICY
          and "never replay" in runner.RESUME_POLICY, runner.RESUME_POLICY)
    check("safety.handoff_dispatch_is_an_enum",
          runner.build_handoff("x", page, {}, "sent")["input_dispatched"] == "unknown")
    check("safety.handoff_reason_is_an_id",
          runner.build_handoff("a reason with spaces", page, {})["reason"] == "unknown")

    passed = {"status": "passed", "declared": 2,
              "checks": [{"status": "passed"}, {"status": "passed"}]}
    check("safety.all_passed", runner.all_declared_checks_passed(passed))
    check("safety.one_failure_is_not_passed",
          not runner.all_declared_checks_passed(
              {"status": "passed", "declared": 2,
               "checks": [{"status": "passed"}, {"status": "failed"}]}))
    check("safety.missing_rows_are_not_passed",
          not runner.all_declared_checks_passed({"status": "passed", "declared": 2,
                                                 "checks": [{"status": "passed"}]}))
    check("safety.no_declared_check_is_not_passed",
          not runner.all_declared_checks_passed({"status": "not_run", "declared": 0, "checks": []})
          and not runner.all_declared_checks_passed(None))
    check("safety.unknown_is_not_passed",
          not runner.all_declared_checks_passed(
              {"status": "unknown", "declared": 1, "checks": [{"status": "unknown"}]}))

    check("safety.provisional_from_the_agent_flag",
          runner.completion_was_provisional({"provisional_done": True}, {}))
    check("safety.provisional_from_the_page",
          runner.completion_was_provisional({}, {"text_truncated": True})
          and runner.completion_was_provisional({}, {"omitted_actions": 3}))
    check("safety.not_provisional_on_a_whole_page",
          not runner.completion_was_provisional({"provisional_done": False},
                                                {"text_truncated": False, "omitted_actions": 0}))


def test_needs_review_status(runner):
    """needs_review is its own status, never a browser error."""
    class NeedsReview(Exception):
        """Same name as the vendored exception; classify matches by name."""

    check("needs_review.classify_is_not_a_browser_error",
          runner.classify(NeedsReview("withheld")) == runner.NEEDS_REVIEW,
          runner.classify(NeedsReview("withheld")))
    result = {"screenshot_path": None, "output": {"completion_claimed": False}}
    check("needs_review.decide_status",
          runner.decide_status("run", "needs_review", None, result, True) == runner.NEEDS_REVIEW)
    check("needs_review.dirty_cleanup_keeps_the_stop_reason",
          runner.decide_status("run", "needs_review", None, result, False) == runner.NEEDS_REVIEW)
    message = runner.DEFAULT_MESSAGES[runner.NEEDS_REVIEW]
    check("needs_review.message_says_inspect_and_do_not_replay",
          "inspect" in message and "not replay" in message and "handoff" in message, message)
    check("needs_review.stale_page_is_still_a_browser_error",
          runner.classify(type("StalePage", (ValueError,), {})("gone")) == runner.BROWSER_ERROR)


def test_cost_rules(runner):
    def attempt(status, cost, role="decision"):
        return {
            "role": role,
            "status_code": status,
            "cost_usd": cost,
            "latency_ms": 1,
            "usage": None,
            "resolved_model": None,
            "provider_message": None,
            "error": None,
        }

    runner.HTTP_ATTEMPTS.clear()
    cost, detail = runner.cost_summary()
    check("cost.no_calls_is_zero", cost == 0.0 and "no model requests" in detail["note"])

    runner.HTTP_ATTEMPTS.clear()
    runner.HTTP_ATTEMPTS.append(attempt(200, 0.0001))
    runner.HTTP_ATTEMPTS.append(attempt(200, 0.0002, "helper"))
    cost, detail = runner.cost_summary()
    check("cost.sums_known", abs(cost - 0.0003) < 1e-12, str(cost))

    runner.HTTP_ATTEMPTS.clear()
    runner.HTTP_ATTEMPTS.append(attempt(200, 0.0001))
    runner.HTTP_ATTEMPTS.append(attempt(200, None))
    cost, detail = runner.cost_summary()
    check("cost.unknown_is_null_not_zero", cost is None and detail["successful_attempts_without_cost"] == 1)

    runner.HTTP_ATTEMPTS.clear()
    runner.HTTP_ATTEMPTS.append(attempt(429, None))
    runner.HTTP_ATTEMPTS.append(attempt(429, None))
    runner.HTTP_ATTEMPTS.append(attempt(200, 0.0005))
    cost, detail = runner.cost_summary()
    identity_ok = detail["failed_attempts_without_cost"] == 2 and detail["successful_attempts_without_cost"] == 0
    check("cost.identical_failed_attempts_counted_individually", identity_ok, json.dumps(detail["per_attempt"]))
    check("cost.failed_attempts_do_not_block_total", cost == 0.0005)

    runner.HTTP_ATTEMPTS.clear()
    runner.HTTP_ATTEMPTS.append(attempt(500, None))
    cost, detail = runner.cost_summary()
    check("cost.all_failed_is_unknown", cost is None)

    runner.HTTP_ATTEMPTS.clear()
    runner.HTTP_ATTEMPTS.append(attempt(200, None))
    check("cost.stop_rule_sees_missing", len(runner.successful_attempts_without_cost()) == 1)
    runner.HTTP_ATTEMPTS.clear()


def test_redaction(runner):
    key = "sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789"
    os.environ["OPENROUTER_API_KEY"] = key
    runner.register_secrets()
    check("redact.exact_value", "[REDACTED]" in runner.redact("auth " + key) and key not in runner.redact(key))
    other = "sk-or-v1-zzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    check("redact.key_shape", other not in runner.redact("token " + other))
    check("redact.bearer", "topsecrettoken12345" not in runner.redact("Authorization: Bearer topsecrettoken12345"))
    payload = json.dumps({"error": "invalid key " + key})
    check("redact.json_payload", key not in runner.redact(payload))


def test_png_capture(runner):
    calls = []

    class FakeCDP:
        def __call__(self, method, session_id=None, **params):
            calls.append({"method": method, "session_id": session_id, "params": params})
            return {"data": base64.b64encode(PNG_1X1).decode("ascii")}

    import browser_harness.helpers as helpers

    original = helpers.cdp
    helpers.cdp = FakeCDP()
    try:
        destination = Path("/tmp/jev-test-shot.png")
        if destination.exists():
            destination.unlink()
        path = runner.capture_png("session-1", destination)
        call = calls[-1]
        check("png.method_is_capture_screenshot", call["method"] == "Page.captureScreenshot", str(call["method"]))
        check("png.params_format_is_png", call["params"].get("format") == "png", json.dumps(call["params"]))
        check("png.session_is_passed", call["session_id"] == "session-1")
        check("png.timeout_is_bounded", call["params"].get("_response_timeout") == runner.SCREENSHOT_TIMEOUT_S)
        written = Path(path).read_bytes()
        check("png.bytes_are_unconverted", written == PNG_1X1, "%d bytes" % len(written))
        check("png.signature", written.startswith(runner.PNG_SIGNATURE))
        mode = oct(Path(path).stat().st_mode & 0o777)
        check("png.file_mode_0600", mode == "0o600", mode)

        # A JPEG body must be refused rather than renamed to .png.
        class JpegCDP:
            def __call__(self, method, session_id=None, **params):
                return {"data": base64.b64encode(JPEG_HEAD).decode("ascii")}

        helpers.cdp = JpegCDP()
        expect_raises(
            "png.rejects_jpeg_bytes",
            RuntimeError,
            lambda: runner.capture_png("session-1", Path("/tmp/jev-test-shot2.png")),
            "PNG",
        )
        check("png.no_file_for_jpeg", not Path("/tmp/jev-test-shot2.png").exists())
    finally:
        helpers.cdp = original


def test_classification(runner):
    class StalePage(ValueError):
        pass

    stale = StalePage("Page changed since this decision. Observe again.")
    stale.__class__.__name__ = "StalePage"
    check("classify.provider_http", runner.classify(RuntimeError("Model provider returned HTTP 401; no action executed.")) == runner.PROVIDER_ERROR)
    check("classify.provider_connection", runner.classify(RuntimeError("Model connection failed; no action executed.")) == runner.PROVIDER_ERROR)
    check("classify.protocol", runner.classify(ValueError("Invalid TypeSafe response; no action executed.")) == runner.PROTOCOL_ERROR)
    check("classify.helper_text", runner.classify(ValueError("Text helper returned no valid field value; nothing typed.")) == runner.PROTOCOL_ERROR)
    check("classify.budget", runner.classify(ValueError("Reached the demo's model-call budget")) == runner.MAX_STEPS)
    check("classify.missing_helper_key", runner.classify(ValueError("TYPE_TEXT needs TEXT_MODEL_API_KEY; no text is hardcoded")) == runner.PROVIDER_ERROR)


def test_provider_errors(runner):
    """Real upstream error paths with a fake transport. No network, no cost."""
    import httpx
    import jev_ultrafast.model as jev_model

    key = "sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789"
    os.environ["TYPESAFE_API_KEY"] = key
    runner.register_secrets()
    runner.install_provider_patch()

    class Response:
        def __init__(self, status, body):
            self.status_code = status
            self._body = body
            self.is_error = status >= 400
            self.text = body

        def json(self):
            return json.loads(self._body)

    class Inner:
        def __init__(self, response=None, error=None):
            self.response = response
            self.error = error

        def post(self, url, **kwargs):
            if self.error:
                raise self.error
            return self.response

    body = json.dumps({"error": {"message": "No auth credentials found for key " + key, "code": 401}})
    runner.HTTP_ATTEMPTS.clear()
    jev_model.CLIENT = runner.RecordingClient(Inner(response=Response(401, body)))
    try:
        jev_model.post_json(runner.UPSTREAM_SYSTEMONE_URL, key, {"model": "jev-latest"})
        check("provider.401_raises", False, "no exception")
    except RuntimeError as exc:
        check("provider.401_raises", "HTTP 401" in str(exc), str(exc))
        check("provider.401_message_has_no_key", key not in str(exc))
    detail = runner.last_provider_message()
    check("provider.body_captured", detail is not None and "No auth credentials" in detail, str(detail))
    check("provider.body_is_redacted", detail is not None and key not in detail)
    check("provider.body_is_bounded", detail is not None and len(detail) <= runner.PROVIDER_MESSAGE_LIMIT)
    check("provider.attempt_recorded", len(runner.HTTP_ATTEMPTS) == 1 and runner.HTTP_ATTEMPTS[0]["status_code"] == 401)
    cost, cost_detail = runner.cost_summary()
    check("provider.failed_call_cost_unknown", cost is None, json.dumps(cost_detail.get("note")))

    runner.HTTP_ATTEMPTS.clear()
    jev_model.CLIENT = runner.RecordingClient(Inner(error=httpx.ConnectError("refused")))
    try:
        jev_model.post_json(runner.UPSTREAM_SYSTEMONE_URL, key, {"model": "jev-latest"})
        check("provider.transport_error_raises", False, "no exception")
    except RuntimeError as exc:
        check("provider.transport_error_raises", "Model connection failed" in str(exc), str(exc))
    check("provider.transport_attempt_recorded", len(runner.HTTP_ATTEMPTS) == 1)
    runner.HTTP_ATTEMPTS.clear()


def test_daemon_patch_fails_closed(runner):
    from browser_harness import _ipc as harness_ipc

    original = harness_ipc.spawn_kwargs
    try:
        check("daemon.pinned_shape_present", original() == runner.EXPECTED_SPAWN_KWARGS, str(original()))
        harness_ipc.spawn_kwargs = lambda: {"start_new_session": True, "extra": 1}
        expect_raises(
            "daemon.unexpected_shape_fails_closed",
            RuntimeError,
            runner.keep_daemon_in_process_group,
            "detachment behaviour is unknown",
        )
        harness_ipc.spawn_kwargs = None
        expect_raises(
            "daemon.missing_hook_fails_closed",
            RuntimeError,
            runner.keep_daemon_in_process_group,
            "is missing",
        )
    finally:
        harness_ipc.spawn_kwargs = original
    runner.keep_daemon_in_process_group()
    check("daemon.patch_applies", harness_ipc.spawn_kwargs() == {})
    harness_ipc.spawn_kwargs = original


def test_status_decisions(runner):
    good_png = Path("/tmp/jev-test-status.png")
    good_png.write_bytes(PNG_1X1)
    fake_png = Path("/tmp/jev-test-status-fake.png")
    fake_png.write_bytes(JPEG_HEAD)
    done_output = {"completion_claimed": True, "verification": "not_performed"}
    result = {"screenshot_path": str(good_png), "output": done_output}
    check("status.done_with_png_is_completed", runner.decide_status("run", "done", None, result, True) == runner.COMPLETED)
    check(
        "status.done_without_png_is_artifact_error",
        runner.decide_status("run", "done", None, {"output": done_output}, True) == runner.ARTIFACT_ERROR,
    )
    check(
        "status.done_with_jpeg_named_png_is_artifact_error",
        runner.decide_status("run", "done", None, {"screenshot_path": str(fake_png), "output": done_output}, True)
        == runner.ARTIFACT_ERROR,
    )
    check(
        "status.done_with_relative_png_is_artifact_error",
        runner.decide_status("run", "done", None, {"screenshot_path": "final.png", "output": done_output}, True)
        == runner.ARTIFACT_ERROR,
    )
    check(
        "status.done_without_completion_claim_is_internal_error",
        runner.decide_status(
            "run", "done", None, {"screenshot_path": str(good_png), "output": {"completion_claimed": False}}, True
        )
        == runner.INTERNAL_ERROR,
    )
    check(
        "status.done_with_verified_claim_is_internal_error",
        runner.decide_status(
            "run",
            "done",
            None,
            {"screenshot_path": str(good_png), "output": {"completion_claimed": True, "verification": "verified"}},
            True,
        )
        == runner.INTERNAL_ERROR,
    )
    check("status.done_with_dirty_cleanup", runner.decide_status("run", "done", None, result, False) == runner.CLEANUP_ERROR)
    check(
        "status.credentials_error",
        runner.classify(runner.MissingCredentials("OPENROUTER_API_KEY is not set")) == runner.CREDENTIALS_ERROR,
    )
    check("status.blocked", runner.decide_status("run", "blocked", None, result, True) == runner.BLOCKED)
    check("status.cost_unknown", runner.decide_status("run", runner.COST_UNKNOWN, None, result, True) == runner.COST_UNKNOWN)
    check("status.timeout", runner.decide_status("run", "timeout", None, result, True) == runner.TIMEOUT)
    check("status.error_wins", runner.decide_status("run", "exception", RuntimeError("Model connection failed"), result, True) == runner.PROVIDER_ERROR)
    check("status.login_closed", runner.decide_status("login", "closed", None, {}, True) == runner.COMPLETED)
    check("status.login_timeout", runner.decide_status("login", "timeout", None, {}, True) == runner.TIMEOUT)


def test_group_scan_excludes_itself(runner):
    """The group scan must be stable and never report its own ps child."""
    owned = runner.OwnedProcesses()
    scans = [owned.group_members() for _ in range(3)]
    check("group.scan_is_stable", scans[0] == scans[1] == scans[2], str(scans))
    commands = []
    for pid in scans[0]:
        try:
            commands.append(
                __import__("subprocess")
                .run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
                .stdout.strip()
            )
        except Exception:
            pass
    check("group.scan_has_no_ps_child", not [c for c in commands if c.startswith("ps ")], str(commands))
    check("group.leader_check_is_boolean", owned.owns_process_group() in (True, False))


def test_helper_response_shape(runner):
    """Metadata only: distinguishes helper failure modes, leaks no content."""

    def payload(content, finish="stop", refusal=None, extra_message=None):
        message = {"content": content}
        if refusal is not None:
            message["refusal"] = refusal
        if extra_message:
            message.update(extra_message)
        return {"choices": [{"finish_reason": finish, "message": message}]}

    good = runner.helper_response_shape(payload(json.dumps({"text": "NW-10428"})))
    check("shape.good_parses", good["json_parse_ok"] and good["json_top_type"] == "dict")
    check("shape.good_is_exact_text_key", good["keys_are_exact_text"] and good["has_text_key"])
    check("shape.good_key_count", good["json_key_count"] == 1)
    check("shape.good_text_type", good["text_value_type"] == "str" and good["text_value_chars"] == 8)
    check("shape.good_not_blank", good["text_is_blank"] is False)
    check("shape.good_finish_reason", good["finish_reason"] == "stop")

    null_text = runner.helper_response_shape(payload(json.dumps({"text": None})))
    check("shape.null_text_type", null_text["text_value_type"] == "NoneType", str(null_text))
    check("shape.null_text_keys_exact", null_text["keys_are_exact_text"] is True)
    check("shape.null_text_chars_unknown", null_text["text_value_chars"] is None)

    extra = runner.helper_response_shape(payload(json.dumps({"text": "x", "field": "Asset tag"})))
    check("shape.extra_keys_counted", extra["json_key_count"] == 2 and extra["keys_are_exact_text"] is False)
    check("shape.extra_keys_has_text", extra["has_text_key"] is True)

    wrong = runner.helper_response_shape(payload(json.dumps({"asset_tag": "NW-10428"})))
    check("shape.wrong_key", wrong["has_text_key"] is False and wrong["json_key_count"] == 1)

    prose = runner.helper_response_shape(payload("The asset tag is NW-10428."))
    check("shape.prose_not_json", prose["json_parse_ok"] is False and prose["content_chars"] == 26)

    blank = runner.helper_response_shape(payload(json.dumps({"text": "   "})))
    check("shape.blank_text", blank["text_is_blank"] is True)

    array = runner.helper_response_shape(payload(json.dumps(["a"])))
    check("shape.array_top_type", array["json_top_type"] == "list" and array["json_key_count"] is None)

    none_content = runner.helper_response_shape(payload(None))
    check("shape.null_content", none_content["content_is_null"] and none_content["content_present"])

    truncated = runner.helper_response_shape(payload('{"text": "partial', finish="length"))
    check("shape.truncated", truncated["finish_reason"] == "length" and truncated["json_parse_ok"] is False)

    refused = runner.helper_response_shape(payload(None, refusal="I cannot help with that"))
    check("shape.refusal_flagged", refused["refusal_present"] is True)

    empty = runner.helper_response_shape({})
    check("shape.empty_payload_safe", empty["json_parse_ok"] is False and empty["finish_reason"] is None)
    check("shape.non_dict_payload_safe", runner.helper_response_shape(None)["content_present"] is False)
    err = runner.helper_response_shape({"error": {"message": "nope"}})
    check("shape.error_flagged", err["error_present"] is True)

    # Leak guard: no field value and no model-chosen key name may survive.
    secret_value = "NW-10428-SECRET-ASSET"
    secret_key = "dana.whitfield@northwind.test"
    leaky = runner.helper_response_shape(
        payload(json.dumps({secret_key: secret_value, "text": secret_value}), finish="stop" + secret_value)
    )
    serialized = json.dumps(leaky)
    check("shape.no_value_leak", secret_value not in serialized, serialized)
    check("shape.no_key_leak", secret_key not in serialized, serialized)
    check("shape.finish_reason_is_enum_or_other", leaky["finish_reason"] == "other", str(leaky["finish_reason"]))
    check("shape.known_finish_reasons_kept", runner.normalized_finish_reason("length") == "length")
    check("shape.unknown_finish_reason_masked", runner.normalized_finish_reason("weird-value-123") == "other")


def test_supplied_values(runner):
    """Exact values in, nothing normalised, and the default generation rule."""
    base = {
        "op": "run",
        "task": "fill the form",
        "url": "http://127.0.0.1:1/",
        "profile_dir": "/tmp/jev-test-profile",
        "artifact_dir": "/tmp/jev-test-artifacts",
    }

    def with_fields(**extra):
        request = dict(base)
        request.update(extra)
        return lambda: runner.normalize(request)

    def normalized(**extra):
        request = dict(base)
        request.update(extra)
        return runner.normalize(request)

    plain = normalized()
    check("values.absent_is_none", plain["values"] is None)
    check("values.absent_means_helper", plain["generation"] == "helper")
    bound = normalized(values={"email": "dana@example.test", "note": ""})
    check("values.accepts_object", bound["values"] == {"email": "dana@example.test", "note": ""})
    check("values.empty_string_is_a_value", bound["values"]["note"] == "")
    check("values.default_generation_is_disabled", bound["generation"] == "disabled")
    check("values.explicit_helper_is_kept", normalized(values={"a": "b"}, generation="helper")["generation"] == "helper")
    check("values.disabled_without_values", normalized(generation="disabled")["generation"] == "disabled")
    check("values.empty_object_still_helper", normalized(values={})["generation"] == "helper")
    exact = " Z\u00fcrich Hauptbahnhof. "
    check("values.copied_byte_for_byte", normalized(values={"a": exact})["values"]["a"] == exact)
    full = normalized(values={f"k{i}": "x" * runner.MAX_VALUE_CHARS for i in range(runner.MAX_VALUES)})
    check("values.boundary_sizes_accepted", len(full["values"]) == 20 and len(full["values"]["k0"]) == 2000)
    check("values.longest_key_accepted", normalized(values={"a" * 64: "x"})["values"]["a" * 64] == "x")
    expect_raises("values.rejects_list", runner.RequestError, with_fields(values=["a"]), "object")
    expect_raises("values.rejects_string", runner.RequestError, with_fields(values="email=x"), "object")
    expect_raises("values.rejects_int_value", runner.RequestError, with_fields(values={"a": 5}), "string")
    expect_raises("values.rejects_bool_value", runner.RequestError, with_fields(values={"a": True}), "string")
    expect_raises("values.rejects_null_value", runner.RequestError, with_fields(values={"a": None}), "string")
    expect_raises("values.rejects_leading_digit_key", runner.RequestError, with_fields(values={"1a": "x"}), "keys must")
    expect_raises("values.rejects_empty_key", runner.RequestError, with_fields(values={"": "x"}), "keys must")
    expect_raises("values.rejects_dashed_key", runner.RequestError, with_fields(values={"a-b": "x"}), "keys must")
    expect_raises("values.rejects_long_key", runner.RequestError, with_fields(values={"a" * 65: "x"}), "keys must")
    expect_raises("values.rejects_key_none", runner.RequestError, with_fields(values={"NONE": "x"}), "NONE")
    expect_raises(
        "values.rejects_too_many",
        runner.RequestError,
        with_fields(values={f"k{i}": "x" for i in range(runner.MAX_VALUES + 1)}),
        "at most 20",
    )
    expect_raises(
        "values.rejects_long_value",
        runner.RequestError,
        with_fields(values={"a": "x" * (runner.MAX_VALUE_CHARS + 1)}),
        "at most 2000",
    )
    expect_raises("generation.rejects_unknown", runner.RequestError, with_fields(generation="auto"), "helper")
    expect_raises("generation.rejects_number", runner.RequestError, with_fields(generation=1), "helper")
    login = runner.normalize(
        {
            "op": "login",
            "url": "https://example.com",
            "profile_dir": "/tmp/p",
            "artifact_dir": "/tmp/a",
            "values": {"a": "b"},
        }
    )
    check("values.login_binds_nothing", login["values"] is None and login["generation"] is None)


def test_reported_actions_and_deviations(runner):
    history = [
        {
            "step": 1, "kind": "fill", "action": "Email", "operation": "TYPE_TEXT", "probability": 0.9,
            "confidence": 0.8, "page_changed": True, "text": "dana@example.test", "value_key": "email",
            "value_source": "supplied", "note": None,
        },
        {
            "step": 2, "kind": "click", "action": "Continue", "operation": "CLICK", "probability": 1.0,
            "confidence": 1.0, "page_changed": True, "text": None, "value_key": None, "value_source": None,
        },
        {
            "step": 3, "kind": "fill", "action": "Phone", "operation": "TYPE_TEXT", "probability": 1.0,
            "confidence": 1.0, "page_changed": False, "text": None, "value_key": None,
            "value_source": "skipped", "note": "no value bound to this field; nothing typed",
        },
    ]
    rows = runner.action_rows(history)
    check("actions.supplied_reported", rows[0]["value_key"] == "email" and rows[0]["value_source"] == "supplied")
    check("actions.non_fill_is_null", rows[1]["value_key"] is None and rows[1]["value_source"] is None)
    check("actions.skip_reported", rows[2]["value_source"] == "skipped" and rows[2]["value_key"] is None)
    serialized = json.dumps(rows)
    check("actions.typed_text_is_never_reported", "dana@example.test" not in serialized, serialized)
    check("actions.note_is_not_reported", "nothing typed" not in serialized, serialized)
    check("actions.old_history_entries_are_safe", runner.action_rows([{"step": 1}])[0]["value_source"] is None)
    legacy = runner.action_rows([{"step": 1}])[0]
    check("actions.old_history_entries_report_null_safety_fields",
          all(legacy[key] is None for key in
              ("operation_confidence", "target_confidence", "binding_confidence", "dispatch")),
          json.dumps(legacy))
    check("actions.confidence_stays_the_operation_score",
          rows[0]["confidence"] == 0.8 and rows[0]["operation_confidence"] is None,
          json.dumps(rows[0]))
    fork = [d for d in runner.DEVIATIONS if d.startswith("fork:")]
    check("deviations.one_fork_entry", len(fork) == 1, str(len(fork)))
    check("deviations.fork_names_binding", "byte for byte" in fork[0], fork[0] if fork else "")
    check("deviations.fork_names_null_helper", "skips the field" in fork[0], fork[0] if fork else "")
    check("deviations.fork_points_at_provenance", "vendor/PROVENANCE.md" in fork[0])
    check("deviations.count_is_seven", len(runner.DEVIATIONS) == 7, str(len(runner.DEVIATIONS)))
    check("deviations.docstring_counts_them", "seven differences" in runner.__doc__)
    check("deviations.docstring_drops_never_edited", "never edited" not in runner.__doc__)
    check("deviations.fork_names_truncation", "truncated" in fork[0], fork[0] if fork else "")
    check("deviations.fork_names_withheld_input", "withholds input" in fork[0],
          fork[0] if fork else "")
    safety = [d for d in runner.DEVIATIONS if d.startswith("safety:")]
    check("deviations.one_safety_entry", len(safety) == 1, str(len(safety)))
    check("deviations.safety_names_the_budget_callback",
          "budget callback" in safety[0] and "before" in safety[0], safety[0] if safety else "")
    check("deviations.safety_names_the_truncated_done_rule",
          "did not all pass" in safety[0] and "needs_review" in safety[0],
          safety[0] if safety else "")
    verification = [d for d in runner.DEVIATIONS if d.startswith("verification:")]
    check("deviations.one_verification_entry", len(verification) == 1, str(len(verification)))
    check("deviations.verification_is_read_only",
          "read-only" in verification[0] and "never written to" in verification[0]
          and "declared_dom_checks_only" in verification[0],
          verification[0] if verification else "")


def test_bind_call_is_costed_like_a_decision(runner):
    """The binding request goes through the patched post_json and is accounted."""
    import jev_ultrafast.model as jev_model

    key = "sk-or-v1-" + "c" * 32
    os.environ["TYPESAFE_API_KEY"] = key
    os.environ["TYPESAFE_MODEL"] = "jev-test"
    runner.register_secrets()
    runner.install_provider_patch()

    class Response:
        status_code = 200
        is_error = False
        text = ""

        def __init__(self, body):
            self._body = body

        def json(self):
            return json.loads(self._body)

    body = json.dumps(
        {
            "model": "typesafe/jev-test-2026",
            "answers": {
                "value": {"choice": "email", "confidence": 0.91, "probabilities": {"email": 0.91, "NONE": 0.09}}
            },
            "usage": {"cost": 0.0004, "total_tokens": 120},
        }
    )
    sent = []

    class Inner:
        def post(self, url, **kwargs):
            sent.append((url, kwargs.get("json")))
            return Response(body)

    runner.HTTP_ATTEMPTS.clear()
    runner.LOGICAL_CALLS.clear()
    jev_model.CLIENT = runner.RecordingClient(Inner())
    page = {"url": "https://example.test/form", "title": "Sign in", "text": "Email address"}
    action = {"kind": "fill", "label": "Email", "role": "textbox", "value": "", "node": 3}
    long_value = "dana@example.test " + "x" * 200
    answer = jev_model.bind_value("Sign in as Dana", action, page, [], {"email": long_value})
    check("bind.returns_the_supplied_key", answer["key"] == "email", str(answer["key"]))
    check("bind.one_http_attempt", len(runner.HTTP_ATTEMPTS) == 1, str(len(runner.HTTP_ATTEMPTS)))
    check("bind.role_is_decision", runner.HTTP_ATTEMPTS[0]["role"] == "decision", str(runner.HTTP_ATTEMPTS[0]["role"]))
    check("bind.url_is_the_runtime_endpoint", sent[0][0] == runner.SYSTEMONE_URL, str(sent[0][0]))
    preview = sent[0][1]["questions"]["value"]["criteria"]["email"]["preview"]
    check("bind.preview_is_bounded", preview == long_value[:80], preview)
    check("bind.none_is_offered", "NONE" in sent[0][1]["questions"]["value"]["criteria"])
    cost, detail = runner.cost_summary()
    check("bind.cost_is_counted", cost is not None and abs(cost - 0.0004) < 1e-12, str(cost))
    summary = runner.usage_summary()
    check("bind.usage_is_decision_role", summary["decision"]["http_attempts"] == 1, json.dumps(summary))
    check("bind.usage_counts_tokens", summary["decision"]["total_tokens"] == 120, json.dumps(summary))
    check("bind.resolved_model_seen", runner.resolved_model_for("decision") == "typesafe/jev-test-2026")
    check("bind.no_helper_attempt", not [a for a in runner.HTTP_ATTEMPTS if a["role"] == "helper"])
    runner.HTTP_ATTEMPTS.clear()
    runner.LOGICAL_CALLS.clear()
    os.environ.pop("TYPESAFE_MODEL", None)


# --------------------------------------------------------------------------
# declared DOM checks: contract, evidence mapping and wiring. No browser here;
# the headless `checks` group below runs the same code against real Chrome.
# --------------------------------------------------------------------------
SECRET_EXPECTATION = "Zurich-order-9f2a-Kn0wn"


class FakeBrowser:
    """Only what verification is allowed to use: one read-only evaluate()."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.expressions = []

    def evaluate(self, expression):
        self.expressions.append(expression)
        if self.error is not None:
            raise self.error
        return self.payload


def good_checks():
    return [
        {"id": "url", "kind": "url", "equals": "https://app.test/done"},
        {"id": "title", "kind": "title", "contains": "Done"},
        {"id": "heading", "kind": "text", "selector": "h1", "equals": "Saved"},
        {"id": "email", "kind": "value", "selector": "#email", "equals": "dana@example.test"},
        {"id": "rows", "kind": "count", "selector": ".row", "equals": 3},
    ]


def evidence(*rows, url="https://app.test/done", title="Done", at=1737000000000):
    return {"url": url, "title": title, "at": at, "rows": list(rows)}


def test_declared_check_contract(runner):
    contract = runner.dom_checks
    skill_root = Path(runner.__file__).resolve().parent.parent
    check(
        "checks.contract_is_the_wrapper_file",
        Path(contract.__file__).resolve() == (skill_root / "src" / "jev" / "checks.py"),
        contract.__file__,
    )

    normalized = contract.normalize_checks(good_checks())
    check("checks.every_kind_normalizes", [row["kind"] for row in normalized]
          == ["url", "title", "text", "value", "count"])
    check("checks.selector_is_none_for_page_kinds",
          normalized[0]["selector"] is None and normalized[2]["selector"] == "h1")
    check("checks.normalize_is_idempotent", contract.normalize_checks(normalized) == normalized)
    check("checks.none_and_empty_mean_no_checks",
          contract.normalize_checks(None) == [] and contract.normalize_checks([]) == [])
    check("checks.id_defaults_to_position",
          contract.normalize_checks([{"kind": "url", "equals": "x"}])[0]["id"] == "check[0]")
    source = [{"id": "a", "kind": "url", "equals": "x"}]
    snapshot = contract.normalize_checks(source)
    source[0]["equals"] = "mutated"
    check("checks.snapshot_survives_caller_mutation", snapshot[0]["equals"] == "x")

    declared = contract.normalize_checks(
        [{"id": "saved", "kind": "text", "selector": "#s", "equals": "Saved"}])[0]
    fingerprint = contract.declaration_fingerprint(declared)
    check("checks.fingerprint_is_a_sha256_digest",
          isinstance(fingerprint, str) and len(fingerprint) == contract.FINGERPRINT_CHARS
          and all(character in "0123456789abcdef" for character in fingerprint),
          fingerprint)
    check("checks.fingerprint_is_stable",
          fingerprint == contract.declaration_fingerprint(dict(declared))
          and fingerprint == contract.declaration_fingerprint(
              {"kind": "text", "id": "saved", "equals": "Saved", "selector": "#s"}))
    changed = [
        ("equals", {**declared, "equals": "Other"}),
        ("selector", {**declared, "selector": "#other"}),
        ("id", {**declared, "id": "other"}),
        ("kind", {**declared, "kind": "value"}),
        ("contains", {"id": "saved", "kind": "text", "selector": "#s", "contains": "Saved"}),
    ]
    differing = [name for name, other in changed
                 if contract.declaration_fingerprint(other) == fingerprint]
    check("checks.fingerprint_changes_with_the_declaration", not differing, str(differing))
    rejected = (("none", None), ("list", [declared]), ("extra_key", {**declared, "script": "1"}))
    for name, payload in rejected:
        expect_raises("checks.fingerprint_rejects." + name, contract.CheckError,
                      lambda payload=payload: contract.declaration_fingerprint(payload))

    # The whole result goes through one redaction pass on the way out, so a
    # row's link to its declaration has to survive that pass. A hex digest
    # holds no "sk-" or "bearer" literal, and these two placeholders are
    # synthetic: no environment value is read here.
    key_shaped = contract.normalize_checks([
        {"id": "bearer", "kind": "text", "selector": "#s", "contains": "Bearer YOUR_TOKEN_HERE"},
        {"id": "key", "kind": "value", "selector": "#k",
         "equals": "sk-EXAMPLE_PLACEHOLDER_00000000"},
    ])
    shaped = [contract.declaration_fingerprint(item) for item in key_shaped]
    transported = json.loads(runner.redact(json.dumps(
        contract.verification_payload(key_shaped, redact=runner.redact))))
    check("checks.fingerprint_survives_the_runner_redaction",
          [runner.redact(item) for item in shaped] == shaped
          and [row["fingerprint"] for row in transported["checks"]] == shaped,
          json.dumps(transported["checks"])[:200])
    check("checks.tally_counts_each_status",
          contract.tally([{"status": "passed"}, {"status": "failed"}, {"status": "failed"},
                          {"status": "unknown"}])
          == {"passed": 1, "failed": 2, "unknown": 1})

    invalid = [
        ("not_a_list", {"id": "a", "kind": "url", "equals": "x"}),
        ("too_many", [{"kind": "url", "equals": "x"}] * (contract.MAX_CHECKS + 1)),
        ("item_not_object", ["h1"]),
        ("unknown_key", [{"id": "a", "kind": "url", "equals": "x", "script": "1"}]),
        ("malicious_key", [{"id": "a", "kind": "url", "equals": "x", "__proto__": {"kind": "url"}}]),
        ("prototype_key", [{"id": "a", "kind": "url", "equals": "x", "constructor": "x"}]),
        ("blank_id", [{"id": "  ", "kind": "url", "equals": "x"}]),
        ("non_string_id", [{"id": 7, "kind": "url", "equals": "x"}]),
        ("long_id", [{"id": "i" * 101, "kind": "url", "equals": "x"}]),
        ("duplicate_id", [{"id": "a", "kind": "url", "equals": "x"},
                          {"id": "a", "kind": "title", "equals": "y"}]),
        ("duplicate_default_id", [{"kind": "url", "equals": "x"},
                                  {"id": "check[0]", "kind": "title", "equals": "y"}]),
        ("unknown_kind", [{"id": "a", "kind": "attribute", "selector": "a", "equals": "x"}]),
        ("missing_kind", [{"id": "a", "equals": "x"}]),
        ("selector_on_url", [{"id": "a", "kind": "url", "selector": "h1", "equals": "x"}]),
        ("missing_selector", [{"id": "a", "kind": "text", "equals": "x"}]),
        ("blank_selector", [{"id": "a", "kind": "text", "selector": " ", "equals": "x"}]),
        ("long_selector", [{"id": "a", "kind": "text", "selector": "d" * 1001, "equals": "x"}]),
        ("both_expectations", [{"id": "a", "kind": "url", "equals": "x", "contains": "x"}]),
        ("no_expectation", [{"id": "a", "kind": "url"}]),
        ("empty_contains", [{"id": "a", "kind": "url", "contains": ""}]),
        ("non_string_expectation", [{"id": "a", "kind": "url", "equals": 3}]),
        ("long_expectation", [{"id": "a", "kind": "url", "equals": "x" * 2001}]),
        ("count_contains", [{"id": "a", "kind": "count", "selector": ".r", "contains": "3"}]),
        ("count_bool", [{"id": "a", "kind": "count", "selector": ".r", "equals": True}]),
        ("count_float", [{"id": "a", "kind": "count", "selector": ".r", "equals": 3.0}]),
        ("count_infinite", [{"id": "a", "kind": "count", "selector": ".r", "equals": float("inf")}]),
        ("count_nan", [{"id": "a", "kind": "count", "selector": ".r", "equals": float("nan")}]),
        ("count_negative", [{"id": "a", "kind": "count", "selector": ".r", "equals": -1}]),
        ("count_string", [{"id": "a", "kind": "count", "selector": ".r", "equals": "3"}]),
    ]
    for name, payload in invalid:
        expect_raises(
            "checks.reject." + name, contract.CheckError,
            lambda payload=payload: contract.normalize_checks(payload),
        )
        # Boundary parity: the runner rejects exactly what the contract rejects.
        expect_raises(
            "checks.runner_rejects." + name, runner.RequestError,
            lambda payload=payload: runner.normalize({
                "op": "run", "task": "t", "url": "http://127.0.0.1:1/",
                "profile_dir": "/tmp/jev-test-profile", "artifact_dir": "/tmp/jev-test-artifacts",
                "checks": payload,
            }),
        )

    # Messages carry indexes, types and lengths; never an expectation.
    leaks = []
    for payload in ([{"id": "a", "kind": "url", "equals": SECRET_EXPECTATION * 100}],
                    [{"id": "a", "kind": "text", "selector": SECRET_EXPECTATION, "equals": 1}],
                    [{"id": "a", "kind": "url", "contains": ""}]):
        try:
            contract.normalize_checks(payload)
        except contract.CheckError as exc:
            if SECRET_EXPECTATION in str(exc):
                leaks.append(str(exc))
    check("checks.errors_never_quote_the_expectation", not leaks, str(leaks))

    base = {"op": "run", "task": "t", "url": "http://127.0.0.1:1/",
            "profile_dir": "/tmp/jev-test-profile", "artifact_dir": "/tmp/jev-test-artifacts"}
    check("checks.request_without_checks_is_unchanged", runner.normalize(dict(base))["checks"] == [])
    check("checks.request_with_null_checks", runner.normalize({**base, "checks": None})["checks"] == [])
    check("checks.login_declares_nothing",
          runner.normalize({"op": "login", "url": "http://127.0.0.1:1/",
                            "profile_dir": "/tmp/jev-test-profile",
                            "artifact_dir": "/tmp/jev-test-artifacts"})["checks"] == [])
    check("checks.runner_normalizes_like_the_contract",
          runner.normalize({**base, "checks": good_checks()})["checks"] == normalized)


def test_declared_check_expression(runner):
    contract = runner.dom_checks
    checks = contract.normalize_checks([
        {"id": "zz_identifier", "kind": "text", "selector": "h1", "equals": "Saved"},
        {"id": "zz_secret", "kind": "value", "selector": "#code", "equals": SECRET_EXPECTATION},
    ])
    expression = contract.read_expression(checks)
    check("checks.expression_sends_no_expectation", SECRET_EXPECTATION not in expression)
    check("checks.expression_sends_no_ids", "zz_identifier" not in expression
          and "zz_secret" not in expression)
    check("checks.expression_carries_selectors", '"#code"' in expression and '"h1"' in expression)
    writes = [token for token in
              ("dispatchEvent", "innerHTML", "outerHTML", ".click(", ".submit(",
               "location.assign", "location.replace", "setAttribute", "removeAttribute",
               "appendChild", "eval(", "Function(", "fetch(", "XMLHttpRequest")
              if token in expression]
    check("checks.expression_is_read_only", not writes, str(writes))
    check("checks.expression_escapes_non_ascii",
          contract.read_expression(contract.normalize_checks(
              [{"id": "u", "kind": "text", "selector": ".x\u2028y", "equals": "a"}])).isascii())
    check("checks.expression_refuses_password_and_hidden",
          "sensitive_field" in expression and "hidden_field" in expression)


def test_declared_check_evidence(runner):
    contract = runner.dom_checks
    checks = contract.normalize_checks(good_checks())

    passing = evidence(
        {"available": True, "value": "https://app.test/done"},
        {"available": True, "value": "Order Done"},
        {"available": True, "value": "Saved"},
        {"available": True, "value": "dana@example.test"},
        {"available": True, "value": 3},
    )
    payload = contract.verification_payload(checks, passing)
    check("checks.all_pass", payload["status"] == "passed", json.dumps(payload["counts"]))
    check("checks.scope_is_declared_only", payload["scope"] == "declared_dom_checks_only")
    check("checks.boundary_is_the_dom", payload["boundary"] == "browser_dom"
          and all(row["boundary"] == "browser_dom" for row in payload["checks"]))
    check("checks.snapshot_records_url_and_time",
          payload["checked_at_url"] == "https://app.test/done"
          and payload["captured_at_ms"] == 1737000000000
          and payload["consistency"] == "single_synchronous_read")
    check("checks.note_is_not_persistence_proof",
          "not evidence that a server stored anything" in payload["note"])
    check("checks.rows_keep_their_ids",
          [row["id"] for row in payload["checks"]] == ["url", "title", "heading", "email", "rows"])
    check("checks.rows_fingerprint_their_declaration",
          [row["fingerprint"] for row in payload["checks"]]
          == [contract.declaration_fingerprint(item) for item in checks])
    check("checks.rows_do_not_echo_the_declaration",
          not [row for row in payload["checks"] if "check" in row]
          and SECRET_EXPECTATION not in json.dumps(contract.verification_payload(
              contract.normalize_checks([{"id": "s", "kind": "value", "selector": "#c",
                                          "equals": SECRET_EXPECTATION}]),
              evidence({"available": True, "value": "something else"}))))
    check("checks.note_is_the_contract_note", payload["note"] == contract.NOTE)
    check("checks.consistency_is_from_the_closed_set",
          payload["consistency"] in contract.CONSISTENCY
          and contract.verification_payload([])["consistency"] in contract.CONSISTENCY)
    check("checks.declared_count", payload["declared"] == 5
          and payload["counts"] == {"passed": 5, "failed": 0, "unknown": 0})

    mixed = contract.verification_payload(checks, evidence(
        {"available": True, "value": "https://app.test/other"},              # failed
        {"available": True, "value": "Done"},                                # passed
        {"available": False, "reason": "missing_or_ambiguous", "matches": 2},  # unknown
        {"available": False, "reason": "sensitive_field"},                   # unknown
        {"available": True, "value": 4},                                     # failed
    ))
    check("checks.mixed_is_failed", mixed["status"] == "failed")
    check("checks.mixed_counts", mixed["counts"] == {"passed": 1, "failed": 2, "unknown": 2},
          json.dumps(mixed["counts"]))
    check("checks.mismatch_is_failed", mixed["checks"][0]["status"] == "failed")
    check("checks.ambiguous_is_unknown_not_failed",
          mixed["checks"][2]["status"] == "unknown"
          and mixed["checks"][2]["reason"] == "missing_or_ambiguous"
          and mixed["checks"][2]["observed"]["matches"] == 2)
    check("checks.password_is_unknown_and_valueless",
          mixed["checks"][3]["status"] == "unknown"
          and mixed["checks"][3]["reason"] == "sensitive_field"
          and "value" not in mixed["checks"][3]["observed"])

    unknown_only = contract.verification_payload(checks[:2], evidence(
        {"available": False, "reason": "unreadable_or_invalid_selector"},
        {"available": False, "reason": "not_visible"},
    ))
    check("checks.unknown_only_is_unknown", unknown_only["status"] == "unknown")
    check("checks.invalid_selector_reason",
          unknown_only["checks"][0]["reason"] == "unreadable_or_invalid_selector")

    for reason in ("hidden_field", "not_a_field", "unsupported_control", "value_too_large"):
        row = contract.verification_payload(checks[3:4], evidence(
            {"available": False, "reason": reason, "length": 99999}))["checks"][0]
        check("checks.reason." + reason, row["status"] == "unknown" and row["reason"] == reason)

    invented = contract.verification_payload(checks[:1], evidence(
        {"available": False, "reason": "because I said so"}))["checks"][0]
    check("checks.unknown_reason_is_normalized", invented["reason"] == "evidence_unavailable")

    wrong_type = contract.verification_payload(checks[4:5], evidence(
        {"available": True, "value": "3"}))["checks"][0]
    check("checks.count_needs_a_number", wrong_type["status"] == "unknown"
          and wrong_type["reason"] == "evidence_type_mismatch")
    bool_count = contract.verification_payload(
        contract.normalize_checks([{"id": "c", "kind": "count", "selector": ".r", "equals": 1}]),
        evidence({"available": True, "value": True}))["checks"][0]
    check("checks.true_is_not_a_count_of_one", bool_count["status"] == "unknown")

    text_type = contract.verification_payload(checks[2:3], evidence(
        {"available": True, "value": 5}))["checks"][0]
    check("checks.text_needs_a_string", text_type["status"] == "unknown"
          and text_type["reason"] == "evidence_type_mismatch")

    contains = contract.normalize_checks(
        [{"id": "c", "kind": "text", "selector": "p", "contains": "order 12"}])
    hit = contract.verification_payload(contains, evidence(
        {"available": True, "value": "We saved order 1234 for you"}))
    miss = contract.verification_payload(contains, evidence(
        {"available": True, "value": "We saved Order 1234 for you"}))
    check("checks.contains_matches_substring", hit["status"] == "passed")
    check("checks.contains_is_case_sensitive", miss["status"] == "failed")

    exact = contract.normalize_checks(
        [{"id": "v", "kind": "value", "selector": "#n", "equals": " Ada  Lovelace "}])
    check("checks.equals_is_byte_for_byte",
          contract.verification_payload(exact, evidence(
              {"available": True, "value": "Ada Lovelace"}))["status"] == "failed")
    check("checks.equals_accepts_an_empty_expectation",
          contract.verification_payload(
              contract.normalize_checks([{"id": "v", "kind": "value", "selector": "#n",
                                          "equals": ""}]),
              evidence({"available": True, "value": ""}))["status"] == "passed")

    long_value = "x" * (contract.MAX_REPORTED_CHARS + 500)
    bounded = contract.verification_payload(
        contract.normalize_checks([{"id": "t", "kind": "text", "selector": "p",
                                    "contains": "xxx"}]),
        evidence({"available": True, "value": long_value}))["checks"][0]
    check("checks.observed_value_is_bounded",
          len(bounded["observed"]["value"]) == contract.MAX_REPORTED_CHARS
          and bounded["observed"]["truncated"] is True
          and bounded["observed"]["length"] == len(long_value)
          and bounded["status"] == "passed")

    url_check = contract.normalize_checks([{"id": "u", "kind": "url", "equals": "nope"}])
    exact_url = "u" * contract.MAX_REPORTED_URL_CHARS
    exact_title = "t" * contract.MAX_REPORTED_CHARS
    at_limit = contract.verification_payload(
        url_check, evidence({"available": True, "value": "nope"},
                            url=exact_url, title=exact_title))
    check("checks.capture_fields_at_limit_are_not_truncated",
          at_limit["checked_at_url"] == exact_url
          and at_limit["checked_at_title"] == exact_title
          and at_limit["capture_metadata"]["url"] == {
              "length": contract.MAX_REPORTED_URL_CHARS, "truncated": False}
          and at_limit["capture_metadata"]["title"] == {
              "length": contract.MAX_REPORTED_CHARS, "truncated": False})

    over_url = exact_url + "X"
    over_title = exact_title + "Y"
    over = contract.verification_payload(
        url_check, evidence({"available": True, "value": "nope"},
                            url=over_url, title=over_title))
    dumped = json.dumps(over)
    check("checks.capture_fields_one_over_are_truncated",
          over["checked_at_url"] == exact_url
          and over["checked_at_title"] == exact_title
          and over["capture_metadata"]["url"] == {
              "length": contract.MAX_REPORTED_URL_CHARS + 1, "truncated": True}
          and over["capture_metadata"]["title"] == {
              "length": contract.MAX_REPORTED_CHARS + 1, "truncated": True}
          and over_url not in dumped and over_title not in dumped
          and "X" not in over["checked_at_url"] and "Y" not in over["checked_at_title"])

    secret_url = ("https://app.test/" + SECRET_EXPECTATION + "z") * 80
    redacted_capture = contract.verification_payload(
        url_check, evidence({"available": True, "value": "nope"}, url=secret_url,
                            title="Done " + SECRET_EXPECTATION),
        redact=lambda text: text.replace(SECRET_EXPECTATION, "[REDACTED]"))
    check("checks.capture_fields_record_redaction_and_drop_the_secret",
          SECRET_EXPECTATION not in json.dumps(redacted_capture)
          and redacted_capture["capture_metadata"]["url"].get("redacted") is True
          and redacted_capture["capture_metadata"]["title"].get("redacted") is True
          and redacted_capture["capture_metadata"]["url"]["truncated"] is True)

    redacted = contract.verification_payload(
        contract.normalize_checks([{"id": "t", "kind": "text", "selector": "p",
                                    "contains": "token"}]),
        evidence({"available": True, "value": "token " + SECRET_EXPECTATION},
                 url="https://app.test/?t=" + SECRET_EXPECTATION),
        redact=lambda text: text.replace(SECRET_EXPECTATION, "[REDACTED]"))
    check("checks.evidence_is_redacted_after_comparison",
          redacted["status"] == "passed"
          and SECRET_EXPECTATION not in json.dumps(redacted))

    check("checks.no_checks_is_not_run",
          contract.verification_payload([])["status"] == "not_run"
          and contract.verification_payload([])["declared"] == 0
          and contract.verification_payload([])["checks"] == [])
    check("checks.not_run_records_no_read",
          contract.verification_payload([])["consistency"] == "not_read"
          and contract.verification_payload([])["captured_at_ms"] is None)

    unreadable = contract.verification_payload(checks, None, reason="page_unavailable")
    check("checks.unreadable_page_is_all_unknown",
          unreadable["status"] == "unknown"
          and len(unreadable["checks"]) == 5
          and {row["reason"] for row in unreadable["checks"]} == {"page_unavailable"})
    short = contract.verification_payload(checks, evidence({"available": True, "value": "x"}))
    check("checks.row_count_mismatch_is_unknown",
          short["status"] == "unknown" and len(short["checks"]) == 5
          and short["consistency"] == "not_read")
    junk = contract.verification_payload(checks[:2], evidence("nope", None))
    check("checks.junk_rows_are_unknown", junk["status"] == "unknown"
          and len(junk["checks"]) == 2)


def test_declared_check_wiring(runner):
    contract = runner.dom_checks
    checks = contract.normalize_checks(good_checks()[:3])

    browser = FakeBrowser(payload=evidence(
        {"available": True, "value": "https://app.test/done"},
        {"available": True, "value": "Done"},
        {"available": True, "value": "Saved"},
    ))
    payload = runner.verify_declared_checks(browser, checks)
    check("wiring.one_read_per_run", len(browser.expressions) == 1)
    check("wiring.passes_through", payload["status"] == "passed")
    check("wiring.no_checks_makes_no_read",
          runner.verify_declared_checks(FakeBrowser(), [])["status"] == "not_run")

    for name, error in (("stale_page", ValueError("Document changed during evaluation")),
                        ("detached", RuntimeError("Session with given id not found.")),
                        ("secret_message", RuntimeError("boom " + SECRET_EXPECTATION))):
        broken = runner.verify_declared_checks(FakeBrowser(error=error), checks)
        check("wiring.error." + name,
              broken["status"] == "unknown"
              and {row["reason"] for row in broken["checks"]} == {"page_unavailable"}
              and SECRET_EXPECTATION not in json.dumps(broken))

    check("wiring.junk_payload_is_unknown",
          runner.verify_declared_checks(FakeBrowser(payload="not a dict"), checks)["status"]
          == "unknown")

    result = {"warnings": [], "verification": contract.verification_payload(checks, evidence(
        {"available": True, "value": "https://app.test/other"},
        {"available": True, "value": "Done"},
        {"available": False, "reason": "not_visible"},
    ))}
    runner.note_verification(result)
    check("wiring.failure_is_warned_not_promoted",
          len(result["warnings"]) == 1 and "1 failed" in result["warnings"][0]
          and "executor claim" in result["warnings"][0])
    quiet = {"warnings": [], "verification": contract.verification_payload([])}
    runner.note_verification(quiet)
    check("wiring.not_run_is_not_warned", quiet["warnings"] == [])

    workspace = Path(tempfile.mkdtemp(prefix="jev-checks-"))
    try:
        shot = workspace / "final.png"
        shot.write_bytes(PNG_1X1)
        # A failed or unknown check never changes the run's own status: a
        # completed run stays an executor claim, and nothing is promoted.
        statuses = []
        for status in ("passed", "failed", "unknown", "not_run"):
            outcome = {"output": {"completion_claimed": True, "verification": "not_performed"},
                       "screenshot_path": str(shot), "verification": {"status": status}}
            statuses.append(runner.decide_status("run", "done", None, outcome, True))
        check("wiring.status_ignores_check_outcomes", set(statuses) == {runner.COMPLETED},
              str(statuses))

        runner.HTTP_ATTEMPTS.clear()
        runner.LOGICAL_CALLS.clear()
        result = {"op": "run", "warnings": [], "verification": None}
        runner.finalize(result, {"op": "run", "checks": checks, "artifact_dir": workspace})
        check("wiring.unattempted_checks_are_unknown",
              result["verification"]["status"] == "unknown"
              and result["verification"]["declared"] == 3
              and {row["reason"] for row in result["verification"]["checks"]}
              == {"verification_not_attempted"})
        saved = json.loads((workspace / "result.json").read_text())
        check("wiring.verification_reaches_result_json",
              saved["verification"]["scope"] == "declared_dom_checks_only"
              and len(saved["verification"]["checks"]) == 3)
        result = {"op": "run", "warnings": [], "verification": None}
        runner.finalize(result, {"op": "run", "checks": [], "artifact_dir": workspace})
        check("wiring.no_checks_finalizes_as_not_run",
              result["verification"]["status"] == "not_run")
        check("wiring.base_result_always_has_the_key",
              "verification" in runner.base_result(
                  {"op": "run", "artifact_dir": workspace, "profile_dir": workspace,
                   "profile": "p"}))
    finally:
        shutil.rmtree(workspace, ignore_errors=True)



# --------------------------------------------------------------------------
# run_operation integration: the real runner loop and the real vendored agent
# loop, driven through a fake browser and fake model answers. No Chrome, no
# harness daemon, no provider request, no key. These tests exist because the
# gates, the budget callback, the dispatch truth and the result assembly only
# meet each other inside run_operation.
# --------------------------------------------------------------------------
TASK_SECRET = "Fill the form for order 4471 with Dana's home address"
VALUE_SECRET = "417 Sunset Road, Apt 9"
LABEL_SECRET = "Address field labelled LABEL-MARKER-9f2a"
PAGE_SECRET = "page body that must never reach a handoff"


class StubProcess:
    """A live owned Chrome, as far as run_operation needs to know."""

    def poll(self):
        return None


def safety_page(**overrides):
    from jev_ultrafast.browser import fingerprint

    page = {
        "url": "https://app.test/form",
        "title": "Form",
        "text": PAGE_SECRET,
        "w": 1120,
        "h": 780,
        "scroll": {"y": 0, "height": 780},
        "actions": [
            {"id": "e1", "kind": "fill", "label": LABEL_SECRET, "role": "textbox",
             "value": "", "node": 10},
            {"id": "e2", "kind": "click", "label": "Continue", "role": "button",
             "value": "", "node": 20},
            {"id": "wait", "kind": "wait", "label": "Wait for the page to update"},
        ],
        "marker": ["marker", PAGE_SECRET],
        "page_key": ["page-key-holds-live-field-values", VALUE_SECRET],
        "guards": {},
        "omitted_actions": 0,
        "text_truncated": False,
    }
    page.update(overrides)
    page["fingerprint"] = fingerprint(page)
    return page


def safety_decision(choice, *, operation=None, target=None, confidence=1.0,
                    target_confidence=None):
    spec = {"e1": ("TYPE_TEXT", "1"), "e2": ("CLICK", "2"), "wait": ("WAIT", None),
            "DONE": ("DONE", None), "BLOCKED": ("BLOCKED", None)}
    inferred_operation, inferred_target = spec.get(choice, ("CLICK", "1"))
    operation = inferred_operation if operation is None else operation
    target = inferred_target if target is None else target
    if target_confidence is None:
        target_confidence = None if target is None else 1.0
    return {
        "choice": choice, "operation": operation, "target": target,
        "confidence": confidence, "target_confidence": target_confidence,
        "probabilities": {choice: 1.0}, "latency_ms": 5, "usage": {},
        # Upstream also returns the whole request body on the decision. It must
        # never reach a handoff, so the fake carries the secrets too.
        "request": {"state": {"page": {"text": PAGE_SECRET}},
                    "supplied_values": {"address": VALUE_SECRET[:80]}},
    }


def attempt_record(runner, role, cost):
    """One HTTP attempt, shaped like RecordingClient's, for the budget guard."""
    runner.HTTP_ATTEMPTS.append({
        "role": role, "status_code": 200, "latency_ms": 3, "usage": {},
        "cost_usd": cost, "resolved_model": "typesafe/fake", "provider_message": None,
        "helper_shape": None, "error": None,
    })


def drive_run_operation(runner, *, decisions, request=None, page=None, values=None,
                        generation=None, confidence=None, checks=None, evidence_rows=None,
                        act_error=None, stale_inputs=None, binding=("address", 1.0),
                        helper_text="written by the helper", costs=None,
                        observe_pages=None, fresh_seq=None, decision_costs=None,
                        observe_errors=None):
    """Run the real run_operation against fakes. Returns a report dict.

    Everything that would touch Chrome, the harness daemon or a provider is
    replaced; the agent loop, the gates, the budget callback, the declared-check
    read and the whole result assembly are the real code.
    """
    import shutil
    import tempfile

    import jev_ultrafast.agent as agent_module

    calls = {"choose": 0, "bind": 0, "helper": 0, "acts": [], "observes": 0}
    queued = list(decisions)
    stale_inputs = list(stale_inputs or [])
    costs = costs or {}
    observe_pages = list(observe_pages or [])
    fresh_seq = list(fresh_seq or [])
    decision_costs = list(decision_costs) if decision_costs is not None else None
    # One entry per observe() call: None reads the page, an exception instance
    # is raised instead. Browser.observe is the read after input.
    observe_errors = list(observe_errors or [])
    work = Path(tempfile.mkdtemp(prefix="jev-safety-")).resolve()
    artifact_dir = work / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    base_page = page if page is not None else safety_page()

    class FakeBrowser:
        def __init__(self, url):
            self.session = "fake-session"
            self.closed = False

        def observe(self, screenshot=False):
            calls["observes"] += 1
            failure = observe_errors.pop(0) if observe_errors else None
            if failure is not None:
                raise failure
            current = observe_pages.pop(0) if observe_pages else base_page
            return json.loads(json.dumps(current))

        def fresh(self, page_state, action=None):
            return fresh_seq.pop(0) if fresh_seq else True

        def act(self, action, page_state, text=None):
            # Browser.act checks freshness itself, immediately before CDP input,
            # and raises StalePage before anything is sent (browser.py:100-102).
            if stale_inputs and stale_inputs.pop(0):
                raise agent_module.StalePage("Page changed since this decision. Observe again.")
            calls["acts"].append({"id": action["id"], "kind": action["kind"], "text": text})
            if act_error is not None:
                raise act_error
            return {"executed": action["id"]}

        def evaluate(self, _expression):
            return evidence_rows

        def close(self):
            self.closed = True

    def fake_choose(state, goal, history, values=None):
        calls["choose"] += 1
        if decision_costs is not None:
            cost = decision_costs.pop(0) if decision_costs else 0.001
        else:
            cost = costs.get("decision", 0.001)
        attempt_record(runner, "decision", cost)
        return queued.pop(0) if queued else safety_decision("DONE")

    def fake_bind(goal, action, page_state, history, supplied):
        calls["bind"] += 1
        attempt_record(runner, "decision", costs.get("bind", 0.001))
        key, score = binding
        return {"key": key, "confidence": score, "probabilities": {}, "usage": {},
                "latency_ms": 4, "model": "fake", "request": {"values": supplied}}

    def fake_field_text(_context):
        calls["helper"] += 1
        attempt_record(runner, "helper", costs.get("helper", 0.001))
        return helper_text, {"model": "fake-helper", "latency_ms": 6, "usage": {}}

    def fake_capture_png(_session, destination):
        Path(destination).write_bytes(PNG_1X1)
        return str(destination)

    saved = {
        "Browser": agent_module.Browser,
        "choose": agent_module.choose,
        "bind_value": agent_module.bind_value,
        "field_text": agent_module.field_text,
        "configure_environment": runner.configure_environment,
        "keep_daemon_in_process_group": runner.keep_daemon_in_process_group,
        "launch_chrome": runner.launch_chrome,
        "install_provider_patch": runner.install_provider_patch,
        "start_private_daemon": runner.start_private_daemon,
        "capture_png": runner.capture_png,
        "safe_snapshot": runner.safe_snapshot,
    }
    previous_cdp = os.environ.get("BU_CDP_URL")
    previous_name = os.environ.get("BU_NAME")
    runner.HTTP_ATTEMPTS.clear()
    runner.LOGICAL_CALLS.clear()
    owned = runner.OwnedProcesses()
    owned.chrome = StubProcess()
    try:
        agent_module.Browser = FakeBrowser
        agent_module.choose = fake_choose
        agent_module.bind_value = fake_bind
        agent_module.field_text = fake_field_text
        # The only thing run_operation reads back from the real environment
        # setup. No provider key is set, so no model call is even possible.
        def fake_environment(*_args, **_kwargs):
            os.environ["BU_NAME"] = "jev-offline-test"

        runner.configure_environment = fake_environment
        runner.keep_daemon_in_process_group = lambda: None
        runner.launch_chrome = lambda *_a, **_k: 9222
        runner.install_provider_patch = lambda: None
        runner.start_private_daemon = lambda *_a, **_k: None
        runner.capture_png = fake_capture_png

        def capture_snapshot(agent):
            # The real snapshot, kept so a test can read the executor's own
            # correlation between its decisions, its rows and what it sent.
            state = saved["safe_snapshot"](agent)
            calls["final_state"] = state
            return state

        runner.safe_snapshot = capture_snapshot

        payload = {
            "op": "run", "task": TASK_SECRET, "url": "https://app.test/form",
            "profile_dir": str(work / "profile"), "artifact_dir": str(artifact_dir),
            "max_steps": 5, "timeout_ms": 30000, "max_cost_usd": 0.5,
            "values": values, "generation": generation, "checks": checks or [],
            "confidence": confidence,
        }
        payload.update(request or {})
        config = runner.normalize(payload)
        result = runner.base_result(config)
        stop_reason, error = runner.run_operation(config, owned, result)
        result["status"] = runner.decide_status("run", stop_reason, error, result, True)
        result["stop_reason"] = stop_reason
        # main() finalizes every result, and cost/usage are set there.
        runner.finalize(result, config)
        return {"result": result, "stop_reason": stop_reason, "error": error,
                "calls": calls, "config": config}
    finally:
        agent_module.Browser = saved["Browser"]
        agent_module.choose = saved["choose"]
        agent_module.bind_value = saved["bind_value"]
        agent_module.field_text = saved["field_text"]
        runner.configure_environment = saved["configure_environment"]
        runner.keep_daemon_in_process_group = saved["keep_daemon_in_process_group"]
        runner.launch_chrome = saved["launch_chrome"]
        runner.install_provider_patch = saved["install_provider_patch"]
        runner.start_private_daemon = saved["start_private_daemon"]
        runner.capture_png = saved["capture_png"]
        runner.safe_snapshot = saved["safe_snapshot"]
        for name, value in (("BU_CDP_URL", previous_cdp), ("BU_NAME", previous_name)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        runner.HTTP_ATTEMPTS.clear()
        runner.LOGICAL_CALLS.clear()
        if owned.runtime_dir:
            shutil.rmtree(owned.runtime_dir, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


def assert_handoff_is_safe(runner, prefix, report):
    """The handoff allowlist, checked against the strings that must never be in it."""
    handoff = report["result"]["handoff"]
    check(prefix + ".handoff_exists", isinstance(handoff, dict), str(handoff)[:120])
    if not isinstance(handoff, dict):
        return {}
    check(prefix + ".handoff_keys_are_the_allowlist",
          tuple(handoff) == runner.HANDOFF_FIELDS, json.dumps(sorted(handoff)))
    blob = json.dumps(handoff)
    for name, secret in (("task", TASK_SECRET), ("value", VALUE_SECRET),
                         ("label", LABEL_SECRET), ("page_text", PAGE_SECRET)):
        check(prefix + ".handoff_omits_" + name, secret not in blob, blob[:200])
    for forbidden in ("page_key", "guards", "marker", "screenshot", "supplied_values",
                      "recent_actions", "session"):
        check(prefix + ".handoff_omits_" + forbidden, forbidden not in blob, blob[:200])
    check(prefix + ".handoff_resume_policy",
          handoff["resume_policy"] == "inspect current state; never replay this decision "
          "or any uncertain input", str(handoff["resume_policy"]))
    return handoff


def test_run_operation_confidence_gates(runner):
    """Each gate is independent, withholds before input, and hands off safely."""

    def report_for(**kwargs):
        return drive_run_operation(runner, **kwargs)

    # 1. operation cutoff only: no bind, no helper, no input.
    low_operation = report_for(
        decisions=[safety_decision("e1", confidence=0.4, target_confidence=0.99)],
        values={"address": VALUE_SECRET}, generation="disabled",
        confidence={"operation": 0.8}, checks=[{"id": "landed", "kind": "url",
                                                "contains": "/form"}],
        evidence_rows={"url": "https://app.test/form", "title": "Form",
                       "at": 1737000000000,
                       "rows": [{"available": True, "value": "https://app.test/form"}]},
    )
    result = low_operation["result"]
    check("integration.low_operation.status", result["status"] == runner.NEEDS_REVIEW,
          str(result["status"]))
    check("integration.low_operation.no_input", low_operation["calls"]["acts"] == [],
          json.dumps(low_operation["calls"]["acts"]))
    check("integration.low_operation.no_bind_or_helper",
          low_operation["calls"]["bind"] == 0 and low_operation["calls"]["helper"] == 0,
          json.dumps({k: low_operation["calls"][k] for k in ("bind", "helper")}))
    check("integration.low_operation.side_effects_none",
          result["side_effects"] == "none_observed", str(result["side_effects"]))
    check("integration.low_operation.completion_not_claimed",
          result["output"]["completion_claimed"] is False)
    check("integration.low_operation.one_row_not_dispatched",
          [row["dispatch"] for row in result["actions"]] == ["not_dispatched"],
          json.dumps(result["actions"]))
    check("integration.low_operation.telemetry_scores",
          result["actions"][0]["operation_confidence"] == 0.4
          and result["actions"][0]["target_confidence"] == 0.99
          and result["actions"][0]["confidence"] == 0.4
          and result["actions"][0]["binding_confidence"] is None,
          json.dumps(result["actions"][0]))
    check("integration.low_operation.typed_text_is_not_reported",
          VALUE_SECRET not in json.dumps(result["actions"]), json.dumps(result["actions"]))
    check("integration.low_operation.policy_is_echoed",
          result["confidence_policy"] == {"operation": 0.8}, str(result["confidence_policy"]))
    check("integration.low_operation.declared_checks_still_ran",
          (result["verification"] or {}).get("status") == "passed"
          and (result["verification"] or {}).get("scope") == "declared_dom_checks_only",
          json.dumps(result["verification"])[:200])
    handoff = assert_handoff_is_safe(runner, "integration.low_operation", low_operation)
    check("integration.low_operation.handoff_reason",
          handoff.get("reason") == "low_operation_confidence", str(handoff.get("reason")))
    check("integration.low_operation.handoff_dispatch",
          handoff.get("input_dispatched") == "not_dispatched",
          str(handoff.get("input_dispatched")))
    check("integration.low_operation.handoff_scores",
          handoff.get("operation_confidence") == 0.4 and handoff.get("target_confidence") == 0.99
          and handoff.get("choice") == "e1" and handoff.get("operation") == "TYPE_TEXT",
          json.dumps(handoff))
    check("integration.low_operation.handoff_observation",
          handoff.get("observation") == result["observation"]
          and result["observation"]["viewport"] == {"w": 1120, "h": 780},
          json.dumps(result["observation"]))

    # 2. target cutoff only, operation score low and ungated: still withheld.
    low_target = report_for(
        decisions=[safety_decision("e1", confidence=0.1, target_confidence=0.3)],
        values={"address": VALUE_SECRET}, generation="disabled",
        confidence={"target": 0.9},
    )
    check("integration.low_target.status",
          low_target["result"]["status"] == runner.NEEDS_REVIEW,
          str(low_target["result"]["status"]))
    check("integration.low_target.no_bind_helper_or_input",
          low_target["calls"]["bind"] == 0 and low_target["calls"]["helper"] == 0
          and low_target["calls"]["acts"] == [], json.dumps(low_target["calls"]))
    check("integration.low_target.reason",
          low_target["result"]["handoff"]["reason"] == "low_target_confidence",
          str(low_target["result"]["handoff"]["reason"]))

    # 3. binding cutoff only: the bind runs once, nothing is typed.
    low_binding = report_for(
        decisions=[safety_decision("e1", confidence=0.2, target_confidence=0.2)],
        values={"address": VALUE_SECRET}, generation="helper",
        confidence={"binding": 0.9}, binding=("address", 0.3),
    )
    check("integration.low_binding.status",
          low_binding["result"]["status"] == runner.NEEDS_REVIEW,
          str(low_binding["result"]["status"]))
    check("integration.low_binding.bound_once_typed_nothing",
          low_binding["calls"]["bind"] == 1 and low_binding["calls"]["helper"] == 0
          and low_binding["calls"]["acts"] == [], json.dumps(low_binding["calls"]))
    row = low_binding["result"]["actions"][0]
    check("integration.low_binding.telemetry",
          row["binding_confidence"] == 0.3 and row["value_key"] == "address"
          and row["dispatch"] == "not_dispatched", json.dumps(row))
    handoff = assert_handoff_is_safe(runner, "integration.low_binding", low_binding)
    check("integration.low_binding.handoff_binding_key",
          handoff.get("binding_key") == "address" and handoff.get("binding_confidence") == 0.3,
          json.dumps(handoff))

    # 4. a NONE binding under a cutoff is withheld, not treated as a skip.
    none_binding = report_for(
        decisions=[safety_decision("e1")], values={"address": VALUE_SECRET},
        generation="disabled", confidence={"binding": 0.5}, binding=(None, 0.2),
    )
    check("integration.none_binding.is_withheld_not_skipped",
          none_binding["result"]["handoff"]["reason"] == "low_binding_confidence"
          and none_binding["result"]["actions"][0]["value_source"] is None,
          json.dumps(none_binding["result"]["actions"][0]))

    # 5. baseline: the same low scores with no policy still type and complete.
    no_policy = report_for(
        decisions=[safety_decision("e1", confidence=0.1, target_confidence=0.1),
                   safety_decision("DONE", confidence=0.1)],
        values={"address": VALUE_SECRET}, generation="disabled",
    )
    result = no_policy["result"]
    check("integration.no_policy.completed", result["status"] == runner.COMPLETED,
          str(result["status"]) + " " + str(result.get("error")))
    check("integration.no_policy.typed_the_supplied_value",
          [a["text"] for a in no_policy["calls"]["acts"]] == [VALUE_SECRET],
          json.dumps([a["id"] for a in no_policy["calls"]["acts"]]))
    check("integration.no_policy.dispatch_is_attempted",
          [row["dispatch"] for row in result["actions"]] == ["attempted"],
          json.dumps(result["actions"]))
    check("integration.no_policy.side_effects_uncertain",
          result["side_effects"] == "uncertain", str(result["side_effects"]))
    check("integration.no_policy.no_handoff_on_completion", result["handoff"] is None,
          json.dumps(result["handoff"]))
    check("integration.no_policy.policy_is_null", result["confidence_policy"] is None,
          str(result["confidence_policy"]))
    check("integration.no_policy.scores_are_still_recorded",
          result["actions"][0]["operation_confidence"] == 0.1
          and result["actions"][0]["binding_confidence"] == 1.0, json.dumps(result["actions"][0]))

    # 6. an unbound field with generation="disabled" still skips, and a skip is
    # not an input: the run is still none_observed.
    skipped = report_for(
        decisions=[safety_decision("e1"), safety_decision("DONE")],
        values={"address": VALUE_SECRET}, generation="disabled",
        confidence={"binding": 0.5}, binding=(None, 0.9),
    )
    result = skipped["result"]
    check("integration.skip.completed_without_typing",
          result["status"] == runner.COMPLETED and skipped["calls"]["acts"] == []
          and skipped["calls"]["helper"] == 0, str(result["status"]))
    check("integration.skip.dispatch_and_side_effects",
          result["actions"][0]["dispatch"] == "not_dispatched"
          and result["actions"][0]["value_source"] == "skipped"
          and result["side_effects"] == "none_observed", json.dumps(result["actions"][0]))

    # 7. A click whose target field is missing still hits the target gate.
    # choose() never produces this shape; the gate keys off action kind.
    for name, score in (("low", 0.01), ("missing", None)):
        malformed = dict(safety_decision("e2", confidence=1.0, target_confidence=0.01))
        malformed["target"] = None
        if score is None:
            malformed.pop("target_confidence", None)
        else:
            malformed["target_confidence"] = score
        report = report_for(decisions=[malformed], confidence={"target": 0.9})
        result = report["result"]
        check("integration.null_target_" + name + ".status",
              result["status"] == runner.NEEDS_REVIEW, str(result["status"]))
        check("integration.null_target_" + name + ".no_input",
              report["calls"]["acts"] == [] and report["calls"]["bind"] == 0,
              json.dumps(report["calls"]))
        check("integration.null_target_" + name + ".reason",
              (result["handoff"] or {}).get("reason") == "low_target_confidence",
              json.dumps(result["handoff"]))


def test_run_operation_budget_and_dispatch(runner):
    """Cost is checked before input, and dispatch truth survives every path."""
    # 1. An uncosted successful attempt stops the run before the fill binds,
    # calls the helper or types anything.
    uncosted = drive_run_operation(
        runner,
        decisions=[safety_decision("e1")], values={"address": VALUE_SECRET},
        generation="helper", costs={"decision": None},
    )
    result = uncosted["result"]
    check("integration.cost_unknown.status", result["status"] == runner.COST_UNKNOWN,
          str(result["status"]))
    check("integration.cost_unknown.nothing_after_the_decision",
          uncosted["calls"]["bind"] == 0 and uncosted["calls"]["helper"] == 0
          and uncosted["calls"]["acts"] == [], json.dumps(uncosted["calls"]))
    check("integration.cost_unknown.cost_is_unknown_not_zero", result["cost"] is None,
          str(result["cost"]))
    check("integration.cost_unknown.no_rows_and_no_side_effects",
          result["actions"] == [] and result["side_effects"] == "none_observed",
          json.dumps(result["actions"]))
    handoff = assert_handoff_is_safe(runner, "integration.cost_unknown", uncosted)
    check("integration.cost_unknown.handoff_reason_and_dispatch",
          handoff.get("reason") == runner.COST_UNKNOWN
          and handoff.get("input_dispatched") == "not_dispatched", json.dumps(handoff))
    check("integration.cost_unknown.handoff_keeps_the_decision",
          handoff.get("choice") == "e1" and handoff.get("operation") == "TYPE_TEXT",
          json.dumps(handoff))

    # 2. An uncosted bind stops before the helper and before input, with the
    # bind already recorded.
    uncosted_bind = drive_run_operation(
        runner,
        decisions=[safety_decision("e1")], values={"address": VALUE_SECRET},
        generation="helper", binding=(None, 0.95), costs={"bind": None},
    )
    check("integration.cost_unknown_bind.status",
          uncosted_bind["result"]["status"] == runner.COST_UNKNOWN,
          str(uncosted_bind["result"]["status"]))
    check("integration.cost_unknown_bind.helper_and_input_never_ran",
          uncosted_bind["calls"]["bind"] == 1 and uncosted_bind["calls"]["helper"] == 0
          and uncosted_bind["calls"]["acts"] == [], json.dumps(uncosted_bind["calls"]))

    # 3. An uncosted helper answer stops before the field is typed.
    uncosted_helper = drive_run_operation(
        runner, decisions=[safety_decision("e1")], generation="helper",
        costs={"helper": None},
    )
    check("integration.cost_unknown_helper.status",
          uncosted_helper["result"]["status"] == runner.COST_UNKNOWN,
          str(uncosted_helper["result"]["status"]))
    check("integration.cost_unknown_helper.nothing_typed",
          uncosted_helper["calls"]["helper"] == 1 and uncosted_helper["calls"]["acts"] == [],
          json.dumps(uncosted_helper["calls"]))

    # 4. Over the cap, the next decision cannot act either.
    over_budget = drive_run_operation(
        runner,
        decisions=[safety_decision("e2"), safety_decision("e2")],
        request={"max_cost_usd": 0.002}, costs={"decision": 0.0015},
    )
    result = over_budget["result"]
    check("integration.cost_limit.status", result["status"] == runner.COST_LIMIT,
          str(result["status"]))
    check("integration.cost_limit.one_click_only",
          [a["id"] for a in over_budget["calls"]["acts"]] == ["e2"],
          json.dumps(over_budget["calls"]["acts"]))
    check("integration.cost_limit.side_effects_uncertain",
          result["side_effects"] == "uncertain", str(result["side_effects"]))
    check("integration.cost_limit.cost_is_known",
          result["cost"] is not None and result["cost"] > 0.002, str(result["cost"]))
    check("integration.cost_limit.handoff_not_dispatched",
          result["handoff"]["input_dispatched"] == "not_dispatched",
          json.dumps(result["handoff"]))

    # 5. An interrupted dropdown: dispatch is unknown, the row survives, and
    # the run stops for review instead of retrying.
    interrupted = drive_run_operation(
        runner, decisions=[safety_decision("e2")],
        act_error=RuntimeError("Dropdown execution was interrupted; inspect before retrying."),
    )
    result = interrupted["result"]
    check("integration.interrupted.status", result["status"] == runner.NEEDS_REVIEW,
          str(result["status"]))
    check("integration.interrupted.one_attempt_only",
          len(interrupted["calls"]["acts"]) == 1 and interrupted["calls"]["choose"] == 1,
          json.dumps(interrupted["calls"]))
    check("integration.interrupted.dispatch_is_unknown",
          [row["dispatch"] for row in result["actions"]] == ["unknown"],
          json.dumps(result["actions"]))
    check("integration.interrupted.side_effects_uncertain",
          result["side_effects"] == "uncertain", str(result["side_effects"]))
    handoff = assert_handoff_is_safe(runner, "integration.interrupted", interrupted)
    check("integration.interrupted.handoff",
          handoff.get("reason") == "input_interrupted"
          and handoff.get("input_dispatched") == "unknown", json.dumps(handoff))

    # 6. A freshness failure before input is a safe re-observation: it must not
    # become an uncertain input, and the retry is a new decision, not a replay.
    stale_first = drive_run_operation(
        runner,
        decisions=[safety_decision("e2"), safety_decision("DONE")],
        stale_inputs=[True],
    )
    result = stale_first["result"]
    check("integration.stale_before_input.completed",
          result["status"] == runner.COMPLETED, str(result["status"]))
    check("integration.stale_before_input.no_input_was_dispatched",
          stale_first["calls"]["acts"] == [] and result["actions"] == [],
          json.dumps(stale_first["calls"]["acts"]))
    check("integration.stale_before_input.side_effects_stay_none_observed",
          result["side_effects"] == "none_observed", str(result["side_effects"]))
    check("integration.stale_before_input.re_observed_and_chose_again",
          stale_first["calls"]["choose"] == 2 and stale_first["calls"]["observes"] >= 2,
          json.dumps(stale_first["calls"]))


def test_run_operation_stopping_dispatch_correlation(runner):
    """The stopping decision's dispatch is correlated, never counted.

    Every case here drives the real run_operation and the real agent loop.
    Cases 1 and 2 have the identical count shape, one row and two decisions,
    with the last row reading "attempted", and the honest answers differ.
    """

    def correlation(report):
        """(rows, decisions, record) as the executor itself recorded them."""
        state = report["calls"].get("final_state") or {}
        return state.get("history") or [], state.get("decisions") or [], state.get("latest_dispatch")

    # 1. The reported regression. A pre-input StalePage retry leaves a decision
    # with no row, the retry then clicks, and the run stops at max_steps. The
    # stopping decision did dispatch.
    stale_then_click = drive_run_operation(
        runner,
        decisions=[safety_decision("e2"), safety_decision("e2")],
        stale_inputs=[True], request={"max_steps": 1},
    )
    result = stale_then_click["result"]
    rows, decisions, record = correlation(stale_then_click)
    check("dispatch_correlation.stale_retry.status", result["status"] == runner.MAX_STEPS,
          str(result["status"]))
    check("dispatch_correlation.stale_retry.one_click_reached_the_page",
          [a["id"] for a in stale_then_click["calls"]["acts"]] == ["e2"],
          json.dumps(stale_then_click["calls"]["acts"]))
    check("dispatch_correlation.stale_retry.row_says_attempted",
          [row["dispatch"] for row in result["actions"]] == ["attempted"],
          json.dumps(result["actions"]))
    check("dispatch_correlation.stale_retry.handoff_says_attempted",
          result["handoff"]["input_dispatched"] == "attempted",
          json.dumps(result["handoff"]))
    check("dispatch_correlation.stale_retry.side_effects_uncertain",
          result["side_effects"] == "uncertain", str(result["side_effects"]))
    # The row the handoff describes is the row the stopping decision produced.
    check("dispatch_correlation.stale_retry.record_names_the_stopping_decision",
          isinstance(record, dict)
          and record["decision_seq"] == decisions[-1]["decision_seq"]
          and record["decision_seq"] == rows[-1]["decision_seq"]
          and record["dispatch"] == rows[-1]["dispatch"],
          json.dumps({"record": record, "rows": [r.get("decision_seq") for r in rows],
                      "decisions": [d.get("decision_seq") for d in decisions]}))
    check("dispatch_correlation.stale_retry.the_stale_decision_made_no_row",
          len(decisions) == 2 and len(rows) == 1
          and decisions[0]["decision_seq"] != rows[0]["decision_seq"],
          json.dumps({"rows": len(rows), "decisions": len(decisions)}))

    # 2. The paired case the counts cannot separate. A click, then a new
    # decision that the cost stop caught before input. Same shape, and
    # "not_dispatched" is the honest answer here.
    click_then_cost = drive_run_operation(
        runner,
        decisions=[safety_decision("e2"), safety_decision("e2")],
        request={"max_cost_usd": 0.002}, costs={"decision": 0.0015},
    )
    result = click_then_cost["result"]
    paired_rows, paired_decisions, paired_record = correlation(click_then_cost)
    check("dispatch_correlation.cost_limit.status", result["status"] == runner.COST_LIMIT,
          str(result["status"]))
    check("dispatch_correlation.cost_limit.handoff_stays_not_dispatched",
          result["handoff"]["input_dispatched"] == "not_dispatched",
          json.dumps(result["handoff"]))
    check("dispatch_correlation.cost_limit.the_earlier_click_is_still_reported",
          [row["dispatch"] for row in result["actions"]] == ["attempted"]
          and result["side_effects"] == "uncertain", json.dumps(result["actions"]))
    check("dispatch_correlation.cost_limit.record_names_the_uncosted_decision",
          isinstance(paired_record, dict)
          and paired_record["decision_seq"] == paired_decisions[-1]["decision_seq"]
          and paired_record["decision_seq"] != paired_rows[-1]["decision_seq"]
          and paired_record["dispatch"] == "not_dispatched",
          json.dumps({"record": paired_record,
                      "rows": [r.get("decision_seq") for r in paired_rows]}))
    # The two runs above are indistinguishable by count.
    check("dispatch_correlation.the_two_cases_have_the_same_count_shape",
          (len(rows), len(decisions), rows[-1]["dispatch"])
          == (len(paired_rows), len(paired_decisions), paired_rows[-1]["dispatch"]),
          json.dumps({"stale_retry": [len(rows), len(decisions), rows[-1]["dispatch"]],
                      "cost_limit": [len(paired_rows), len(paired_decisions),
                                     paired_rows[-1]["dispatch"]]}))
    check("dispatch_correlation.the_two_cases_report_different_answers",
          stale_then_click["result"]["handoff"]["input_dispatched"] == "attempted"
          and click_then_cost["result"]["handoff"]["input_dispatched"] == "not_dispatched")

    # 3. An uncosted second decision stops before input for the same reason.
    click_then_uncosted = drive_run_operation(
        runner,
        decisions=[safety_decision("e2"), safety_decision("e2")],
        decision_costs=[0.001, None],
    )
    result = click_then_uncosted["result"]
    check("dispatch_correlation.cost_unknown.status", result["status"] == runner.COST_UNKNOWN,
          str(result["status"]))
    check("dispatch_correlation.cost_unknown.handoff_not_dispatched",
          result["handoff"]["input_dispatched"] == "not_dispatched"
          and [row["dispatch"] for row in result["actions"]] == ["attempted"],
          json.dumps(result["handoff"]))

    # 4. A withheld second decision after a dispatched first one.
    click_then_withheld = drive_run_operation(
        runner,
        decisions=[safety_decision("e2", confidence=0.95, target_confidence=0.95),
                   safety_decision("e2", confidence=0.1, target_confidence=0.95)],
        confidence={"operation": 0.8},
    )
    result = click_then_withheld["result"]
    withheld_rows, withheld_decisions, withheld_record = correlation(click_then_withheld)
    check("dispatch_correlation.low_confidence_second.status",
          result["status"] == runner.NEEDS_REVIEW, str(result["status"]))
    check("dispatch_correlation.low_confidence_second.handoff_not_dispatched",
          result["handoff"]["input_dispatched"] == "not_dispatched",
          json.dumps(result["handoff"]))
    check("dispatch_correlation.low_confidence_second.rows_keep_both_decisions",
          [row["dispatch"] for row in result["actions"]] == ["attempted", "not_dispatched"],
          json.dumps(result["actions"]))
    check("dispatch_correlation.low_confidence_second.record_matches_the_withheld_row",
          isinstance(withheld_record, dict)
          and withheld_record["decision_seq"] == withheld_decisions[-1]["decision_seq"]
          and withheld_record["decision_seq"] == withheld_rows[-1]["decision_seq"]
          and withheld_record["dispatch"] == "not_dispatched",
          json.dumps({"record": withheld_record,
                      "rows": [r.get("decision_seq") for r in withheld_rows]}))

    # 5. Two freshness failures in a row send nothing at all.
    repeated_stale = drive_run_operation(
        runner,
        decisions=[safety_decision("e2"), safety_decision("e2")],
        stale_inputs=[True, True], decision_costs=[0.001, None],
    )
    result = repeated_stale["result"]
    stale_rows, stale_decisions, stale_record = correlation(repeated_stale)
    check("dispatch_correlation.repeated_stale.no_input_reached_the_page",
          repeated_stale["calls"]["acts"] == [] and result["actions"] == [],
          json.dumps(repeated_stale["calls"]["acts"]))
    check("dispatch_correlation.repeated_stale.none_observed_and_not_dispatched",
          result["side_effects"] == "none_observed"
          and result["handoff"]["input_dispatched"] == "not_dispatched",
          json.dumps({"side_effects": result["side_effects"], "handoff": result["handoff"]}))
    check("dispatch_correlation.repeated_stale.two_decisions_no_rows",
          len(stale_decisions) == 2 and stale_rows == []
          and stale_record["decision_seq"] == stale_decisions[-1]["decision_seq"],
          json.dumps({"decisions": len(stale_decisions), "rows": len(stale_rows)}))

    # 6. An interrupted select stays unknown and is never replayed.
    interrupted = drive_run_operation(
        runner, decisions=[safety_decision("e2")],
        act_error=RuntimeError("Dropdown execution was interrupted; inspect before retrying."),
    )
    result = interrupted["result"]
    _, interrupted_decisions, interrupted_record = correlation(interrupted)
    check("dispatch_correlation.interrupted.unknown_is_not_downgraded",
          result["handoff"]["input_dispatched"] == "unknown"
          and [row["dispatch"] for row in result["actions"]] == ["unknown"]
          and result["side_effects"] == "uncertain", json.dumps(result["handoff"]))
    check("dispatch_correlation.interrupted.one_attempt_only",
          len(interrupted["calls"]["acts"]) == 1 and interrupted["calls"]["choose"] == 1,
          json.dumps(interrupted["calls"]))
    check("dispatch_correlation.interrupted.record_is_unknown",
          interrupted_record["dispatch"] == "unknown"
          and interrupted_record["decision_seq"] == interrupted_decisions[-1]["decision_seq"],
          json.dumps(interrupted_record))

    # 7. The read after input failed. The dispatched input must survive it.
    import jev_ultrafast.agent as agent_module

    stale_after_input = drive_run_operation(
        runner, decisions=[safety_decision("e2")],
        observe_errors=[None, agent_module.StalePage("Page changed after input.")],
    )
    result = stale_after_input["result"]
    _, _, after_record = correlation(stale_after_input)
    check("dispatch_correlation.stale_after_input.status",
          result["status"] == runner.NEEDS_REVIEW, str(result["status"]))
    check("dispatch_correlation.stale_after_input.attempted_survives",
          result["handoff"]["input_dispatched"] == "attempted"
          and [row["dispatch"] for row in result["actions"]] == ["attempted"]
          and result["side_effects"] == "uncertain", json.dumps(result["handoff"]))
    check("dispatch_correlation.stale_after_input.record_is_attempted",
          after_record["dispatch"] == "attempted", json.dumps(after_record))

    # A non-StalePage read failure after input keeps the same uncertainty. Its
    # status is the separate post-input observe question and is unchanged here.
    broken_after_input = drive_run_operation(
        runner, decisions=[safety_decision("e2")],
        observe_errors=[None, RuntimeError("CDP transport died mid-observe")],
    )
    result = broken_after_input["result"]
    _, _, broken_record = correlation(broken_after_input)
    check("dispatch_correlation.observe_error.uncertainty_is_kept",
          result["handoff"]["input_dispatched"] == "unknown"
          and [row["dispatch"] for row in result["actions"]] == ["attempted"]
          and result["side_effects"] == "uncertain",
          json.dumps({"handoff": result["handoff"], "actions": result["actions"]}))
    check("dispatch_correlation.observe_error.record_still_says_attempted",
          broken_record["dispatch"] == "attempted", json.dumps(broken_record))

    # 8. A run that stops on its own decision, with no retry anywhere, still
    # reports the row it stopped on.
    plain_max_steps = drive_run_operation(
        runner, decisions=[safety_decision("e2"), safety_decision("e2")],
        request={"max_steps": 1},
    )
    result = plain_max_steps["result"]
    plain_rows, plain_decisions, plain_record = correlation(plain_max_steps)
    check("dispatch_correlation.control.attempted",
          result["status"] == runner.MAX_STEPS
          and result["handoff"]["input_dispatched"] == "attempted",
          json.dumps(result["handoff"]))
    check("dispatch_correlation.control.one_decision_one_row",
          len(plain_decisions) == 1 and len(plain_rows) == 1
          and plain_record["decision_seq"] == plain_rows[-1]["decision_seq"],
          json.dumps({"decisions": len(plain_decisions), "rows": len(plain_rows)}))


def test_run_operation_truncated_completion(runner):
    """A DONE on truncated evidence is only a completion when the checks pass."""
    truncated = safety_page(text_truncated=True, omitted_actions=12)
    passing_evidence = {"url": "https://app.test/form", "title": "Form",
                        "at": 1737000000000,
                        "rows": [{"available": True, "value": "https://app.test/form"}]}
    failing_evidence = {"url": "https://app.test/form", "title": "Form",
                        "at": 1737000000000,
                        "rows": [{"available": True, "value": "https://app.test/elsewhere"}]}
    unknown_evidence = {"url": "https://app.test/form", "title": "Form",
                        "at": 1737000000000,
                        "rows": [{"available": False, "reason": "missing_or_ambiguous",
                                  "matches": 0}]}
    landed = [{"id": "landed", "kind": "url", "contains": "/form"}]

    # 1. No declared check: a truncated DONE is needs_review, not completed.
    no_checks = drive_run_operation(runner, decisions=[safety_decision("DONE")], page=truncated)
    result = no_checks["result"]
    check("integration.truncated_done.status", result["status"] == runner.NEEDS_REVIEW,
          str(result["status"]))
    check("integration.truncated_done.completion_not_claimed",
          result["output"]["completion_claimed"] is False)
    check("integration.truncated_done.observation_says_why",
          result["observation"]["text_truncated"] is True
          and result["observation"]["omitted_actions"] == 12,
          json.dumps(result["observation"]))
    handoff = assert_handoff_is_safe(runner, "integration.truncated_done", no_checks)
    check("integration.truncated_done.reason", handoff.get("reason") == "truncated_done",
          str(handoff.get("reason")))

    # 2. Declared checks that all pass: the provisional DONE is accepted, and
    # the warning still says what that evidence does and does not mean.
    passed = drive_run_operation(
        runner, decisions=[safety_decision("DONE")], page=truncated,
        checks=landed, evidence_rows=passing_evidence,
    )
    result = passed["result"]
    check("integration.truncated_done_passed.completed",
          result["status"] == runner.COMPLETED, str(result["status"]) + str(result.get("error")))
    check("integration.truncated_done_passed.checks_passed",
          result["verification"]["status"] == "passed", json.dumps(result["verification"])[:200])
    check("integration.truncated_done_passed.warning_is_scoped",
          any("truncated observation" in w and "not proof the whole task finished" in w
              for w in result["warnings"]), json.dumps(result["warnings"]))
    check("integration.truncated_done_passed.no_handoff", result["handoff"] is None)

    # 3. Declared checks that fail, and checks that could not be read: the
    # completion claim is withheld both times.
    for name, rows in (("failed", failing_evidence), ("unknown", unknown_evidence)):
        report = drive_run_operation(
            runner, decisions=[safety_decision("DONE")], page=truncated,
            checks=landed, evidence_rows=rows,
        )
        result = report["result"]
        check("integration.truncated_done_" + name + ".status",
              result["status"] == runner.NEEDS_REVIEW, str(result["status"]))
        check("integration.truncated_done_" + name + ".completion_not_claimed",
              result["output"]["completion_claimed"] is False)
        check("integration.truncated_done_" + name + ".evidence_is_kept",
              result["verification"]["status"] == name
              and len(result["verification"]["checks"]) == 1,
              json.dumps(result["verification"])[:200])
        handoff = assert_handoff_is_safe(runner, "integration.truncated_done_" + name, report)
        check("integration.truncated_done_" + name + ".reason",
              handoff.get("reason") == "truncated_done_checks_not_passed",
              str(handoff.get("reason")))
        check("integration.truncated_done_" + name + ".warned",
              any("did not all pass" in w for w in result["warnings"]),
              json.dumps(result["warnings"]))

    # 4. BLOCKED with omitted actions is needs_review; a cut action list is not
    # proof that no supported operation exists.
    blocked = drive_run_operation(runner, decisions=[safety_decision("BLOCKED")], page=truncated)
    check("integration.truncated_blocked.status",
          blocked["result"]["status"] == runner.NEEDS_REVIEW,
          str(blocked["result"]["status"]))
    check("integration.truncated_blocked.reason",
          blocked["result"]["handoff"]["reason"] == "truncated_blocked",
          str(blocked["result"]["handoff"]["reason"]))

    # 5. Truncation does not stop ordinary navigation: a click on the same page
    # runs, and the run still completes.
    navigated = drive_run_operation(
        runner, decisions=[safety_decision("e2"), safety_decision("DONE")],
        page=safety_page(text_truncated=True),
        checks=landed, evidence_rows=passing_evidence,
    )
    result = navigated["result"]
    check("integration.truncated_click.completed", result["status"] == runner.COMPLETED,
          str(result["status"]) + str(result.get("error")))
    check("integration.truncated_click.clicked",
          [a["id"] for a in navigated["calls"]["acts"]] == ["e2"],
          json.dumps(navigated["calls"]["acts"]))
    check("integration.truncated_click.side_effects_uncertain",
          result["side_effects"] == "uncertain", str(result["side_effects"]))

    # 6. An untruncated DONE with no declared check is a plain completion: the
    # previous behaviour is unchanged.
    plain = drive_run_operation(runner, decisions=[safety_decision("DONE")])
    check("integration.plain_done.completed",
          plain["result"]["status"] == runner.COMPLETED,
          str(plain["result"]["status"]) + str(plain["result"].get("error")))
    check("integration.plain_done.claimed_and_not_warned",
          plain["result"]["output"]["completion_claimed"] is True
          and not any("truncated" in w for w in plain["result"]["warnings"]),
          json.dumps(plain["result"]["warnings"]))


def test_run_operation_live_observation(runner):
    """A raise after a re-observe must report the new page, not the yielded one."""
    old_page = safety_page()
    new_page = safety_page(
        text_truncated=True, omitted_actions=7, text="later page " + PAGE_SECRET,
    )
    check("integration.live_obs.fingerprints_differ",
          old_page["fingerprint"] != new_page["fingerprint"]
          and old_page["text_truncated"] is False
          and new_page["text_truncated"] is True,
          old_page["fingerprint"][:16] + " " + new_page["fingerprint"][:16])
    # observe: init, post-click, predict re-observe. fresh: predict1, predict2, DONE/budget.
    observe_pages = [old_page, old_page, new_page]
    fresh_seq = [True, False, True]
    want = runner.observation_of(new_page)

    def assert_new_page(prefix, report, *, reason, extra_rows=0):
        result = report["result"]
        handoff = assert_handoff_is_safe(runner, prefix, report)
        check(prefix + ".status_is_not_completed",
              result["status"] != runner.COMPLETED, str(result["status"]))
        check(prefix + ".reason", handoff.get("reason") == reason, str(handoff.get("reason")))
        check(prefix + ".result_observation_is_the_new_page",
              result["observation"] == want, json.dumps(result["observation"]))
        check(prefix + ".handoff_observation_is_the_new_page",
              handoff.get("observation") == want, json.dumps(handoff.get("observation")))
        check(prefix + ".fingerprint_is_not_the_old_page",
              result["observation"]["fingerprint"] == new_page["fingerprint"]
              and result["observation"]["fingerprint"] != old_page["fingerprint"],
              str(result["observation"]["fingerprint"]))
        check(prefix + ".prior_click_is_retained",
              len(result["actions"]) == 1 + extra_rows
              and result["actions"][0]["kind"] == "click"
              and result["actions"][0]["dispatch"] == "attempted",
              json.dumps(result["actions"]))
        check(prefix + ".side_effects_uncertain",
              result["side_effects"] == "uncertain", str(result["side_effects"]))
        return result, handoff

    # 1. Tick 1 clicks the untruncated page. Tick 2 re-observes a truncated page,
    # answers DONE, and withholds. Both observation fields must describe page 2.
    truncated = drive_run_operation(
        runner,
        decisions=[safety_decision("e2"), safety_decision("DONE")],
        page=old_page, observe_pages=list(observe_pages), fresh_seq=list(fresh_seq),
    )
    result, handoff = assert_new_page(
        "integration.live_obs.truncated_done", truncated,
        reason="truncated_done", extra_rows=1,
    )
    check("integration.live_obs.truncated_done.status",
          result["status"] == runner.NEEDS_REVIEW, str(result["status"]))
    check("integration.live_obs.truncated_done.withheld_row",
          result["actions"][1]["dispatch"] == "not_dispatched"
          and result["actions"][1]["kind"] == "done",
          json.dumps(result["actions"][1]))

    # 2. Same re-observe, then an uncosted second decision. History from tick 1 stays.
    uncosted = drive_run_operation(
        runner,
        decisions=[safety_decision("e2"), safety_decision("DONE")],
        page=old_page, observe_pages=list(observe_pages), fresh_seq=list(fresh_seq),
        decision_costs=[0.001, None],
    )
    result, handoff = assert_new_page(
        "integration.live_obs.cost_unknown", uncosted,
        reason=runner.COST_UNKNOWN, extra_rows=0,
    )
    check("integration.live_obs.cost_unknown.status",
          result["status"] == runner.COST_UNKNOWN, str(result["status"]))
    check("integration.live_obs.cost_unknown.no_second_input",
          [a["id"] for a in uncosted["calls"]["acts"]] == ["e2"],
          json.dumps(uncosted["calls"]["acts"]))

    # 3. Same re-observe, then a low-confidence DONE. Prior click is kept.
    low = drive_run_operation(
        runner,
        decisions=[safety_decision("e2"), safety_decision("DONE", confidence=0.1)],
        page=old_page, observe_pages=list(observe_pages), fresh_seq=list(fresh_seq),
        confidence={"operation": 0.9},
    )
    result, handoff = assert_new_page(
        "integration.live_obs.low_confidence", low,
        reason="low_operation_confidence", extra_rows=1,
    )
    check("integration.live_obs.low_confidence.status",
          result["status"] == runner.NEEDS_REVIEW, str(result["status"]))
    check("integration.live_obs.low_confidence.no_second_input",
          [a["id"] for a in low["calls"]["acts"]] == ["e2"],
          json.dumps(low["calls"]["acts"]))


UNIT_TESTS = [
    test_safety_metadata,
    test_needs_review_status,
    test_run_operation_confidence_gates,
    test_run_operation_budget_and_dispatch,
    test_run_operation_stopping_dispatch_correlation,
    test_run_operation_truncated_completion,
    test_run_operation_live_observation,
    test_group_scan_excludes_itself,
    test_supplied_values,
    test_reported_actions_and_deviations,
    test_bind_call_is_costed_like_a_decision,
    test_helper_response_shape,
    test_validation,
    test_cost_rules,
    test_redaction,
    test_png_capture,
    test_classification,
    test_provider_errors,
    test_daemon_patch_fails_closed,
    test_status_decisions,
    test_declared_check_contract,
    test_declared_check_expression,
    test_declared_check_evidence,
    test_declared_check_wiring,
]


# --------------------------------------------------------------------------
# browser and login groups. No model calls anywhere in these tests.
# --------------------------------------------------------------------------
import shutil
import signal
import subprocess
import tempfile
import urllib.request

import fixture_server


RUNTIME_PYTHON = RUNTIME / ".venv" / "bin" / "python"


def runner_command():
    """The documented launch: the runtime interpreter directly, never uv run."""
    return [str(RUNTIME_PYTHON), str(RUNTIME / "runner.py")]


OPEN_REQUEST_FILES = []


def start_runner(request, env=None, new_session=True):
    """Start a runner with the request on a file-backed stdin, in its own group."""
    handle = tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False)
    handle.write(json.dumps(request))
    handle.flush()
    handle.seek(0)
    OPEN_REQUEST_FILES.append(handle)
    process = subprocess.Popen(
        runner_command(),
        stdin=handle,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env or os.environ.copy(),
        start_new_session=new_session,
    )
    return process


def finish_runner(process, timeout_s):
    try:
        out, err = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        process.kill()
        out, err = process.communicate(timeout=10)
        return None, out, err
    payload = None
    for line in out.strip().splitlines():
        if line.startswith("{"):
            payload = json.loads(line)
    return payload, out, err


def clear_devtools_port(profile_dir):
    """Remove a previous run's port file so a reused profile cannot be misread."""
    try:
        (Path(profile_dir) / "DevToolsActivePort").unlink()
    except OSError:
        pass


def devtools_port(profile_dir, timeout_s=30.0, previous=None):
    """Wait for a freshly written DevTools port for this profile.

    A reused profile still holds the previous run's DevToolsActivePort for a
    moment, so a naive read can return a dead port. Accept only a value that
    differs from the one recorded before the runner started.
    """
    port_file = Path(profile_dir) / "DevToolsActivePort"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            content = port_file.read_text()
            lines = content.splitlines()
            if lines and lines[0].strip().isdigit() and content != previous:
                return int(lines[0].strip())
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    return None


def devtools_targets(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=2) as response:
            return json.loads(response.read())
    except Exception:
        return None


def close_all_pages(port, timeout_s=20.0):
    """Act as the person closing every window of this profile."""
    deadline = time.time() + timeout_s
    closed = 0
    while time.time() < deadline:
        targets = devtools_targets(port)
        if targets is None:
            return closed
        pages = [t for t in targets if t.get("type") == "page"]
        if not pages:
            return closed
        for target in pages:
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json/close/%s" % (port, target["id"]), timeout=2
                ) as response:
                    response.read()
                closed += 1
            except Exception:
                pass
        time.sleep(0.3)
    return closed


def wait_for_page(port, timeout_s=30.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        targets = devtools_targets(port)
        if targets and any(t.get("type") == "page" for t in targets):
            return True
        time.sleep(0.2)
    return False


def process_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def is_zombie(pid):
    """True when the PID is an already-exited process awaiting reaping."""
    try:
        out = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        return False
    return out.startswith("Z")


def daemon_process_count():
    try:
        out = subprocess.run(
            ["ps", "ax", "-o", "pid=,command="], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return -1
    return sum(1 for line in out.splitlines() if "browser_harness.daemon" in line)


def group_pids(pgid):
    try:
        out = subprocess.run(
            ["ps", "ax", "-o", "pid=,pgid="], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) == pgid:
            pids.append(int(parts[0]))
    return pids


class Workspace:
    def __init__(self):
        self.base = Path(tempfile.mkdtemp(prefix="jev-test-"))

    def profile(self, name="default"):
        path = self.base / "profiles" / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifacts(self, name):
        path = self.base / "artifacts" / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cleanup(self):
        shutil.rmtree(self.base, ignore_errors=True)


def test_login_twice_and_persistence(_runner):
    """Two headed logins on one profile. Zero model calls; markers persist."""
    workspace = Workspace()
    server, thread, base_url, state = fixture_server.start()
    profile = workspace.profile("login-test")
    try:
        for attempt in (1, 2):
            request = {
                "op": "login",
                "url": base_url,
                "profile_dir": str(profile),
                "artifact_dir": str(workspace.artifacts("login-%d" % attempt)),
                "timeout_ms": 90000,
                "run_id": "logintest%d" % attempt,
            }
            env = os.environ.copy()
            env.pop("OPENROUTER_API_KEY", None)  # login must need no credentials
            clear_devtools_port(profile)
            process = start_runner(request, env=env)
            port = devtools_port(profile)
            check("login%d.devtools_up" % attempt, port is not None)
            check("login%d.page_opened" % attempt, wait_for_page(port))
            time.sleep(1.5)  # let the fixture page run its script
            close_all_pages(port)
            payload, out, err = finish_runner(process, timeout_s=60)
            check("login%d.emitted_json" % attempt, payload is not None, out[:200])
            if payload is None:
                continue
            check("login%d.status_completed" % attempt, payload["status"] == "completed", str(payload.get("error")))
            check("login%d.no_screenshot" % attempt, payload["screenshot_path"] is None)
            check("login%d.authenticated_is_null" % attempt, payload["output"]["authenticated"] is None)
            check("login%d.cost_zero_no_calls" % attempt, payload["cost"] == 0.0 and payload["usage"] is None)
            check("login%d.exit_zero" % attempt, process.returncode == 0, str(process.returncode))
            check("login%d.profile_state_written" % attempt, payload["output"]["profile_state_written"] is True)
            check("login%d.clean_cleanup" % attempt, payload.get("cleanup_ok") is True)
        with urllib.request.urlopen(base_url + "state", timeout=5) as response:
            recorded = json.loads(response.read())
        check("login.visited_twice", recorded["visits"] >= 2, json.dumps(recorded))
        check("login.cookie_persisted", recorded["cookie_seen"] is True, json.dumps(recorded))
        check("login.storage_persisted", recorded["storage_seen"] is True, json.dumps(recorded))
    finally:
        fixture_server.stop(server, thread)
        workspace.cleanup()


def test_profile_contention_and_reuse(_runner):
    """A second runner on a busy profile must refuse, then succeed after release."""
    workspace = Workspace()
    server, thread, base_url, _state = fixture_server.start()
    profile = workspace.profile("contended")
    try:
        clear_devtools_port(profile)
        first = start_runner(
            {
                "op": "login",
                "url": base_url,
                "profile_dir": str(profile),
                "artifact_dir": str(workspace.artifacts("hold")),
                "timeout_ms": 60000,
                "run_id": "holder",
            },
            env={**os.environ, "OPENROUTER_API_KEY": ""},
        )
        port = devtools_port(profile)
        check("contention.first_started", port is not None and wait_for_page(port))
        second_payload, out, _err = finish_runner(
            start_runner(
                {
                    "op": "login",
                    "url": base_url,
                    "profile_dir": str(profile),
                    "artifact_dir": str(workspace.artifacts("blocked")),
                    "timeout_ms": 20000,
                    "run_id": "blocked",
                }
            ),
            timeout_s=30,
        )
        check("contention.second_refused", second_payload is not None and second_payload["status"] == "profile_busy",
              json.dumps(second_payload) if second_payload else out[:200])
        close_all_pages(port)
        first_payload, _out, _err = finish_runner(first, timeout_s=60)
        check("contention.first_completed", first_payload is not None and first_payload["status"] == "completed")
        third_payload, out, _err = finish_runner(
            start_runner(
                {
                    "op": "login",
                    "url": base_url,
                    "profile_dir": str(profile),
                    "artifact_dir": str(workspace.artifacts("reuse")),
                    "timeout_ms": 30000,
                    "run_id": "reuse",
                }
            ),
            timeout_s=45,
        )
        reused = third_payload is not None and third_payload["status"] != "profile_busy"
        check("contention.lock_released_after_cleanup", reused, json.dumps(third_payload) if third_payload else out[:200])
    finally:
        fixture_server.stop(server, thread)
        workspace.cleanup()


def test_cancel_and_forced_group_kill(_runner):
    """SIGTERM stops cleanly; a forced group kill leaves no owned survivors."""
    workspace = Workspace()
    server, thread, base_url, _state = fixture_server.start()
    try:
        baseline_daemons = daemon_process_count()
        profile = workspace.profile("cancel")
        clear_devtools_port(profile)
        process = start_runner(
            {
                "op": "login",
                "url": base_url,
                "profile_dir": str(profile),
                "artifact_dir": str(workspace.artifacts("cancel")),
                "timeout_ms": 60000,
                "run_id": "cancelme",
            }
        )
        port = devtools_port(profile)
        check("cancel.browser_up", port is not None and wait_for_page(port))
        pids = group_pids(os.getpgid(process.pid))
        process.send_signal(signal.SIGTERM)
        payload, out, _err = finish_runner(process, timeout_s=45)
        check("cancel.emitted_json", payload is not None, out[:200])
        if payload is not None:
            check("cancel.status_cancelled", payload["status"] == "cancelled", str(payload.get("status")))
            check("cancel.exit_zero", process.returncode == 0, str(process.returncode))
        survivors = [pid for pid in pids if process_alive(pid) and not is_zombie(pid)]
        check("cancel.no_owned_survivors", not survivors, str(survivors))

        profile2 = workspace.profile("forced")
        process2 = start_runner(
            {
                "op": "login",
                "url": base_url,
                "profile_dir": str(profile2),
                "artifact_dir": str(workspace.artifacts("forced")),
                "timeout_ms": 60000,
                "run_id": "forcedkill",
            }
        )
        port2 = devtools_port(profile2)
        check("forced.browser_up", port2 is not None and wait_for_page(port2))
        pgid = os.getpgid(process2.pid)
        tracked = group_pids(pgid)
        os.killpg(pgid, signal.SIGKILL)
        try:
            process2.wait(timeout=10)  # reap the killed runner so it is not a zombie
        except Exception:
            pass
        deadline = time.time() + 15
        while time.time() < deadline and any(
            process_alive(pid) and not is_zombie(pid) for pid in tracked
        ):
            time.sleep(0.2)
        survivors2 = [pid for pid in tracked if process_alive(pid) and not is_zombie(pid)]
        check("forced.group_kill_reaches_all_owned", not survivors2, str(survivors2))
        time.sleep(1.0)
        after = daemon_process_count()
        check("forced.no_detached_daemon_left", after <= baseline_daemons, "before=%d after=%d" % (baseline_daemons, after))
        try:
            process2.wait(timeout=5)
        except Exception:
            pass
    finally:
        fixture_server.stop(server, thread)
        workspace.cleanup()


def test_run_requires_credentials(_runner):
    """The run path needs a key; the failure is typed and leaks nothing."""
    workspace = Workspace()
    server, thread, base_url, _state = fixture_server.start()
    try:
        env = os.environ.copy()
        env.pop("OPENROUTER_API_KEY", None)
        payload, out, err = finish_runner(
            start_runner(
                {
                    "op": "run",
                    "task": "open the page",
                    "url": base_url,
                    "profile_dir": str(workspace.profile("nokey")),
                    "artifact_dir": str(workspace.artifacts("nokey")),
                    "timeout_ms": 30000,
                    "max_steps": 2,
                    "run_id": "nokey",
                },
                env=env,
            ),
            timeout_s=45,
        )
        check("nokey.emitted_json", payload is not None, out[:200])
        if payload is not None:
            check("nokey.status_credentials_error", payload["status"] == "credentials_error", str(payload.get("status")))
            check("nokey.cost_is_zero_no_calls", payload["cost"] == 0.0 or payload["cost"] is None)
            check("nokey.no_key_in_output", "sk-or-v1-" not in json.dumps(payload) and "sk-or-v1-" not in err)
    finally:
        fixture_server.stop(server, thread)
        workspace.cleanup()


def test_launch_guard(_runner):
    """Without its own process group the runner must refuse before any browser."""
    workspace = Workspace()
    server, thread, base_url, _state = fixture_server.start()
    profile = workspace.profile("noleader")
    try:
        payload, out, _err = finish_runner(
            start_runner(
                {
                    "op": "login",
                    "url": base_url,
                    "profile_dir": str(profile),
                    "artifact_dir": str(workspace.artifacts("noleader")),
                    "timeout_ms": 20000,
                    "run_id": "noleader",
                },
                new_session=False,
            ),
            timeout_s=30,
        )
        check("launch.emitted_json", payload is not None, out[:200])
        if payload is not None:
            check("launch.status_launch_error", payload["status"] == "launch_error", str(payload.get("status")))
            check("launch.explains_start_new_session", "start_new_session" in (payload.get("error") or ""))
        check("launch.no_browser_started", not (profile / "DevToolsActivePort").exists())
    finally:
        fixture_server.stop(server, thread)
        workspace.cleanup()


def test_clean_login_reports_clean_cleanup(_runner):
    """Regression: the cleanup scan must not count its own ps child."""
    workspace = Workspace()
    server, thread, base_url, _state = fixture_server.start()
    profile = workspace.profile("cleanup-regression")
    try:
        clear_devtools_port(profile)
        process = start_runner(
            {
                "op": "login",
                "url": base_url,
                "profile_dir": str(profile),
                "artifact_dir": str(workspace.artifacts("cleanup-regression")),
                "timeout_ms": 60000,
                "run_id": "cleanupregression",
            }
        )
        port = devtools_port(profile)
        check("cleanup.browser_up", port is not None and wait_for_page(port))
        close_all_pages(port)
        payload, out, _err = finish_runner(process, timeout_s=60)
        check("cleanup.emitted_json", payload is not None, out[:200])
        if payload is not None:
            check("cleanup.ok_true", payload.get("cleanup_ok") is True, json.dumps(payload.get("warnings")))
            check("cleanup.status_completed", payload["status"] == "completed", str(payload.get("error")))
            leftovers = [w for w in payload.get("warnings", []) if "still share" in w]
            check("cleanup.no_phantom_leftovers", not leftovers, str(leftovers))
    finally:
        fixture_server.stop(server, thread)
        workspace.cleanup()


# --------------------------------------------------------------------------
# checks group: declared DOM checks against real headless Chrome. No model
# call, no API key, no headed window, and nothing but the local fixture.
# --------------------------------------------------------------------------
PASSWORD_IN_FIXTURE = "fixture-password-never-read"
HIDDEN_IN_FIXTURE = "fixture-hidden-csrf-value"

CHECK_CASES = [
    # (id, check, expected status, expected reason)
    ("url_exact", {"kind": "url", "equals": "{base}checks"}, "passed", None),
    ("url_contains", {"kind": "url", "contains": "/checks"}, "passed", None),
    ("url_wrong", {"kind": "url", "equals": "https://example.test/"}, "failed", None),
    ("title_exact", {"kind": "title", "equals": "Jev checks fixture"}, "passed", None),
    ("title_contains", {"kind": "title", "contains": "checks"}, "passed", None),
    ("title_wrong", {"kind": "title", "contains": "Checkout"}, "failed", None),
    ("text_exact", {"kind": "text", "selector": "#heading", "equals": "Saved"}, "passed", None),
    ("text_contains", {"kind": "text", "selector": "#summary", "contains": "Order 4471"},
     "passed", None),
    ("text_wrong", {"kind": "text", "selector": "#heading", "equals": "saved"}, "failed", None),
    ("text_invisible", {"kind": "text", "selector": "#invisible", "equals": "Invisible text"},
     "unknown", "not_visible"),
    ("text_ambiguous", {"kind": "text", "selector": ".ambiguous", "equals": "first"},
     "unknown", "missing_or_ambiguous"),
    ("text_missing", {"kind": "text", "selector": "#nowhere", "equals": "x"},
     "unknown", "missing_or_ambiguous"),
    ("text_bad_selector", {"kind": "text", "selector": "h1[", "equals": "x"},
     "unknown", "unreadable_or_invalid_selector"),
    ("value_input", {"kind": "value", "selector": "#email", "equals": "dana@example.test"},
     "passed", None),
    ("value_textarea", {"kind": "value", "selector": "#note", "contains": "note line"},
     "passed", None),
    ("value_select", {"kind": "value", "selector": "#choice", "equals": "beta"}, "passed", None),
    ("value_editable", {"kind": "value", "selector": "#editable", "equals": "Editable text"},
     "passed", None),
    ("value_wrong", {"kind": "value", "selector": "#email", "equals": "someone@example.test"},
     "failed", None),
    ("value_password", {"kind": "value", "selector": "#secret", "equals": PASSWORD_IN_FIXTURE},
     "unknown", "sensitive_field"),
    ("text_password", {"kind": "text", "selector": "#secret", "contains": "fixture"},
     "unknown", "sensitive_field"),
    ("value_hidden", {"kind": "value", "selector": "#token", "equals": HIDDEN_IN_FIXTURE},
     "unknown", "hidden_field"),
    ("value_file", {"kind": "value", "selector": "#upload", "equals": ""},
     "unknown", "unsupported_control"),
    ("value_not_a_field", {"kind": "value", "selector": "#heading", "equals": "Saved"},
     "unknown", "not_a_field"),
    ("count_exact", {"kind": "count", "selector": ".row", "equals": 3}, "passed", None),
    ("count_wrong", {"kind": "count", "selector": ".row", "equals": 2}, "failed", None),
    ("count_zero", {"kind": "count", "selector": ".nothing-here", "equals": 0}, "passed", None),
    ("count_many", {"kind": "count", "selector": ".ambiguous", "equals": 2}, "passed", None),
    ("count_bad_selector", {"kind": "count", "selector": "*::", "equals": 1},
     "unknown", "unreadable_or_invalid_selector"),
]


def checks_environment(work, name, runtime_dir):
    """Private browser-harness identity for one headless Chrome.

    No provider key and no TYPESAFE/TEXT_MODEL variable is set: this group
    never reaches a model. runtime_dir is short and under /tmp for the same
    reason runner.run_operation uses one: the harness IPC socket lives there
    and an AF_UNIX path is limited to about 100 characters. Returns the
    previous values so the caller restores the test process's own environment.
    """
    wanted = {
        "BU_NAME": name,
        "BH_HOME": str(work / "harness"),
        "BH_RUNTIME_DIR": str(runtime_dir),
        "BH_TMP_DIR": str(work / "harness-tmp"),
        "BH_AGENT_WORKSPACE": str(work / "harness-workspace"),
        "BH_TELEMETRY": "0",
        "BROWSER_HARNESS_TELEMETRY": "0",
        "ANONYMIZED_TELEMETRY": "false",
        "DO_NOT_TRACK": "1",
    }
    previous = {key: os.environ.get(key) for key in
                list(wanted) + ["BU_CDP_URL", "BU_CDP_WS", "BU_BROWSER_ID"]}
    for key in ("BU_CDP_URL", "BU_CDP_WS", "BU_BROWSER_ID"):
        os.environ.pop(key, None)
    os.environ.update(wanted)
    return previous


def restore_environment(previous):
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def wait_for_ready(browser, timeout_s=10.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if browser.evaluate("document.readyState") == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def test_declared_checks_against_headless_chrome(runner):
    """The real thing: one headless Chrome, the local fixture, no model call."""
    contract = runner.dom_checks
    work = Path(tempfile.mkdtemp(prefix="jev-checks-browser-")).resolve()
    harness_runtime = Path(tempfile.mkdtemp(prefix="jv", dir="/tmp"))
    server, thread, base_url, _state = fixture_server.start()
    owned = runner.OwnedProcesses()
    previous = checks_environment(work, "jev-checks-" + work.name[-8:], harness_runtime)
    browser = None
    try:
        try:
            runner.chrome_binary()
        except Exception as exc:
            check("browser_checks.chrome_available", False, "%s: %s" % (type(exc).__name__, exc))
            return
        profile_dir = work / "profile"
        artifact_dir = work / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        port = runner.launch_chrome(profile_dir, artifact_dir, headless=True, owned=owned)
        os.environ["BU_CDP_URL"] = "http://127.0.0.1:%d" % port
        runner.start_private_daemon(owned, artifact_dir, os.environ["BU_NAME"])

        from jev_ultrafast.browser import Browser

        page_url = base_url + "checks"
        browser = Browser(page_url)
        check("browser_checks.page_loaded", wait_for_ready(browser))

        declared = []
        for name, body, _status, _reason in CHECK_CASES:
            item = {"id": name}
            for key, value in body.items():
                if key in ("equals", "contains") and isinstance(value, str):
                    value = value.replace("{base}", base_url)
                item[key] = value
            declared.append(item)
        # More cases than one call may declare, so they run in bounded batches.
        rows = {}
        batches = []
        for start in range(0, len(declared), contract.MAX_CHECKS):
            batch_checks = contract.normalize_checks(declared[start:start + contract.MAX_CHECKS])
            batches.append((batch_checks, runner.verify_declared_checks(browser, batch_checks)))
            rows.update({row["id"]: row for row in batches[-1][1]["checks"]})
        checks, payload = batches[0]

        check("browser_checks.one_row_per_check", len(rows) == len(CHECK_CASES))
        for name, _body, status, reason in CHECK_CASES:
            row = rows.get(name, {})
            check("browser_checks.%s.%s" % (name, status),
                  row.get("status") == status and (reason is None or row.get("reason") == reason),
                  "status=%r reason=%r" % (row.get("status"), row.get("reason")))
        check("browser_checks.summary_is_failed",
              all(batch["status"] == "failed" for _checks, batch in batches),
              json.dumps([batch["counts"] for _checks, batch in batches]))
        check("browser_checks.snapshot_url", payload["checked_at_url"] == page_url,
              str(payload["checked_at_url"]))
        check("browser_checks.snapshot_title", payload["checked_at_title"] == "Jev checks fixture")
        check("browser_checks.snapshot_is_one_read",
              payload["consistency"] == "single_synchronous_read"
              and isinstance(payload["captured_at_ms"], int)
              and all(row["captured_at_ms"] == payload["captured_at_ms"]
                      for row in payload["checks"]))
        check("browser_checks.scope_is_declared_only",
              payload["scope"] == "declared_dom_checks_only"
              and payload["declared"] == len(payload["checks"]))

        # The page holds both strings. They may appear in the result only
        # because these two cases declared them as expectations; no observed
        # evidence ever carries them back.
        observed = json.dumps([row["observed"] for _checks, batch in batches
                               for row in batch["checks"]])
        check("browser_checks.password_never_leaves_the_page",
              PASSWORD_IN_FIXTURE not in observed
              and "value" not in rows["value_password"]["observed"]
              and "value" not in rows["text_password"]["observed"])
        check("browser_checks.hidden_field_never_leaves_the_page",
              HIDDEN_IN_FIXTURE not in observed
              and "value" not in rows["value_hidden"]["observed"])
        check("browser_checks.observed_values_are_reported",
              rows["value_input"]["observed"]["value"] == "dana@example.test"
              and rows["count_exact"]["observed"]["value"] == 3)

        # Read-only in a real browser: no event fired and the DOM is unchanged.
        check("browser_checks.no_event_was_dispatched",
              browser.evaluate("window.__fixtureEvents") == 0)
        check("browser_checks.dom_is_unchanged",
              browser.evaluate("document.getElementById('email').value") == "dana@example.test"
              and browser.evaluate("document.querySelectorAll('.row').length") == 3)

        # The snapshot follows the document: checks are not atomic across a
        # navigation, and the payload says which URL it read.
        browser.call("Page.navigate", url=base_url + "checks?second=1")
        check("browser_checks.second_page_loaded", wait_for_ready(browser))
        after = runner.verify_declared_checks(browser, checks)
        check("browser_checks.navigation_moves_the_snapshot",
              after["checked_at_url"] == base_url + "checks?second=1"
              and {row["id"] for row in after["checks"] if row["status"] == "failed"}
              != {row["id"] for row in payload["checks"] if row["status"] == "failed"},
              str(after["checked_at_url"]))

        # A torn-down page reports unknown, never failed, and never raises.
        closed, browser = browser, None
        closed.close()
        gone = runner.verify_declared_checks(closed, checks)
        reasons = {row["reason"] for row in gone["checks"]}
        check("browser_checks.torn_down_page_is_unknown",
              gone["status"] == "unknown" and len(gone["checks"]) == len(checks)
              and reasons <= {"page_unavailable", "evidence_unavailable"},
              "%s %s" % (gone["status"], sorted(reasons)))
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        # Direct handles only: no process-group sweep from inside the test
        # process, which does not own this process group.
        owned.stop_daemon()
        owned.stop_chrome()
        fixture_server.stop(server, thread)
        restore_environment(previous)
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(harness_runtime, ignore_errors=True)


def test_declared_checks_through_a_real_runner_process(runner):
    """End to end through the runner process: no key, no browser, no model.

    Without OPENROUTER_API_KEY the run stops before Chrome starts, which is
    exactly the case where a declared check must be reported as unknown rather
    than silently dropped. The second request proves the runner re-validates
    the contract itself, in its own process, after the wrapper already has.
    """
    contract = runner.dom_checks
    work = Path(tempfile.mkdtemp(prefix="jev-checks-runner-")).resolve()
    try:
        env = os.environ.copy()
        for name in ("OPENROUTER_API_KEY", "TYPESAFE_API_KEY", "TEXT_MODEL_API_KEY"):
            env.pop(name, None)
        check("runner_process.no_key_is_set", not env.get("OPENROUTER_API_KEY"))
        artifacts = work / "artifacts"
        # The third declaration is credential-shaped on purpose: a synthetic
        # placeholder that the runner's own redaction would rewrite if it were
        # echoed back. It must not change the run's outcome.
        declared = [{"id": "landed", "kind": "url", "contains": "/done"},
                    {"id": "rows", "kind": "count", "selector": ".row", "equals": 3},
                    {"id": "auth", "kind": "text", "selector": "#s",
                     "contains": "Bearer YOUR_TOKEN_HERE"}]
        request = {
            "op": "run", "task": "do the thing", "url": "http://127.0.0.1:9/",
            "profile_dir": str(work / "profile"), "artifact_dir": str(artifacts),
            "max_steps": 1, "timeout_ms": 30000, "max_cost_usd": 0.01, "checks": declared,
        }
        payload, out, err = finish_runner(start_runner(request, env=env), timeout_s=120)
        check("runner_process.credentials_error",
              isinstance(payload, dict) and payload.get("status") == "credentials_error",
              str(payload)[:200] + err[-200:])
        verification = (payload or {}).get("verification") or {}
        check("runner_process.declared_checks_are_unknown",
              verification.get("status") == "unknown"
              and verification.get("declared") == 3
              and verification.get("scope") == "declared_dom_checks_only"
              and [row["reason"] for row in verification.get("checks", [])]
              == ["verification_not_attempted"] * 3,
              json.dumps(verification)[:300])
        expected = [contract.declaration_fingerprint(item)
                    for item in contract.normalize_checks(declared)]
        check("runner_process.rows_fingerprint_their_declarations",
              [row.get("fingerprint") for row in verification.get("checks", [])] == expected,
              json.dumps(verification.get("checks", []))[:300])
        check("runner_process.the_declaration_is_not_echoed_back",
              "Bearer YOUR_TOKEN_HERE" not in out
              and not [row for row in verification.get("checks", []) if "check" in row],
              out[-200:])
        check("runner_process.no_browser_started", not (artifacts / "chrome.log").exists())
        saved = json.loads((artifacts / "result.json").read_text())
        check("runner_process.result_json_carries_the_evidence",
              saved["verification"]["declared"] == 3
              and len(saved["verification"]["checks"]) == 3
              and "Bearer YOUR_TOKEN_HERE" not in json.dumps(saved))

        rejected = dict(request, artifact_dir=str(work / "artifacts-2"),
                        checks=[{"kind": "attribute", "selector": "a", "equals": "x"}])
        payload, _out, err = finish_runner(start_runner(rejected, env=env), timeout_s=120)
        check("runner_process.invalid_check_is_invalid_request",
              isinstance(payload, dict) and payload.get("status") == "invalid_request"
              and "checks[0].kind" in (payload.get("error") or ""),
              str(payload)[:200] + err[-200:])
    finally:
        shutil.rmtree(work, ignore_errors=True)


CHECKS_TESTS = [
    test_declared_checks_through_a_real_runner_process,
    test_declared_checks_against_headless_chrome,
]


# --------------------------------------------------------------------------
# guards group: the snapshot's own truncation and action-cap metadata, read
# from real headless Chrome. Same ownership rules as the checks group: a
# throwaway profile, a private browser-harness daemon, a loopback fixture, no
# model call, no API key, and never the user's own Chrome.
# --------------------------------------------------------------------------
TINY_TEXT_STYLE = "font-size:1px;line-height:1px;word-break:break-all;margin:0"


def set_body(browser, html):
    """Replace the fixture body. Read-only afterwards: only observe() runs."""
    browser.evaluate("document.body.innerHTML=" + json.dumps(html))


def test_snapshot_metadata_against_headless_chrome(runner):
    """text_truncated, omitted_actions and the viewport, measured in Chrome.

    The vendored snapshot decides these, so a Python-side guess is not
    evidence. This is the group that actually exercises snapshot.js.
    """
    work = Path(tempfile.mkdtemp(prefix="jev-guards-browser-")).resolve()
    harness_runtime = Path(tempfile.mkdtemp(prefix="jv", dir="/tmp"))
    server, thread, base_url, _state = fixture_server.start()
    owned = runner.OwnedProcesses()
    previous = checks_environment(work, "jev-guards-" + work.name[-8:], harness_runtime)
    daemons_before = daemon_process_count()
    browser = None
    chrome_pid = None
    try:
        try:
            runner.chrome_binary()
        except Exception as exc:
            check("snapshot.chrome_available", False, "%s: %s" % (type(exc).__name__, exc))
            return
        profile_dir = work / "profile"
        artifact_dir = work / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        port = runner.launch_chrome(profile_dir, artifact_dir, headless=True, owned=owned)
        chrome_pid = owned.chrome.pid
        os.environ["BU_CDP_URL"] = "http://127.0.0.1:%d" % port
        runner.start_private_daemon(owned, artifact_dir, os.environ["BU_NAME"])

        from jev_ultrafast.browser import Browser

        browser = Browser(base_url + "snapshot")
        check("snapshot.page_loaded", wait_for_ready(browser))

        page = browser.observe(screenshot=False)
        check("snapshot.flag_is_present_on_a_normal_page",
              page["text_truncated"] is False and page["omitted_actions"] == 0,
              json.dumps({k: page[k] for k in ("text_truncated", "omitted_actions")}))
        check("snapshot.viewport_is_w_and_h",
              page["w"] == 1120 and page["h"] == 780, json.dumps({"w": page["w"], "h": page["h"]}))
        observation = runner.observation_of(page)
        check("snapshot.observation_reads_the_real_snapshot",
              observation == {"omitted_actions": 0, "text_truncated": False,
                              "viewport": {"w": 1120, "h": 780},
                              "fingerprint": page["fingerprint"]},
              json.dumps(observation))

        cases = [
            ("twenty_characters", '<p style="%s">%s</p>' % (TINY_TEXT_STYLE, "a" * 20), False, 20),
            ("exactly_6000", '<p style="%s">%s</p>' % (TINY_TEXT_STYLE, "b" * 6000), False, 6000),
            ("over_6000", '<p style="%s">%s</p>' % (TINY_TEXT_STYLE, "c" * 7000), True, 6000),
            ("extra_node_after_the_cap",
             '<p style="%s">%s</p><p style="%s">more</p>'
             % (TINY_TEXT_STYLE, "d" * 6000, TINY_TEXT_STYLE), True, 6000),
            ("hidden_trailing_nodes",
             '<p style="%s">%s</p><p style="display:none">hidden trailing text</p>'
             '<p hidden>also hidden</p>' % (TINY_TEXT_STYLE, "e" * 6000), False, 6000),
            ("offscreen_trailing_node",
             '<p style="%s">%s</p><p style="position:absolute;top:4000px">below the fold</p>'
             % (TINY_TEXT_STYLE, "f" * 6000), False, 6000),
        ]
        for name, html, truncated, length in cases:
            set_body(browser, html)
            observed = browser.observe(screenshot=False)
            check("snapshot.%s.text_truncated_is_%s" % (name, str(truncated).lower()),
                  observed["text_truncated"] is truncated,
                  "%r len=%d" % (observed["text_truncated"], len(observed["text"])))
            check("snapshot.%s.text_length" % name, len(observed["text"]) == length,
                  str(len(observed["text"])))

        buttons = "".join(
            '<button class="g">%d</button>' % index for index in range(251)
        )
        set_body(browser,
                 '<style>button.g{position:absolute;width:14px;height:14px;padding:0;margin:0;'
                 'font-size:8px;border:0}button.g:nth-child(n){}</style>'
                 '<div style="position:relative;width:1000px;height:90px">%s</div>' % buttons)
        # Lay the controls out inside the 1120x780 viewport so every one of them
        # is a real in-view candidate, which is what the 250 cap counts.
        browser.evaluate(
            "document.querySelectorAll('button.g').forEach((b,i)=>{"
            "b.style.left=(16*(i%60))+'px'; b.style.top=(16*Math.floor(i/60))+'px';});"
        )
        capped = browser.observe(screenshot=False)
        element_actions = [a for a in capped["actions"] if str(a.get("id", "")).startswith("e")]
        waits = [a for a in capped["actions"] if a.get("id") == "wait"]
        scrolls = [a for a in capped["actions"] if a.get("kind") == "scroll"]
        check("snapshot.251_controls_report_one_omitted", capped["omitted_actions"] == 1,
              str(capped["omitted_actions"]))
        check("snapshot.action_list_is_capped_at_250", len(element_actions) == 250,
              str(len(element_actions)))
        check("snapshot.sentinels_are_outside_the_cap",
              len(waits) == 1 and len(capped["actions"]) == 250 + len(waits) + len(scrolls),
              json.dumps({"actions": len(capped["actions"]), "waits": len(waits),
                          "scrolls": len(scrolls)}))
        check("snapshot.omitted_actions_reach_the_observation",
              runner.observation_of(capped)["omitted_actions"] == 1)
        check("snapshot.truncation_does_not_hide_the_controls",
              all(action["id"] != "e251" for action in element_actions))
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        # Direct handles only: this test process does not own the process group.
        owned.stop_daemon()
        owned.stop_chrome()
        fixture_server.stop(server, thread)
        restore_environment(previous)
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(harness_runtime, ignore_errors=True)
    check("snapshot.owned_chrome_is_gone",
          chrome_pid is not None and not process_alive(chrome_pid), str(chrome_pid))
    check("snapshot.no_daemon_was_left_behind",
          daemon_process_count() <= daemons_before,
          "before=%d after=%d" % (daemons_before, daemon_process_count()))


GUARD_TESTS = [test_snapshot_metadata_against_headless_chrome]


BROWSER_TESTS = [
    test_launch_guard,
    test_clean_login_reports_clean_cleanup,
    test_profile_contention_and_reuse,
    test_cancel_and_forced_group_kill,
    test_run_requires_credentials,
]
LOGIN_TESTS = [test_login_twice_and_persistence]


def main():
    group = "unit"
    if "--group" in sys.argv:
        group = sys.argv[sys.argv.index("--group") + 1]
    for module in (RUNTIME / "runner.py", HERE / "fixture_server.py", HERE / "run_tests.py"):
        py_compile.compile(str(module), doraise=True)
    print("compiled runner and test modules")
    import runner as runner_module

    groups = {"unit": UNIT_TESTS, "checks": CHECKS_TESTS, "guards": GUARD_TESTS,
              "browser": BROWSER_TESTS, "login": LOGIN_TESTS}
    groups["all"] = UNIT_TESTS + CHECKS_TESTS + GUARD_TESTS + BROWSER_TESTS + LOGIN_TESTS
    selected = groups.get(group)
    if selected is None:
        print("unknown group %r" % group)
        return 2
    started = time.time()
    for test in selected:
        print("--- %s" % test.__name__)
        try:
            test(runner_module)
        except Exception as exc:
            check(test.__name__ + ".crashed", False, "%s: %s" % (type(exc).__name__, exc))
            import traceback

            traceback.print_exc()
    failed = [name for name, ok, _ in RESULTS if not ok]
    print("\n%d checks, %d failed, %.1fs" % (len(RESULTS), len(failed), time.time() - started))
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
