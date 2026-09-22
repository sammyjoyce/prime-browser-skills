"""Bounded Jev-first loop with exact inputs and independently evaluated DOM checks."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .contracts import Halt, origin
from .decisions import build_request, permission, resolve
from .evidence import collect, extract, redact_text, save_json, screenshot, summarize, verify


class Engine:
    def __init__(self, browser, provider, config, result, *, check_stop=lambda: None):
        self.browser, self.provider, self.config, self.result = browser, provider, config, result
        self.options, self.check_stop = config["options"], check_stop
        self.started = time.monotonic()
        self.uses, self.history, self.calls = {}, [], 0
        self.path = Path(config["artifact_dir"])
        result.update(actions=self.history, milestones=[], verification={"status":"not_run","checks":[],
                      "scope":"declared_dom_checks_only"}, side_effects="none_observed", handoff=None,
                      collectors={}, evidence_paths=[])

    def budget(self, *, action=False):
        self.check_stop()
        if self.remaining() <= 0:
            raise Halt("timeout", "task time budget exhausted")
        if action and len(self.history) >= self.config["max_steps"]:
            raise Halt("max_steps", "browser action budget exhausted")
        if self.calls > self.config["max_steps"]*2:
            raise Halt("max_steps", "decision budget exhausted")
        self.provider.check_budget(self.config["max_cost_usd"])

    def remaining(self):
        return self.config["timeout_ms"]/1000 - (time.monotonic() - self.started)

    def journal(self):
        # Append-only checkpoints before every dispatch; never overwrite failure evidence.
        target = self.path / "actions.jsonl"
        fd = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(redact_text(json.dumps(self.history[-1], ensure_ascii=False))+"\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.result["steps"] = len(self.history)

    def observe(self):
        self.budget()
        page = self.browser.observe()
        if origin(page["url"]) not in self.options["origins"]:
            raise Halt("policy_blocked", "browser left the approved origins; no further input dispatched")
        self.result["output"] = {
            "final_url":page["url"], "final_title":page["title"], "page_text":page["text"],
            "completion_claimed":False, "verification":"not_performed",
        }
        self.result["observation"] = {"fingerprint":page["fingerprint"], "region":page.get("region"),
                                      "omitted_actions":page.get("omitted_actions",0),
                                      "text_truncated":page.get("text_truncated",False)}
        if page.get("omitted_actions",0) or page.get("text_truncated",False):
            raise Halt("needs_review", "observation was truncated; select a smaller region before continuing")
        return page

    def checkpoint(self, name, rows):
        evidence = {"checks":rows, "observation":self.result.get("observation"),
                    "collectors":collect(self.browser, self.options["collect"]),
                    "extractions":extract(self.browser, self.options["extract"])}
        image = screenshot(self.browser, self.path / f"{name}.png")
        evidence["screenshot_path"] = image
        path = save_json(self.path / f"{name}.json", evidence)
        self.result["evidence_paths"].extend([path,image])
        self.result["collectors"] = evidence["collectors"]
        self.result["extractions"] = evidence["extractions"]
        return path

    def run(self):
        plan = self.options["milestones"] or [{"id":"task","goal":self.config["task"],"checks":[]}]
        try:
            for index, milestone in enumerate(plan):
                self.result["current_milestone"] = milestone["id"]
                while True:
                    page = self.observe()
                    state, questions, groups, permissions = build_request(
                        page, milestone["goal"], self.options, self.history, self.uses)
                    if self.calls >= self.config["max_steps"]*2:
                        raise Halt("max_steps", "decision budget exhausted")
                    self.calls += 1
                    payload = self.provider.evaluate(state, questions,
                        remaining_seconds=self.remaining(), limit=self.config["max_cost_usd"])
                    self.budget()
                    selected = resolve(payload, questions, groups, permissions, self.options)
                    if selected["operation"] == "BLOCKED":
                        raise Halt("blocked", "Jev found no supported authorized way to progress")
                    # Full observation freshness before DONE or binding, not just element geometry.
                    if not self.browser.fresh(page):
                        continue  # No input has been dispatched. Inference remains budgeted.
                    if selected["operation"] == "DONE":
                        rows = verify(self.browser, milestone["checks"])
                        path = self.checkpoint(f"milestone-{index:02d}", rows)
                        status = summarize(rows)
                        self.result["milestones"].append({"id":milestone["id"],"status":status,"evidence_path":path})
                        if rows and status != "passed":
                            self.result["verification"] = {"status":status,"checks":rows,"scope":"declared_dom_checks_only"}
                            raise Halt("verification_failed", "declared milestone checks did not pass")
                        break
                    action = selected["action"]
                    # Recheck authority and freshness immediately before a one-shot dispatch.
                    allowed = permission(action, self.options, self.uses)
                    if allowed != selected["permission"]:
                        raise Halt("policy_blocked", "action permission changed")
                    self.budget(action=True)
                    if not self.browser.fresh(page, action):
                        continue
                    if allowed["rule"] is not None:
                        self.uses[allowed["rule"]] = self.uses.get(allowed["rule"],0)+1
                    event = {"step":len(self.history)+1,"kind":action["kind"],"action":action["label"],
                             "operation":selected["operation"],"snapshot":page["fingerprint"],
                             "dispatch":"started","page_changed":None,
                             "operation_confidence":selected["operation_confidence"],
                             "target_confidence":selected["target_confidence"]}
                    self.history.append(event)
                    if allowed["side_effect"]:
                        self.result["side_effects"] = "uncertain"
                    self.journal()
                    try:
                        self.browser.act(action, page, text=selected["value"])
                    except Exception:
                        # Even a stale/transport error may follow partial input. Never auto-replay it.
                        raise Halt("needs_review", "input dispatch was interrupted; inspect state before any retry") from None
                    event["dispatch"] = "returned"
                    self.journal()
                    after = self.observe()
                    event["page_changed"] = after["fingerprint"] != page["fingerprint"]
                    if action["kind"] == "fill":
                        current = [a for a in after["actions"] if a.get("node") == action["node"] and a["kind"] == "fill"]
                        if len(current) != 1 or current[0].get("value") != selected["value"]:
                            raise Halt("needs_review", "exact field readback did not match; no submission may follow")
                    if len(self.history) >= 3 and all(h["page_changed"] is False and h["kind"] != "wait" for h in self.history[-3:]):
                        raise Halt("blocked", "three actions made no observable progress")
            rows = verify(self.browser, self.options["checks"])
            status = summarize(rows)
            self.result["verification"] = {"status":status,"checks":rows,"scope":"declared_dom_checks_only"}
            self.checkpoint("verification", rows)
            self.result["output"]["completion_claimed"] = True
            if rows and status != "passed":
                raise Halt("verification_failed", "declared final checks did not pass")
            return "done"
        except Halt as exc:
            self.result["handoff"] = {"reason":exc.status,"message":str(exc),
                "observation":self.result.get("observation"), "current_milestone":self.result.get("current_milestone"),
                "completed_milestones":self.result["milestones"], "actions":self.history,
                "resume_policy":"inspect current state; never replay uncertain input", "browser_closed_after_return":True}
            raise
        finally:
            self.result["steps"] = len(self.history)
            self.result["duration_ms"] = round((time.monotonic()-self.started)*1000)
            self.result["decision_metrics"] = self.provider.metrics()
