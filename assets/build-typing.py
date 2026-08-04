#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild the typing animation under the banner.

    python3 assets/build-typing.py

Writes typing-dark.svg and typing-light.svg.

Self-hosted rather than pulled from readme-typing-svg, for two reasons: that
service takes one global colour, while each line here wants the colour of the
outfit it names, and a local file cannot blank out when someone else's server
goes down.

Two implementation notes:

* Animation is SMIL `<animate>` on a clip rectangle's width. readme-typing-svg
  animates a path's `d` the same way, which is the proof that SMIL survives
  GitHub's camo image proxy; CSS `clip-path: inset()` on an SVG group is far
  less certain there.
* Type is converted to vector paths, so no font has to be embedded or loaded
  and the caret stays glued to the last glyph whatever fonts the viewer has.

Requires fonttools.
"""
import os
from fontTools.misc.transform import Transform
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTCollection

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = "/System/Library/Fonts/Supplemental/Baskerville.ttc"
FONT_FACE = "Baskerville SemiBold"     # pairs with the Ming 雲月 on the banner

W, H = 760, 48
SIZE = 23.5
BASELINE = 32
SEC_PER_CHAR = 0.055
SEC_PER_CHAR_ERASE = 0.022
HOLD = 1.6
CARET_W = 2

# Each line wears the colour of what it names: the role takes ungetsu.net's own
# accent, then miHoYo blue, Call of Duty orange, League of Legends gold. Two
# values per line so each one holds up on its own GitHub canvas.
# The verb belongs in the line: "@" flattened shipping Genshin Impact,
# working on Call of Duty and interning on League of Legends into one claim.
LINES = [
    ("AI Product Manager",                          "#B13A25", "#CF5F45"),
    ("Shipped Genshin Impact at miHoYo",            "#1455B4", "#5A9BFF"),
    ("Worked on Call of Duty at Tencent TiMi",      "#B4661A", "#E8912A"),
    ("Interned on League of Legends at Riot Games", "#9A7B2E", "#C8AA6E"),
]


def _short(v):
    """Trim coordinate precision; full float repr triples the file size."""
    return f"{v:.1f}".rstrip("0").rstrip(".") or "0"


class Face:
    def __init__(self, path, name):
        faces = TTCollection(path, lazy=False).fonts
        names = [(f["name"].getDebugName(4) or "") for f in faces]
        for i, n in enumerate(names):
            if n.lower() == name.lower():
                self.f = faces[i]
                break
        else:
            raise SystemExit(f"{name!r} not in {path}; available: {names}")
        self.upem = self.f["head"].unitsPerEm
        self.gs = self.f.getGlyphSet()
        self.cmap = self.f.getBestCmap()
        self.hm = self.f["hmtx"]

    def _g(self, ch):
        g = self.cmap.get(ord(ch))
        if g is None:
            raise SystemExit(f"{FONT_FACE} has no glyph for {ch!r}")
        return g

    def width(self, s, size):
        return sum(self.hm[self._g(c)][0] for c in s) * size / self.upem

    def path(self, s, size, x, y):
        k, cx, out = size / self.upem, x, []
        for ch in s:
            g = self._g(ch)
            pen = SVGPathPen(self.gs, ntos=_short)
            self.gs[g].draw(TransformPen(pen, Transform(k, 0, 0, -k, cx, y)))
            if (d := pen.getCommands()):
                out.append(d)
            cx += self.hm[g][0] * k
        return " ".join(out)


def animate(attr, values, keytimes, total, discrete=False):
    mode = ' calcMode="discrete"' if discrete else ""
    return (f'<animate attributeName="{attr}" dur="{total:.2f}s" '
            f'repeatCount="indefinite"{mode} '
            f'values="{";".join(values)}" keyTimes="{";".join(keytimes)}"/>')


def build(theme):
    face = Face(FONT_PATH, FONT_FACE)
    col = 2 if theme == "dark" else 1

    # lay the four slots end to end, then express each schedule as a fraction
    # of one shared cycle so every animation can share `dur`
    slots, t = [], 0.0
    for text, *_ in LINES:
        n = len(text)
        ty, er = n * SEC_PER_CHAR, n * SEC_PER_CHAR_ERASE
        slots.append((t, ty, er))
        t += ty + HOLD + er
    total = t

    defs, body = [], []
    for i, (line, (start, ty, er)) in enumerate(zip(LINES, slots)):
        text, colour = line[0], line[col]
        w = face.width(text, SIZE)
        if w > W - 24:
            raise SystemExit(f"{text!r} is {w:.0f}px, too wide for a {W}px canvas")
        x = (W - w) / 2
        a, b = start / total, (start + ty) / total
        c, d = (start + ty + HOLD) / total, (start + ty + HOLD + er) / total
        kt = [f"{v:.5f}" for v in (0, a, b, c, d, 1)]

        defs.append(
            f'<clipPath id="c{i}"><rect x="{x:.2f}" y="0" height="{H}" width="0">'
            + animate("width", ["0", "0", f"{w:.2f}", f"{w:.2f}", "0", "0"], kt, total)
            + '</rect></clipPath>')

        body.append(
            f'<g opacity="0">'
            + animate("opacity", ["0", "1", "1", "1", "0", "0"], kt, total, discrete=True)
            + f'<path d="{face.path(text, SIZE, x, BASELINE)}" fill="{colour}" '
              f'clip-path="url(#c{i})"/>'
            + f'<rect y="{BASELINE - SIZE * 0.78:.2f}" width="{CARET_W}" '
              f'height="{SIZE * 0.96:.2f}" fill="{colour}" x="{x:.2f}">'
            + animate("x", [f"{x:.2f}", f"{x:.2f}", f"{x + w:.2f}",
                            f"{x + w:.2f}", f"{x:.2f}", f"{x:.2f}"], kt, total)
            + '</rect></g>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="{"; ".join(l[0] for l in LINES)}">\n'
           f'<defs>{"".join(defs)}</defs>\n' + "\n".join(body) + "\n</svg>\n")

    out = os.path.join(HERE, f"typing-{theme}.svg")
    with open(out, "w") as fh:
        fh.write(svg)
    print(f"wrote {out}  cycle {total:.1f}s  {os.path.getsize(out) // 1024}KB")


if __name__ == "__main__":
    for th in ("dark", "light"):
        build(th)
