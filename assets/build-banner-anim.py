#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Banner as an animated SVG: the handwritten Ungetsu draws itself on.

    python3 assets/build-centrelines.py     # only when the wordmark changes
    python3 assets/build-banner-anim.py

Writes banner-anim-<theme>.svg, two files, photo embedded.

Only the wordmark animates. 雲月 stays exactly as it is, set in Songti TC Bold,
because that is not what was asked for and Make Me A Hanzi's stroke-order data
is a kai brush face that would have changed how those two characters look.

How the draw-on works, and why not the obvious way: animating stroke-dashoffset
on the *outline* of the lettering traces its contour, which is a loop around the
shape, not the path a pen took. So the real ink stays as a filled outline from
potrace, and what animates is a mask: a fat stroke running along the glyph's
centreline, revealing the ink in writing order. Centrelines come from
build-centrelines.py, which thins the mask bitmap and decomposes each of the
three pen-downs into runs that are each drawn once, forward.

A single soft-edged front sweeping across the whole word was tried first. It is
monotonic by construction and needs no centrelines, but it is a wipe rather than
a hand, and the feather it needs to hide that is wider than the strokes.

Requires Pillow, fontTools, and potrace on PATH.
"""
import base64
import io
import json
import os
import re
import subprocess

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTCollection
from PIL import Image, ImageChops, ImageDraw, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "moon.jpg")
MARK = os.path.join(HERE, "ungetsu-mark.png")
CENTRELINES = os.path.join(HERE, "centrelines.json")

SONGTI, SONGTI_FACE = "/System/Library/Fonts/Supplemental/Songti.ttc", "Songti TC Bold"

THEMES = {
    "dark":  dict(ground=(0x0D, 0x11, 0x17), ink="#E8E6E0", blend=0.72),
    "light": dict(ground=(0xFF, 0xFF, 0xFF), ink="#1C1C1C", blend=0.60),
}

RATIO, FOCAL_Y = 3.0, 0.25
NAME, TRACKING_EM = "雲月", 0.14
RIGHT, BASELINE, SIZE = 0.915, 0.475, 0.185
MARK_GAP, MARK_SCALE = 0.045, 1.06

PHOTO_BOX = [206, 128, 392, 164]
SCRIPT_MAX_X = 392
MASK_STROKE = 18          # 100% ink coverage was reached at 18; measured, not guessed
# A soft leading edge, as copies of each stroke set a little further ahead and
# fainter, painted faintest-first so the solid core wins where they overlap.
# It was three layers 11 apart, carried over from the sweep: 22 units of feather
# on an 18-unit stroke, so the soft edge was wider than the stroke itself and,
# running along the direction of travel, read as ink seeping ahead of the nib
# rather than leaving it. The sweep needed that, having no pen to point at; a pen
# path wants the opposite, because a nib reads as a nib by being crisp. Kept only
# as much as it takes to stop the edge popping: 0.28 of the stroke width. The
# visible difference is smaller than that ratio suggests. Measured at a matched
# leading-edge position with the nib highlight off, partial-opacity ink went from
# 15.7% of the revealed area to 9.8%; most of the ghost the wide feather was
# blamed for was in fact the nib highlight, which came down from 15 to 11.
FEATHER_STEP = 5          # crop units between layers
FEATHER_OPACITY = (0.45, 1.0)
SEC_PER_100PX = 0.34      # pen speed along the centreline, at full tilt
GAP_BETWEEN = 0.05        # pen lifts between the three pen-downs
HOLD_AFTER = 0.5          # beat before the whole thing settles
TIP_R = 11                # nib highlight radius, in mask-bitmap units
TIP_FADE = 0.32           # it fades out as the pen leaves the paper
HOP_LIFT = 26             # how high the nib arcs through the air between them
SAMPLES = 40              # points per stroke used to sample the velocity curve

# One velocity profile for the whole word, not one per stroke. Easing each
# stroke separately meant fifteen accelerate-and-brake cycles in five seconds,
# which is what made it drag: the pen came to a standstill at the end of every
# run and every flourish. A hand speeds up once at the start and settles once at
# the end, and holds a steady pace in between, straight through the pen-lifts.
RAMP, SETTLE = 0.07, 0.15         # share of the word's length spent on each
SPEED_IN, SPEED_OUT = 0.42, 0.30  # speed at the very first and very last point


def cover(im):
    W, H = im.size
    h = round(W / RATIO)
    if h <= H:
        top = round((H - h) * FOCAL_Y)
        return im.crop((0, top, W, top + h))
    w = round(H * RATIO)
    return im.crop((round((W - w) / 2), 0, round((W - w) / 2) + w, H))


def plate(theme):
    """The blended photo with no lettering on it, as JPEG bytes."""
    t = THEMES[theme]
    art = cover(Image.open(ART).convert("RGB"))
    ground = Image.new("RGB", art.size, t["ground"])
    mixed = (ImageChops.screen(ground, ImageOps.invert(art)) if theme == "dark"
             else ImageChops.multiply(ground, art))
    im = Image.blend(ground, mixed, t["blend"])
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90, optimize=True, progressive=True)
    return im.size, buf.getvalue()


def songti_paths(size_px, right_px, baseline_px):
    """雲月 as outlines, laid out the way the raster build lays it out."""
    faces = TTCollection(SONGTI, lazy=False).fonts
    face = next(f for f in faces
                if (f["name"].getDebugName(4) or "").lower() == SONGTI_FACE.lower())
    upem = face["head"].unitsPerEm
    gs, cmap, hm = face.getGlyphSet(), face.getBestCmap(), face["hmtx"]
    k = size_px / upem
    tr = size_px * TRACKING_EM
    adv = [hm[cmap[ord(c)]][0] * k for c in NAME]
    block = sum(adv) + tr
    x = right_px - block
    out = []
    for ch, a in zip(NAME, adv):
        pen = SVGPathPen(gs)
        gs[cmap[ord(ch)]].draw(TransformPen(pen, Transform(k, 0, 0, -k, x, baseline_px)))
        if (d := pen.getCommands()):
            out.append(d)
        x += a + tr
    return " ".join(out), block


def script_bitmap():
    a = Image.open(MARK).split()[-1]
    ImageDraw.Draw(a).rectangle(PHOTO_BOX, fill=0)
    bb = a.getbbox()
    return a.crop((bb[0], bb[1], SCRIPT_MAX_X, bb[3]))


def script_outline():
    """potrace the wordmark; returns its path data in crop-pixel space."""
    crop = script_bitmap()
    pbm = os.path.join(HERE, "_script.pbm")
    svg = os.path.join(HERE, "_script.svg")
    # ink must be black for potrace: it traces black, so writing the ink
    # as white made it vectorise the background instead
    crop.point(lambda v: 0 if v > 96 else 255).convert("1").save(pbm)
    subprocess.run(["potrace", "-s", "-o", svg, "--turdsize", "2",
                    "--alphamax", "1.0", "--opttolerance", "0.2", pbm], check=True)
    raw = open(svg).read()
    for f in (pbm, svg):
        os.remove(f)
    ds = re.findall(r'<path[^>]*\sd="([^"]+)"', raw)
    m = re.search(r'<g transform="([^"]+)"', raw)
    return " ".join(ds), (m.group(1) if m else ""), crop.size


def _speed(u):
    """Pen speed at u, the share of the whole word already written."""
    if u < RAMP:
        s = u / RAMP
        return SPEED_IN + (1 - SPEED_IN) * (s * s * (3 - 2 * s))
    if u > 1 - SETTLE:
        s = (u - (1 - SETTLE)) / SETTLE
        return 1 - (1 - SPEED_OUT) * (s * s * (3 - 2 * s))
    return 1.0


class Clock:
    """Time as a function of distance written, integrated once for the word.

    Every stroke reads its window and its interior timing off this, so the pace
    is continuous across strokes and across the pen-lifts between them. Total
    time is normalised to the nominal, so slowing the ends speeds up the middle
    rather than making the whole thing longer.
    """

    def __init__(self, total_px, sec_per_100, steps=2000):
        self.total = total_px
        acc, self.ts = 0.0, [0.0]
        for i in range(steps):
            acc += (1.0 / steps) / _speed((i + 0.5) / steps)
            self.ts.append(acc)
        k = (total_px / 100.0 * sec_per_100) / self.ts[-1]
        self.ts = [t * k for t in self.ts]

    def t(self, u):
        x = min(1.0, max(0.0, u)) * (len(self.ts) - 1)
        i = int(x)
        if i >= len(self.ts) - 1:
            return self.ts[-1]
        return self.ts[i] + (self.ts[i + 1] - self.ts[i]) * (x - i)


def walk(pts):
    """Cumulative length along a polyline, plus a point-at-fraction lookup."""
    cum = [0.0]
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        cum.append(cum[-1] + ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    total = cum[-1] or 1.0

    def at(frac):
        d = min(1.0, max(0.0, frac)) * total
        lo, hi = 0, len(cum) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if cum[mid] <= d else (lo, mid)
        seg = cum[hi] - cum[lo] or 1.0
        s = (d - cum[lo]) / seg
        (x0, y0), (x1, y1) = pts[lo], pts[hi]
        return (x0 + (x1 - x0) * s, y0 + (y1 - y0) * s)

    return total, at


def air_hop(p, q, n=14):
    """The nib's arc through the air between two pen-downs.

    The wordmark is three separate patches of ink, so the hand really did lift
    twice and no reveal can join them without drawing in the air. What can be
    joined is the nib: it arcs across the gap at the same pace instead of
    blinking out and reappearing, which is what makes three pen-downs read as
    one movement rather than three takes.
    """
    cx = (p[0] + q[0]) / 2
    cy = (p[1] + q[1]) / 2 - HOP_LIFT
    out = []
    for i in range(1, n + 1):
        s = i / n
        a, b, c = (1 - s) ** 2, 2 * (1 - s) * s, s * s
        out.append((a * p[0] + b * cx + c * q[0], a * p[1] + b * cy + c * q[1]))
    return out


def build(theme):
    t = THEMES[theme]
    (W, H), jpeg = plate(theme)
    b64 = base64.b64encode(jpeg).decode()

    size_px = round(H * SIZE)
    baseline = round(H * BASELINE)
    name_d, block = songti_paths(size_px, round(W * RIGHT), baseline)

    outline_d, potrace_tr, (cw, ch) = script_outline()
    cl = json.load(open(CENTRELINES))
    assert cl["size"] == [cw, ch], f"centrelines {cl['size']} vs outline {[cw, ch]}"

    mw = block * MARK_SCALE
    k = mw / cw
    mx = W * RIGHT - mw
    my = baseline + round(H * MARK_GAP)

    groups = cl["strokes"]
    mains = [g["main"] for g in groups]
    clock = Clock(sum(m["len"] for m in mains), SEC_PER_100PX)
    total = clock.total

    def feather(length):
        # the feather cannot run ahead further than the stroke is long, or a
        # short branch starts fully revealed; and nothing may show before its
        # own begin, which is what put faint ink across the whole word at t=0
        step_px = min(FEATHER_STEP, length / (len(FEATHER_OPACITY) + 1))
        for op, step in zip(FEATHER_OPACITY, range(len(FEATHER_OPACITY) - 1, -1, -1)):
            yield op, step * step_px

    def stroke_layers(pts, length, begin, dur, kt, vs_of):
        """One stroke's mask layers. Interior timing comes from the clock, so
        there is no per-stroke easing left to brake against."""
        d = "M " + " L ".join(f"{x} {y}" for x, y in pts)
        out = []
        for op, ahead in feather(length):
            out.append(
                f'<path d="{d}" fill="none" stroke="#fff" opacity="{op}" '
                f'stroke-width="{MASK_STROKE}" stroke-linecap="round" '
                f'stroke-linejoin="round" '
                # the gap has to be longer than the dash. With both equal to the
                # path length the pattern wraps to a new dash exactly at the far
                # end, and a zero-length dash under a round cap paints a dot: a
                # bright speck sat at the end of the U before anything had been
                # written. Two units of slack is enough to keep the wrap off the
                # end of the path.
                f'stroke-dasharray="{length} {length + 2}" '
                f'stroke-dashoffset="{length}">'
                f'<animate attributeName="stroke-dashoffset" begin="{begin:.3f}s" '
                f'dur="{dur:.3f}s" fill="freeze" calcMode="linear" '
                f'keyTimes="{kt}" values="{vs_of(ahead)}"/></path>')
        return d, [f'<g opacity="0"><set attributeName="opacity" to="1" '
                   f'begin="{begin:.3f}s"/>' + "".join(out) + '</g>']

    def _values(length, ahead, ss):
        # The lead is earned rather than granted: it ramps in over its own width
        # at the start of the stroke. Handing a layer `ahead` units of head start
        # as its initial attribute meant it was already showing that much ink
        # before its own animation began, which put a faint smudge at the start
        # of the word at t=0 and fully revealed any branch shorter than the lead.
        return ";".join(f"{length * (1 - s) - min(ahead, s * length):.2f}"
                        for s in ss)

    def curve(u0, u1, length):
        """keyTimes and a values-builder that put this stroke on the clock."""
        t_a, t_b = clock.t(u0), clock.t(u1)
        span = (t_b - t_a) or 1e-6
        ss = [j / SAMPLES for j in range(SAMPLES + 1)]
        kt = [f"{(clock.t(u0 + (u1 - u0) * s) - t_a) / span:.5f}" for s in ss]
        kt[0], kt[-1] = "0", "1"
        return (";".join(kt), lambda ahead: _values(length, ahead, ss), t_a, span)

    layers, nib_pts, nib_t, hops, done = [], [], [], [], 0.0
    for i, g in enumerate(groups):
        m = g["main"]
        u0 = done / total
        done += m["len"]
        u1 = done / total
        lift = i * GAP_BETWEEN
        kt, vs_of, t_a, dur = curve(u0, u1, m["len"])
        d, ls = stroke_layers(m["points"], m["len"], t_a + lift, dur, kt, vs_of)
        layers += ls

        for b in g["branches"]:
            u_at = u0 + (u1 - u0) * b["at"]
            # a flourish is drawn at the pace the pen is going when it gets there
            bd = max(0.10, b["len"] / 100.0 * SEC_PER_100PX / _speed(u_at))
            bss = [j / 4 for j in range(5)]
            layers += stroke_layers(
                b["points"], b["len"], clock.t(u_at) + lift, bd,
                ";".join(f"{s:.2f}" for s in bss),
                lambda ahead, L=b["len"]: _values(L, ahead, bss))[1]

        # the nib rides every main line and arcs across the lifts between them
        _, at = walk([tuple(p) for p in m["points"]])
        if i:
            hop = air_hop(nib_pts[-1], at(0.0))
            hops.append((nib_t[-1], nib_t[-1] + GAP_BETWEEN))
            for j, p in enumerate(hop):
                nib_pts.append(p)
                nib_t.append(nib_t[-1] + GAP_BETWEEN / len(hop))
        for j in range(SAMPLES + 1):
            s = j / SAMPLES
            if i and j == 0:
                continue          # the hop already landed on this point
            nib_pts.append(at(s))
            nib_t.append(clock.t(u0 + (u1 - u0) * s) + lift)

    draw_end = nib_t[-1]
    ncum, acc = [0.0], 0.0
    for j in range(len(nib_pts) - 1):
        (x0, y0), (x1, y1) = nib_pts[j], nib_pts[j + 1]
        acc += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        ncum.append(acc)
    nib_d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in nib_pts)
    nkt = ";".join(f"{t / draw_end:.5f}" for t in nib_t)
    nkp = ";".join(f"{c / (acc or 1):.5f}" for c in ncum)
    # dimmed while it is off the paper, so a lift reads as a lift and not as the
    # nib gliding over a blank stretch
    okt, ovs = ["0", "0.02"], ["0", "1"]
    for a, b in hops:
        for tk, v in ((a, 1), (a + (b - a) * 0.25, 0.3),
                      (b - (b - a) * 0.25, 0.3), (b, 1)):
            okt.append(f"{tk / draw_end:.5f}")
            ovs.append(f"{v:g}")
    okt.append("1")
    ovs.append("1")
    tips = [f'<circle r="{TIP_R}" fill="url(#nib)" opacity="0">'
            f'<animate attributeName="opacity" begin="0s" dur="{draw_end:.3f}s" '
            f'fill="freeze" calcMode="linear" keyTimes="{";".join(okt)}" '
            f'values="{";".join(ovs)}"/>'
            f'<animate attributeName="opacity" begin="{draw_end:.3f}s" '
            f'dur="{TIP_FADE}s" values="1;0" fill="freeze"/>'
            f'<animateMotion begin="0s" dur="{draw_end:.3f}s" fill="freeze" '
            f'path="{nib_d}" calcMode="linear" keyTimes="{nkt}" '
            f'keyPoints="{nkp}"/></circle>']

    end = draw_end + HOLD_AFTER
    masks = ['<mask id="pen" maskUnits="userSpaceOnUse" '
             f'x="{-MASK_STROKE}" y="{-MASK_STROKE}" width="{cw + MASK_STROKE * 2}" '
             f'height="{ch + MASK_STROKE * 2}">' + "".join(layers) + '</mask>']

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="雲月 Ungetsu">
<defs>{"".join(masks)}
<radialGradient id="nib"><stop offset="0" stop-color="{t["ink"]}" stop-opacity="0.5"/><stop offset="0.55" stop-color="{t["ink"]}" stop-opacity="0.14"/><stop offset="1" stop-color="{t["ink"]}" stop-opacity="0"/></radialGradient>
</defs>
<image x="0" y="0" width="{W}" height="{H}" preserveAspectRatio="none" href="data:image/jpeg;base64,{b64}"/>
<path d="{name_d}" fill="{t["ink"]}"/>
<g transform="translate({mx:.2f} {my:.2f}) scale({k:.6f})">
  <g mask="url(#pen)">
    <g transform="{potrace_tr}"><path d="{outline_d}" fill="{t["ink"]}"/></g>
  </g>
  {"".join(tips)}
</g>
</svg>
'''
    out = os.path.join(HERE, f"banner-anim-{theme}.svg")
    open(out, "w").write(svg)
    return out, W, H, end, len(svg)


if __name__ == "__main__":
    for th in THEMES:
        p, W, H, end, n = build(th)
        print(f"{os.path.basename(p):24s} {W}x{H}  {end:.1f}s  {n // 1024}KB")
