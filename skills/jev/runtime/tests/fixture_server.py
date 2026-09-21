"""Local fixture server for Jev runtime tests.

Serves an ASCII-only page that sets a cookie and a localStorage marker, and
records what the browser sent back. No external network access, no secrets.
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
