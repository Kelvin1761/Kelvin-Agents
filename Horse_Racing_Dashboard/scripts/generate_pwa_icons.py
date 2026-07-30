"""Generate the 旺財 Dashboard PWA app icons.

The icons are committed under `Horse_Racing_Dashboard/pwa/` so `deploy.sh` never
needs Pillow (or a CJK font) on the deploying machine — this script only has to
run when the icon design itself changes:

    python3 Horse_Racing_Dashboard/scripts/generate_pwa_icons.py

Outputs:
    icon-180.png           apple-touch-icon (iOS home screen)
    icon-192.png           manifest icon, purpose="any"
    icon-512.png           manifest icon, purpose="any" / splash source
    icon-512-maskable.png  manifest icon, purpose="maskable" (Android adaptive)

iOS applies its own rounded-rect mask to apple-touch-icon, so the "any" icons
are deliberately full-bleed squares with no transparency and no self-drawn
corner radius. The maskable variant keeps the glyph inside the inner 80% safe
zone that the maskable spec guarantees will survive any platform mask shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "pwa"

GLYPH = "旺"
# Deep blue → brand blue, matching --sport-accent / .sport-switch--active (#1E40AF)
# and the <meta name="theme-color"> in static_template.html.
GRADIENT_TOP = (30, 58, 138)     # #1E3A8A
GRADIENT_BOTTOM = (37, 99, 235)  # #2563EB

# STHeiti Medium has the weight to stay legible at 60px on a home screen;
# Hiragino Sans GB is the fallback. Both ship with macOS.
FONT_CANDIDATES = (
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit(
        "❌ 搵唔到 CJK 字體，無法生成 icon。已試："
        + ", ".join(FONT_CANDIDATES)
    )


def _gradient(size: int) -> Image.Image:
    """Vertical two-stop gradient, drawn a row at a time."""
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(size - 1, 1)
        draw.line(
            [(0, y), (size, y)],
            fill=tuple(
                round(GRADIENT_TOP[i] + (GRADIENT_BOTTOM[i] - GRADIENT_TOP[i]) * t)
                for i in range(3)
            ),
        )
    return img


def build_icon(size: int, *, glyph_ratio: float) -> Image.Image:
    """Render one icon.

    `glyph_ratio` is the glyph's target height as a fraction of the canvas —
    0.62 for the plain icons, 0.46 for maskable so the glyph stays inside the
    inner 80% safe zone even after a circular mask.
    """
    img = _gradient(size)
    draw = ImageDraw.Draw(img)

    # Binary-search the point size that lands the glyph on the target height,
    # rather than guessing a ratio: CJK faces vary a lot in how much of the em
    # box the ink actually fills.
    target = size * glyph_ratio
    lo, hi = 8, size * 2
    font = _load_font(lo)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = _load_font(mid)
        left, top, right, bottom = draw.textbbox((0, 0), GLYPH, font=candidate)
        if max(right - left, bottom - top) <= target:
            font, lo = candidate, mid
        else:
            hi = mid - 1

    left, top, right, bottom = draw.textbbox((0, 0), GLYPH, font=font)
    # Centre on the ink bounding box, not the em box, so the glyph is optically
    # centred instead of sitting low.
    draw.text(
        ((size - (right - left)) / 2 - left, (size - (bottom - top)) / 2 - top),
        GLYPH,
        font=font,
        fill=(255, 255, 255),
    )
    return img


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = (
        ("icon-180.png", 180, 0.62),
        ("icon-192.png", 192, 0.62),
        ("icon-512.png", 512, 0.62),
        ("icon-512-maskable.png", 512, 0.46),
    )
    for name, size, ratio in targets:
        path = OUT_DIR / name
        build_icon(size, glyph_ratio=ratio).save(path, "PNG", optimize=True)
        print(f"✅ {name}  {size}×{size}  {path.stat().st_size / 1024:.1f} KB")
    print(f"\n📂 輸出目錄：{OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
