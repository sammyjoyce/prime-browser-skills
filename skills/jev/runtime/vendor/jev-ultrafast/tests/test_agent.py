"""Offline contracts for a dynamic operation/target policy. No paid APIs."""

import json
import time
from copy import deepcopy
from unittest.mock import Mock

import pytest

from jev_ultrafast import agent as loop
from jev_ultrafast import model
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


def choice(ids, selected):
    return {"choice": selected, "confidence": 1.0, "probabilities": {i: float(i == selected) for i in ids}}


def decision(action="e1"):
    return {
        "choice": action,
        "operation": "TYPE_TEXT",
        "target": "1",
        "confidence": 1.0,
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
    with pytest.raises(StalePage):
        runner.command("act", {"fingerprint": runner.state["page"]["fingerprint"]})
    assert runner.state["history"][-1]["action"] == "Go"
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
    assert "supplied_values" not in plain["state"]
    assert bound["state"]["supplied_values"] == {"city": "Z" * 80, "note": "hi"}
    assert "A small LLM will supply" in plain["questions"]["operation"]["criteria"]["TYPE_TEXT"]
    assert "A supplied value" in bound["questions"]["operation"]["criteria"]["TYPE_TEXT"]
    assert plain["state"]["page"] == bound["state"]["page"]
    assert plain["state"]["elements"] == bound["state"]["elements"]


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
