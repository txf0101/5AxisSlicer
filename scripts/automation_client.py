from __future__ import annotations

import argparse
import base64
import json
import urllib.request


def request(method: str, url: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Small HTTP client for GUI automation.")
    parser.add_argument("endpoint", help="Endpoint such as /health or /selection/mode")
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--payload", default="{}")
    parser.add_argument("--payload64", default="", help="Base64 encoded JSON payload for shell-safe calls")
    parser.add_argument("--method", default="POST")
    args = parser.parse_args()

    method = "GET" if args.endpoint in {"/health", "/state"} else args.method.upper()
    raw_payload = args.payload
    if args.payload64:
        raw_payload = base64.b64decode(args.payload64.encode("ascii")).decode("utf-8")
    payload = None if method == "GET" else json.loads(raw_payload)
    result = request(method, args.base.rstrip("/") + args.endpoint, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
