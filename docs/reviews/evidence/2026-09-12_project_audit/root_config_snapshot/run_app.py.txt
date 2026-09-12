from __future__ import annotations

import sys
from pathlib import Path


def run() -> int:
    """Start from an uninstalled checkout; packaged users call the console script."""
    source_root = Path(__file__).resolve().parent / "src"
    sys.path.insert(0, str(source_root))

    from five_axis_slicer.app import main

    return main()


if __name__ == "__main__":
    raise SystemExit(run())
