from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.automation import (
    READ_ONLY_GET_PATHS,
    AutomationServer,
    is_loopback_host,
    validate_automation_bind,
)


def _health(_path: str, _payload: dict[str, object]) -> dict[str, object]:
    return {"status": "ready"}


def test_loopback_detection_is_explicit() -> None:
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("::1")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("0.0.0.0")
    assert not is_loopback_host("workstation.example")


def test_remote_bind_requires_opt_in_and_strong_token() -> None:
    with pytest.raises(ValueError, match="allow-remote"):
        validate_automation_bind("0.0.0.0", allow_remote=False, token=None)
    with pytest.raises(ValueError, match="at least 32"):
        validate_automation_bind("0.0.0.0", allow_remote=True, token="short")
    validate_automation_bind("0.0.0.0", allow_remote=True, token="x" * 32)


def test_configured_token_protects_http_requests() -> None:
    token = "test-token-" + "x" * 32
    server = AutomationServer("127.0.0.1", 0, _health, token=token)
    server.start()
    try:
        with pytest.raises(HTTPError) as missing:
            urlopen(server.url + "/health", timeout=2.0)
        assert missing.value.code == 401
        missing.value.close()

        request = Request(
            server.url + "/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urlopen(request, timeout=2.0) as response:
            payload = json.load(response)
        assert payload == {"ok": True, "status": "ready"}
    finally:
        server.stop()


def test_loopback_rejects_get_for_mutating_route() -> None:
    server = AutomationServer("127.0.0.1", 0, _health)
    server.start()
    try:
        with pytest.raises(HTTPError) as rejected:
            urlopen(server.url + "/demo/load", timeout=2.0)
        assert rejected.value.code == 405
        rejected.value.close()
    finally:
        server.stop()


@pytest.mark.parametrize("path", ("/results/perf", "/preview/perf"))
def test_loopback_allows_get_for_performance_state(path: str) -> None:
    assert path in READ_ONLY_GET_PATHS


def test_loopback_post_requires_json_media_type() -> None:
    server = AutomationServer("127.0.0.1", 0, _health)
    server.start()
    try:
        request = Request(
            server.url + "/health",
            data=b"{}",
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        with pytest.raises(HTTPError) as rejected:
            urlopen(request, timeout=2.0)
        assert rejected.value.code == 415
        rejected.value.close()
    finally:
        server.stop()


@pytest.mark.parametrize(
    ("header", "value"),
    (
        ("Host", "attacker.example"),
        ("Origin", "https://attacker.example"),
    ),
)
def test_loopback_rejects_untrusted_browser_authority(header: str, value: str) -> None:
    server = AutomationServer("127.0.0.1", 0, _health)
    server.start()
    try:
        request = Request(server.url + "/health", headers={header: value})
        with pytest.raises(HTTPError) as rejected:
            urlopen(request, timeout=2.0)
        assert rejected.value.code == 403
        rejected.value.close()
    finally:
        server.stop()


def test_loopback_accepts_script_json_and_same_origin_browser_requests() -> None:
    server = AutomationServer("127.0.0.1", 0, _health)
    server.start()
    try:
        for headers in (
            {"Content-Type": "application/json"},
            {"Content-Type": "application/json", "Origin": server.url},
        ):
            request = Request(
                server.url + "/health",
                data=b"{}",
                headers=headers,
                method="POST",
            )
            with urlopen(request, timeout=2.0) as response:
                assert json.load(response) == {"ok": True, "status": "ready"}
    finally:
        server.stop()
