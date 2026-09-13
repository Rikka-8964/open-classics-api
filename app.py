#!/usr/bin/env python3
"""open-classics-api — HTTP entry point.

A dependency-free JSON API over the classical Chinese literature corpus in
``data/works.json``. Run it with:

    python app.py                 # http://127.0.0.1:8000
    PORT=3000 python app.py       # bind a specific port

The server binds ``0.0.0.0`` so it can be reached from outside a container.
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from classics import ClassicsStore, __version__

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Public-API hygiene: a small per-client sliding window so a single caller
# cannot monopolise the process. Deliberately in-memory — if this ever needs to
# scale horizontally, move the counter to shared storage first.
RATE_LIMIT_REQUESTS = 120
RATE_LIMIT_WINDOW = 60.0

STORE = ClassicsStore()

_metrics_lock = threading.Lock()
_metrics = {"requests": 0, "errors": 0, "started_at": time.time()}
_rate_buckets: dict[str, deque[float]] = {}


def _rate_limited(client_ip: str) -> bool:
    now = time.time()
    with _metrics_lock:
        bucket = _rate_buckets.setdefault(client_ip, deque())
        while bucket and now - bucket[0] > RATE_LIMIT_WINDOW:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_REQUESTS:
            return True
        bucket.append(now)
        # Opportunistic cleanup so the dict cannot grow without bound.
        if len(_rate_buckets) > 4096:
            for key in [k for k, v in _rate_buckets.items() if not v][:2048]:
                _rate_buckets.pop(key, None)
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = f"open-classics-api/{__version__}"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------- utilities

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # This is a public API: allow any origin to consume it.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, code: str, message: str) -> None:
        with _metrics_lock:
            _metrics["errors"] += 1
        self._json({"error": {"code": code, "message": message, "status": status}}, status)

    def _static(self, relative: str) -> None:
        safe = os.path.normpath(relative).lstrip("\\/")
        if safe.startswith(".."):
            self._error(400, "bad_path", "Path escapes the static directory.")
            return
        path = os.path.join(STATIC_DIR, safe)
        if not os.path.isfile(path):
            self._error(404, "not_found", f"No such static asset: {relative}")
            return
        ctype, _ = mimetypes.guess_type(path)
        with open(path, "rb") as fh:
            self._send(200, fh.read(), ctype or "application/octet-stream")

    # --------------------------------------------------------------- routing

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"", "text/plain")

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = unquote(parsed.path).rstrip("/") or "/"
        query = parse_qs(parsed.query)

        with _metrics_lock:
            _metrics["requests"] += 1

        if route.startswith("/api/"):
            if _rate_limited(self.client_address[0]):
                self._error(429, "rate_limited", "Too many requests. Please slow down.")
                return
            try:
                self._api(route, query)
            except BrokenPipeError:
                pass
            except Exception as exc:  # pragma: no cover - defensive
                self._error(500, "internal_error", str(exc))
            return

        if route == "/":
            self._static("index.html")
            return
        if route == "/favicon.ico":
            self._send(204, b"", "text/plain")
            return
        if route.startswith("/static/"):
            self._static(route[len("/static/") :])
            return
        self._error(404, "not_found", "Unknown route. See /api/openapi.json for the contract.")

    def _api(self, route: str, query: dict[str, list[str]]) -> None:
        one = lambda key, default=None: (query.get(key) or [default])[0]  # noqa: E731
        as_int = lambda key, default: int(one(key) or default)  # noqa: E731

        if route == "/api/health":
            self._json({"status": "ok", "version": __version__})
            return

        if route == "/api/stats":
            with _metrics_lock:
                served = _metrics["requests"]
                errors = _metrics["errors"]
                uptime = round(time.time() - _metrics["started_at"], 1)
            self._json(
                {
                    "corpus": STORE.stats(),
                    "service": {"requests_served": served, "errors": errors, "uptime_seconds": uptime},
                }
            )
            return

        if route == "/api/works":
            result = STORE.search(
                q=one("q"),
                author=one("author"),
                dynasty=one("dynasty"),
                genre=one("genre"),
                tag=one("tag"),
                page=as_int("page", 1),
                limit=as_int("limit", 20),
                sort=one("sort", "relevance") or "relevance",
            )
            self._json(result)
            return

        if route.startswith("/api/works/"):
            work = STORE.get(route[len("/api/works/") :])
            if not work:
                self._error(404, "work_not_found", "No work with that id.")
                return
            self._json(work)
            return

        if route == "/api/random":
            seed = one("seed")
            work = STORE.random(
                tag=one("tag"),
                dynasty=one("dynasty"),
                seed=int(seed) if seed else None,
            )
            if not work:
                self._error(404, "empty_pool", "No work matches those constraints.")
                return
            self._json(work)
            return

        if route in ("/api/authors", "/api/tags", "/api/dynasties", "/api/genres"):
            key = route[len("/api/") :]
            self._json({"items": STORE.facets()[key]})
            return

        if route == "/api/facets":
            self._json(STORE.facets())
            return

        if route == "/api/openapi.json":
            self._json(OPENAPI)
            return

        self._error(404, "not_found", "Unknown API route. See /api/openapi.json.")


OPENAPI = {
    "openapi": "3.1.0",
    "info": {
        "title": "open-classics-api",
        "version": __version__,
        "license": {"name": "MIT"},
        "description": (
            "An open, dependency-free JSON API over a curated corpus of "
            "public-domain classical Chinese poetry and prose. Built for "
            "learners, teachers and educational software."
        ),
    },
    "servers": [{"url": "/"}],
    "paths": {
        "/api/health": {"get": {"summary": "Liveness probe", "responses": {"200": {"description": "ok"}}}},
        "/api/stats": {"get": {"summary": "Corpus and service statistics"}},
        "/api/works": {
            "get": {
                "summary": "Search and filter works",
                "parameters": [
                    {"name": "q", "in": "query", "schema": {"type": "string"}, "description": "Free-text query. Multiple space-separated terms are combined with AND."},
                    {"name": "author", "in": "query", "schema": {"type": "string"}},
                    {"name": "dynasty", "in": "query", "schema": {"type": "string"}},
                    {"name": "genre", "in": "query", "schema": {"type": "string"}},
                    {"name": "tag", "in": "query", "schema": {"type": "string"}},
                    {"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}},
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 20, "maximum": 100}},
                    {"name": "sort", "in": "query", "schema": {"type": "string", "enum": ["relevance", "title", "author", "dynasty"]}},
                ],
            }
        },
        "/api/works/{id}": {"get": {"summary": "Fetch a single work by id"}},
        "/api/random": {
            "get": {
                "summary": "Random work",
                "parameters": [
                    {"name": "tag", "in": "query", "schema": {"type": "string"}},
                    {"name": "dynasty", "in": "query", "schema": {"type": "string"}},
                    {"name": "seed", "in": "query", "schema": {"type": "integer"}, "description": "Deterministic draw, useful for tests."},
                ],
            }
        },
        "/api/authors": {"get": {"summary": "Author facet counts"}},
        "/api/tags": {"get": {"summary": "Tag facet counts"}},
        "/api/dynasties": {"get": {"summary": "Dynasty facet counts"}},
        "/api/genres": {"get": {"summary": "Genre facet counts"}},
        "/api/facets": {"get": {"summary": "All facet counts in one call"}},
    },
}


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    stats = STORE.stats()
    print(f"open-classics-api {__version__}")
    print(f"  corpus : {stats['works']} works / {stats['authors']} authors / {stats['characters']} characters")
    print(f"  listen : http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
