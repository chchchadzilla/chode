#!/usr/bin/env python3
"""Regenerate CHODE's own brand assets (banner + icon) with the built-in generator.

    python scripts/make_brand.py [--font path/to/Heavy.ttf]

Outputs: assets/banner.png, assets/banner.svg, assets/icon.svg, assets/icon.png, assets/social.png
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chode import TAGLINE  # noqa: E402
from chode.banner import collision_png, collision_svg, find_font, icon_svg  # noqa: E402

MAGENTA, CYAN = "#ff3fb3", "#2ee6ff"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", help="heavy display font (.ttf/.otf)")
    args = ap.parse_args()
    font = args.font or find_font()
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    tag = f"code {TAGLINE.replace('code ', '', 1)}"
    print("font:", font or "(Pillow default)")
    print("svg :", collision_svg("CHAD", "CODE", "CHODE", tag, out / "banner.svg", MAGENTA, CYAN, seed=42,
                                 subtitle="the coding harness that keeps your repo in ORDER"))
    png = collision_png("CHAD", "CODE", "CHODE", tag, out / "banner.png", MAGENTA, CYAN, seed=42, font_path=font,
                        subtitle="the coding harness that keeps your repo in ORDER")
    print("png :", png or "(Pillow missing — skipped)")
    social = collision_png("CHAD", "CODE", "CHODE", tag, out / "social.png", MAGENTA, CYAN, width=1280, height=640,
                           seed=42, font_path=font)
    print("og  :", social or "(skipped)")
    print("icon:", icon_svg(out / "icon.svg", MAGENTA, CYAN))
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
        s = 512
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=112, fill=(17, 17, 24, 255))
        f = ImageFont.truetype(font, 380) if font else ImageFont.load_default()
        bb = d.textbbox((0, 0), "C", font=f)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        x, y = (s - w) / 2 - bb[0], (s - h) / 2 - bb[1] - 6
        left = Image.new("RGBA", (s, s), (0, 0, 0, 0)); ImageDraw.Draw(left).text((x, y), "C", font=f, fill=(255, 63, 179, 255))
        right = Image.new("RGBA", (s, s), (0, 0, 0, 0)); ImageDraw.Draw(right).text((x, y), "C", font=f, fill=(46, 230, 255, 255))
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).polygon([(0, 0), (262, 0), (248, 120), (270, 250), (246, 380), (262, 512), (0, 512)], fill=255)
        glyph = Image.composite(left, right, mask)
        img.alpha_composite(glyph.filter(ImageFilter.GaussianBlur(14)))
        img.alpha_composite(glyph)
        img.save(out / "icon.png")
        print("icon:", out / "icon.png")
    except Exception as e:  # pragma: no cover
        print("icon.png skipped:", e)


if __name__ == "__main__":
    main()
