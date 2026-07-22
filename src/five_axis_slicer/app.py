from __future__ import annotations

import argparse
import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from .ui import MainWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="5AxisSclicer V2.0 workbench and NC preview")
    parser.add_argument("--model", help="STEP/STP file to open on startup")
    parser.add_argument("--gcode", help="NC/G-code file to open on startup")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Load the built-in impeller STEP and complete G-code project",
    )
    parser.add_argument("--results", action="store_true", help="Open the slicing-result preview page")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP automation host")
    parser.add_argument("--port", default=8765, type=int, help="HTTP automation port")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = QApplication(sys.argv[:1])
    window = MainWindow(http_host=args.host, http_port=args.port)
    window.show()
    for viewer in (window.viewer, window.result_page.viewer):
        if hasattr(viewer, "Initialize"):
            viewer.Initialize()

    def load_startup_inputs() -> None:
        if args.demo:
            window.load_results_demo()
            return
        if args.results:
            window.show_results_page()
            if args.model or args.gcode:
                window.start_result_load(model_path=args.model, gcode_path=args.gcode)
            return
        if args.model:
            window.open_model(args.model)
        if args.gcode:
            window.open_gcode(args.gcode)

    if args.demo or args.results or args.model or args.gcode:
        QTimer.singleShot(100, load_startup_inputs)

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
