"""Strict, bounded task options. Unknown configuration is rejected, never ignored."""
from __future__ import annotations

import json
import math
import re
from urllib.parse import urlsplit


class Halt(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def invalid(message):
    raise Halt("invalid_request", message)


def object_keys(value, keys, name):
    if not isinstance(value, dict) or set(value) - set(keys):
        invalid(f"{name} must be an object containing only: {', '.join(sorted(keys))}")
    return value


def string(value, name, limit=2000, blank=False):
    if not isinstance(value, str) or len(value) > limit or (not blank and not value.strip()):
        invalid(f"{name} must be a {'possibly empty ' if blank else 'nonempty '}string of at most {limit} characters")
    return value


def number(value, name, low, high, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or not low <= value <= high or
            (integer and not isinstance(value, int))):
        invalid(f"{name} must be a {'whole ' if integer else ''}number between {low} and {high}")
    return value


def array(value, name, maximum=50):
    if not isinstance(value, list) or len(value) > maximum:
        invalid(f"{name} must be a list of at most {maximum} items")
    return value


def origin(url):
    try:
        parts = urlsplit(url)
        port = parts.port
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError()
        if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
            raise ValueError()
        host = parts.hostname.lower()
        if ':' in host:
            host = f"[{host}]"
        default = 443 if parts.scheme == "https" else 80
        return f"{parts.scheme}://{host}" + (f":{port}" if port and port != default else "")
    except (TypeError, ValueError):
        invalid("an absolute HTTP(S) URL without user information is required")


def checks(items, name):
    result, ids = [], set()
    for item in array(items, name):
        object_keys(item, {"id", "kind", "selector", "attribute", "equals", "contains"}, name)
        identifier = string(item.get("id"), "check.id", 100)
        if identifier in ids:
            invalid(f"duplicate check id in {name}")
        ids.add(identifier)
        kind = item.get("kind")
        if kind not in {"url", "title", "text", "value", "count", "attribute"}:
            invalid("unsupported check.kind")
        if ("equals" in item) == ("contains" in item):
            invalid("a check needs exactly one of equals or contains")
        if kind in {"text", "value", "count", "attribute"}:
            string(item.get("selector"), "check.selector", 1000)
        elif "selector" in item:
            invalid("url/title checks do not accept selectors")
        if kind == "attribute":
            string(item.get("attribute"), "check.attribute", 100)
        elif "attribute" in item:
            invalid("only attribute checks accept an attribute")
        expected = item.get("equals", item.get("contains"))
        if kind == "count":
            if "contains" in item:
                invalid("count checks require equals")
            number(expected, "check.equals", 0, 100_000, integer=True)
        else:
            string(expected, "check expectation", 20_000, blank="equals" in item)
        result.append(dict(item))
    return result


def normalize_options(raw, url):
    opts = object_keys({} if raw is None else raw, {
        "values", "generation", "allow", "origins", "confidence", "viewport",
        "theme", "region", "checks", "extract", "milestones", "collect", "provider",
    }, "options")
    try:
        if len(json.dumps(opts, allow_nan=False)) > 100_000:
            invalid("options exceeds the 100000-character limit")
    except (ValueError, TypeError, RecursionError):
        invalid("options must be finite JSON")
    values = opts.get("values", {})
    if not isinstance(values, dict) or len(values) > 50:
        invalid("values must contain at most 50 references")
    for key, value in values.items():
        if key == "NONE" or not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", key):
            invalid("value references must be short alphanumeric identifiers")
        string(value, "exact value", blank=True)
    if opts.get("generation", "disabled") != "disabled":
        invalid("text generation is disabled; supply approved exact values")
    allowed_origins = [origin(x) for x in array(opts.get("origins", [origin(url)]), "origins", 10)]
    if origin(url) not in allowed_origins:
        invalid("the starting URL must belong to an approved origin")
    allowed = []
    for item in array(opts.get("allow", []), "allow", 50):
        object_keys(item, {"kind", "label", "role", "value_refs", "max_uses"}, "allow rule")
        if item.get("kind") not in {"click", "fill", "select"}:
            invalid("allow.kind must be click, fill or select")
        string(item.get("label"), "allow.label", 500)
        if "role" in item:
            string(item["role"], "allow.role", 100)
        refs = array(item.get("value_refs", []), "value_refs", 50)
        if any(not isinstance(ref, str) or ref not in values for ref in refs):
            invalid("allow.value_refs must name supplied exact values")
        if item["kind"] == "fill" and not refs:
            invalid("fill permissions must name at least one value reference")
        if item["kind"] != "fill" and refs:
            invalid("only fill permissions accept value_refs")
        allowed.append({**item, "value_refs": list(refs),
                        "max_uses": number(item.get("max_uses", 1), "max_uses", 1, 25, integer=True)})
    confidence = object_keys(opts.get("confidence", {}), {"operation", "target", "binding"}, "confidence")
    confidence = {key: number(confidence.get(key, default), key, 0, 1)
                  for key, default in {"operation": .8, "target": .85, "binding": .95}.items()}
    viewport = object_keys(opts.get("viewport", {}), {"width", "height", "dpr"}, "viewport")
    viewport = {"width": number(viewport.get("width", 1280), "width", 320, 3840, integer=True),
                "height": number(viewport.get("height", 800), "height", 240, 2160, integer=True),
                "dpr": number(viewport.get("dpr", 1), "dpr", .5, 4)}
    if viewport["width"]*viewport["height"]*viewport["dpr"]**2 > 32_000_000:
        invalid("viewport exceeds the 32-million-device-pixel limit")
    theme = opts.get("theme", "light")
    if theme not in {"light", "dark"}:
        invalid("theme must be light or dark")
    region = opts.get("region")
    if region is not None:
        string(region, "region", 1000)
    collect = array(opts.get("collect", []), "collect", 4)
    if any(item not in {"accessibility", "focus", "render"} for item in collect):
        invalid("collect supports accessibility, focus and render")
    milestones, ids = [], set()
    for milestone in array(opts.get("milestones", []), "milestones", 20):
        object_keys(milestone, {"id", "goal", "checks"}, "milestone")
        identifier = string(milestone.get("id"), "milestone.id", 100)
        if identifier in ids:
            invalid("duplicate milestone id")
        ids.add(identifier)
        verified_by = checks(milestone.get("checks", []), "milestone.checks")
        if not verified_by:
            invalid("each milestone must declare at least one check")
        milestones.append({"id": identifier, "goal": string(milestone.get("goal"), "milestone.goal", 4000),
                           "checks": verified_by})
    provider = object_keys(opts.get("provider", {}), {"name", "model", "estimate_per_million"}, "provider")
    name = provider.get("name", "openrouter")
    if name not in {"openrouter", "cloudflare"}:
        invalid("provider.name must be openrouter or cloudflare")
    model = string(provider.get("model", "jev-latest" if name == "openrouter" else "typesafe/jev"), "model", 200)
    rates = provider.get("estimate_per_million")
    if rates is not None:
        object_keys(rates, {"input", "output"}, "estimate_per_million")
        rates = {key: number(rates.get(key), f"estimate {key}", 0, 1000) for key in ("input", "output")}
    extractions = []
    for item in array(opts.get("extract", []), "extract"):
        object_keys(item, {"id", "kind", "selector", "attribute"}, "extract")
        expectation = 0 if item.get("kind") == "count" else ""
        normalized = checks([{**item, "equals": expectation}], "extract")[0]
        normalized.pop("equals")
        extractions.append(normalized)
    if len({item["id"] for item in extractions}) != len(extractions):
        invalid("duplicate extraction id")
    return {"values": dict(values), "allow": allowed, "origins": allowed_origins,
            "confidence": confidence, "viewport": viewport, "theme": theme, "region": region,
            "checks": checks(opts.get("checks", []), "checks"), "extract": extractions, "milestones": milestones,
            "collect": list(collect), "provider": {"name": name, "model": model, "rates": rates}}
