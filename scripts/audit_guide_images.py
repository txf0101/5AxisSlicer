"""Check local guide images for broken links and visually sparse screenshots."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image, ImageStat


IMAGE_LINK = re.compile(r"!\[[^]]*\]\(([^)]+)\)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guides", type=Path, default=Path("docs/guides"))
    parser.add_argument("--low-contrast", type=float, default=20.0)
    args = parser.parse_args()

    missing: list[str] = []
    candidates: dict[Path, tuple[float, tuple[int, int]]] = {}
    checked = 0
    for document in sorted(args.guides.rglob("*.md")):
        for link in IMAGE_LINK.findall(document.read_text(encoding="utf-8")):
            if "://" in link or link.startswith("#"):
                continue
            target = (document.parent / link.split("#", 1)[0]).resolve()
            if not target.is_file():
                missing.append(f"{document}: {link}")
                continue
            checked += 1
            with Image.open(target) as source:
                sample = source.convert("RGB")
                sample.thumbnail((128, 72))
                contrast = sum(ImageStat.Stat(sample).stddev) / 3.0
                if contrast < args.low_contrast:
                    candidates[target] = (contrast, source.size)

    print(f"Checked {checked} local image references; missing {len(missing)}.")
    for item in missing:
        print(f"MISSING {item}")
    print(f"Low-contrast images to review: {len(candidates)}")
    for path, (contrast, size) in sorted(
        candidates.items(), key=lambda item: item[1][0]
    ):
        relative = path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path
        print(f"{contrast:5.1f}  {size[0]}x{size[1]}  {relative}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
