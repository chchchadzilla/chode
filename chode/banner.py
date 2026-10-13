"""Banner & image generation.

Every repo deserves a banner. `chode banner` makes one:
  1. If an image-model key exists (OpenAI, Gemini, xAI) → ask it for a real illustration.
  2. Always → a clean, deterministic SVG (stdlib) and PNG (if Pillow is installed)
     in the "collision" house style: two words slam together in a burst of dust.
"""
import base64
import colorsys
import json
import math
import os
import random
from pathlib import Path

import requests

from .config import api_key_for

ACCENTS = {"magenta": "#ff3fb3", "cyan": "#2ee6ff", "green": "#3dff8f", "yellow": "#ffd23f",
           "blue": "#4d7cff", "red": "#ff4d4d", "white": "#f4f4f8"}
BG = "#0b0b10"

FONT_CANDIDATES = [
    # heavy display fonts first, then safe system fallbacks
    "BigShoulders-Bold.ttf", "BigShouldersDisplay-Black.ttf", "Impact.ttf", "impact.ttf",
    "InterDisplay-Black.otf", "Inter-Black.otf", "Inter-ExtraBold.otf", "InterDisplay-Bold.otf",
    "Arial Black.ttf", "ariblk.ttf", "Helvetica-Bold.ttf", "HelveticaNeue-CondensedBlack.ttf",
    "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "FreeSansBold.ttf", "arialbd.ttf", "Arial Bold.ttf",
]
FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
             os.path.expanduser("~/.local/share/fonts"), "/Library/Fonts", "/System/Library/Fonts",
             os.path.expanduser("~/Library/Fonts"), "C:/Windows/Fonts"]


def find_font(extra_dirs=None):
    dirs = list(extra_dirs or []) + FONT_DIRS
    env = os.environ.get("CHODE_BANNER_FONT")
    if env and Path(env).exists():
        return env
    index = {}
    for d in dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        try:
            for f in p.rglob("*"):
                if f.suffix.lower() in (".ttf", ".otf") and f.name not in index:
                    index[f.name] = str(f)
        except Exception:
            continue
    for name in FONT_CANDIDATES:
        if name in index:
            return index[name]
    return None


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lighten(h, amt=0.25):
    r, g, b = [x / 255 for x in _hex_to_rgb(h)]
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    ll = min(1.0, ll + amt)
    r, g, b = colorsys.hls_to_rgb(hh, ll, ss)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


# --------------------------------------------------------------------------
# SVG (always available)
# --------------------------------------------------------------------------

def collision_svg(left, right, result, tagline, out, accent1="#ff3fb3", accent2="#2ee6ff",
                  width=1600, height=600, seed=7, subtitle=""):
    """Two rows: `left` →💥← `right` slam together up top; `result` emerges below."""
    rnd = random.Random(seed)
    cx = width / 2
    iy = height * 0.25   # impact row
    cy = height * 0.60   # hero row
    dust = []
    for i in range(220):
        ang = rnd.uniform(0, math.tau)
        dist = abs(rnd.gauss(0, width * 0.07))
        x = cx + math.cos(ang) * dist * 1.5
        y = iy + math.sin(ang) * dist * 0.9 + abs(rnd.gauss(0, height * 0.12))
        r = max(1.2, rnd.gauss(3.5, 2.5))
        col = accent1 if x < cx else accent2
        if rnd.random() < 0.35:
            col = "#ffffff"
        op = max(0.08, min(0.92, 1.05 - dist / (width * 0.16)))
        dust.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{col}" opacity="{op:.2f}"/>')
    spikes = []
    for _ in range(14):
        ang = rnd.uniform(0, math.tau)
        ln = rnd.uniform(width * 0.03, width * 0.11)
        spikes.append(f'<line x1="{cx:.0f}" y1="{iy:.0f}" x2="{cx+math.cos(ang)*ln:.0f}" y2="{iy+math.sin(ang)*ln*0.7:.0f}" stroke="#ffffff" stroke-opacity="{rnd.uniform(0.25,0.6):.2f}" stroke-width="{rnd.uniform(1,3):.1f}" stroke-linecap="round"/>')
    speed = []
    for i in range(26):
        y = iy + rnd.uniform(-height * 0.11, height * 0.11)
        ln = rnd.uniform(width * 0.06, width * 0.22)
        x0 = rnd.uniform(0, width * 0.30)
        speed.append(f'<line x1="{x0:.0f}" y1="{y:.0f}" x2="{x0+ln:.0f}" y2="{y:.0f}" stroke="{accent1}" stroke-opacity="{rnd.uniform(0.15,0.45):.2f}" stroke-width="{rnd.uniform(1,4):.1f}" stroke-linecap="round"/>')
        x1 = rnd.uniform(width * 0.70, width)
        speed.append(f'<line x1="{x1-ln:.0f}" y1="{y:.0f}" x2="{x1:.0f}" y2="{y:.0f}" stroke="{accent2}" stroke-opacity="{rnd.uniform(0.15,0.45):.2f}" stroke-width="{rnd.uniform(1,4):.1f}" stroke-linecap="round"/>')
    font = "'Inter Display', Inter, 'Big Shoulders Display', Impact, 'Arial Black', 'Helvetica Neue', Arial, sans-serif"
    big = int(height * 0.40)
    small = int(height * 0.20)
    gap = width * 0.045
    trails_l = "".join(f'<text x="{cx-gap-k*16:.0f}" y="{iy+small*0.36:.0f}" font-family="{font}" font-weight="900" font-size="{small}" fill="{accent1}" opacity="{max(0.03,0.28-k*0.03):.2f}" text-anchor="end" filter="url(#blur5)">{_esc(left)}</text>' for k in range(9, 0, -1))
    trails_r = "".join(f'<text x="{cx+gap+k*16:.0f}" y="{iy+small*0.36:.0f}" font-family="{font}" font-weight="900" font-size="{small}" fill="{accent2}" opacity="{max(0.03,0.28-k*0.03):.2f}" text-anchor="start" filter="url(#blur5)">{_esc(right)}</text>' for k in range(9, 0, -1))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#121219"/><stop offset="1" stop-color="{BG}"/>
    </linearGradient>
    <radialGradient id="flash" cx="50%" cy="25%" r="22%">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.55"/>
      <stop offset="0.5" stop-color="#ffffff" stop-opacity="0.12"/>
      <stop offset="1" stop-color="{BG}" stop-opacity="0"/>
    </radialGradient>
    <filter id="blur14"><feGaussianBlur stdDeviation="14"/></filter>
    <filter id="blur5"><feGaussianBlur stdDeviation="5"/></filter>
    <filter id="blur2"><feGaussianBlur stdDeviation="2"/></filter>
    <clipPath id="leftHalf"><polygon points="0,0 {cx+12:.0f},0 {cx-14:.0f},{cy-big*0.25:.0f} {cx+16:.0f},{cy} {cx-10:.0f},{cy+big*0.3:.0f} {cx+8:.0f},{height} 0,{height}"/></clipPath>
    <clipPath id="rightHalf"><polygon points="{cx+12:.0f},0 {width},0 {width},{height} {cx+8:.0f},{height} {cx-10:.0f},{cy+big*0.3:.0f} {cx+16:.0f},{cy} {cx-14:.0f},{cy-big*0.25:.0f}"/></clipPath>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <g>{''.join(speed)}</g>
  <!-- the two words slamming together -->
  {trails_l}{trails_r}
  <text x="{cx-gap:.0f}" y="{iy+small*0.36:.0f}" font-family="{font}" font-weight="900" font-size="{small}" fill="{accent1}" text-anchor="end" opacity="0.6" filter="url(#blur14)">{_esc(left)}</text>
  <text x="{cx+gap:.0f}" y="{iy+small*0.36:.0f}" font-family="{font}" font-weight="900" font-size="{small}" fill="{accent2}" text-anchor="start" opacity="0.6" filter="url(#blur14)">{_esc(right)}</text>
  <text x="{cx-gap:.0f}" y="{iy+small*0.36:.0f}" font-family="{font}" font-weight="900" font-size="{small}" fill="{accent1}" text-anchor="end">{_esc(left)}</text>
  <text x="{cx+gap:.0f}" y="{iy+small*0.36:.0f}" font-family="{font}" font-weight="900" font-size="{small}" fill="{accent2}" text-anchor="start">{_esc(right)}</text>
  <!-- impact -->
  <rect width="100%" height="100%" fill="url(#flash)"/>
  <g>{''.join(spikes)}</g>
  <g filter="url(#blur2)">{''.join(dust)}</g>
  <!-- the result: left side accent1, right side accent2, jagged seam -->
  <text x="{cx:.0f}" y="{cy+big*0.36:.0f}" font-family="{font}" font-weight="900" font-size="{big}" fill="{_lighten(accent1,0.12)}" text-anchor="middle" letter-spacing="2" clip-path="url(#leftHalf)" filter="url(#blur14)" opacity="0.6">{_esc(result)}</text>
  <text x="{cx:.0f}" y="{cy+big*0.36:.0f}" font-family="{font}" font-weight="900" font-size="{big}" fill="{_lighten(accent2,0.12)}" text-anchor="middle" letter-spacing="2" clip-path="url(#rightHalf)" filter="url(#blur14)" opacity="0.6">{_esc(result)}</text>
  <text x="{cx:.0f}" y="{cy+big*0.36:.0f}" font-family="{font}" font-weight="900" font-size="{big}" fill="{accent1}" text-anchor="middle" letter-spacing="2" clip-path="url(#leftHalf)">{_esc(result)}</text>
  <text x="{cx:.0f}" y="{cy+big*0.36:.0f}" font-family="{font}" font-weight="900" font-size="{big}" fill="{accent2}" text-anchor="middle" letter-spacing="2" clip-path="url(#rightHalf)">{_esc(result)}</text>
  <text x="{cx:.0f}" y="{cy+big*0.36+height*0.13:.0f}" font-family="Inter, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="{int(height*0.075)}" fill="#e8e8f0" opacity="0.92" text-anchor="middle" letter-spacing="1">{_esc(tagline)}</text>
  {f'<text x="{cx:.0f}" y="{cy+big*0.36+height*0.21:.0f}" font-family="Inter, Helvetica, Arial, sans-serif" font-size="{int(height*0.042)}" fill="#9a9ab0" text-anchor="middle" letter-spacing="1">{_esc(subtitle)}</text>' if subtitle else ''}
  <text x="{width-24}" y="{height-18}" font-family="Inter, Helvetica, Arial, sans-serif" font-size="{int(height*0.035)}" fill="#6b6b80" text-anchor="end">made with chode</text>
</svg>
"""
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(svg, encoding="utf-8")
    return str(out)


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------------------
# PNG (Pillow, optional)
# --------------------------------------------------------------------------

def collision_png(left, right, result, tagline, out, accent1="#ff3fb3", accent2="#2ee6ff",
                  width=1600, height=600, seed=7, font_path=None, subtitle=""):
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except ImportError:
        return None
    rnd = random.Random(seed)
    font_path = font_path or find_font()

    def font(size, path=font_path):
        try:
            return ImageFont.truetype(path, size) if path else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    a1, a2 = _hex_to_rgb(accent1), _hex_to_rgb(accent2)
    img = Image.new("RGBA", (width, height), _hex_to_rgb(BG) + (255,))
    cx = width // 2
    iy = int(height * 0.25)   # impact row: LEFT →💥← RIGHT
    cy = int(height * 0.60)   # hero row: the result word
    # soft glow behind the impact and the hero word
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(10, 0, -1):
        rx, ry = int(width * 0.05 * i), int(height * 0.06 * i)
        alpha = int(16 * (11 - i) / 10)
        gd.ellipse([cx - rx, iy - ry, cx + rx, iy + ry], fill=(255, 255, 255, alpha))
        gd.ellipse([cx - rx * 1.4, cy - ry, cx + rx * 1.4, cy + ry], fill=(255, 255, 255, alpha // 2))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40)))

    big = int(height * 0.40)
    F = font(big)
    small_italic = font(int(height * 0.20))

    def text_size(f, s):
        bb = ImageDraw.Draw(img).textbbox((0, 0), s, font=f)
        return bb[2] - bb[0], bb[3] - bb[1], bb

    # speed lines along the impact row
    sl = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sl)
    for _ in range(26):
        y = iy + rnd.randint(-int(height * 0.11), int(height * 0.11))
        ln = rnd.randint(int(width * 0.06), int(width * 0.22))
        x0 = rnd.randint(0, int(width * 0.30))
        sd.line([(x0, y), (x0 + ln, y)], fill=a1 + (rnd.randint(40, 110),), width=rnd.randint(1, 4))
        x1 = rnd.randint(int(width * 0.70), width)
        sd.line([(x1 - ln, y), (x1, y)], fill=a2 + (rnd.randint(40, 110),), width=rnd.randint(1, 4))
    img.alpha_composite(sl.filter(ImageFilter.GaussianBlur(1)))

    # the two words slamming into the center, with motion trails behind them
    lw, lh, lbb = text_size(small_italic, left)
    rw, rh, rbb = text_size(small_italic, right)
    gap = int(width * 0.045)

    def slam(word, x_left, color, direction, bb, h):
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        base_x = x_left - bb[0]
        base_y = iy - h / 2 - bb[1]
        for k in range(9, 0, -1):
            d.text((base_x - direction * k * 16, base_y), word, font=small_italic, fill=color + (max(6, 70 - k * 7),))
        img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(5)))
        crisp = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(crisp).text((base_x, base_y), word, font=small_italic, fill=color + (235,))
        img.alpha_composite(crisp.filter(ImageFilter.GaussianBlur(14)))
        img.alpha_composite(crisp)
    slam(left, cx - gap - lw, a1, +1, lbb, lh)
    slam(right, cx + gap, a2, -1, rbb, rh)

    # dust burst at the impact point, raining down onto the hero word
    dust = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dust)
    for _ in range(520):
        ang = rnd.uniform(0, math.tau)
        dist = abs(rnd.gauss(0, width * 0.07))
        x = cx + math.cos(ang) * dist * 1.5
        y = iy + math.sin(ang) * dist * 0.9 + abs(rnd.gauss(0, height * 0.12))
        r = max(1, int(abs(rnd.gauss(3.5, 2.5))))
        col = a1 if x < cx else a2
        if rnd.random() < 0.35:
            col = (255, 255, 255)
        alpha = int(max(20, min(235, 255 * (1.05 - dist / (width * 0.16)))))
        dd.ellipse([x - r, y - r, x + r, y + r], fill=col + (alpha,))
    for _ in range(14):  # impact spikes
        ang = rnd.uniform(0, math.tau)
        ln = rnd.uniform(width * 0.03, width * 0.11)
        dd.line([(cx, iy), (cx + math.cos(ang) * ln, iy + math.sin(ang) * ln * 0.7)],
                fill=(255, 255, 255, rnd.randint(60, 160)), width=rnd.randint(1, 3))
    img.alpha_composite(dust.filter(ImageFilter.GaussianBlur(3)))
    img.alpha_composite(dust.filter(ImageFilter.GaussianBlur(0.6)))
    flash = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(flash).ellipse([cx - width * 0.08, iy - height * 0.12, cx + width * 0.08, iy + height * 0.12],
                                  fill=(255, 255, 255, 120))
    img.alpha_composite(flash.filter(ImageFilter.GaussianBlur(28)))

    # main word with a jagged seam between the two colors + glow
    w, h, bb = text_size(F, result)
    tx, ty = cx - w / 2 - bb[0], cy - h / 2 - bb[1]
    word_l = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    word_r = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(word_l).text((tx, ty), result, font=F, fill=a1 + (255,))
    ImageDraw.Draw(word_r).text((tx, ty), result, font=F, fill=a2 + (255,))
    seam = Image.new("L", (width, height), 0)
    sd2 = ImageDraw.Draw(seam)
    pts = [(0, 0), (cx + rnd.randint(-10, 10), 0)]
    yy = 0
    while yy < height:
        yy += rnd.randint(12, 30)
        pts.append((cx + rnd.randint(-26, 26), yy))
    pts += [(0, height)]
    sd2.polygon(pts, fill=255)
    word = Image.composite(word_l, word_r, seam)
    glow_w = word.filter(ImageFilter.GaussianBlur(18))
    img.alpha_composite(glow_w)
    img.alpha_composite(glow_w)
    img.alpha_composite(word)

    # tagline
    tf = None
    for cand in ("Inter-Medium.otf", "InterDisplay-Medium.otf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        p = _find_named_font(cand)
        if p:
            tf = font(int(height * 0.075), p)
            break
    tf = tf or font(int(height * 0.075))
    tw, th, tbb = text_size(tf, tagline)
    ImageDraw.Draw(img).text((cx - tw / 2 - tbb[0], cy + h / 2 + height * 0.06 - tbb[1]), tagline,
                             font=tf, fill=(232, 232, 240, 235))
    if subtitle:
        sf = font(int(height * 0.042), _find_named_font("Inter-Regular.otf") or font_path)
        sw, sh, sbb = text_size(sf, subtitle)
        ImageDraw.Draw(img).text((cx - sw / 2 - sbb[0], cy + h / 2 + height * 0.15 - sbb[1]), subtitle,
                                 font=sf, fill=(154, 154, 176, 220))
    mf = font(int(height * 0.035), _find_named_font("Inter-Regular.otf") or font_path)
    mw, mh, mbb = text_size(mf, "made with chode")
    ImageDraw.Draw(img).text((width - 24 - mw - mbb[0], height - 18 - mh - mbb[1]), "made with chode",
                             font=mf, fill=(107, 107, 128, 255))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "PNG", optimize=True)
    return str(out)


def _find_named_font(name):
    for d in FONT_DIRS:
        p = Path(d)
        if p.is_dir():
            for f in p.rglob(name):
                return str(f)
    return None


def icon_svg(out, accent1="#ff3fb3", accent2="#2ee6ff", size=512):
    """Minimalist app icon: rounded dark tile, a bold 'C' split at a jagged seam."""
    s = size
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#17171f"/><stop offset="1" stop-color="#0b0b10"/></linearGradient>
    <clipPath id="l"><polygon points="0,0 262,0 248,120 270,250 246,380 262,512 0,512"/></clipPath>
    <clipPath id="r"><polygon points="262,0 512,0 512,512 262,512 246,380 270,250 248,120"/></clipPath>
    <filter id="b"><feGaussianBlur stdDeviation="14"/></filter>
  </defs>
  <rect width="512" height="512" rx="112" fill="url(#g)"/>
  <g font-family="Impact, 'Arial Black', 'Helvetica Neue', Arial, sans-serif" font-weight="900" font-size="372" text-anchor="middle">
    <text x="256" y="388" fill="{accent1}" opacity="0.55" filter="url(#b)" clip-path="url(#l)">C</text>
    <text x="256" y="388" fill="{accent2}" opacity="0.55" filter="url(#b)" clip-path="url(#r)">C</text>
    <text x="256" y="388" fill="{accent1}" clip-path="url(#l)">C</text>
    <text x="256" y="388" fill="{accent2}" clip-path="url(#r)">C</text>
  </g>
  <circle cx="256" cy="250" r="7" fill="#ffffff" opacity="0.9"/>
  <circle cx="236" cy="232" r="3" fill="#ffffff" opacity="0.6"/>
  <circle cx="280" cy="270" r="4" fill="#ffffff" opacity="0.6"/>
</svg>
"""
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(svg, encoding="utf-8")
    return str(out)


# --------------------------------------------------------------------------
# Image-model APIs (optional, when you have a key)
# --------------------------------------------------------------------------

IMAGE_BACKENDS = ("openai", "gemini", "xai")


def image_backend(cfg):
    pref = (cfg.get("banner") or {}).get("image_provider", "auto")
    order = [pref] if pref in IMAGE_BACKENDS else list(IMAGE_BACKENDS)
    for p in order:
        if api_key_for(cfg, p):
            return p
    return None


def generate_image(cfg, prompt, out_path, size="1536x1024", backend=None):
    """Returns the saved path, or raises RuntimeError with a human explanation."""
    backend = backend or image_backend(cfg)
    if not backend:
        raise RuntimeError("no image-capable API key found (OPENAI_API_KEY, GEMINI_API_KEY or XAI_API_KEY) — "
                           "falling back to the built-in SVG/PNG generator")
    key = api_key_for(cfg, backend)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if backend == "openai":
        r = requests.post("https://api.openai.com/v1/images/generations",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": "gpt-image-1", "prompt": prompt, "size": size, "n": 1}, timeout=180)
        _raise(r)
        b64 = r.json()["data"][0].get("b64_json")
        if not b64:
            url = r.json()["data"][0].get("url")
            out_path.write_bytes(requests.get(url, timeout=60).content)
        else:
            out_path.write_bytes(base64.b64decode(b64))
        return str(out_path)
    if backend == "gemini":
        model = "gemini-2.5-flash-image"
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}}, timeout=180)
        _raise(r)
        for cand in r.json().get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    out_path.write_bytes(base64.b64decode(inline["data"]))
                    return str(out_path)
        raise RuntimeError("gemini returned no image data")
    if backend == "xai":
        r = requests.post("https://api.x.ai/v1/images/generations",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": "grok-2-image", "prompt": prompt, "n": 1, "response_format": "b64_json"},
                          timeout=180)
        _raise(r)
        d = r.json()["data"][0]
        if d.get("b64_json"):
            out_path.write_bytes(base64.b64decode(d["b64_json"]))
        else:
            out_path.write_bytes(requests.get(d["url"], timeout=60).content)
        return str(out_path)
    raise RuntimeError(f"unknown image backend {backend}")


def _raise(r):
    if r.status_code >= 400:
        try:
            msg = json.dumps(r.json())[:400]
        except Exception:
            msg = r.text[:400]
        raise RuntimeError(f"image API HTTP {r.status_code}: {msg}")


def banner_prompt(project_name, description, tagline=""):
    return (f"A wide (3:1) repository banner for a software project called '{project_name}'. "
            f"{description[:400]} Minimalist, dark background, one or two vivid accent colors, "
            f"bold modern typography of the project name as the hero element"
            + (f", with the tagline '{tagline}' in smaller text" if tagline else "")
            + ". No clutter, no fake UI screenshots, no gibberish text. Crisp, print-quality.")


def make_banner(cfg, project_name, tagline, out_dir, description="", left=None, right=None,
                accent=None, use_api=True, seed=7):
    """Generate banner assets for a project. Returns dict of what was written."""
    out_dir = Path(out_dir)
    theme = (cfg or {}).get("theme", "magenta")
    a1 = accent or ACCENTS.get(theme, ACCENTS["magenta"])
    a2 = ACCENTS["cyan"] if a1 != ACCENTS["cyan"] else ACCENTS["magenta"]
    name = project_name.strip() or "PROJECT"
    if left is None or right is None:
        mid = max(1, len(name) // 2)
        left, right = name[:mid].upper(), name[mid:].upper()
    result = {"svg": collision_svg(left, right, name.upper(), tagline, out_dir / "banner.svg", a1, a2, seed=seed)}
    png = collision_png(left, right, name.upper(), tagline, out_dir / "banner.png", a1, a2, seed=seed)
    if png:
        result["png"] = png
    result["icon"] = icon_svg(out_dir / "icon.svg", a1, a2)
    if use_api and image_backend(cfg):
        try:
            result["ai"] = generate_image(cfg, banner_prompt(name, description, tagline), out_dir / "banner-ai.png")
        except Exception as e:
            result["ai_error"] = str(e)[:200]
    return result
