from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import json
import time
import urllib.request
from pathlib import Path

from PIL import ImageGrab


SW_RESTORE = 9
SW_MAXIMIZE = 3
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
WM_CLOSE = 0x0010
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002

user32 = ctypes.windll.user32


def enum_windows() -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                result.append((hwnd, buffer.value))
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return result


def find_window(title_contains: str, timeout: float = 40.0) -> int:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        for hwnd, title in enum_windows():
            if title_contains in title:
                return hwnd
        time.sleep(0.25)
    raise RuntimeError(f"Window not found: {title_contains}")


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def focus_and_resize(hwnd: int, width: int = 1500, height: int = 900) -> tuple[int, int, int, int]:
    screen_width = user32.GetSystemMetrics(0)
    width = min(width, max(screen_width - 40, 900))
    x = max(0, min(30, screen_width - width - 20))
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.MoveWindow(hwnd, x, 50, width, height, True)
    time.sleep(0.25)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, x, 50, width, height, SWP_SHOWWINDOW)
    user32.BringWindowToTop(hwnd)
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetActiveWindow(hwnd)
    user32.SetFocus(hwnd)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, x, 50, width, height, SWP_SHOWWINDOW)
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    time.sleep(1.5)
    return window_rect(hwnd)


def screenshot(hwnd: int, output: Path) -> str:
    left, top, right, bottom = window_rect(hwnd)
    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return str(output)


def http_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_state(base: str, timeout: float = 90.0) -> dict:
    deadline = time.perf_counter() + timeout
    last_error = ""
    last_visible = -1
    stable_seen = 0
    while time.perf_counter() < deadline:
        try:
            state = http_json(base.rstrip("/") + "/state")
            preview = state.get("preview", {}).get("summary")
            visible = state.get("preview", {}).get("visible_path_segment_count", 0)
            if preview and preview.get("segment_count", 0) > 0 and visible > 0:
                if visible == last_visible:
                    stable_seen += 1
                else:
                    stable_seen = 0
                    last_visible = visible
                if stable_seen >= 2:
                    return state
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Preview state not ready: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Workbench UI smoke test for 5AxisSclicer.")
    parser.add_argument("--title", default="5AxisSclicer V2.0")
    parser.add_argument("--base", default="http://127.0.0.1:8769")
    parser.add_argument("--out", default="outputs/workbench_smoke")
    args = parser.parse_args()

    out_dir = Path(args.out)
    state = wait_state(args.base)
    hwnd = find_window(args.title)
    rect = focus_and_resize(hwnd)
    final_state = http_json(args.base.rstrip("/") + "/state")
    time.sleep(1.0)
    image_path = screenshot(hwnd, out_dir / "01_workbench_preview.png")
    summary = {
        "window_rect": rect,
        "state": final_state,
        "screenshots": [image_path],
    }
    output = out_dir / "summary.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
