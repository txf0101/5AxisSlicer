from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from typing import Any, Callable

from PyQt5.QtCore import QObject, pyqtSignal


CommandHandler = Callable[[str, dict[str, Any]], dict[str, Any]]


class AutomationBridge(QObject):
    command = pyqtSignal(str, dict, object)


class AutomationServer:
    def __init__(self, host: str, port: int, handler: CommandHandler) -> None:
        self.host = host
        self.port = port
        self.handler = handler
        self.bridge = AutomationBridge()
        self.bridge.command.connect(self._handle_on_qt_thread)
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        parent = self

        class RequestHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib API
                parent._handle_request(self, "GET")

            def do_POST(self) -> None:  # noqa: N802 - stdlib API
                parent._handle_request(self, "POST")

            def log_message(self, format: str, *args: object) -> None:
                return

        self.httpd = ThreadingHTTPServer((self.host, self.port), RequestHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None

    def _handle_request(self, request: BaseHTTPRequestHandler, method: str) -> None:
        try:
            length = int(request.headers.get("Content-Length", "0"))
            body = request.rfile.read(length) if length else b"{}"
            payload = json.loads(body.decode("utf-8") or "{}") if method == "POST" else {}
            result = self.call(request.path, payload)
            self._send_json(request, 200, {"ok": True, **result})
        except Exception as exc:  # pragma: no cover - exercised through GUI smoke tests
            self._send_json(request, 500, {"ok": False, "error": str(exc)})

    def call(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path in {"/health", "/state"}:
            return self.handler(path, payload)
        queue: Queue[tuple[bool, dict[str, Any] | str]] = Queue(maxsize=1)
        self.bridge.command.emit(path, payload, queue)
        ok, result = queue.get(timeout=30.0)
        if ok:
            return result if isinstance(result, dict) else {"result": result}
        raise RuntimeError(str(result))

    def _handle_on_qt_thread(self, path: str, payload: dict[str, Any], queue: Queue) -> None:
        try:
            queue.put((True, self.handler(path, payload)))
        except Exception as exc:
            queue.put((False, str(exc)))

    @staticmethod
    def _send_json(request: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request.send_response(status)
        request.send_header("Content-Type", "application/json; charset=utf-8")
        request.send_header("Content-Length", str(len(data)))
        request.end_headers()
        request.wfile.write(data)

