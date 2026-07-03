from __future__ import annotations

import argparse
import sys

from PyQt5.QtWidgets import QApplication

from .ui import MainWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="5AxisSclicer V2.0 STEP selector")
    parser.add_argument("--model", help="STEP/STP file to open on startup")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP automation host")
    parser.add_argument("--port", default=8765, type=int, help="HTTP automation port")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = QApplication(sys.argv[:1])
    window = MainWindow(http_host=args.host, http_port=args.port)
    if args.model:
        window.open_model(args.model)
    window.show()
    window.viewer.Initialize()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
