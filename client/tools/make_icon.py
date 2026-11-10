"""Generate MyClash icon assets (PNG + ICO)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "assets"
UI = HERE.parent / "ui"


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


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

    # subtle inner highlight ring
    d.rounded_rectangle((56, 56, S - 56, S - 56), radius=230, outline=(255, 255, 255, 48), width=6)

    # white M
    font = None
    for name in ("segoeuib.ttf", "arialbd.ttf"):
        try:
            font = ImageFont.truetype(f"C:/Windows/Fonts/{name}", 470)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    d.text((S / 2, S / 2 + 18), "M", font=font, fill=(255, 255, 255, 240), anchor="mm")

    # speed accent dot
    d.ellipse((S * 0.66, S * 0.24, S * 0.76, S * 0.34), fill=(61, 220, 151, 255))

    master = img.resize((256, 256), Image.LANCZOS)
    master.save(OUT / "icon.png")
    master.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    master.save(UI / "icon.png")
    print("icon written:", OUT / "icon.png", OUT / "icon.ico", UI / "icon.png")


if __name__ == "__main__":
    main()
