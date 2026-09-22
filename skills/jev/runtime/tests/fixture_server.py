"""Local fixture server for Jev runtime tests.

Serves an ASCII-only page that sets a cookie and a localStorage marker, and
records what the browser sent back. /checks serves a second, static page for
the declared-DOM-check group. No external network access, no secrets: every
value on these pages is synthetic test data.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Jev login fixture</title></head>
<body>
<h1>Jev login fixture</h1>
<p id="state">checking</p>
<script>
var had = window.localStorage.getItem("jev_marker");
if (had) { fetch("/mark?storage=1"); }
window.localStorage.setItem("jev_marker", "present");
document.getElementById("state").textContent = had ? "storage present" : "storage written";
</script>
</body></html>
"""


# Static, minimal page for the snapshot guard group. The group replaces the
# body itself for each truncation case, so the served page only has to be a
# real document from a real origin (a data: URL is not one).
SNAPSHOT_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Jev snapshot fixture</title></head>
<body>
<h1 id="heading">Snapshot fixture</h1>
<p id="body">Short visible text.</p>
</body></html>
"""


# Static, deterministic page for declared DOM checks. It counts the events a
# mutation would produce, so a test can prove the checks only read.
CHECKS_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Jev checks fixture</title></head>
<body>
<h1 id="heading">Saved</h1>
<p id="summary">Order 4471 was saved for Dana.</p>
<p id="invisible" style="display:none">Invisible text</p>
<p class="ambiguous">first</p>
<p class="ambiguous">second</p>
<ul>
  <li class="row">one</li>
  <li class="row">two</li>
  <li class="row">three</li>
</ul>
<form id="form" onsubmit="return false">
  <input id="email" name="email" value="dana@example.test">
  <input id="secret" name="secret" type="password" value="fixture-password-never-read">
  <input id="token" name="token" type="hidden" value="fixture-hidden-csrf-value">
  <input id="upload" name="upload" type="file">
  <textarea id="note">note line one</textarea>
  <select id="choice">
    <option value="alpha">Alpha</option>
    <option value="beta" selected>Beta</option>
  </select>
  <div id="editable" contenteditable="true">Editable text</div>
  <button id="go" type="button">Do not press</button>
</form>
<script>
window.__fixtureEvents = 0;
for (var name of ["click", "input", "change", "submit", "keydown", "pointerdown"]) {
  document.addEventListener(name, function () { window.__fixtureEvents += 1; }, true);
}
</script>
</body></html>
"""


class State:
    def __init__(self):
        self.visits = 0
        self.cookie_seen = False
        self.storage_seen = False


class Handler(BaseHTTPRequestHandler):
    state = None

    def log_message(self, *_args):
        return

    def _send(self, code, body, headers=()):
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        state = Handler.state
        if self.path.startswith("/snapshot"):
            self._send(200, SNAPSHOT_PAGE)
            return
        if self.path.startswith("/checks"):
            # Static: no cookie, no counter, so a re-read is always identical.
            self._send(200, CHECKS_PAGE)
            return
        if self.path.startswith("/mark"):
            if "storage=1" in self.path:
                state.storage_seen = True
            self._send(200, "ok")
            return
        if self.path.startswith("/state"):
            body = json.dumps(
                {"visits": state.visits, "cookie_seen": state.cookie_seen, "storage_seen": state.storage_seen}
            )
            self._send(200, body)
            return
        state.visits += 1
        if "jev_cookie=present" in (self.headers.get("Cookie") or ""):
            state.cookie_seen = True
        self._send(200, PAGE, headers=[("Set-Cookie", "jev_cookie=present; Path=/; Max-Age=86400")])


def start(port=0):
    """Start the fixture server. Returns (server, thread, base_url, state)."""
    state = State()
    Handler.state = state
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    return server, thread, "http://127.0.0.1:%d/" % server.server_address[1], state


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
