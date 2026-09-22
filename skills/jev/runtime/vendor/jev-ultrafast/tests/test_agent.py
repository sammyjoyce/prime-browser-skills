"""Offline contracts for a dynamic operation/target policy. No paid APIs."""

import json
import time
from copy import deepcopy
from unittest.mock import Mock

import pytest

from jev_ultrafast import agent as loop
from jev_ultrafast import model
from jev_ultrafast.agent import NeedsReview
from jev_ultrafast.browser import StalePage, browser_operation, fingerprint


def page():
    state = {
        "url": "https://example.test/",
        "title": "Search",
        "text": "Search",
        "scroll": {"y": 0},
        "actions": [
            {"id": "e1", "kind": "fill", "label": "Search", "role": "textbox", "value": "", "node": 10},
            {"id": "e2", "kind": "click", "label": "Open Search", "role": "textbox", "value": "", "node": 10},
            {"id": "e3", "kind": "click", "label": "Go", "role": "button", "value": "", "node": 20},
            {"id": "wait", "kind": "wait", "label": "Wait"},
        ],
    }
    state["fingerprint"] = fingerprint(state)
    return state


def form_page(url="https://example.test/checkout", origin=1000.5):
    """Two fields no label can tell apart, in one identified document."""
    state = {
        "url": url,
        "title": "Checkout",
        "text": "Checkout",
        "scroll": {"y": 0},
        "actions": [
            {"id": "e1", "kind": "fill", "label": "First name", "role": "textbox", "value": "", "node": 10},
            {"id": "e2", "kind": "fill", "label": "First name", "role": "textbox", "value": "", "node": 40},
            {"id": "wait", "kind": "wait", "label": "Wait"},
        ],
        # page_key[0] is the document's time origin, exactly as snapshot.js reports it.
        "page_key": [origin, url, 0, 0, 1120, 780, []],
    }
    state["fingerprint"] = fingerprint(state)
    return state


def choice(ids, selected):
    return {"choice": selected, "confidence": 1.0, "probabilities": {i: float(i == selected) for i in ids}}


def decision(action="e1", *, confidence=1.0, target_confidence=None, operation=None, target=None):
    spec = {
        "e1": ("TYPE_TEXT", "1"),
        "e2": ("CLICK", "1"),
        "e3": ("CLICK", "2"),
        "wait": ("WAIT", None),
        "DONE": ("DONE", None),
        "BLOCKED": ("BLOCKED", None),
    }
    inferred_operation, inferred_target = spec.get(action, ("CLICK", "1"))
    operation = inferred_operation if operation is None else operation
    target = inferred_target if target is None else target
    if target_confidence is None:
        target_confidence = None if target is None else 1.0
    return {
        "choice": action,
        "operation": operation,
        "target": target,
        "confidence": confidence,
        "target_confidence": target_confidence,
        "probabilities": {action: 1.0},
        "latency_ms": 10,
        "usage": {},
    }


@pytest.mark.parametrize("mutation", ["unknown", "nan", "missing", "negative", "non_max", "confidence"])
def test_invalid_choice_is_rejected(mutation):
    a = choice(["a", "b"], "a")
    if mutation == "unknown":
        a["choice"] = "invented"
    elif mutation == "nan":
        a["probabilities"]["a"] = float("nan")
    elif mutation == "missing":
        del a["probabilities"]["b"]
    elif mutation == "negative":
        a["probabilities"]["b"] = -1
    elif mutation == "non_max":
        a["choice"] = "b"
    else:
        a["confidence"] = 5
    with pytest.raises(ValueError, match="Invalid TypeSafe"):
        model.validate_choice(a, {"a", "b"})


def test_one_index_per_node_with_operation_specific_targets():
    elements, targets, controls = model.action_space(page()["actions"])
    assert len(elements) == 2
    assert elements[0]["operations"] == ["TYPE_TEXT", "CLICK"]
    assert targets["TYPE_TEXT"]["1"]["id"] == "e1"
    assert targets["CLICK"]["1"]["id"] == "e2"
    assert targets["CLICK"]["2"]["id"] == "e3"
    assert "WAIT" in controls


def test_all_heads_are_one_request_and_only_matching_head_executes(monkeypatch):
    calls = []

    def post(_url, _key, body):
        calls.append(body)
        return {
            "model": "test",
            "answers": {
                "operation": choice(body["questions"]["operation"]["criteria"], "TYPE_TEXT"),
                "type_text_target": choice(["1"], "1"),
                "click_target": {"choice": "invented"},
            },
        }

    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(model, "post_json", post)
    d = model.choose(page(), "Find a book", [])
    assert len(calls) == 1
    assert d["operation"] == "TYPE_TEXT" and d["target"] == "1" and d["choice"] == "e1"
    assert set(calls[0]["questions"]) == {"operation", "click_target", "type_text_target"}


def test_choose_sets_a_target_for_click_and_none_for_wait(monkeypatch):
    """choose() still always binds a target when the operation has one."""

    def post_for(operation, target=None):
        def post(_url, _key, body):
            questions = body["questions"]
            answers = {"operation": choice(questions["operation"]["criteria"], operation)}
            if operation == "CLICK":
                answers["click_target"] = choice(questions["click_target"]["criteria"], target)
            return {"model": "test", "answers": answers}
        return post

    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(model, "post_json", post_for("CLICK", "2"))
    clicked = model.choose(page(), "Find a book", [])
    assert clicked["operation"] == "CLICK" and clicked["target"] == "2" and clicked["choice"] == "e3"
    monkeypatch.setattr(model, "post_json", post_for("WAIT"))
    waited = model.choose(page(), "Find a book", [])
    assert waited["operation"] == "WAIT" and waited["target"] is None and waited["choice"] == "wait"


def test_click_cannot_consume_a_text_target(monkeypatch):
    def post(_url, _key, body):
        return {
            "model": "test",
            "answers": {
                "operation": choice(body["questions"]["operation"]["criteria"], "CLICK"),
                "type_text_target": choice(["1"], "1"),
                "click_target": choice(["1", "2", "999"], "999"),
            },
        }

    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(model, "post_json", post)
    with pytest.raises(ValueError, match="Invalid TypeSafe"):
        model.choose(page(), "Find a book", [])


def test_target_head_receives_control_state_and_full_next_step_rules(monkeypatch):
    p = page()
    p["actions"].insert(0, {
        "id": "toggle", "kind": "click", "label": "Free cancellation", "node": 30,
        "role": "checkbox", "checked": "true", "selected": False,
    })

    def post(_url, _key, body):
        questions = body["questions"]
        target = questions["click_target"]
        assert target["criteria"]["1"]["checked"] == "true"
        assert target["criteria"]["1"]["selected"] is False
        assert questions["operation"]["instructions"]["rules"] in target["instructions"]["rules"]
        return {
            "model": "test",
            "answers": {
                "operation": choice(questions["operation"]["criteria"], "CLICK"),
                "click_target": choice(target["criteria"], "3"),
            },
        }

    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(model, "post_json", post)
    d = model.choose(p, "Search with free cancellation", [])
    assert d["choice"] == "e3"


def test_quoted_task_text_still_uses_the_llm(monkeypatch):
    monkeypatch.setenv("TEXT_MODEL_API_KEY", "test")
    post = Mock(return_value={"choices": [{"message": {"content": '{"text":"Zurich"}'}}]})
    monkeypatch.setattr(model, "post_json", post)
    context = model.field_context('Fly from "Zurich" to London', page()["actions"][0], page(), [])
    assert model.field_text(context)[0] == "Zurich"
    assert post.call_count == 1
    sent = json.loads(post.call_args.args[2]["messages"][1]["content"])
    assert sent["goal"] == 'Fly from "Zurich" to London'


def test_missing_text_credential_stops_before_guessing(monkeypatch):
    monkeypatch.delenv("TEXT_MODEL_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TEXT_MODEL_API_KEY"):
        model.field_text({"goal": 'Enter "Zurich"'})


@pytest.fixture
def runner():
    a = loop.Agent.__new__(loop.Agent)
    a.screenshots = False
    a.pending_text = None
    a.values = {}
    a.generation = "helper"
    a.confidence = None
    a.budget_guard = None
    a.checks = None
    p = page()
    a.state = {
        "browser": Mock(fresh=Mock(return_value=True), observe=Mock(return_value=p)),
        "page": p,
        "decision": decision(),
        "goal": "Find a book",
        "history": [],
        "decisions": [],
        "status": "predicted",
        "started_at": time.perf_counter(),
        "record": False,
        "text_calls": [],
        "bind_calls": [],
        "provisional_done": False,
    }
    return a


def binding(key):
    """What a mocked bind_value returns: a supplied key, or None for NONE."""
    return {
        "key": key,
        "confidence": 1.0,
        "probabilities": {"city": 1.0},
        "usage": {},
        "latency_ms": 7,
        "model": "test",
        "request": {"questions": {}},
    }


def act(runner):
    return runner.command("act", {"fingerprint": runner.state["page"]["fingerprint"]})


def test_stale_decision_is_consumed_before_any_mutation(runner):
    runner.state["browser"].fresh.return_value = False
    with pytest.raises(StalePage):
        runner.command("act", {"fingerprint": runner.state["page"]["fingerprint"]})
    runner.state["browser"].act.assert_not_called()
    assert runner.state["decision"] is None


def test_generated_text_reused_only_for_identical_retry_context(runner, monkeypatch):
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "field_text", helper)
    runner.state["browser"].act.side_effect = [StalePage("Changed before input"), None]
    with pytest.raises(StalePage):
        runner.command("act", {"fingerprint": runner.state["page"]["fingerprint"]})
    runner.state["decision"] = decision()
    runner.command("act", {"fingerprint": runner.state["page"]["fingerprint"]})
    assert helper.call_count == 1
    assert runner.state["browser"].act.call_count == 2  # The first call rejects before any browser input.
    assert runner.pending_text is None


def test_changed_field_context_does_not_reuse_generated_text(runner, monkeypatch):
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "field_text", helper)
    runner.state["browser"].act.side_effect = [StalePage("Changed before input"), None]
    with pytest.raises(StalePage):
        runner.command("act", {"fingerprint": runner.state["page"]["fingerprint"]})
    runner.state["page"]["text"] = "Different page context"
    runner.state["decision"] = decision()
    runner.command("act", {"fingerprint": runner.state["page"]["fingerprint"]})
    assert helper.call_count == 2


def test_loading_waits_do_not_trigger_no_progress_stop(runner):
    for _ in range(5):
        runner.state["decision"] = decision("wait")
        runner.command("act", {"fingerprint": runner.state["page"]["fingerprint"]})
    assert len(runner.state["history"]) == 5 and runner.state["status"] == "ready"


def test_stale_observation_preserves_executed_action(runner):
    runner.state["decision"] = decision("e3")
    runner.state["browser"].observe.side_effect = StalePage("changed")
    with pytest.raises(NeedsReview) as caught:
        runner.command("act", {"fingerprint": runner.state["page"]["fingerprint"]})
    assert caught.value.reason == "stale_after_input"
    assert caught.value.input_dispatched == "attempted"
    entry = runner.state["history"][-1]
    assert entry["action"] == "Go"
    assert entry["dispatch"] == "attempted"
    assert runner.state["status"] == "needs_review"
    runner.state["browser"].act.assert_called_once()


def test_observation_is_one_atomic_browser_read(monkeypatch):
    import jev_ultrafast.browser as browser

    p = page()
    cdp = Mock(return_value={"result": {"value": p}})
    monkeypatch.setattr(browser, "cdp", cdp)
    actual = browser_operation({"operation": "observe", "session": "test", "screenshot": False})
    assert actual["actions"] == p["actions"]
    assert cdp.call_count == 1
    assert cdp.call_args.args[0] == "Runtime.evaluate"


def test_executor_rejects_a_stale_page_before_browser_input(monkeypatch):
    import jev_ultrafast.browser as browser

    b = browser.Browser.__new__(browser.Browser)
    b.fresh = Mock(return_value=False)
    operation = Mock()
    monkeypatch.setattr(browser, "browser_operation", operation)
    with pytest.raises(StalePage):
        b.act(page()["actions"][0], page(), "book")
    operation.assert_not_called()


@pytest.mark.parametrize("response", [{"exceptionDetails": {}}, {"result": {}}])
def test_interrupted_dropdown_mutation_cannot_be_retried_as_stale(monkeypatch, response):
    import jev_ultrafast.browser as browser

    # A navigation can destroy the evaluation result after the change event already fired.
    if "exceptionDetails" in response:
        response["exceptionDetails"] = {"text": "Execution context destroyed"}
    cdp = Mock(return_value=response)
    monkeypatch.setattr(browser, "cdp", cdp)
    with pytest.raises(RuntimeError, match="Dropdown execution"):
        browser_operation({"operation": "act", "session": "test", "action": {
            "id": "e1", "kind": "select", "node": 1, "value": "Design",
        }})
    assert cdp.call_count == 1


def test_fingerprint_tracks_values_and_identity_not_screenshots():
    p = page()
    other = deepcopy(p)
    other["screenshot"] = "changed"
    assert fingerprint(p) == fingerprint(other)
    other["actions"][0]["node"] = 99
    assert fingerprint(p) != fingerprint(other)


@pytest.mark.parametrize("changed", ["Departure", "Where from?", "Where to?", "year"])
def test_flight_verification_rejects_wrong_trip(changed):
    from examples.flights import verify

    actual = {
        "url": "https://www.google.com/travel/flights/search?tfs=example",
        "text": "Track prices from Zürich to London departing 2026-09-20",
        "actions": [
            {"label": k, "value": v}
            for k, v in [
                ("Change ticket type. One way", "One way"),
                ("Where from?", "Zürich"),
                ("Where to?", "London"),
                ("Departure", "Sun, Sep 20"),
                ("Nonstop flight on Sunday, September 20. Select flight", ""),
            ]
        ],
    }
    assert verify(actual)["passed"]
    if changed == "year":
        actual["text"] = actual["text"].replace("2026", "2027")
    else:
        next(a for a in actual["actions"] if a["label"] == changed)["value"] = "wrong"
    assert not verify(actual)["passed"]


@pytest.mark.parametrize(
    "content",
    ["Thinking: Zurich", '{"text":"Zurich","extra":true}', '{"text":123}', '{"text":"  "}', '{"value":"Zurich"}'],
)
def test_text_helper_rejects_invalid_values(monkeypatch, content):
    monkeypatch.setenv("TEXT_MODEL_API_KEY", "test")
    monkeypatch.setattr(model, "post_json", Mock(return_value={"choices": [{"message": {"content": content}}]}))
    with pytest.raises(ValueError, match="nothing typed"):
        model.field_text({"goal": "Find a flight"})


def test_text_helper_null_is_a_valid_no_value_answer(monkeypatch):
    """{"text": null} is the documented answer for a missing value, not a broken response."""
    monkeypatch.setenv("TEXT_MODEL_API_KEY", "test")
    monkeypatch.setattr(
        model, "post_json", Mock(return_value={"choices": [{"message": {"content": '{"text":null}'}}]})
    )
    text, helper = model.field_text({"goal": "Find a flight"})
    assert text is None
    assert helper["model"] and helper["latency_ms"] >= 0


def test_navigation_during_prediction_reobserves_without_action(runner):
    runner.state["browser"].fresh.side_effect = StalePage("Document navigating")
    runner.command("tick")
    assert runner.state["status"] == "ready"
    assert runner.state["decision"] is None
    runner.state["browser"].act.assert_not_called()


# --- Supplied values: exact binding, clearing and skipping ---------------------


def test_choose_offers_supplied_values_and_leaves_the_unbound_request_alone(monkeypatch):
    bodies = []

    def post(_url, _key, body):
        bodies.append(body)
        return {
            "model": "test",
            "answers": {
                "operation": choice(body["questions"]["operation"]["criteria"], "TYPE_TEXT"),
                "type_text_target": choice(["1"], "1"),
            },
        }

    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(model, "post_json", post)
    model.choose(page(), "Book a room", [])
    model.choose(page(), "Book a room", [], values={"city": "Z" * 200, "note": "hi"})
    plain, bound = bodies
    expected_observation = {"omitted_actions": 0, "text_truncated": False, "viewport": {"w": None, "h": None}}
    assert "supplied_values" not in plain["state"]
    assert bound["state"]["supplied_values"] == {"city": "Z" * 80, "note": "hi"}
    assert "A small LLM will supply" in plain["questions"]["operation"]["criteria"]["TYPE_TEXT"]
    assert "A supplied value" in bound["questions"]["operation"]["criteria"]["TYPE_TEXT"]
    assert plain["state"]["page"] == bound["state"]["page"]
    assert plain["state"]["elements"] == bound["state"]["elements"]
    assert plain["state"]["observation"] == bound["state"]["observation"] == expected_observation


def test_bind_value_offers_every_supplied_key_plus_none(monkeypatch):
    bodies = []

    def post(_url, _key, body):
        bodies.append(body)
        return {"model": "test", "answers": {"value": choice(body["questions"]["value"]["criteria"], "city")}}

    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setenv("TYPESAFE_MODEL", "jev-test")
    monkeypatch.setattr(model, "post_json", post)
    p = page()
    p["text"] = "x" * 9000
    long_value = "Z\u00fcrich " + "!" * 200
    history = [{"action": "Search", "text": "book", "kind": "fill", "page_changed": True}]
    answer = model.bind_value("Find a book", p["actions"][0], p, history, {"city": long_value, "note": ""})
    body = bodies[0]
    question = body["questions"]["value"]
    assert set(question["criteria"]) == {"city", "note", "NONE"}
    assert question["criteria"]["city"] == {"key": "city", "preview": long_value[:80]}
    assert question["criteria"]["NONE"] == "No supplied value belongs in this field."
    assert question["type"] == "choice"
    assert question["instructions"]["goal"] == "Find a book"
    assert question["instructions"]["field"] == {"label": "Search", "role": "textbox", "value": ""}
    assert question["instructions"]["rules"] == model.BIND_VALUE
    assert body["model"] == "jev-test"
    assert len(body["state"]["page"]["text"]) == 6000
    assert body["state"]["page"]["url"] == "https://example.test/"
    assert body["state"]["observation"] == {
        "omitted_actions": 0,
        "text_truncated": False,
        "viewport": {"w": None, "h": None},
    }
    assert "supplied_values" not in body["state"]
    assert long_value not in json.dumps(body)
    assert body["state"]["recent_actions"] == [{"action": "Search", "text": "book"}]
    assert answer["key"] == "city"
    assert answer["model"] == "test" and answer["latency_ms"] >= 0


def test_bind_value_reports_none_and_rejects_an_invented_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    p = page()
    none = {"model": "t", "answers": {"value": choice(["city", "NONE"], "NONE")}}
    monkeypatch.setattr(model, "post_json", Mock(return_value=none))
    assert model.bind_value("g", p["actions"][0], p, [], {"city": "Zurich"})["key"] is None
    invented = {"model": "t", "answers": {"value": choice(["city", "NONE", "invented"], "invented")}}
    monkeypatch.setattr(model, "post_json", Mock(return_value=invented))
    with pytest.raises(ValueError, match="Invalid TypeSafe"):
        model.bind_value("g", p["actions"][0], p, [], {"city": "Zurich"})


@pytest.mark.parametrize(
    "value",
    ["Ends with a period.", "trailing space ", "Z\u00fcrich Hauptbahnhof", "two\nlines", "   ", "x" * 2000],
)
def test_supplied_value_is_typed_byte_for_byte(runner, monkeypatch, value):
    monkeypatch.setattr(loop, "bind_value", Mock(return_value=binding("city")))
    helper = Mock()
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": value}
    runner.generation = "disabled"
    act(runner)
    assert runner.state["browser"].act.call_args.kwargs["text"] == value
    helper.assert_not_called()
    entry = runner.state["history"][-1]
    assert (entry["value_key"], entry["value_source"], entry["text"]) == ("city", "supplied", value)
    assert entry["note"] is None


def test_supplied_empty_value_clears_the_field_without_the_helper(runner, monkeypatch):
    monkeypatch.setattr(loop, "bind_value", Mock(return_value=binding("city")))
    helper = Mock()
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": ""}
    act(runner)  # generation is "helper": an empty supplied value is still a value
    assert runner.state["browser"].act.call_args.kwargs["text"] == ""
    helper.assert_not_called()
    entry = runner.state["history"][-1]
    assert (entry["value_key"], entry["value_source"]) == ("city", "supplied")


def test_bind_metadata_is_recorded_without_the_value(runner, monkeypatch):
    secret = "417 Sunset Road, Apt 9"
    monkeypatch.setattr(loop, "bind_value", Mock(return_value=binding("address")))
    runner.values = {"address": secret}
    runner.generation = "disabled"
    act(runner)
    recorded = runner.state["bind_calls"]
    assert len(recorded) == 1
    assert recorded[0]["key"] == "address" and recorded[0]["field"] == "Search"
    assert "request" not in recorded[0]
    assert secret not in json.dumps(recorded)
    assert runner.state["text_calls"] == []


def test_no_supplied_values_means_no_bind_call(runner, monkeypatch):
    binder = Mock()
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "field_text", Mock(return_value=("book", {"model": "test", "latency_ms": 10})))
    act(runner)
    binder.assert_not_called()
    assert runner.state["bind_calls"] == []
    entry = runner.state["history"][-1]
    assert (entry["value_key"], entry["value_source"]) == (None, "helper")


def test_unbound_field_with_generation_disabled_is_skipped(runner, monkeypatch):
    monkeypatch.setattr(loop, "bind_value", Mock(return_value=binding(None)))
    helper = Mock()
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}
    runner.generation = "disabled"
    act(runner)
    helper.assert_not_called()
    runner.state["browser"].act.assert_not_called()
    runner.state["browser"].observe.assert_called_once()  # the page is still observed
    entry = runner.state["history"][-1]
    assert entry["kind"] == "fill" and entry["text"] is None
    assert (entry["value_key"], entry["value_source"]) == (None, "skipped")
    assert entry["page_changed"] is False
    assert entry["note"] == "no value bound to this field; nothing typed"
    assert runner.state["status"] == "ready"


def test_unbound_field_with_generation_helper_uses_the_helper(runner, monkeypatch):
    monkeypatch.setattr(loop, "bind_value", Mock(return_value=binding(None)))
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}
    act(runner)
    assert helper.call_count == 1
    assert runner.state["browser"].act.call_args.kwargs["text"] == "book"
    entry = runner.state["history"][-1]
    assert (entry["value_key"], entry["value_source"]) == (None, "helper")
    assert runner.state["bind_calls"][0]["key"] is None


def test_helper_without_a_value_skips_instead_of_ending_the_run(runner, monkeypatch):
    helper = Mock(return_value=(None, {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "field_text", helper)
    act(runner)
    runner.state["browser"].act.assert_not_called()
    entry = runner.state["history"][-1]
    assert (entry["text"], entry["value_source"]) == (None, "skipped")
    assert runner.state["text_calls"][0]["value"] is None
    assert runner.state["status"] == "ready"


def test_three_skipped_fields_stop_the_run(runner, monkeypatch):
    monkeypatch.setattr(loop, "bind_value", Mock(return_value=binding(None)))
    runner.values = {"city": "Zurich"}
    runner.generation = "disabled"
    observed = []
    for index in range(3):
        p = page()
        p["text"] = f"Page {index}"
        p["fingerprint"] = fingerprint(p)
        observed.append(p)
    runner.state["browser"].observe.side_effect = observed
    for _ in range(3):
        runner.state["decision"] = decision()
        act(runner)
    # Each observation differs, so only the skip itself can hold page_changed False.
    assert [h["page_changed"] for h in runner.state["history"]] == [False, False, False]
    assert [h["value_source"] for h in runner.state["history"]] == ["skipped"] * 3
    assert runner.state["browser"].act.call_count == 0
    assert runner.state["status"] == "blocked"


def test_stale_retry_reuses_the_binding_without_a_second_bind_call(runner, monkeypatch):
    binder = Mock(return_value=binding("city"))
    monkeypatch.setattr(loop, "bind_value", binder)
    helper = Mock()
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}
    runner.generation = "disabled"
    runner.state["browser"].act.side_effect = [StalePage("Changed before input"), None]
    with pytest.raises(StalePage):
        act(runner)
    runner.state["decision"] = decision()
    act(runner)
    assert binder.call_count == 1
    helper.assert_not_called()
    assert runner.state["browser"].act.call_count == 2
    assert runner.state["browser"].act.call_args.kwargs["text"] == "Zurich"
    assert runner.pending_text is None


def test_stale_retry_does_not_reuse_a_binding_on_another_field(runner, monkeypatch):
    """Two fields carry one label. The retry must bind the field it actually selected."""
    keys = {10: "billing_first", 40: "shipping_first"}
    binder = Mock(side_effect=lambda goal, action, page, history, values: binding(keys[action["node"]]))
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "choose", Mock(side_effect=[decision("e1"), decision("e2")]))
    helper = Mock()
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"billing_first": "Ada ", "shipping_first": "Gr\u00e2ce"}
    runner.generation = "disabled"
    runner.state.update(page=form_page(), decision=None, status="ready")
    runner.state["browser"].observe.return_value = form_page()
    runner.state["browser"].act.side_effect = [StalePage("Changed before input"), None]
    runner.command("tick")  # binds billing_first for e1; the page changes before any input
    runner.command("tick")  # the new decision selects the other field with the same label
    assert binder.call_count == 2
    assert [c.args[1]["node"] for c in binder.call_args_list] == [10, 40]
    assert runner.state["browser"].act.call_args.kwargs["text"] == "Gr\u00e2ce"
    entry = runner.state["history"][-1]
    assert (entry["value_key"], entry["value_source"]) == ("shipping_first", "supplied")
    helper.assert_not_called()


def test_stale_retry_does_not_reuse_a_binding_from_another_url(runner, monkeypatch):
    binder = Mock(return_value=binding("code"))
    monkeypatch.setattr(loop, "bind_value", binder)
    runner.values = {"code": "ALPHA"}
    runner.generation = "disabled"
    first, second = form_page(), form_page(url="https://example.test/checkout?step=2")
    # Same label, same value, same page text: only the address moved on.
    assert model.field_context("Find a book", first["actions"][0], first, []) == model.field_context(
        "Find a book", second["actions"][0], second, []
    )
    runner.state.update(page=first, decision=decision("e1"))
    runner.state["browser"].act.side_effect = [StalePage("Changed before input"), None]
    with pytest.raises(StalePage):
        act(runner)
    runner.state.update(page=second, decision=decision("e1"))
    act(runner)
    assert binder.call_count == 2
    assert [c.args[2]["url"] for c in binder.call_args_list] == [first["url"], second["url"]]


def test_stale_retry_does_not_reuse_a_binding_across_documents_at_one_url(runner, monkeypatch):
    """A reload at the same URL renumbers nodes from scratch, so the node alone proves nothing."""
    binder = Mock(return_value=binding("code"))
    monkeypatch.setattr(loop, "bind_value", binder)
    runner.values = {"code": "ALPHA"}
    runner.generation = "disabled"
    first, second = form_page(origin=1000.5), form_page(origin=2000.5)
    assert first["fingerprint"] == second["fingerprint"]  # url, text, actions and scroll all match
    runner.state.update(page=first, decision=decision("e1"))
    runner.state["browser"].act.side_effect = [StalePage("Changed before input"), None]
    with pytest.raises(StalePage):
        act(runner)
    runner.state.update(page=second, decision=decision("e1"))
    act(runner)
    assert binder.call_count == 2


def test_stale_retry_reuses_the_binding_for_the_same_field_and_document(runner, monkeypatch):
    """A re-observation of the same field in the same document still costs one bind."""
    binder = Mock(return_value=binding("code"))
    monkeypatch.setattr(loop, "bind_value", binder)
    helper = Mock()
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"code": "ALPHA "}
    runner.generation = "disabled"
    runner.state.update(page=form_page(), decision=decision("e1"))
    runner.state["browser"].act.side_effect = [StalePage("Changed before input"), None]
    with pytest.raises(StalePage):
        act(runner)
    runner.state.update(page=form_page(), decision=decision("e1"))  # observed again, same document
    act(runner)
    assert binder.call_count == 1
    helper.assert_not_called()
    assert runner.state["browser"].act.call_args.kwargs["text"] == "ALPHA "
    assert runner.pending_text is None


def test_stale_retry_does_not_reuse_generated_text_on_another_field(runner, monkeypatch):
    helper = Mock(side_effect=[("Ada ", {"model": "test", "latency_ms": 10}),
                               ("Gr\u00e2ce", {"model": "test", "latency_ms": 10})])
    monkeypatch.setattr(loop, "field_text", helper)
    binder = Mock()
    monkeypatch.setattr(loop, "bind_value", binder)
    runner.state.update(page=form_page(), decision=decision("e1"))
    runner.state["browser"].act.side_effect = [StalePage("Changed before input"), None]
    with pytest.raises(StalePage):
        act(runner)
    runner.state.update(page=form_page(), decision=decision("e2"))
    act(runner)
    assert helper.call_count == 2
    assert runner.state["browser"].act.call_args.kwargs["text"] == "Gr\u00e2ce"
    assert runner.state["history"][-1]["value_source"] == "helper"
    binder.assert_not_called()


def cdp_recorder(calls, target=None):
    def cdp(method, session_id=None, **params):
        calls.append((method, params))
        if method == "Runtime.evaluate":
            return {"result": {"value": target if target is not None else {"x": 5.0, "y": 6.0}}}
        return {}

    return cdp


def test_empty_text_clears_with_a_delete_key_not_an_empty_insert(monkeypatch):
    import jev_ultrafast.browser as browser

    calls = []
    monkeypatch.setattr(browser, "cdp", cdp_recorder(calls))
    browser_operation({"operation": "act", "session": "test", "action": page()["actions"][0], "text": ""})
    assert not [method for method, _ in calls if method == "Input.insertText"]
    keys = [params for method, params in calls if method == "Input.dispatchKeyEvent"]
    assert [k["key"] for k in keys] == ["a", "a", "Delete", "Delete"]
    assert [k["type"] for k in keys[-2:]] == ["keyDown", "keyUp"]
    assert [k["code"] for k in keys[-2:]] == ["Delete", "Delete"]


def test_non_empty_text_is_still_inserted_verbatim(monkeypatch):
    import jev_ultrafast.browser as browser

    calls = []
    monkeypatch.setattr(browser, "cdp", cdp_recorder(calls))
    browser_operation({"operation": "act", "session": "test", "action": page()["actions"][0], "text": " Z\u00fcrich. "})
    inserted = [params["text"] for method, params in calls if method == "Input.insertText"]
    assert inserted == [" Z\u00fcrich. "]
    assert [k["key"] for method, k in calls if method == "Input.dispatchKeyEvent"] == ["a", "a"]


# --- Observation metadata on decision and bind requests -----------------------


def test_choose_observation_defaults_when_snapshot_keys_are_missing(monkeypatch):
    captured = []

    def post(_url, _key, body):
        captured.append(body)
        return {
            "model": "test",
            "answers": {
                "operation": choice(body["questions"]["operation"]["criteria"], "TYPE_TEXT"),
                "type_text_target": choice(["1"], "1"),
            },
        }

    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(model, "post_json", post)
    model.choose(page(), "Find a book", [])
    observation = captured[0]["state"]["observation"]
    assert set(observation) == {"omitted_actions", "text_truncated", "viewport"}
    assert observation == {"omitted_actions": 0, "text_truncated": False, "viewport": {"w": None, "h": None}}


def test_choose_observation_uses_snapshot_flags(monkeypatch):
    captured = []

    def post(_url, _key, body):
        captured.append(body)
        return {
            "model": "test",
            "answers": {
                "operation": choice(body["questions"]["operation"]["criteria"], "CLICK"),
                "click_target": choice(["1", "2"], "2"),
                "type_text_target": choice(["1"], "1"),
            },
        }

    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(model, "post_json", post)
    p = page()
    p["omitted_actions"] = 12
    p["text_truncated"] = True
    p["w"], p["h"] = 1120, 780
    model.choose(p, "Find a book", [])
    assert captured[0]["state"]["observation"] == {
        "omitted_actions": 12,
        "text_truncated": True,
        "viewport": {"w": 1120, "h": 780},
    }
    assert "observation" not in captured[0]["state"]["page"]


class Stopped(Exception):
    """Stand-in for the runner's stop exception. Vendor must not import runner."""


def _assert_no_input(runner, helper=None, binder=None):
    runner.state["browser"].act.assert_not_called()
    if helper is not None:
        helper.assert_not_called()
    if binder is not None:
        binder.assert_not_called()
    assert runner.pending_text is None


def test_low_operation_confidence_withholds_before_bind_helper_and_input(runner, monkeypatch):
    binder = Mock(return_value=binding("city"))
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}
    runner.confidence = {"operation": 0.8, "target": 0.5}
    runner.state["decision"] = decision(confidence=0.2, target_confidence=0.99)
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "low_operation_confidence"
    assert caught.value.input_dispatched == "not_dispatched"
    assert caught.value.handoff["resume_policy"] == loop.RESUME_POLICY
    _assert_no_input(runner, helper=helper, binder=binder)
    assert len(runner.state["history"]) == 1
    entry = runner.state["history"][0]
    assert entry["dispatch"] == "not_dispatched"
    assert entry["page_changed"] is False
    assert entry["operation_confidence"] == 0.2
    assert entry["target_confidence"] == 0.99
    assert entry["binding_confidence"] is None
    assert entry["text"] is None
    assert runner.state["status"] == "needs_review"
    assert runner.state["review_reason"] == "low_operation_confidence"


def test_low_target_confidence_withholds_before_bind_and_helper(runner, monkeypatch):
    binder = Mock(return_value=binding("city"))
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}
    runner.confidence = {"operation": 0.5, "target": 0.8}
    runner.state["decision"] = decision(confidence=0.99, target_confidence=0.2)
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "low_target_confidence"
    _assert_no_input(runner, helper=helper, binder=binder)
    assert runner.state["history"][0]["dispatch"] == "not_dispatched"


def test_low_binding_confidence_calls_bind_once_and_does_not_type(runner, monkeypatch):
    binder = Mock(return_value={**binding("city"), "confidence": 0.2})
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}
    runner.confidence = {"operation": 0.5, "target": 0.5, "binding": 0.9}
    runner.state["decision"] = decision(confidence=0.99, target_confidence=0.99)
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "low_binding_confidence"
    assert caught.value.binding_key == "city"
    assert caught.value.binding_confidence == 0.2
    binder.assert_called_once()
    helper.assert_not_called()
    runner.state["browser"].act.assert_not_called()
    assert runner.pending_text is None
    entry = runner.state["history"][0]
    assert entry["dispatch"] == "not_dispatched"
    assert entry["binding_confidence"] == 0.2
    assert entry["value_key"] == "city"
    assert entry["text"] is None
    assert "Zurich" not in json.dumps(entry)
    assert "Zurich" not in json.dumps(runner.state["bind_calls"])


def test_low_confidence_none_binding_is_withheld_not_skipped(runner, monkeypatch):
    binder = Mock(return_value={**binding(None), "confidence": 0.1})
    helper = Mock()
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}
    runner.generation = "disabled"
    runner.confidence = {"binding": 0.5}
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "low_binding_confidence"
    helper.assert_not_called()
    runner.state["browser"].act.assert_not_called()
    entry = runner.state["history"][0]
    assert entry["value_source"] is None
    assert entry["note"] is None
    assert entry["dispatch"] == "not_dispatched"


def test_operation_gate_only_does_not_block_low_target(runner, monkeypatch):
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "field_text", helper)
    runner.confidence = {"operation": 0.8}
    runner.state["decision"] = decision(confidence=0.9, target_confidence=0.1)
    act(runner)
    helper.assert_called_once()
    runner.state["browser"].act.assert_called_once()
    assert runner.state["history"][-1]["dispatch"] == "attempted"


def test_binding_gate_only_still_binds_when_operation_is_low(runner, monkeypatch):
    binder = Mock(return_value=binding("city"))
    helper = Mock()
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}
    runner.generation = "disabled"
    runner.confidence = {"binding": 0.5}
    runner.state["decision"] = decision(confidence=0.1, target_confidence=0.1)
    act(runner)
    binder.assert_called_once()
    helper.assert_not_called()
    assert runner.state["browser"].act.call_args.kwargs["text"] == "Zurich"
    assert runner.state["history"][-1]["dispatch"] == "attempted"


def test_no_confidence_policy_records_low_scores_and_still_types(runner, monkeypatch):
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "field_text", helper)
    runner.confidence = None
    runner.state["decision"] = decision(confidence=0.1, target_confidence=0.1)
    act(runner)
    runner.state["browser"].act.assert_called_once()
    entry = runner.state["history"][-1]
    assert entry["confidence"] == 0.1
    assert entry["operation_confidence"] == 0.1
    assert entry["dispatch"] == "attempted"


def test_empty_confidence_dict_does_not_withhold(runner, monkeypatch):
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "field_text", helper)
    runner.confidence = {}
    runner.state["decision"] = decision(confidence=0.1, target_confidence=0.1)
    act(runner)
    runner.state["browser"].act.assert_called_once()


def test_generation_disabled_none_binding_still_skips_when_gate_passes(runner, monkeypatch):
    monkeypatch.setattr(loop, "bind_value", Mock(return_value=binding(None)))
    helper = Mock()
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}
    runner.generation = "disabled"
    runner.confidence = {"binding": 0.5}
    act(runner)
    helper.assert_not_called()
    runner.state["browser"].act.assert_not_called()
    entry = runner.state["history"][-1]
    assert (entry["value_key"], entry["value_source"]) == (None, "skipped")
    assert entry["dispatch"] == "not_dispatched"
    assert entry["binding_confidence"] == 1.0


@pytest.mark.parametrize(
    "value",
    ["Ends with a period.", "trailing space ", "Z\u00fcrich Hauptbahnhof", "two\nlines", "", "x" * 200],
)
def test_high_cutoffs_still_type_supplied_values_byte_for_byte(runner, monkeypatch, value):
    monkeypatch.setattr(loop, "bind_value", Mock(return_value=binding("city")))
    helper = Mock()
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": value}
    runner.generation = "disabled"
    runner.confidence = {"operation": 1.0, "target": 1.0, "binding": 1.0}
    act(runner)
    assert runner.state["browser"].act.call_args.kwargs["text"] == value
    helper.assert_not_called()
    entry = runner.state["history"][-1]
    assert (entry["value_key"], entry["value_source"], entry["text"]) == ("city", "supplied", value)
    assert entry["dispatch"] == "attempted"


def test_wait_skips_the_target_gate(runner):
    runner.confidence = {"target": 0.99}
    runner.state["decision"] = decision("wait", confidence=1.0, target_confidence=None)
    act(runner)
    runner.state["browser"].act.assert_called_once()
    entry = runner.state["history"][-1]
    assert entry["kind"] == "wait"
    assert entry["dispatch"] == "not_dispatched"
    assert entry["target_confidence"] is None


def test_scroll_skips_the_target_gate(runner):
    runner.state["page"]["actions"].append(
        {"id": "scroll", "kind": "scroll", "label": "Scroll down", "delta": 400, "node": 99}
    )
    runner.confidence = {"target": 0.99}
    malformed = decision("wait", confidence=1.0, target_confidence=None)
    malformed["choice"] = "scroll"
    malformed["operation"] = "SCROLL"
    runner.state["decision"] = malformed
    act(runner)
    runner.state["browser"].act.assert_called_once()
    entry = runner.state["history"][-1]
    assert entry["kind"] == "scroll"
    assert entry["dispatch"] == "attempted"


@pytest.mark.parametrize(
    "action_id,score_missing",
    [("e3", False), ("e3", True), ("e1", False)],
)
def test_null_target_fails_closed_on_action_kind(runner, monkeypatch, action_id, score_missing):
    binder = Mock()
    helper = Mock()
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "field_text", helper)
    runner.confidence = {"target": 0.9}
    malformed = decision(action_id, confidence=1.0, target_confidence=0.01)
    malformed["target"] = None
    if score_missing:
        malformed.pop("target_confidence", None)
    runner.state["decision"] = malformed
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "low_target_confidence"
    _assert_no_input(runner, helper=helper, binder=binder)
    assert runner.state["history"][-1]["dispatch"] == "not_dispatched"


def test_missing_target_confidence_fails_closed_when_target_gate_is_on(runner, monkeypatch):
    binder = Mock()
    helper = Mock()
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "field_text", helper)
    runner.confidence = {"target": 0.5}
    runner.state["decision"] = decision(confidence=1.0, target_confidence=float("nan"))
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "low_target_confidence"
    _assert_no_input(runner, helper=helper, binder=binder)


def test_malformed_operation_score_fails_closed_when_gate_configured(runner, monkeypatch):
    helper = Mock()
    monkeypatch.setattr(loop, "field_text", helper)
    runner.confidence = {"operation": 0.5}
    runner.state["decision"] = decision(confidence=None)
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "low_operation_confidence"
    helper.assert_not_called()
    runner.state["browser"].act.assert_not_called()


def test_bool_cutoff_fails_closed(runner, monkeypatch):
    helper = Mock()
    monkeypatch.setattr(loop, "field_text", helper)
    runner.confidence = {"operation": True}
    runner.state["decision"] = decision(confidence=1.0)
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "low_operation_confidence"
    helper.assert_not_called()
    runner.state["browser"].act.assert_not_called()


def test_budget_stop_after_predict_prevents_act(runner, monkeypatch):
    monkeypatch.setattr(loop, "choose", Mock(return_value=decision("e3")))
    runner.budget_guard = Mock(side_effect=Stopped("cost_unknown"))
    runner.state["decision"] = None
    runner.state["status"] = "ready"
    with pytest.raises(Stopped, match="cost_unknown"):
        runner.command("tick")
    runner.state["browser"].act.assert_not_called()
    assert runner.pending_text is None
    assert runner.state["history"] == []


def test_budget_stop_at_start_of_act_prevents_bind(runner, monkeypatch):
    binder = Mock(return_value=binding("city"))
    helper = Mock()
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}
    runner.budget_guard = Mock(side_effect=Stopped("cost_limit"))
    with pytest.raises(Stopped, match="cost_limit"):
        act(runner)
    binder.assert_not_called()
    helper.assert_not_called()
    runner.state["browser"].act.assert_not_called()
    assert runner.pending_text is None


def test_budget_stop_after_bind_prevents_helper_and_input(runner, monkeypatch):
    binder = Mock(return_value=binding("city"))
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "bind_value", binder)
    monkeypatch.setattr(loop, "field_text", helper)
    runner.values = {"city": "Zurich"}

    def guard():
        if runner.state["bind_calls"]:
            raise Stopped("cost_unknown")

    runner.budget_guard = guard
    with pytest.raises(Stopped, match="cost_unknown"):
        act(runner)
    binder.assert_called_once()
    helper.assert_not_called()
    runner.state["browser"].act.assert_not_called()
    assert runner.pending_text is None


def test_budget_stop_after_helper_prevents_input(runner, monkeypatch):
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "field_text", helper)

    def guard():
        if runner.state["text_calls"]:
            raise Stopped("cost_unknown")

    runner.budget_guard = guard
    with pytest.raises(Stopped, match="cost_unknown"):
        act(runner)
    helper.assert_called_once()
    runner.state["browser"].act.assert_not_called()
    assert runner.pending_text is None


def test_budget_stop_clears_pending_text_from_a_stale_retry(runner, monkeypatch):
    helper = Mock(return_value=("book", {"model": "test", "latency_ms": 10}))
    monkeypatch.setattr(loop, "field_text", helper)
    runner.state["browser"].act.side_effect = StalePage("Changed before input")
    with pytest.raises(StalePage):
        act(runner)
    assert runner.pending_text is not None
    runner.state["decision"] = decision()
    runner.budget_guard = Mock(side_effect=Stopped("cost_limit"))
    with pytest.raises(Stopped):
        act(runner)
    assert runner.pending_text is None
    helper.assert_called_once()


def test_select_interruption_is_needs_review_with_unknown_dispatch(runner):
    runner.state["page"]["actions"].append(
        {
            "id": "e4",
            "kind": "select",
            "label": "Category → Design",
            "role": "combobox",
            "value": "Design",
            "node": 40,
        }
    )
    runner.state["decision"] = decision("e4", operation="SELECT", target="1:1", target_confidence=1.0)
    runner.state["browser"].act.side_effect = RuntimeError(
        "Dropdown execution was interrupted; inspect before retrying."
    )
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "input_interrupted"
    assert caught.value.input_dispatched == "unknown"
    entry = runner.state["history"][-1]
    assert entry["dispatch"] == "unknown"
    assert entry["action"] == "Category → Design"
    assert runner.state["status"] == "needs_review"
    assert runner.state["history"]


def test_tick_does_not_retry_an_unknown_dispatch(runner, monkeypatch):
    monkeypatch.setattr(loop, "choose", Mock(return_value=decision("e3")))
    runner.state["decision"] = None
    runner.state["status"] = "ready"
    runner.state["browser"].act.side_effect = RuntimeError(
        "Dropdown execution was interrupted; inspect before retrying."
    )
    with pytest.raises(NeedsReview) as caught:
        runner.command("tick")
    assert caught.value.reason == "input_interrupted"
    assert runner.state["status"] == "needs_review"
    assert runner.state["history"][-1]["dispatch"] == "unknown"
    # tick must not have cleared history or switched back to ready for a replay.
    assert runner.state["decision"] is None


def test_truncated_done_is_withheld_without_checks(runner):
    runner.state["page"]["text_truncated"] = True
    runner.state["decision"] = decision("DONE")
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "truncated_done"
    assert caught.value.input_dispatched == "not_dispatched"
    runner.state["browser"].act.assert_not_called()
    assert runner.state["status"] == "needs_review"
    assert runner.state["history"][-1]["dispatch"] == "not_dispatched"


def test_omitted_actions_blocked_is_withheld(runner):
    runner.state["page"]["omitted_actions"] = 12
    runner.state["decision"] = decision("BLOCKED")
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "truncated_blocked"
    runner.state["browser"].act.assert_not_called()
    assert runner.state["status"] == "needs_review"


def test_click_is_allowed_on_a_truncated_observation(runner):
    runner.state["page"]["text_truncated"] = True
    runner.state["page"]["omitted_actions"] = 12
    runner.state["decision"] = decision("e3")
    act(runner)
    runner.state["browser"].act.assert_called_once()
    assert runner.state["history"][-1]["dispatch"] == "attempted"
    assert runner.state["status"] == "ready"


def test_truncated_done_is_accepted_when_checks_are_declared(runner):
    runner.state["page"]["text_truncated"] = True
    runner.checks = [{"kind": "url_contains", "value": "example"}]
    runner.state["decision"] = decision("DONE")
    act(runner)
    runner.state["browser"].act.assert_not_called()
    assert runner.state["status"] == "done"
    # The runtime reads this flag and still refuses to call the run completed
    # unless every declared check passed. PROVISIONAL is said out loud, in state.
    assert runner.state["provisional_done"] is True


def test_untruncated_done_is_not_provisional(runner):
    runner.state["decision"] = decision("DONE")
    act(runner)
    assert runner.state["status"] == "done"
    assert runner.state["provisional_done"] is False


def test_truncated_done_with_omitted_actions_is_accepted_when_checks_are_declared(runner):
    runner.state["page"]["omitted_actions"] = 3
    runner.checks = [{"kind": "url_contains", "value": "example"}]
    runner.state["decision"] = decision("DONE")
    act(runner)
    assert runner.state["status"] == "done"
    assert runner.state["provisional_done"] is True


def test_empty_checks_do_not_accept_truncated_done(runner):
    runner.state["page"]["text_truncated"] = True
    runner.checks = []
    runner.state["decision"] = decision("DONE")
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    assert caught.value.reason == "truncated_done"


def test_blocked_without_omitted_actions_is_still_blocked(runner):
    runner.state["page"]["text_truncated"] = True
    runner.state["page"]["omitted_actions"] = 0
    runner.state["decision"] = decision("BLOCKED")
    act(runner)
    assert runner.state["status"] == "blocked"
    runner.state["browser"].act.assert_not_called()


def test_wait_dispatch_is_not_dispatched(runner):
    for _ in range(2):
        runner.state["decision"] = decision("wait")
        act(runner)
    assert {row["dispatch"] for row in runner.state["history"]} == {"not_dispatched"}


def test_needs_review_handoff_omits_goal_values_and_page_text(runner, monkeypatch):
    secret = "417 Sunset Road, Apt 9"
    monkeypatch.setattr(loop, "bind_value", Mock(return_value={**binding("address"), "confidence": 0.1}))
    runner.values = {"address": secret}
    runner.confidence = {"binding": 0.9}
    runner.state["page"]["text"] = "secret page body"
    with pytest.raises(NeedsReview) as caught:
        act(runner)
    blob = json.dumps(caught.value.handoff)
    assert secret not in blob
    assert "secret page body" not in blob
    assert "Find a book" not in blob
    assert "page_key" not in blob
