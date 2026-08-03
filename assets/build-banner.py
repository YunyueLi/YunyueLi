#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild the profile banner.

    python3 assets/build-banner.py

Sources, both vendored next to this script from ungetsu.net:
  moon.jpg         the homepage curtain artwork (public/curtain/moon.jpg)
  ungetsu-mark.png the handwritten wordmark, alpha-only (public/ungetsu-mark.png)

The site blends that artwork over the page colour the same way — multiply in
light, inverted + screen in dark, because multiply on a near-black ground just
crushes to black. Here the ground is GitHub's own canvas colour so the banner
has no visible edge, and the dark blend runs stronger than the site's 0.5: on
the site the artwork sits behind body copy and has to stay faint, whereas here
it is the whole picture.

Writes banner-dark.jpg and banner-light.jpg. Requires Pillow.
"""
import os
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "moon.jpg")
MARK = os.path.join(HERE, "ungetsu-mark.png")

# Songti SC Regular — what ungetsu.net's --font-serif resolves to for CJK.
# (Songti SC Black, index 0, is simplified-only and has no 雲.)
SONGTI, SONGTI_INDEX = "/System/Library/Fonts/Supplemental/Songti.ttc", 6

THEMES = {
    # ground colour = GitHub's canvas, so the plate melts into the README
    "dark":  dict(ground=(0x0D, 0x11, 0x17), ink=(0xE8, 0xE6, 0xE0), blend=0.72),
    "light": dict(ground=(0xFF, 0xFF, 0xFF), ink=(0x1C, 0x1C, 0x1C), blend=0.60),
}

RATIO = 3.0        # banner aspect
FOCAL_Y = 0.25     # matches the site's `background-position: center 25%`
NAME = "雲月"
TRACKING_EM = 0.14  # matches .curtain-name
RIGHT = 0.915      # right edge of the lockup, fraction of width
BASELINE = 0.475   # 雲月 baseline, fraction of height
SIZE = 0.185       # 雲月 size, fraction of height
MARK_GAP = 0.045   # gap under the baseline before the wordmark
MARK_SCALE = 1.06  # wordmark width relative to the 雲月 block


def wordmark():
    """Alpha of the handwritten mark, with PHOTOGRAPHY dropped and the brush
    glyph split off — this profile is not the photography site."""
    a = Image.open(MARK).split()[-1]
    ImageDraw.Draw(a).rectangle([206, 128, 392, 164], fill=0)
    cols = [sum(a.crop((x, 0, x + 1, a.height)).getdata()) for x in range(a.width)]
    bb = a.getbbox()
    runs, run = [], None
    for x in range(bb[0], bb[2]):
        if cols[x] == 0:
            run = (x, x) if run is None else (run[0], x)
        elif run:
            runs.append(run); run = None
    if run:
        runs.append(run)
    # the brush glyph is the last element, so the split is the RIGHT-most gap;
    # the widest gap is the hole left by erasing PHOTOGRAPHY
    split = (lambda g: (g[0] + g[1]) // 2)(max(runs, key=lambda t: t[1])) if runs else bb[2]
    return a.crop((bb[0], bb[1], split, bb[3]))


def cover(im):
    """`background-size: cover; background-position: center 25%`."""
    W, H = im.size
    h = round(W / RATIO)
    if h <= H:
        top = round((H - h) * FOCAL_Y)
        return im.crop((0, top, W, top + h))
    w = round(H * RATIO)
    return im.crop((round((W - w) / 2), 0, round((W - w) / 2) + w, H))


def build(theme):
    t = THEMES[theme]
    art = cover(Image.open(ART).convert("RGB"))
    W, H = art.size
    ground = Image.new("RGB", (W, H), t["ground"])
    if theme == "dark":
        mixed = ImageChops.screen(ground, ImageOps.invert(art))
    else:
        mixed = ImageChops.multiply(ground, art)
    im = Image.blend(ground, mixed, t["blend"])

    d = ImageDraw.Draw(im)
    size = round(H * SIZE)
    font = ImageFont.truetype(SONGTI, size, index=SONGTI_INDEX)
    if any(font.getmask(c).getbbox() is None for c in NAME):
        raise SystemExit(f"font is missing a glyph for one of {NAME!r}")

    tr = size * TRACKING_EM
    block = sum(d.textlength(c, font=font) for c in NAME) + tr
    x = round(W * RIGHT) - block
    baseline = round(H * BASELINE)
    cx = x
    for ch in NAME:
        d.text((cx, baseline), ch, font=font, fill=t["ink"], anchor="ls")
        cx += d.textlength(ch, font=font) + tr

    mk = wordmark()
    mw = block * MARK_SCALE
    mh = max(1, round(mw * mk.height / mk.width))
    m = mk.resize((round(mw), mh), Image.LANCZOS)
    im.paste(Image.new("RGB", m.size, t["ink"]),
             (round(W * RIGHT - mw), baseline + round(H * MARK_GAP)), m)

    out = os.path.join(HERE, f"banner-{theme}.jpg")
    im.save(out, "JPEG", quality=93, optimize=True, progressive=True)
    print(f"wrote {out}  {W}x{H}  {os.path.getsize(out) // 1024}KB")


if __name__ == "__main__":
    for th in THEMES:
        build(th)
