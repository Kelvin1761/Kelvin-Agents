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

Two sources of artwork:

    (default)          render the CJK glyph in GLYPH on the brand gradient
    --source LOGO.png  use your own image / logo

`--source` picks its fit automatically: an image with real transparency (a logo)
is centred on the brand gradient at 62% of the canvas, an opaque image (a photo,
a finished square icon) is cover-cropped full-bleed. Override with
`--fit contain|cover`.

iOS applies its own rounded-rect mask to apple-touch-icon, so the "any" icons
are deliberately full-bleed squares with no transparency and no self-drawn
corner radius. The maskable variant keeps the artwork inside the inner 80% safe
zone that the maskable spec guarantees will survive any platform mask shape.

⚠️ iOS caches home-screen icons for the life of the installed app. After
changing the icon and deploying, every user has to DELETE the home-screen icon
and re-add the site — there is no way to push a new icon to an existing install.
"""

from __future__ import annotations

import argparse
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


def _has_transparency(img: Image.Image) -> bool:
    """True if the image carries alpha that actually does something.

    A logo exported as RGBA is almost always mostly-transparent; a photo saved
    as RGBA has a fully opaque alpha channel. Checking the channel minimum tells
    the two apart, which is what decides contain-vs-cover below.
    """
    if img.mode not in ("RGBA", "LA", "P"):
        return False
    rgba = img.convert("RGBA")
    return rgba.getchannel("A").getextrema()[0] < 250


def build_icon_from_source(
    source: Image.Image, size: int, *, fit: str, art_ratio: float
) -> Image.Image:
    """Render one icon from a supplied image.

    `fit="cover"` crops the source to a square and fills the whole canvas —
    right for a photo or an already-finished square icon.
    `fit="contain"` puts the source on the brand gradient at `art_ratio` of the
    canvas — right for a logo, and the only option that keeps a maskable icon's
    artwork inside the safe zone.
    """
    if fit == "cover":
        src = source.convert("RGB")
        # Scale so the SHORT side reaches `size`, then centre-crop the overflow.
        scale = size / min(src.size)
        scaled = src.resize(
            (max(round(src.width * scale), size), max(round(src.height * scale), size)),
            Image.LANCZOS,
        )
        left = (scaled.width - size) // 2
        top = (scaled.height - size) // 2
        canvas = scaled.crop((left, top, left + size, top + size))
        if art_ratio >= 0.62:
            return canvas
        # Maskable: a cover crop would lose the edges to the platform mask, so
        # inset the same crop onto the gradient instead of trusting the bleed.
        inner = round(size * art_ratio / 0.62 * 0.8)
        out = _gradient(size)
        out.paste(canvas.resize((inner, inner), Image.LANCZOS),
                  ((size - inner) // 2, (size - inner) // 2))
        return out

    # contain — composite the artwork onto the brand gradient.
    src = source.convert("RGBA")
    target = round(size * art_ratio)
    scale = target / max(src.size)
    art = src.resize(
        (max(round(src.width * scale), 1), max(round(src.height * scale), 1)),
        Image.LANCZOS,
    )
    out = _gradient(size).convert("RGBA")
    out.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2))
    # Flatten: the "any" icons must have no transparency (iOS renders alpha black).
    return out.convert("RGB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="生成旺財 Dashboard PWA app icons（預設畫 CJK 字，或用 --source 用自訂圖）"
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="自訂圖片／logo 路徑（PNG / JPG）。唔傳就照畫 GLYPH 個字。",
    )
    parser.add_argument(
        "--fit",
        choices=("auto", "contain", "cover"),
        default="auto",
        help="contain = logo 置中喺品牌漸變上；cover = 滿版裁切。"
        "auto（預設）：有透明度就 contain，冇就 cover。",
    )
    args = parser.parse_args(argv)

    source = None
    fit = args.fit
    if args.source is not None:
        if not args.source.exists():
            raise SystemExit(f"❌ 搵唔到來源圖片：{args.source}")
        source = Image.open(args.source)
        if fit == "auto":
            fit = "contain" if _has_transparency(source) else "cover"
        smallest = min(source.size)
        if smallest < 512:
            print(
                f"⚠️ 來源圖最短邊只有 {smallest}px —— 512 icon 會被放大，會見到糊。"
                " 建議俾一張 1024×1024 或以上。"
            )
        print(f"🖼️ 來源：{args.source.name}  {source.width}×{source.height}  fit={fit}")
    else:
        print(f"🖼️ 來源：內建字形「{GLYPH}」")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # `ratio` is the artwork's target size as a fraction of the canvas. The
    # maskable entry is smaller on purpose — see the module docstring.
    targets = (
        ("icon-180.png", 180, 0.62),
        ("icon-192.png", 192, 0.62),
        ("icon-512.png", 512, 0.62),
        ("icon-512-maskable.png", 512, 0.46),
    )
    for name, size, ratio in targets:
        path = OUT_DIR / name
        if source is None:
            img = build_icon(size, glyph_ratio=ratio)
        else:
            img = build_icon_from_source(source, size, fit=fit, art_ratio=ratio)
        img.save(path, "PNG", optimize=True)
        print(f"✅ {name}  {size}×{size}  {path.stat().st_size / 1024:.1f} KB")
    print(f"\n📂 輸出目錄：{OUT_DIR}")
    print("⚠️ deploy 之後，每個用戶要刪掉主畫面圖示再重新「加入主畫面」先會見到新 icon。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
