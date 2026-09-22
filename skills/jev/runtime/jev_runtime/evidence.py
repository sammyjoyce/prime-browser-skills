"""Deterministic DOM assertions. Browser evidence is not authoritative store proof."""
from __future__ import annotations

import base64
import json
import os
import re
import time

from .contracts import Halt

READ = r'''(checks => checks.map(check => {
  try {
    let value;
    if (check.kind==='url') value=location.href;
    else if (check.kind==='title') value=document.title;
    else {
      const nodes=[...document.querySelectorAll(check.selector)];
      if (check.kind==='count') value=nodes.length;
      else {
        if (nodes.length!==1) return {available:false,reason:'missing_or_ambiguous',matches:nodes.length};
        const e=nodes[0];
        if (e.type==='password') return {available:false,reason:'sensitive_field'};
        if (check.kind==='value') {
          if (!('value' in e) && !e.isContentEditable) return {available:false,reason:'not_a_field'};
          value='value' in e ? e.value : e.innerText;
        } else if (check.kind==='text') {
          if (!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})) return {available:false,reason:'not_visible'};
          value=e.innerText;
        } else value=e.getAttribute(check.attribute);
      }
    }
    if (typeof value==='string' && value.length>20000) return {available:false,reason:'value_truncated'};
    return {available:true,value};
  } catch (_) {return {available:false,reason:'unreadable_or_invalid_selector'}}
}))'''

FOCUS = """(() => {const e=document.activeElement;return e ? {
    tag:e.tagName,id:e.id,role:e.getAttribute('role'),aria_label:e.getAttribute('aria-label'),
    outline:getComputedStyle(e).outline,rect:JSON.stringify(e.getBoundingClientRect())
}:null})()"""
RENDER = """({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,
    theme:matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light',
    user_agent:navigator.userAgent,fonts_status:document.fonts.status})"""


def summarize(rows):
    if not rows:
        return "not_run"
    statuses = {row["status"] for row in rows}
    if "failed" in statuses:
        return "failed"
    if statuses != {"passed"}:
        return "unknown"
    return "passed"


def verify(browser, checks):
    if not checks:
        return []
    try:
        observed = browser.evaluate(f"{READ}({json.dumps(checks)})")
    except Exception:
        observed = None
    if not isinstance(observed, list) or len(observed) != len(checks):
        observed = [{} for _ in checks]
    rows = []
    for check, evidence in zip(checks, observed):
        evidence = evidence if isinstance(evidence, dict) else {}
        row = {"id": check["id"], "status": "unknown", "boundary": "browser_dom",
               "check": check, "observed": evidence, "captured_at_ms": round(time.time()*1000)}
        if evidence.get("available") is True and "value" in evidence:
            value = evidence["value"]
            if "equals" in check:
                # bool is not the same evidence type as a numeric count.
                matches = type(value) is type(check["equals"]) and value == check["equals"]
            else:
                matches = isinstance(value, str) and check["contains"] in value
            row["status"] = "passed" if matches else "failed"
        rows.append(row)
    return rows


def collect(browser, kinds):
    result = {}
    for kind in kinds:
        try:
            if kind == "accessibility":
                tree = browser.call("Accessibility.getFullAXTree")
                nodes = tree.get("nodes", [])
                result[kind] = {"nodes": nodes[:1000], "truncated": len(nodes)>1000,
                                "boundary": "chrome_accessibility_tree_not_screen_reader"}
            else:
                result[kind] = {"value": browser.evaluate(FOCUS if kind == "focus" else RENDER),
                                "boundary": "browser_dom"}
        except Exception:
            result[kind] = {"available": False, "reason": "collector_failed"}
    return result


def redact_text(text):
    for name, value in os.environ.items():
        if len(value) >= 8 and re.search(r"API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", name, re.I):
            text = text.replace(value, "[REDACTED]")
    return text


def extract(browser, specifications):
    if not specifications:
        return []
    try:
        values = browser.evaluate(f"{READ}({json.dumps(specifications)})")
    except Exception:
        values = None
    if not isinstance(values, list) or len(values) != len(specifications):
        values = [{} for _ in specifications]
    return [{"id":spec["id"], "boundary":"browser_dom", "evidence":value,
             "status":"observed" if isinstance(value,dict) and value.get("available") is True else "unknown"}
            for spec,value in zip(specifications,values)]


def save_json(path, data):
    encoded = redact_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2))
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(encoded)
    return str(path.resolve())


def screenshot(browser, path):
    data = browser.call("Page.captureScreenshot", format="png").get("data")
    if not isinstance(data, str):
        raise Halt("artifact_error", "Chrome returned no screenshot")
    raw = base64.b64decode(data, validate=True)
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise Halt("artifact_error", "Chrome did not return native PNG bytes")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
    return str(path.resolve())
