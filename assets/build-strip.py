#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the career strip shown at the top of the profile README.

    python3 assets/build-strip.py

Writes assets/strip-dark.svg and assets/strip-light.svg. Edit ROWS below and
re-run after any career change. Column widths are measured from the text, so
the layout stays a proper grid without hand-tuning coordinates.

Pillow is optional; without it the script falls back to a rougher width
estimate, which only means slightly looser column gaps.
"""
import os

OUT = os.path.dirname(os.path.abspath(__file__))

ROWS = [
    ("Now",        [(None, "AI Product Manager")]),
    ("Previously", [("miHoYo", "Genshin Impact"),
                    ("Tencent TiMi", "Call of Duty"),
                    ("Riot Games", "League of Legends")]),
    ("Education",  [("NTU Singapore", "MSc Economics"),
                    ("Shandong University", "Japanese & Finance")]),
    ("Also",       [(None, "Landscape Photography")]),
]

THEMES = {
    "dark":  dict(section="#656c76", label="#7d8590", title="#e6edf3",
                  rule="#30363d", dot="#3fb950"),
    "light": dict(section="#818b98", label="#59636e", title="#1f2328",
                  rule="#d1d9e0", dot="#1a7f37"),
}

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','Helvetica Neue',Helvetica,Arial,sans-serif"
SEC_SIZE, SEC_TRACK = 9.5, 1.0
LAB_SIZE, LAB_TRACK = 9.5, 0.7
TIT_SIZE = 13.5
ROW_H, GAP, TOP = 44, 30, 6
LAB_DY, TIT_DY = 13, 30
SAFETY = 1.06

try:
    from PIL import ImageFont
    _font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 100)

    def measure(t, size, tracking=0.0):
        return (_font.getlength(t) * size / 100.0) * SAFETY + tracking * max(len(t) - 1, 0)
except Exception:
    def measure(t, size, tracking=0.0):
        return len(t) * size * 0.60 + tracking * max(len(t) - 1, 0)


def xml(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(theme):
    c = THEMES[theme]
    gutter = max(measure(s.upper(), SEC_SIZE, SEC_TRACK) for s, _ in ROWS) + 26
    rule_x, content_x = round(gutter - 15, 1), round(gutter, 1)

    ncol = max(len(cells) for _, cells in ROWS)
    colw = [0.0] * ncol
    for _, cells in ROWS:
        for i, (lab, tit) in enumerate(cells):
            w = measure(tit, TIT_SIZE)
            if lab:
                w = max(w, measure(lab.upper(), LAB_SIZE, LAB_TRACK))
            colw[i] = max(colw[i], w)

    body = []
    for r, (sec, cells) in enumerate(ROWS):
        y = TOP + r * ROW_H
        body.append(f'<text x="0" y="{y + TIT_DY}" font-family="{FONT}" font-size="{SEC_SIZE}" '
                    f'font-weight="600" letter-spacing="{SEC_TRACK}" fill="{c["section"]}">'
                    f'{xml(sec.upper())}</text>')
        if sec == "Now":
            body.append(f'<circle cx="{round(content_x - 7.5, 1)}" cy="{y + TIT_DY - 4.5}" '
                        f'r="3" fill="{c["dot"]}"/>')
        x = content_x
        for i, (lab, tit) in enumerate(cells):
            if lab:
                body.append(f'<text x="{round(x, 1)}" y="{y + LAB_DY}" font-family="{FONT}" '
                            f'font-size="{LAB_SIZE}" font-weight="600" letter-spacing="{LAB_TRACK}" '
                            f'fill="{c["label"]}">{xml(lab.upper())}</text>')
            body.append(f'<text x="{round(x, 1)}" y="{y + TIT_DY}" font-family="{FONT}" '
                        f'font-size="{TIT_SIZE}" font-weight="500" fill="{c["title"]}">'
                        f'{xml(tit)}</text>')
            x += colw[i] + GAP

    w = round(content_x + sum(colw) + GAP * (ncol - 1) + 2)
    h = TOP + len(ROWS) * ROW_H - 4
    rule = (f'<line x1="{rule_x}" y1="{TOP + 2}" x2="{rule_x}" y2="{h - 6}" '
            f'stroke="{c["rule"]}" stroke-width="1"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="Career summary">\n'
            f'{rule}\n' + "\n".join(body) + "\n</svg>\n")


for theme in THEMES:
    path = os.path.join(OUT, f"strip-{theme}.svg")
    with open(path, "w") as fh:
        fh.write(build(theme))
    print("wrote", path)
