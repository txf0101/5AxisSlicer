from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from pathlib import Path

from PIL import ImageGrab

SW_RESTORE = 9
SWP_SHOWWINDOW = 0x0040
HWND_NOTOPMOST = -2
WM_CLOSE = 0x0010
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

user32 = ctypes.windll.user32
user32.MoveWindow.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.wintypes.BOOL,
]
user32.MoveWindow.restype = ctypes.wintypes.BOOL


def enum_windows() -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def callback(hwnd: int, lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                result.append((hwnd, buffer.value))
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return result


def find_window(title_contains: str, timeout: float = 30.0) -> int:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        for hwnd, title in enum_windows():
            if title_contains in title:
                return hwnd
        time.sleep(0.25)
    raise RuntimeError(f"Window not found: {title_contains}")


def close_dialogs(titles: Iterable[str]) -> None:
    for hwnd, title in enum_windows():
        if any(token in title for token in titles):
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def focus_and_resize(hwnd: int, width: int = 1400, height: int = 860) -> tuple[int, int, int, int]:
    screen_width = user32.GetSystemMetrics(0)
    width = min(width, max(screen_width - 40, 900))
    x = max(0, min(40, screen_width - width - 20))
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.MoveWindow(hwnd, x, 60, width, height, True)
    time.sleep(0.2)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, x, 60, width, height, SWP_SHOWWINDOW)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    return window_rect(hwnd)


def screenshot(hwnd: int, output: Path) -> None:
    left, top, right, bottom = window_rect(hwnd)
    image = ImageGrab.grab(bbox=(left, top, right, bottom))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def click_abs(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.08)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.25)


def http_json(method: str, url: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post(base: str, endpoint: str, payload: dict) -> dict:
    return http_json("POST", base.rstrip("/") + endpoint, payload)


def post_expect_error(base: str, endpoint: str, payload: dict) -> dict:
    try:
        return post(base, endpoint, payload)
    except urllib.error.HTTPError as exc:
        data = exc.read().decode("utf-8")
        return json.loads(data)
    raise RuntimeError(f"Expected HTTP error from {endpoint}")


def state(base: str) -> dict:
    return http_json("GET", base.rstrip("/") + "/state")


def body_list_candidates(rect: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    left, top, right, bottom = rect
    x_values = [right - 245, right - 190, right - 135]
    y_values = [top + 190 + step * 28 for step in range(8)]
    return [(x, y) for y in y_values for x in x_values if left < x < right and top < y < bottom]


def viewer_candidates(rect: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    left, top, right, bottom = rect
    x0 = left + 260
    x1 = right - 330
    y0 = top + 115
    y1 = bottom - 80
    points: list[tuple[int, int]] = []
    for y_frac in (0.44, 0.50, 0.56, 0.38, 0.62):
        for x_frac in (0.35, 0.42, 0.50, 0.58, 0.65, 0.72):
            x = int(x0 + (x1 - x0) * x_frac)
            y = int(y0 + (y1 - y0) * y_frac)
            if left < x < right and top < y < bottom:
                points.append((x, y))
    for x_frac in (0.30, 0.40, 0.50, 0.60, 0.70):
        for y_frac in (0.30, 0.40, 0.50, 0.60, 0.70):
            x = int(x0 + (x1 - x0) * x_frac)
            y = int(y0 + (y1 - y0) * y_frac)
            points.append((x, y))
    return points


def click_until(base: str, candidates: list[tuple[int, int]], key: str) -> tuple[int, int, dict]:
    for x, y in candidates:
        click_abs(x, y)
        current = state(base)
        if current["selection"][key]:
            return x, y, current
    raise RuntimeError(f"No selection after {len(candidates)} clicks for {key}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Desktop mouse-click smoke test for 5AxisSclicer.")
    parser.add_argument("--title", default="5AxisSclicer V2.0")
    parser.add_argument("--base", default="http://127.0.0.1:8767")
    parser.add_argument("--out", default="outputs/desktop_click_test")
    args = parser.parse_args()

    out_dir = Path(args.out)
    close_dialogs(["打开 STEP", "Open STEP"])
    time.sleep(0.5)
    hwnd = find_window(args.title)
    rect = focus_and_resize(hwnd)
    screenshot(hwnd, out_dir / "01_initial.png")

    post(args.base, "/selection/clear", {})
    body_x, body_y, body_state = click_until(args.base, body_list_candidates(rect), "body_ids")
    screenshot(hwnd, out_dir / "02_body_list_selected.png")

    post(args.base, "/selection/clear", {})
    post(args.base, "/selection/mode", {"mode": "edge"})
    screenshot(hwnd, out_dir / "03_edge_preview_mode.png")
    edge_x, edge_y, edge_state = click_until(args.base, viewer_candidates(rect), "edge_ids")
    screenshot(hwnd, out_dir / "04_edge_selected.png")
    mode_error = post_expect_error(args.base, "/selection/mode", {"mode": "body"})
    if mode_error.get("ok") is not False or "edge mode" not in mode_error.get("error", ""):
        raise RuntimeError(f"Unexpected /selection/mode body response: {mode_error}")

    summary = {
        "window_rect": rect,
        "body_list_click": [body_x, body_y],
        "body_selection": body_state["selection"],
        "edge_click": [edge_x, edge_y],
        "edge_selection": edge_state["selection"],
        "body_mode_error": mode_error,
        "screenshots": [
            str(out_dir / "01_initial.png"),
            str(out_dir / "02_body_list_selected.png"),
            str(out_dir / "03_edge_preview_mode.png"),
            str(out_dir / "04_edge_selected.png"),
        ],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
