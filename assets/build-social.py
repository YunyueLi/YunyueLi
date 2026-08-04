#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild the social row.

    python3 assets/build-social.py

Writes social-<platform>-<theme>.svg, eight files.

One file per platform rather than one strip, because each has to be its own
link and an <a> inside an SVG does not survive GitHub's image proxy.

Why not shields.io: its badges are set in Verdana with DejaVu Sans as the
fallback, so Chinese is handed to whatever the viewer's machine happens to
have. 小红书 and 倦默轩 then look different on every screen and can never line
up with the Ming face on the banner or the Baskerville in the typing line.
Here CJK is Songti SC and Latin is Baskerville, both outlined to paths, so the
row is identical everywhere and loads nothing.

Each chip carries its platform's own mark, vendored under icons/ from
simple-icons; see icons/SOURCE.md. Every mark is composed the way the real logo
reads, a white symbol on a brand-coloured plate, which also keeps the knockout
marks from going black on a dark canvas. Colour is confined to that 14px plate,
because the typing animation above already spends the page's colour budget.

Requires fonttools.
"""
import math
import os
import re
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTCollection

HERE = os.path.dirname(os.path.abspath(__file__))
SUP = "/System/Library/Fonts/Supplemental"

# platform key, display name, handle, brand colour on light, on dark, icon slug,
# and how that slug is built. simple-icons ships two shapes of mark:
#   "glyph"    the letterforms alone, so the brand plate has to be drawn here
#   "knockout" the plate with the mark punched out of it, so a white backing has
#              to go behind it or the hole shows the page through, which on a
#              dark canvas turns LinkedIn's "in" and Zhihu's 知 black
PLATFORMS = [
    ("xhs",      "小红书",      "雲月Ungetsu", "#FF2442", "#FF4D63", "xiaohongshu", "glyph"),
    ("wechat",   "微信公众号",  "倦默轩",      "#07C160", "#3DD98A", "wechat",      "glyph"),
    ("linkedin", "LinkedIn",   "ungetsu",     "#0A66C2", "#4C9BE8", "linkedin",    "knockout"),
    ("zhihu",    "知乎",        "三不开居士",   "#0084FF", "#3DA5FF", "zhihu",       "knockout"),
    # X's brand is monochrome. Pure black is right on the light canvas but
    # vanishes into #0d1117, so the dark plate lifts to a neutral charcoal
    # rather than inverting to a light plate, which would make X the only pale
    # chip in the row.
    ("x",        "X",          "ungetsucaspian", "#000000", "#3F3F46", "x",        "glyph"),
]

THEMES = {
    "dark":  dict(ink="#E8E6E0", muted="#8E8C85", rule="#3A3733"),
    "light": dict(ink="#1C1C1C", muted="#777570", rule="#D8D3C8"),
}

SIZE = 13.5
BOX_H = 26       # the visible chip
GUTTER = 1       # transparent margin outside the border, on all four sides
H = BOX_H + GUTTER * 2
BASE = 18 + GUTTER
GAP = 7          # between name and handle
PAD, ICON, ICON_VB = 11, 14, 24    # icons are single paths on a 24x24 box
PLATE_RX = 5                       # corner radius of the brand plate, in icon units
MARK = "#FFFFFF"                   # every mark sits white on its own plate
# simple-icons draws every mark to fill its whole 24x24 box, with no padding,
# because the mark is meant to BE the icon. Put one on a plate of the same size
# and it runs into the rounded corners: Xiaohongshu's letterforms touched the
# left edge and X's strokes reached all four corners, quartering the plate. The
# glyph shapes get scaled to this fraction of the plate and centred on their own
# measured bounds. Knockout marks already carry a correctly proportioned plate.
GLYPH_FILL = 0.60
LAT_RATIO = 1.06  # Baskerville's x-height runs small beside a Ming face

# The border used to sit at x=0.5 with a 1px stroke, so its outer half landed
# exactly on the canvas boundary and browsers dropped it under fractional
# scaling. Worse, the canvas width was rounded to an integer while the border
# was placed from the unrounded float, so the right edge fell in a different
# spot on every chip. Width is rounded up first now, and everything is laid out
# inside that integer with GUTTER to spare.

# Everything stays at Regular. Baskerville SemiBold beside Songti Bold reads
# heavier than the Ming face at the same nominal weight, because the Didone has
# thicker stems relative to its counters, so "LinkedIn" shouted over the three
# Chinese names. Hierarchy is carried by ink versus muted instead.

CJK_RANGES = ((0x3000, 0x303F), (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
              (0xF900, 0xFAFF), (0xFF00, 0xFFEF))


def is_cjk(ch):
    return any(a <= ord(ch) <= b for a, b in CJK_RANGES)


def _short(v):
    return f"{v:.1f}".rstrip("0").rstrip(".") or "0"


class Face:
    def __init__(self, path, want):
        faces = TTCollection(path, lazy=False).fonts
        names = [(f["name"].getDebugName(4) or "") for f in faces]
        for i, n in enumerate(names):
            if n.lower() == want.lower():
                self.f = faces[i]
                break
        else:
            raise SystemExit(f"{want!r} not in {path}; available: {names}")
        self.upem = self.f["head"].unitsPerEm
        self.gs = self.f.getGlyphSet()
        self.cmap = self.f.getBestCmap()
        self.hm = self.f["hmtx"]

    def _g(self, ch):
        g = self.cmap.get(ord(ch))
        if g is None:
            raise SystemExit(f"no glyph for {ch!r}")
        return g

    def adv(self, ch, size):
        return self.hm[self._g(ch)][0] * size / self.upem

    def draw(self, ch, size, x, y):
        pen = SVGPathPen(self.gs, ntos=_short)
        k = size / self.upem
        self.gs[self._g(ch)].draw(TransformPen(pen, Transform(k, 0, 0, -k, x, y)))
        return pen.getCommands()


def icon_path(slug):
    """The single `d` from a vendored simple-icons mark."""
    raw = open(os.path.join(HERE, "icons", f"{slug}.svg"), encoding="utf-8").read()
    m = re.search(r'<path[^>]*\sd="([^"]+)"', raw)
    if not m:
        raise SystemExit(f"no path found in icons/{slug}.svg")
    return m.group(1)


HAN = Face(f"{SUP}/Songti.ttc", "Songti SC Regular")
LAT = Face(f"{SUP}/Baskerville.ttc", "Baskerville")


def _runs(s):
    out = []
    for ch in s:
        kind = "han" if is_cjk(ch) else "lat"
        if out and out[-1][0] == kind:
            out[-1][1].append(ch)
        else:
            out.append([kind, [ch]])
    return [(k, "".join(v)) for k, v in out]


def measure(s):
    w = 0.0
    for kind, run in _runs(s):
        f, sz = (HAN, SIZE) if kind == "han" else (LAT, SIZE * LAT_RATIO)
        w += sum(f.adv(c, sz) for c in run)
    return w


def render(s, x, y, fill):
    d, cx = [], x
    for kind, run in _runs(s):
        f, sz = (HAN, SIZE) if kind == "han" else (LAT, SIZE * LAT_RATIO)
        for ch in run:
            if (p := f.draw(ch, sz, cx, y)):
                d.append(p)
            cx += f.adv(ch, sz)
    return f'<path d="{" ".join(d)}" fill="{fill}"/>'


def glyph_fit(d):
    """Scale and centre a full-bleed mark inside the plate, on its real bounds."""
    bp = BoundsPen(None)
    parse_path(d, bp)
    x0, y0, x1, y1 = bp.bounds
    s = ICON_VB * GLYPH_FILL / max(x1 - x0, y1 - y0)
    c = ICON_VB / 2
    return (f'translate({c - (x0 + x1) / 2 * s:.3f} {c - (y0 + y1) / 2 * s:.3f}) '
            f'scale({s:.4f})')


def mark(slug, kind, brand):
    """A brand plate with a white mark on it, whichever shape the slug ships."""
    d = icon_path(slug)
    if kind == "glyph":
        return (f'<rect width="{ICON_VB}" height="{ICON_VB}" rx="{PLATE_RX}" fill="{brand}"/>'
                f'<g transform="{glyph_fit(d)}"><path d="{d}" fill="{MARK}"/></g>')
    # knockout: the white backing is inset so it cannot fringe past the plate's
    # own rounded corners
    return (f'<rect x="1.5" y="1.5" width="{ICON_VB - 3}" height="{ICON_VB - 3}" '
            f'rx="{PLATE_RX - 1.5}" fill="{MARK}"/>'
            f'<path d="{d}" fill="{brand}"/>')


def build(key, name, handle, brand, theme, slug, kind):
    t = THEMES[theme]
    wn, wh = measure(name), measure(handle)
    x = GUTTER + PAD + ICON + 7
    W = math.ceil(x + wn + GAP + wh + PAD + GUTTER)
    k = ICON / ICON_VB
    iy = (H - ICON) / 2
    # border box: inset by GUTTER, then a further 0.5 so the 1px stroke lands
    # wholly inside instead of straddling the boundary
    body = (f'<rect x="{GUTTER + 0.5}" y="{GUTTER + 0.5}" width="{W - GUTTER * 2 - 1}" '
            f'height="{H - GUTTER * 2 - 1}" rx="4" fill="none" stroke="{t["rule"]}"/>'
            f'<g transform="translate({GUTTER + PAD} {iy:g}) scale({k:.5f})">'
            f'{mark(slug, kind, brand)}</g>'
            + render(name, x, BASE, t["ink"])
            + render(handle, x + wn + GAP, BASE, t["muted"]))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}" role="img" aria-label="{name} {handle}">'
           f'{body}</svg>\n')
    out = os.path.join(HERE, f"social-{key}-{theme}.svg")
    with open(out, "w") as fh:
        fh.write(svg)
    return os.path.basename(out), W, os.path.getsize(out)


if __name__ == "__main__":
    for theme in THEMES:
        for key, name, handle, c_light, c_dark, slug, kind in PLATFORMS:
            brand = c_dark if theme == "dark" else c_light
            fn, w, size = build(key, name, handle, brand, theme, slug, kind)
            print(f"{fn:28s} {w:3d}x{H}  {size // 1024 or 1}KB")
