"""Generate responsive WebP variants and the Open Graph card for site/.

Source images in packaging/screenshots/*.png (2240x1440 originals stay out of
the deployed tree). Outputs:

  site/assets/<name>-800.webp
  site/assets/<name>-1600.webp
  site/assets/og.jpg            1200x630 social card

Run after changing screenshots:

  python scripts/optimize_site_images.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "site" / "assets"
SRC = ROOT / "packaging" / "screenshots"

WIDTHS = (800, 1600)
QUALITY = 78
OG_SIZE = (1200, 630)
OG_BG = (7, 10, 16)


def webp_variants(path: Path) -> list[str]:
    """Write <name>-<width>.webp for every target width, return written names."""
    written: list[str] = []
    with Image.open(path) as img:
        img = img.convert("RGB")
        for width in WIDTHS:
            if width > img.width:
                continue
            height = round(img.height * width / img.width)
            out = ASSETS / f"{path.stem}-{width}.webp"
            img.resize((width, height), Image.LANCZOS).save(
                out, "WEBP", quality=QUALITY, method=6
            )
            written.append(f"{out.name} ({out.stat().st_size // 1024} KB)")
    return written


def og_card(source: Path) -> str:
    """Centre-crop the overview screenshot into a 1200x630 social card."""
    target_w, target_h = OG_SIZE
    with Image.open(source) as img:
        img = img.convert("RGB")
        scale = max(target_w / img.width, target_h / img.height)
        resized = img.resize(
            (round(img.width * scale), round(img.height * scale)), Image.LANCZOS
        )
        left = (resized.width - target_w) // 2
        top = (resized.height - target_h) // 2
        card = resized.crop((left, top, left + target_w, top + target_h))

    canvas = Image.new("RGB", OG_SIZE, OG_BG)
    canvas.paste(card, (0, 0))
    out = ASSETS / "og.jpg"
    canvas.save(out, "JPEG", quality=86, optimize=True, progressive=True)
    return f"{out.name} ({out.stat().st_size // 1024} KB)"


def main() -> int:
    sources = sorted(SRC.glob("*.png"))
    if not sources:
        print(f"no source screenshots found in {SRC}", file=sys.stderr)
        return 1

    summary: dict[str, list[str]] = {}
    for path in sources:
        summary[path.name] = webp_variants(path)

    overview = next((p for p in sources if "overview" in p.name), sources[0])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("og:", og_card(overview))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
