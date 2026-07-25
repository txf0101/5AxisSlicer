"""HTTP-to-Qt bridge for local test automation.

The default server is loopback-only.  A non-loopback bind requires an explicit
opt-in and a bearer token so a desktop test hook cannot become an unauthenticated
remote-control endpoint by changing one command-line argument.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from json import JSONDecodeError
from queue import Empty, Queue
from typing import Any
from urllib.parse import urlsplit

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

CommandHandler = Callable[[str, dict[str, Any]], dict[str, Any]]
Reply = Queue[tuple[bool, dict[str, Any] | str]]
DEFAULT_MAX_BODY_BYTES = 1_048_576
MIN_REMOTE_TOKEN_LENGTH = 32
READ_ONLY_GET_PATHS = frozenset(
    {
        "/health",
        "/state",
        "/model/state",
        "/project/state",
        "/results/state",
        "/results/perf",
        "/preview/state",
        "/preview/perf",
        "/tube/state",
    }
)


class AutomationRequestError(RuntimeError):
    """Request failure with a stable HTTP status code."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = int(status)


class AutomationBridge(QObject):
    """Deliver commands from HTTP worker threads to the Qt owner thread."""

    command = pyqtSignal(str, dict, object)


class _AutomationHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def is_loopback_host(host: str) -> bool:
    """Return whether *host* is an explicit loopback bind target."""

    normalized = str(host).strip().strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def validate_automation_bind(
    host: str,
    *,
    allow_remote: bool,
    token: str | None,
) -> None:
    """Reject accidental network exposure before the listening socket opens."""

    if is_loopback_host(host):
        return
    if not allow_remote:
        raise ValueError("non-loopback automation requires --allow-remote-automation")
    if token is None or len(token) < MIN_REMOTE_TOKEN_LENGTH:
        raise ValueError(
            f"remote automation token must contain at least {MIN_REMOTE_TOKEN_LENGTH} characters"
        )


def _parse_authority(value: str, *, field: str) -> tuple[str, int | None]:
    if not value or "," in value:
        raise AutomationRequestError(400, f"invalid {field} header")
    try:
        parsed = urlsplit(f"//{value}")
        port = parsed.port
    except ValueError as exc:
        raise AutomationRequestError(400, f"invalid {field} header") from exc
    if (
        parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise AutomationRequestError(400, f"invalid {field} header")
    return parsed.hostname, port


class AutomationServer(QObject):
    """Run the HTTP listener and synchronously marshal commands into Qt."""

    def __init__(
        self,
        host: str,
        port: int,
        handler: CommandHandler,
        *,
        allow_remote: bool = False,
        token: str | None = None,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        call_timeout_seconds: float = 120.0,
    ) -> None:
        super().__init__()
        validate_automation_bind(host, allow_remote=allow_remote, token=token)
        if not 0 <= int(port) <= 65_535:
            raise ValueError("automation port must be in [0, 65535]")
        if int(max_body_bytes) <= 0:
            raise ValueError("max_body_bytes must be positive")
        if float(call_timeout_seconds) <= 0.0:
            raise ValueError("call_timeout_seconds must be positive")

        self.host = str(host)
        self.port = int(port)
        self.handler = handler
        self.token = token
        self.max_body_bytes = int(max_body_bytes)
        self.call_timeout_seconds = float(call_timeout_seconds)
        self.bridge = AutomationBridge()
        self.bridge.command.connect(self._handle_on_qt_thread)
        self.httpd: _AutomationHttpServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        display_host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{display_host}:{self.port}"

    def start(self) -> None:
        if self.httpd is not None:
            return
        parent = self

        class RequestHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
                parent._handle_request(self, "GET")

            def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
                parent._handle_request(self, "POST")

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = _AutomationHttpServer((self.host, self.port), RequestHandler)
        self.httpd = server
        self.port = int(server.server_address[1])
        self.thread = threading.Thread(
            target=server.serve_forever,
            name="five-axis-slicer-automation",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        server, thread = self.httpd, self.thread
        self.httpd = None
        self.thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2.0)

    def _handle_request(self, request: BaseHTTPRequestHandler, method: str) -> None:
        try:
            path = urlsplit(request.path).path
            self._validate_http_boundary(request, method, path)
            self._authenticate(request)
            payload = self._read_payload(request, method)
            result = self.call(path, payload)
            self._send_json(request, 200, {"ok": True, **result})
        except AutomationRequestError as exc:
            self._send_json(request, exc.status, {"ok": False, "error": str(exc)})
        except Exception as exc:  # Domain failures are returned to automation clients.
            self._send_json(request, 500, {"ok": False, "error": str(exc)})

    def _validate_http_boundary(
        self,
        request: BaseHTTPRequestHandler,
        method: str,
        path: str,
    ) -> None:
        if method == "GET" and path not in READ_ONLY_GET_PATHS:
            raise AutomationRequestError(405, "GET is allowed only for read-only routes")
        if is_loopback_host(self.host):
            self._validate_loopback_host(request.headers.get("Host", ""))
            self._validate_loopback_origin(request.headers.get("Origin"))

    def _validate_loopback_host(self, authority: str) -> None:
        hostname, port = _parse_authority(authority, field="Host")
        if not is_loopback_host(hostname):
            raise AutomationRequestError(403, "loopback automation requires a loopback Host")
        if port is not None and port != self.port:
            raise AutomationRequestError(403, "automation Host port does not match the listener")

    def _validate_loopback_origin(self, origin: str | None) -> None:
        if origin is None:
            return
        try:
            parsed = urlsplit(origin)
            port = parsed.port
        except ValueError as exc:
            raise AutomationRequestError(403, "invalid automation Origin") from exc
        default_port = 80 if parsed.scheme.lower() == "http" else 443
        origin_port = default_port if port is None else port
        valid = (
            parsed.scheme.lower() == "http"
            and parsed.hostname is not None
            and is_loopback_host(parsed.hostname)
            and origin_port == self.port
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
        )
        if not valid:
            raise AutomationRequestError(403, "browser Origin is not the automation listener")

    def _authenticate(self, request: BaseHTTPRequestHandler) -> None:
        if self.token is None:
            return
        authorization = request.headers.get("Authorization", "")
        candidate = (
            authorization[7:]
            if authorization.lower().startswith("bearer ")
            else request.headers.get("X-Automation-Token", "")
        )
        if not compare_digest(candidate, self.token):
            raise AutomationRequestError(401, "invalid or missing automation token")

    def _read_payload(self, request: BaseHTTPRequestHandler, method: str) -> dict[str, Any]:
        if method == "GET":
            return {}
        raw_length = request.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise AutomationRequestError(400, "invalid Content-Length") from exc
        if length < 0:
            raise AutomationRequestError(400, "invalid Content-Length")
        if length > self.max_body_bytes:
            raise AutomationRequestError(413, "automation request body is too large")
        body = request.rfile.read(length) if length else b"{}"
        # Read the bounded body before rejecting its media type. Closing a
        # Windows socket with unread request bytes can hide the 415 response.
        media_type = request.headers.get("Content-Type", "").partition(";")[0].strip().lower()
        if media_type != "application/json":
            raise AutomationRequestError(415, "POST requests must use application/json")
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, JSONDecodeError) as exc:
            raise AutomationRequestError(400, "request body must be UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise AutomationRequestError(400, "request JSON must be an object")
        return payload

    def call(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path == "/health":
            return self.handler(path, payload)
        reply: Reply = Queue(maxsize=1)
        self.bridge.command.emit(path, payload, reply)
        try:
            ok, result = reply.get(timeout=self.call_timeout_seconds)
        except Empty as exc:
            raise AutomationRequestError(504, "Qt automation command timed out") from exc
        if ok:
            return result if isinstance(result, dict) else {"result": result}
        raise RuntimeError(str(result))

    @pyqtSlot(str, dict, object)
    def _handle_on_qt_thread(self, path: str, payload: dict[str, Any], reply: Reply) -> None:
        try:
            reply.put_nowait((True, self.handler(path, payload)))
        except Exception as exc:
            reply.put_nowait((False, str(exc)))

    @staticmethod
    def _send_json(
        request: BaseHTTPRequestHandler,
        status: int,
        payload: dict[str, Any],
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request.send_response(status)
        request.send_header("Content-Type", "application/json; charset=utf-8")
        request.send_header("Content-Length", str(len(data)))
        request.send_header("Cache-Control", "no-store")
        request.end_headers()
        request.wfile.write(data)


__all__ = [
    "AutomationRequestError",
    "AutomationServer",
    "READ_ONLY_GET_PATHS",
    "is_loopback_host",
    "validate_automation_bind",
]
