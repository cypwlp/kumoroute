"""Inline site/style.css into every page and pin it with a CSP hash.

The stylesheet is the single source of truth; this script minifies it, inlines it
as <style data-inline-css> and rewrites the style-src directive so the CSP stays
strict (no 'unsafe-inline'). Inlining removes the one render-blocking request
before first paint.

  python scripts/inline_css.py           # regenerate
  python scripts/inline_css.py --check   # verify (used by CI)

Keep site/style.css for editing; never hand-edit the inlined <style> blocks.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
CSS = SITE / "style.css"
HEADERS = SITE / "_headers"

STYLE_OPEN = '<style data-inline-css>'
STYLE_RE = re.compile(r"<style data-inline-css>.*?</style>", re.S)
LINK_RE = re.compile(r'\s*<link rel="stylesheet" href="[^"]*">')
STYLE_SRC_RE = re.compile(r"style-src ([^;\"]*)")


def minify(css: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*([{};:,>])\s*", r"\1", text)
    text = text.replace(";}", "}")
    text = re.sub(r"(?<=\S) (?=[{}])", "", text)
    return text


def csp_hash(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def apply_csp(text: str, hash_value: str) -> str:
    return STYLE_SRC_RE.sub(f"style-src 'self' {hash_value}", text)


def render() -> tuple[str, str, dict[Path, str]]:
    css = minify(CSS.read_text(encoding="utf-8"))
    block = STYLE_OPEN + css + "</style>"
    want: dict[Path, str] = {}

    pages = sorted(SITE.glob("*.html")) + sorted(SITE.glob("*/*.html"))
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if STYLE_RE.search(text):
            text = STYLE_RE.sub(lambda _: block, text, count=1)
        else:
            text, n = LINK_RE.subn("\n" + block, text, count=1)
            if n == 0:
                raise SystemExit(f"{page}: no stylesheet link to replace")
        want[page] = text

    headers = HEADERS.read_text(encoding="utf-8")
    want[HEADERS] = headers
    return css, csp_hash(css), want


def apply(css: str, hash_value: str, files: dict[Path, str]) -> None:
    for path, text in files.items():
        if path == HEADERS or path.suffix == ".html":
            text = apply_csp(text, hash_value)
        path.write_text(text, encoding="utf-8", newline="\n")


def check(css: str, hash_value: str, files: dict[Path, str]) -> int:
    bad = []
    for path, text in files.items():
        expected = apply_csp(text, hash_value) if path == HEADERS or path.suffix == ".html" else text
        if path.read_text(encoding="utf-8") != expected:
            bad.append(path.relative_to(ROOT))
    if bad:
        print("inline CSS out of date in:", *bad, sep="\n  ")
        print("run: python scripts/inline_css.py")
        return 1
    print(f"inline CSS up to date ({len(css)} bytes, {hash_value})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    css, hash_value, files = render()
    if args.check:
        return check(css, hash_value, files)
    apply(css, hash_value, files)
    print(f"inlined {len(css)} bytes into {sum(p.suffix == '.html' for p in files)} pages ({hash_value})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
