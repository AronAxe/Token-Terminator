"""Optional localhost dashboard. No analytics service starts in an agent process."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .dashboard_data import configuration, snapshot

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
    "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
}


def asset(name):
    return files("rtk_hermes_plus").joinpath("dashboard_assets", name).read_bytes()


class DashboardReader:
    def __init__(self, home: Path, config_path: Path | None = None):
        self.home, self.config_path = home, config_path
        self._lock = threading.Lock()
        self._at, self._data = 0.0, None

    def read(self, profile=None):
        with self._lock:
            if self._data is None or time.monotonic() - self._at > 5:
                sources, rates = configuration(self.home, self.config_path)
                self._data = snapshot(sources, rates)
                self._at = time.monotonic()
            data = self._data
        if profile is None:
            return data
        found = [p for p in data["profiles"] if p["id"] == profile]
        if not found:
            raise KeyError("unknown profile")
        # Keep the same aggregate definition; filter without rereading databases.
        from .dashboard_data import summary_from_profiles

        return summary_from_profiles(found, generated_at=data["generated_at"])


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 8

    def __init__(self, reader: DashboardReader, port=7474):
        self.reader = reader
        self._slots = threading.BoundedSemaphore(8)
        super().__init__(("127.0.0.1", port), DashboardHandler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "TokenTerminatorDashboard"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        pass  # no identifiers, query text or local filesystem paths in logs

    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        origins = {f"http://{host}"}
        if (
            self.client_address[0] != "127.0.0.1"
            or len(self.headers.get_all("Host", [])) != 1
            or host not in hosts
            or len(self.headers.get_all("Origin", [])) > 1
            or ("Origin" in self.headers and self.headers["Origin"] not in origins)
            or self.headers.get("Sec-Fetch-Site") == "cross-site"
        ):
            self._send(403, b'{"error":"local_same_origin_only"}')
            return
        if len(self.path) > 2048:
            self._send(414, b'{"error":"request_too_long"}')
            return
        parts = urlsplit(self.path)
        if parts.scheme or parts.netloc or parts.fragment:
            self._send(400, b'{"error":"invalid_path"}')
            return
        try:
            query = parse_qs(parts.query, keep_blank_values=True, max_num_fields=4)
            if set(query) - {"profile"} or any(len(v) != 1 for v in query.values()):
                raise ValueError("invalid query")
            profile = query.get("profile", [None])[0]
            if parts.path in ASSETS and not query:
                name, mime = ASSETS[parts.path]
                self._send(200, asset(name), mime)
            elif parts.path == "/api/v1/summary":
                body = json.dumps(
                    self.server.reader.read(profile),
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode()
                self._send(200, body)
            elif parts.path == "/api/v1/health" and not query:
                self._send(
                    200, b'{"service":"token-terminator-dashboard","read_only":true}'
                )
            else:
                self._send(404, b'{"error":"not_found"}')
        except KeyError:
            self._send(404, b'{"error":"unknown_profile"}')
        except ValueError:
            self._send(400, b'{"error":"invalid_request_or_configuration"}')
        except Exception:  # noqa: BLE001 - do not expose paths/SQL/source data
            self._send(503, b'{"error":"accounting_unavailable"}')

    def do_POST(self):
        self._send(405, b'{"error":"read_only"}')

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST


def serve(home: Path, config_path: Path | None = None, *, port=7474):
    reader = DashboardReader(home, config_path)
    reader.read()  # fail clearly on invalid paths/config before claiming readiness
    with DashboardServer(reader, port) as server:
        print(
            f"Token Terminator dashboard: http://localhost:{server.server_port} (read-only; Ctrl+C to stop)",
            flush=True,
        )
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
