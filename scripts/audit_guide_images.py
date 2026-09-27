"""Check local guide images for broken links and visually sparse screenshots."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image, ImageStat


IMAGE_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+\.(?:png|jpe?g|webp)(?:#[^)]*)?)\)", re.I)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guides", type=Path, default=Path("docs/guides"))
    parser.add_argument("--low-contrast", type=float, default=20.0)
    parser.add_argument("--min-width", type=int, default=1920)
    parser.add_argument("--min-height", type=int, default=1080)
    args = parser.parse_args()

    missing: list[str] = []
    undersized: dict[Path, tuple[int, int]] = {}
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
                if source.width < args.min_width or source.height < args.min_height:
                    undersized[target] = source.size
                sample = source.convert("RGB")
                sample.thumbnail((128, 72))
                contrast = sum(ImageStat.Stat(sample).stddev) / 3.0
                if contrast < args.low_contrast:
                    candidates[target] = (contrast, source.size)

    print(f"Checked {checked} local image references; missing {len(missing)}.")
    for item in missing:
        print(f"MISSING {item}")
    print(f"Below {args.min_width}x{args.min_height}: {len(undersized)}")
    for path, size in sorted(undersized.items()):
        print(f"UNDERSIZED {size[0]}x{size[1]} {path}")
    print(f"Low-contrast images to review: {len(candidates)}")
    for path, (contrast, size) in sorted(
        candidates.items(), key=lambda item: item[1][0]
    ):
        relative = path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path
        print(f"{contrast:5.1f}  {size[0]}x{size[1]}  {relative}")
    return 1 if missing or undersized else 0


if __name__ == "__main__":
    raise SystemExit(main())
