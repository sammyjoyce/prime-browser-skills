"""The complete agent loop. Typed choices, observable state, bounded execution."""

import base64
import math
import time
from pathlib import Path

from .browser import Browser, StalePage
from .model import action_space, bind_value, choose, field_context, field_text
from .questions import MAX_STEPS

GENERATION = ("helper", "disabled")
NOTHING_TYPED = "no value bound to this field; nothing typed"
RESUME_POLICY = "inspect current state; never replay this decision or any uncertain input"


class NeedsReview(Exception):
    """The next input was not safe to take. Inspect current state; do not replay."""

    def __init__(
        self,
        reason,
        *,
        choice=None,
        operation=None,
        operation_confidence=None,
        target=None,
        target_confidence=None,
        binding_key=None,
        binding_confidence=None,
        input_dispatched="not_dispatched",
    ):
        self.reason = reason
        self.choice = choice
        self.operation = operation
        self.operation_confidence = operation_confidence
        self.target = target
        self.target_confidence = target_confidence
        self.binding_key = binding_key
        self.binding_confidence = binding_confidence
        self.input_dispatched = input_dispatched
        # Allowlisted handoff fields only. No goal, values, page text, or helper output.
        self.handoff = {
            "reason": reason,
            "choice": choice,
            "operation": operation,
            "operation_confidence": operation_confidence,
            "target": target,
            "target_confidence": target_confidence,
            "binding_key": binding_key,
            "binding_confidence": binding_confidence,
            "input_dispatched": input_dispatched,
            "resume_policy": RESUME_POLICY,
        }
        super().__init__(reason)


def binding_identity(action, page):
    """Which observed field, in which document, a cached bind and text belong to.

    ``node`` is the identity the snapshot gave that element, not its position in the
    action list, and ``page_key[0]`` is the document's time origin. A second field with
    the same label, a changed URL and a fresh document at one URL each produce a
    different value here, so none of them can reuse the first field's text.
    """
    node, key = action.get("node"), page.get("page_key")
    document = key[0] if isinstance(key, (list, tuple)) and key else None
    return (node if type(node) is int else action.get("id"), document, page.get("url"))


class Agent:
    def __init__(
        self,
        url,
        goals,
        *,
        values=None,
        generation="helper",
        record_dir=None,
        screenshots=False,
        confidence=None,
        budget_guard=None,
        checks=None,
    ):
        task = goals.strip() if isinstance(goals, str) else "\n".join(goals).strip()
        if not task:
            raise ValueError("Supply a task")
        if generation not in GENERATION:
            raise ValueError(f"generation must be one of {GENERATION}")
        plan = [task]
        # Caller-supplied field values. They are copied into fields byte for byte.
        self.values = dict(values) if values else {}
        self.generation = generation
        self.pending_text = None
        # Opt-in cutoffs: None or {} records scores and never withholds. Absent keys leave that gate off.
        self.confidence = confidence
        # Runner-owned callable. May raise a runner stop exception. This module does not import the runner.
        self.budget_guard = budget_guard
        # PROVISIONAL seam with follow-up A: truncated DONE becomes status=done only when this is a
        # non-empty list. The runtime must still require every declared check to pass before
        # accepting completed. Missing or failed checks never allow it.
        self.checks = checks
        self.browser = Browser(url)
        self.record_dir = Path(record_dir) if record_dir else None
        self.screenshots = screenshots or bool(record_dir)
        try:
            page = self.browser.observe(screenshot=self.screenshots)
        except Exception:
            self.browser.close()
            raise
        self.state = dict(
            browser=self.browser,
            goal="\n".join(plan),
            page=page,
            decision=None,
            history=[],
            status="ready",
            # True only when a DONE was accepted on an observation the snapshot
            # reports as truncated. The runtime re-checks the declared evidence.
            provisional_done=False,
            plan=plan,
            plan_index=0,
            decisions=[],
            text_calls=[],
            bind_calls=[],
            elapsed_ms=0,
            started_at=None,
            record=bool(self.record_dir),
        )
        if self.record_dir:
            self.record_dir.mkdir(parents=True, exist_ok=True)
            (self.record_dir / "000000.jpg").write_bytes(base64.b64decode(page["screenshot"]))

    def snapshot(self):
        return {
            **{k: v for k, v in self.state.items() if k != "browser"},
            "elements": action_space(self.state["page"]["actions"])[0],
        }

    def _check_budget(self):
        guard = getattr(self, "budget_guard", None)
        if guard is None:
            return
        try:
            guard()
        except Exception:
            self.pending_text = None
            raise

    def _blocks(self, name, score):
        """True when an opt-in gate is on and the score is below cutoff or unusable."""
        policy = getattr(self, "confidence", None)
        if policy is None or policy == {}:
            return False
        if not isinstance(policy, dict):
            return True
        if name not in policy:
            return False
        cutoff = policy[name]
        if type(cutoff) is bool or not isinstance(cutoff, (int, float)) or not math.isfinite(cutoff):
            return True
        if cutoff <= 0 or cutoff > 1:
            return True
        if type(score) is bool or not isinstance(score, (int, float)) or not math.isfinite(score):
            return True
        return score < cutoff

    def _provisional_truncated_done(self):
        """PROVISIONAL: truncated DONE may become status=done.

        Runtime must still require every declared DOM check to pass before
        accepting completed. Missing or failed checks never allow completed.
        """
        checks = getattr(self, "checks", None)
        return isinstance(checks, (list, tuple)) and len(checks) > 0

    def _review(
        self,
        reason,
        decision,
        *,
        dispatch="not_dispatched",
        value_key=None,
        binding_confidence=None,
    ):
        self.state["status"] = "needs_review"
        self.state["review_reason"] = reason
        return NeedsReview(
            reason,
            choice=decision.get("choice"),
            operation=decision.get("operation"),
            operation_confidence=decision.get("confidence"),
            target=decision.get("target"),
            target_confidence=decision.get("target_confidence"),
            binding_key=value_key,
            binding_confidence=binding_confidence,
            input_dispatched=dispatch,
        )

    def _history_row(
        self,
        decision,
        page,
        *,
        action,
        selected,
        text,
        helper,
        value_key,
        value_source,
        binding_confidence,
        dispatch,
        page_changed,
        skipped,
    ):
        state = self.state
        if action is not None:
            label, kind = action["label"], action["kind"]
        else:
            label, kind = selected, selected.lower()
        probabilities = decision.get("probabilities") or {}
        return {
            "step": len(state["history"]) + 1,
            "action": label,
            "kind": kind,
            "choice": selected,
            "probability": probabilities.get(selected),
            "confidence": decision.get("confidence"),
            "operation_confidence": decision.get("confidence"),
            "target_confidence": decision.get("target_confidence"),
            "binding_confidence": binding_confidence,
            "dispatch": dispatch,
            "latency_ms": decision.get("latency_ms"),
            "text": text,
            "text_helper": helper["model"] if helper else None,
            "text_latency_ms": helper["latency_ms"] if helper else 0,
            "value_key": value_key,
            "value_source": value_source,
            "note": NOTHING_TYPED if skipped else None,
            "operation": decision.get("operation"),
            "target": decision.get("target"),
            "page_changed": page_changed,
            "url": page["url"],
            "usage": decision.get("usage"),
            "executed_ms": round((time.perf_counter() - state["started_at"]) * 1000),
            "elapsed_ms": state["elapsed_ms"],
        }

    def _withhold(
        self,
        reason,
        decision,
        page,
        *,
        action=None,
        value_key=None,
        binding_confidence=None,
        dispatch="not_dispatched",
    ):
        self.pending_text = None
        state = self.state
        selected = decision["choice"]
        if action is None:
            action = next((item for item in page["actions"] if item["id"] == selected), None)
        state["elapsed_ms"] = round((time.perf_counter() - state["started_at"]) * 1000)
        state["history"].append(
            self._history_row(
                decision,
                page,
                action=action,
                selected=selected,
                text=None,
                helper=None,
                value_key=value_key,
                value_source=None,
                binding_confidence=binding_confidence,
                dispatch=dispatch,
                page_changed=False,
                skipped=False,
            )
        )
        raise self._review(
            reason,
            decision,
            dispatch=dispatch,
            value_key=value_key,
            binding_confidence=binding_confidence,
        )

    def field_value(self, action, page, context):
        """(text, helper, value_key, value_source, binding_confidence) for one fill action.

        A supplied value wins and is copied byte for byte. Otherwise the text
        helper writes one, if generation allows it. Anything else is skipped,
        which types nothing at all. A low-confidence bind, including NONE, is
        withheld: it is not a skip and does not call the helper.
        """
        state = self.state
        bind_confidence = None
        if self.values:
            bind = bind_value(state["goal"], action, page, state["history"], self.values)
            # Metadata only: the request holds value previews and never enters the state.
            state["bind_calls"].append(
                {
                    **{k: bind[k] for k in ("key", "confidence", "probabilities", "usage", "latency_ms", "model")},
                    "field": action["label"],
                }
            )
            bind_confidence = bind["confidence"]
            self._check_budget()
            if self._blocks("binding", bind_confidence):
                return None, None, bind["key"], "withheld", bind_confidence
            if bind["key"] is not None:
                return self.values[bind["key"]], None, bind["key"], "supplied", bind_confidence
        if self.generation != "helper":
            return None, None, None, "skipped", bind_confidence
        text, helper = field_text(context)
        state["text_calls"].append({**helper, "field": action["label"], "value": text})
        self._check_budget()
        # The helper answered {"text": null}: no value exists, so nothing is typed.
        if text is None:
            return None, helper, None, "skipped", bind_confidence
        return text, helper, None, "helper", bind_confidence

    def command(self, name, body=None):
        body = body or {}
        state = self.state
        if name == "tick":
            try:
                self.command("predict", {})
                return self.command("act", {"fingerprint": state["page"]["fingerprint"]})
            except StalePage:
                state["decision"] = None
                state["status"] = "ready"
                state["page"] = state["browser"].observe(screenshot=self.screenshots)
                state["elapsed_ms"] = round((time.perf_counter() - state["started_at"]) * 1000)
                return self.snapshot()
        elif name == "predict":
            if not state["browser"]:
                raise ValueError("Start a demo first")
            if state["started_at"] is None:
                state["started_at"] = time.perf_counter()
            if not state["browser"].fresh(state["page"]):
                state["page"] = state["browser"].observe(screenshot=self.screenshots)
            state["decision"] = None
            if state["status"] in {"done", "blocked", "needs_review"}:
                raise ValueError("This run has stopped. Start a fresh demo.")
            if len(state["decisions"]) >= MAX_STEPS * 2:
                raise ValueError("Reached the demo's model-call budget")
            state["decision"] = choose(state["page"], state["goal"], state["history"], values=self.values)
            state["decisions"].append(
                {
                    **state["decision"],
                    "fingerprint": state["page"]["fingerprint"],
                    "elapsed_ms": round((time.perf_counter() - state["started_at"]) * 1000),
                }
            )
            state["status"] = "predicted"
            self._check_budget()
        elif name == "act":
            decision, page = state["decision"], state["page"]
            if not decision or body.get("fingerprint") != page["fingerprint"]:
                raise ValueError("Observe and choose before acting")
            # Consume once, before any mutation or model call. A retry cannot double-click.
            state["decision"] = None
            self._check_budget()
            selected = decision["choice"]
            if selected in {"DONE", "BLOCKED"}:
                if not state["browser"].fresh(page):
                    state["status"] = "ready"
                    raise StalePage("Page changed since the decision. Choose again.")
                if self._blocks("operation", decision.get("confidence")):
                    self._withhold("low_operation_confidence", decision, page)
                omitted = int(page.get("omitted_actions") or 0)
                truncated = bool(page.get("text_truncated")) or omitted > 0
                if selected == "DONE" and truncated and not self._provisional_truncated_done():
                    self._withhold("truncated_done", decision, page)
                if selected == "BLOCKED" and omitted > 0:
                    self._withhold("truncated_blocked", decision, page)
                # PROVISIONAL and stated in the state: this DONE was taken on evidence the
                # snapshot itself reports as incomplete. The runtime must not call such a
                # run completed unless every declared check actually passed.
                state["provisional_done"] = selected == "DONE" and truncated
                state["status"] = "done" if selected == "DONE" else "blocked"
                state["plan_index"] = int(selected == "DONE")
                state["elapsed_ms"] = round((time.perf_counter() - state["started_at"]) * 1000)
                return self.snapshot()
            action = next(a for a in page["actions"] if a["id"] == selected)
            if len(state["history"]) >= MAX_STEPS:
                state["status"] = "blocked"
                raise ValueError(f"Stopped at the {MAX_STEPS}-action demo budget")
            if self._blocks("operation", decision.get("confidence")):
                self._withhold("low_operation_confidence", decision, page, action=action)
            # WAIT/SCROLL/DONE/BLOCKED have no target. The gate keys off the
            # action kind, not whether the provider supplied a target field.
            if action["kind"] not in {"wait", "scroll"}:
                if self._blocks("target", decision.get("target_confidence")):
                    self._withhold("low_target_confidence", decision, page, action=action)
            text, helper, value_key, value_source, binding_confidence = None, None, None, None, None
            if action["kind"] == "fill":
                if not state["browser"].fresh(page):
                    raise StalePage("Page changed before text generation. Choose again.")
                context = field_context(state["goal"], action, page, state["history"])
                # The cache key covers the bind decision too, so a StalePage retry repeats
                # neither the bind call nor the helper call. It names the observed field and
                # its document, so only a real retry of that same field can reuse the text.
                cached = (binding_identity(action, page), context, sorted(self.values), self.generation)
                if self.pending_text and self.pending_text[0] == cached:
                    _, text, helper, value_key, value_source, binding_confidence = self.pending_text
                else:
                    text, helper, value_key, value_source, binding_confidence = self.field_value(action, page, context)
                    if value_source == "withheld":
                        self._withhold(
                            "low_binding_confidence",
                            decision,
                            page,
                            action=action,
                            value_key=value_key,
                            binding_confidence=binding_confidence,
                        )
                    self.pending_text = (cached, text, helper, value_key, value_source, binding_confidence)
                if self.values and self._blocks("binding", binding_confidence):
                    self._withhold(
                        "low_binding_confidence",
                        decision,
                        page,
                        action=action,
                        value_key=value_key,
                        binding_confidence=binding_confidence,
                    )
            skipped = value_source == "skipped"
            # Browser.act checks freshness immediately before input, including after text generation.
            dispatch = "not_dispatched"
            if not skipped:
                self._check_budget()
                try:
                    state["browser"].act(action, page, text=text)
                except StalePage:
                    # Pre-input: fresh() failed before CDP, or the target was gone before input.
                    # tick re-observes. pending_text stays so a fill retry does not re-bind.
                    raise
                except Exception as exc:
                    # After a passing freshness check, a generic exception does not prove
                    # nothing was sent. Select interruption is the named case.
                    self.pending_text = None
                    dispatch = "unknown"
                    state["elapsed_ms"] = round((time.perf_counter() - state["started_at"]) * 1000)
                    state["history"].append(
                        self._history_row(
                            decision,
                            page,
                            action=action,
                            selected=selected,
                            text=text,
                            helper=helper,
                            value_key=value_key,
                            value_source=value_source,
                            binding_confidence=binding_confidence,
                            dispatch=dispatch,
                            page_changed=None,
                            skipped=False,
                        )
                    )
                    raise self._review(
                        "input_interrupted",
                        decision,
                        dispatch=dispatch,
                        value_key=value_key,
                        binding_confidence=binding_confidence,
                    ) from exc
                dispatch = "not_dispatched" if action["kind"] == "wait" else "attempted"
            self.pending_text = None
            state["elapsed_ms"] = round((time.perf_counter() - state["started_at"]) * 1000)
            # Record execution before observing. A stale post-action observation must not erase the action.
            state["history"].append(
                self._history_row(
                    decision,
                    page,
                    action=action,
                    selected=selected,
                    text=text,
                    helper=helper,
                    value_key=value_key,
                    value_source=value_source,
                    binding_confidence=binding_confidence,
                    dispatch=dispatch,
                    page_changed=None,
                    skipped=skipped,
                )
            )
            try:
                state["page"] = state["browser"].observe(screenshot=self.screenshots)
            except StalePage as exc:
                if dispatch in {"attempted", "unknown"}:
                    # Input may have landed. Do not replay. History already has the row.
                    raise self._review(
                        "stale_after_input",
                        decision,
                        dispatch=dispatch,
                        value_key=value_key,
                        binding_confidence=binding_confidence,
                    ) from exc
                raise
            state["elapsed_ms"] = round((time.perf_counter() - state["started_at"]) * 1000)
            state["history"][-1].update(
                # A skipped field typed nothing, so this step changed nothing, whatever the
                # page did on its own. Three of them in a row still stop the run.
                page_changed=False if skipped else state["page"]["fingerprint"] != page["fingerprint"],
                url=state["page"]["url"],
                elapsed_ms=state["elapsed_ms"],
            )
            if state["record"]:
                (self.record_dir / f"{state['elapsed_ms']:06d}.jpg").write_bytes(
                    base64.b64decode(state["page"]["screenshot"])
                )
            repeated = state["history"][-3:]
            state["status"] = (
                "blocked"
                if len(repeated) == 3 and all(h["page_changed"] is False and h["kind"] != "wait" for h in repeated)
                else "ready"
            )
        else:
            raise ValueError("Unknown command")
        return self.snapshot()

    def run(self):
        while self.state["status"] not in {"done", "blocked", "needs_review"}:
            yield self.command("tick")

    def close(self):
        self.browser.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
