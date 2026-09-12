"""Command-line client for the application's bounded HTTP automation API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.request
from typing import Any
from urllib.parse import urlsplit


def request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("automation URL must use HTTP or HTTPS")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - scheme checked above
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as response:  # noqa: S310 - scheme checked above
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Small HTTP client for GUI automation.")
    parser.add_argument("endpoint", help="Endpoint such as /health or /selection/mode")
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--payload", default="{}")
    parser.add_argument(
        "--payload64", default="", help="Base64 encoded JSON payload for shell-safe calls"
    )
    parser.add_argument("--method", default="POST")
    args = parser.parse_args()

    method = "GET" if args.endpoint in {"/health", "/state"} else args.method.upper()
    raw_payload = args.payload
    if args.payload64:
        raw_payload = base64.b64decode(args.payload64.encode("ascii")).decode("utf-8")
    payload = None if method == "GET" else json.loads(raw_payload)
    result = request(
        method,
        args.base.rstrip("/") + args.endpoint,
        payload,
        token=os.environ.get("FIVE_AXIS_SLICER_AUTOMATION_TOKEN"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
