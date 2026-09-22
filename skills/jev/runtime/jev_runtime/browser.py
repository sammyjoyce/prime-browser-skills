"""Own observation policy; retain pinned observed-node input and stale-page guards."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from jev_ultrafast.browser import Browser, StalePage

from .contracts import Halt

SNAPSHOT = Path(__file__).with_name("snapshot.js").read_text()


class ObservedBrowser(Browser):
    def __init__(self, url, options):
        self.options = options
        super().__init__(url)
        viewport = options["viewport"]
        self.call("Emulation.setDeviceMetricsOverride", width=viewport["width"], height=viewport["height"],
                  deviceScaleFactor=viewport["dpr"], mobile=False)
        self.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": options["theme"]}])

    def observe(self, screenshot=False):
        state = self.evaluate(f"({SNAPSHOT})({json.dumps({'region': self.options['region']})})")
        if not isinstance(state, dict):
            raise StalePage("Document is navigating")
        if state.get("region_error"):
            raise Halt("needs_review", "observation region is missing, hidden or ambiguous")
        state["fingerprint"] = hashlib.sha256(json.dumps(state["marker"], sort_keys=True).encode()).hexdigest()
        return state

    def fresh(self, page, action=None):
        if action is not None and action["kind"] in {"click", "select"}:
            return super().fresh(page, action)
        return self.observe()["marker"] == page["marker"]

