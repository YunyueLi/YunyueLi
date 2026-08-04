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
simple-icons; see icons/SOURCE.md. Brand colour is confined to that 14px glyph,
because the typing animation above already spends the page's colour budget.

Requires fonttools.
"""
import os
import re
from fontTools.misc.transform import Transform
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTCollection

HERE = os.path.dirname(os.path.abspath(__file__))
SUP = "/System/Library/Fonts/Supplemental"

# platform key, display name, handle, brand colour on light, on dark, icon slug
PLATFORMS = [
    ("xhs",      "小红书",      "雲月Ungetsu", "#FF2442", "#FF4D63", "xiaohongshu"),
    ("wechat",   "微信公众号",  "倦默轩",      "#07C160", "#3DD98A", "wechat"),
    ("linkedin", "LinkedIn",   "ungetsu",     "#0A66C2", "#4C9BE8", "linkedin"),
    ("zhihu",    "知乎",        "三不开居士",   "#0084FF", "#3DA5FF", "zhihu"),
]

THEMES = {
    "dark":  dict(ink="#E8E6E0", muted="#8E8C85", rule="#3A3733"),
    "light": dict(ink="#1C1C1C", muted="#777570", rule="#D8D3C8"),
}

SIZE, H, BASE = 13.5, 26, 18
GAP = 7          # between name and handle
PAD, ICON, ICON_VB = 11, 14, 24    # icons are single paths on a 24x24 box
LAT_RATIO = 1.06  # Baskerville's x-height runs small beside a Ming face

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


def build(key, name, handle, brand, theme, slug):
    t = THEMES[theme]
    wn, wh = measure(name), measure(handle)
    x = PAD + ICON + 7
    w = x + wn + GAP + wh + PAD
    k = ICON / ICON_VB
    iy = (H - ICON) / 2
    body = (f'<rect x="0.5" y="0.5" width="{w - 1:.1f}" height="{H - 1}" rx="4" '
            f'fill="none" stroke="{t["rule"]}"/>'
            f'<g transform="translate({PAD} {iy:g}) scale({k:.5f})">'
            f'<path d="{icon_path(slug)}" fill="{brand}"/></g>'
            + render(name, x, BASE, t["ink"])
            + render(handle, x + wn + GAP, BASE, t["muted"]))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{H}" '
           f'viewBox="0 0 {w:.0f} {H}" role="img" aria-label="{name} {handle}">'
           f'{body}</svg>\n')
    out = os.path.join(HERE, f"social-{key}-{theme}.svg")
    with open(out, "w") as fh:
        fh.write(svg)
    return os.path.basename(out), int(w), os.path.getsize(out)


if __name__ == "__main__":
    for theme in THEMES:
        for key, name, handle, c_light, c_dark, slug in PLATFORMS:
            brand = c_dark if theme == "dark" else c_light
            fn, w, size = build(key, name, handle, brand, theme, slug)
            print(f"{fn:28s} {w:3d}x{H}  {size // 1024 or 1}KB")
