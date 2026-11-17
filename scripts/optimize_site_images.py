"""Generate responsive AVIF/WebP variants and the Open Graph card for site/.

Source images live in packaging/screenshots/*.png so the 2240x1440 originals
stay out of the deployed tree. Outputs:

  site/assets/<name>-<width>.avif   AVIF q60, served first via <picture>
  site/assets/<name>-<width>.webp   WebP fallback (includes Safari < 16.4)
  site/assets/og.jpg                1200x630 social card (JPEG for crawlers)

AVIF needs ImageMagick with libheif; the script degrades to WebP-only when it
is missing, so contributors without it can still regenerate the site.

Run after changing screenshots:

  python scripts/optimize_site_images.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "site" / "assets"
SRC = ROOT / "packaging" / "screenshots"

WIDTHS = (800, 1600)
WEBP_QUALITY = 78
AVIF_QUALITY = 60
OG_SIZE = (1200, 630)
OG_BG = (7, 10, 16)


def have_magick() -> bool:
    return shutil.which("magick") is not None


def webp_variants(path: Path) -> list[str]:
    written: list[str] = []
    with Image.open(path) as img:
        img = img.convert("RGB")
        for width in WIDTHS:
            if width > img.width:
                continue
            height = round(img.height * width / img.width)
            out = ASSETS / f"{path.stem}-{width}.webp"
            img.resize((width, height), Image.LANCZOS).save(
                out, "WEBP", quality=WEBP_QUALITY, method=6
            )
            written.append(out)
    return written


def avif_variants(path: Path) -> list[str]:
    written: list[str] = []
    for width in WIDTHS:
        out = ASSETS / f"{path.stem}-{width}.avif"
        subprocess.run(
            [
                "magick",
                str(path),
                "-resize",
                f"{width}x",
                "-depth",
                "8",
                "-quality",
                str(AVIF_QUALITY),
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        written.append(out)
    return written


def og_card(source: Path) -> Path:
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
    return out


def main() -> int:
    sources = sorted(SRC.glob("*.png"))
    if not sources:
        print(f"no source screenshots found in {SRC}", file=sys.stderr)
        return 1

    avif = have_magick()
    if not avif:
        print("ImageMagick not found - skipping AVIF, keeping WebP only")

    summary: dict[str, dict[str, str]] = {}
    for path in sources:
        files = webp_variants(path)
        if avif:
            files += avif_variants(path)
        summary[path.name] = {
            f.name: f"{f.stat().st_size // 1024} KB" for f in sorted(files)
        }

    overview = next((p for p in sources if "overview" in p.name), sources[0])
    og = og_card(overview)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("og:", og.name, f"{og.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
