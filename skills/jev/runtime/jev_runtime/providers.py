"""Explicit Jev transports; never substitute a provider or invent billed cost."""
from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.request

from .contracts import Halt


def finite_number(value):
    return (not isinstance(value, bool) and isinstance(value, (float, int))
            and math.isfinite(value) and value >= 0)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a provider token to a redirect target.
        return None


def http_post(url, key, body, timeout):
    request = urllib.request.Request(url, json.dumps(body, allow_nan=False).encode(),
                                     {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        response = urllib.request.build_opener(NoRedirect).open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise Halt("protocol_error", "provider response exceeds 2 MB")
        return response.code, data.decode("utf-8", "replace")


class Provider:
    def __init__(self, settings, *, attempts=None, logical_calls=None, post=http_post, env=None, check_stop=lambda: None):
        self.settings = settings
        self.attempts = attempts if attempts is not None else []
        self.logical_calls = logical_calls if logical_calls is not None else []
        self.post, self.check_stop = post, check_stop
        env = os.environ if env is None else env
        name = settings["name"]
        if name == "openrouter":
            self.url = "https://openrouter.ai/api/v1/systemone"
            self.key = env.get("OPENROUTER_API_KEY")
        else:
            account = env.get("CLOUDFLARE_ACCOUNT_ID", "")
            if not re.fullmatch(r"[a-fA-F0-9]{32}", account):
                raise Halt("credentials_error", "CLOUDFLARE_ACCOUNT_ID must be a 32-character account identifier")
            self.url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run"
            self.key = env.get("CLOUDFLARE_API_TOKEN")
        if not self.key:
            raise Halt("credentials_error", "OPENROUTER_API_KEY is not set" if name == "openrouter" else "CLOUDFLARE_API_TOKEN is not set")

    def evaluate(self, state, questions, *, remaining_seconds, limit):
        self.check_stop()
        self.check_budget(limit)
        content = {"state": state, "questions": questions}
        model = self.settings["model"]
        body = ({"model": model, "input": content} if self.settings["name"] == "cloudflare"
                else {"model": model, **content})
        if len(json.dumps(body, allow_nan=False)) > 250_000:
            raise Halt("needs_review", "decision context is too large; narrow the observation region")
        logical = {"role": "decision", "ok": False}
        self.logical_calls.append(logical)
        started = time.monotonic()
        for retry in range(3):
            self.check_stop()
            left = remaining_seconds - (time.monotonic() - started)
            if left <= 0:
                raise Halt("timeout", "model-call deadline reached")
            record = {"role": "decision", "status_code": None, "usage": None,
                      "cost_usd": None, "estimated_cost_usd": None, "resolved_model": None,
                      "latency_ms": None, "helper_shape": None, "provider_message": None, "error": None}
            self.attempts.append(record)
            t0 = time.monotonic()
            try:
                code, text = self.post(self.url, self.key, body, min(25, left))
                record["status_code"] = code
                try:
                    payload = json.loads(text)
                except ValueError:
                    payload = None
                if isinstance(payload, dict) and "result" in payload:
                    if payload.get("success") is False or payload.get("errors"):
                        raise Halt("provider_error", "Cloudflare returned an unsuccessful result")
                    payload = payload["result"]
                if not 200 <= code < 300:
                    record["provider_message"] = text.replace(self.key, "[REDACTED]")[:500]
                    # No replay of browser input: these retries are inference-only.
                    if code in {429, 503, 529} and retry < 2:
                        time.sleep(min(.5 * 2**retry, max(0, left)))
                        continue
                    raise Halt("provider_error", f"provider HTTP {code}: {record['provider_message']}")
                if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
                    raise Halt("protocol_error", "provider returned no typed answers")
                record["resolved_model"] = payload.get("model")
                if not isinstance(record["resolved_model"], str) or not record["resolved_model"]:
                    raise Halt("protocol_error", "provider did not identify the resolved model")
                usage = payload.get("usage")
                if isinstance(usage, dict):
                    record["usage"] = usage
                    cost = usage.get("cost", usage.get("total_cost"))
                    if finite_number(cost):
                        record["cost_usd"] = cost
                    rates = self.settings["rates"]
                    tokens = [usage.get("input_tokens", usage.get("prompt_tokens")),
                              usage.get("output_tokens", usage.get("completion_tokens"))]
                    if rates is not None and all(type(n) is int and n >= 0 for n in tokens):
                        record["estimated_cost_usd"] = (tokens[0]*rates["input"] + tokens[1]*rates["output"])/1_000_000
                self.check_stop()
                self.check_budget(limit)  # Before a response can authorize browser input.
                logical.update(ok=True, latency_ms=round((time.monotonic()-started)*1000),
                               resolved_model=record["resolved_model"])
                return payload
            except Halt as exc:
                record["error"] = exc.status
                raise
            except Exception as exc:
                if type(exc).__name__ == "Stopped":
                    raise
                record["error"] = type(exc).__name__
                raise Halt("provider_error", f"provider transport failed: {type(exc).__name__}") from None
            finally:
                record["latency_ms"] = round((time.monotonic() - t0) * 1000)
        raise Halt("provider_error", "provider retry limit reached")

    def check_budget(self, limit):
        subtotal = 0
        for attempt in self.attempts:
            code = attempt["status_code"]
            if code is None or not 200 <= code < 300:
                continue
            cost = attempt["cost_usd"]
            if cost is None:
                cost = attempt["estimated_cost_usd"]
            if cost is None:
                raise Halt("cost_unknown", "successful request has no reported cost or explicitly authorized token estimate")
            subtotal += cost
        if subtotal >= limit:
            raise Halt("cost_limit", "soft model-cost budget exhausted before browser input")

    def metrics(self):
        successful = [a for a in self.attempts if a["status_code"] is not None and 200 <= a["status_code"] < 300]
        billed = [a["cost_usd"] for a in successful]
        estimated = [a["estimated_cost_usd"] for a in successful]
        return {"provider": self.settings["name"], "model": self.settings["model"],
                "resolved_models": list(dict.fromkeys(a["resolved_model"] for a in successful if a["resolved_model"])),
                "http_attempts": len(self.attempts), "logical_requests": len(self.logical_calls), "helper_calls": 0,
                "reported_cost_usd": (sum(billed) if successful and all(c is not None for c in billed) else (0 if not self.attempts else None)),
                "estimated_cost_usd": (sum(estimated) if estimated and all(c is not None for c in estimated) else None),
                "budget_basis": "reported_or_explicit_estimate" if self.settings["rates"] else "reported",
                "estimate_rates_per_million": self.settings["rates"]}
