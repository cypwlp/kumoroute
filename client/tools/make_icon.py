"""Generate KumoRoute icon assets (PNG + ICO)."""

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "assets"
UI = HERE.parent / "ui"
TAURI = HERE.parents[1] / "tauri" / "icons"
SITE = HERE.parents[1] / "site" / "assets"


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def bezier(p0, p1, p2, p3, steps=72):
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        points.append((
            u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
        ))
    return points


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    S = 1024
    top, bottom = (91, 140, 255), (139, 92, 246)
    grad = Image.new("RGB", (1, S))
    for y in range(S):
        grad.putpixel((0, y), lerp(top, bottom, y / S))
    grad = grad.resize((S, S))

    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((56, 56, S - 56, S - 56), radius=230, fill=255)

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)

    d.rounded_rectangle((56, 56, S - 56, S - 56), radius=230, outline=(255, 255, 255, 48), width=6)

    # Abstract route: a winding path from a starting node to a target node.
    nodes = [(300, 742), (462, 500), (606, 548), (722, 332)]
    width = 84
    for a, b in zip(nodes, nodes[1:]):
        d.line((a, b), fill=(255, 255, 255, 238), width=width)
    for x, y in nodes[:-1]:
        r = width // 2
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 238))

    # Mint target node, intentionally distinct from letter-based marks.
    tx, ty = nodes[-1]
    d.ellipse((tx - 66, ty - 66, tx + 66, ty + 66), fill=(255, 255, 255, 245))
    d.ellipse((tx - 50, ty - 50, tx + 50, ty + 50), fill=(61, 220, 151, 255))

    master = img.resize((256, 256), Image.LANCZOS)
    for directory in (OUT, UI, TAURI, SITE):
        directory.mkdir(parents=True, exist_ok=True)
    master.save(OUT / "icon.png")
    master.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    master.save(UI / "icon.png")
    master.save(TAURI / "icon.png")
    master.save(TAURI / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    master.resize((128, 128), Image.LANCZOS).save(TAURI / "128x128.png")
    master.resize((32, 32), Image.LANCZOS).save(TAURI / "32x32.png")
    master.save(SITE / "icon.png")
    print("icons written for KumoRoute")


if __name__ == "__main__":
    main()
