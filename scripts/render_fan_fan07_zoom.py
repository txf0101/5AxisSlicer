"""Render blade-focused crops from the verified FAN07 assembly preview."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/reviews/evidence/2026-09-20_fan_complete_program/fan06_fan07"
SOURCE = EVIDENCE / "fan_fan07_toolpath_preview.png"


def _render(
    crop_box, output_name: str, title: str, subtitle: str, *, clean_top_px: int = 0
) -> None:
    source = Image.open(SOURCE).convert("RGB")
    detail = source.crop(crop_box)
    if clean_top_px:
        ImageDraw.Draw(detail).rectangle((0, 0, detail.width, clean_top_px), fill=(250, 252, 254))
    canvas = Image.new("RGB", (2400, 1400), (238, 243, 248))
    available = (2320, 1240)
    scale = min(available[0] / detail.width, available[1] / detail.height)
    resized = detail.resize(
        (round(detail.width * scale), round(detail.height * scale)), Image.Resampling.LANCZOS
    )
    left = (canvas.width - resized.width) // 2
    top = 125 + (available[1] - resized.height) // 2
    canvas.paste(resized, (left, top))
    draw = ImageDraw.Draw(canvas)
    draw.text((55, 28), title, fill=(20, 31, 43), font=ImageFont.load_default(30))
    draw.text((55, 72), subtitle, fill=(74, 87, 101), font=ImageFont.load_default(17))
    draw.rounded_rectangle(
        (left - 2, top - 2, left + resized.width + 2, top + resized.height + 2),
        radius=12,
        outline=(188, 199, 211),
        width=3,
    )
    canvas.save(EVIDENCE / output_name)


def main() -> int:
    _render(
        (45, 150, 1290, 720),
        "fan_fan07_blade_zoom.png",
        "FAN07 blade 1 - enlarged complete path view",
        "Actual assembly-frame deposition paths; shell and 100% internal fill, root to tip",
        clean_top_px=28,
    )
    _render(
        (650, 250, 1320, 760),
        "fan_fan07_blade_root_zoom.png",
        "FAN07 blade 1 - enlarged root connection",
        "Detail of the blade root beside the upper hub; source path geometry is unchanged",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
