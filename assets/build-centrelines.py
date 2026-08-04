#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract writing centrelines from the handwritten wordmark.

A draw-on animation has to follow the pen, not the outline. potrace only gives
outlines and the machine has no autotrace, so the centreline is thinned here:
Zhang-Suen to one-pixel skeletons, then each connected component is walked from
its left-most endpoint into an ordered polyline. Components are emitted left to
right, which for this cursive is the order it was written in.

Writes centrelines.json, which build-banner-anim.py turns into the
reveal. Needs only Pillow.
"""
import json
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
MARK = os.path.join(HERE, "ungetsu-mark.png")
PHOTO_BOX = [206, 128, 392, 164]   # the PHOTOGRAPHY line, dropped
SCRIPT_MAX_X = 392                 # the brush glyph sits to the right of this
THRESHOLD = 96
SIMPLIFY = 1.1                     # Douglas-Peucker tolerance, in mask pixels


def load_bitmap():
    a = Image.open(MARK).split()[-1]
    ImageDraw.Draw(a).rectangle(PHOTO_BOX, fill=0)
    bb = a.getbbox()
    crop = a.crop((bb[0], bb[1], SCRIPT_MAX_X, bb[3]))
    w, h = crop.size
    px = crop.load()
    grid = [[1 if px[x, y] > THRESHOLD else 0 for y in range(h)] for x in range(w)]
    return grid, w, h, (bb[0], bb[1])


def zhang_suen(g, w, h):
    """Thin to a one-pixel skeleton."""
    def nb(x, y):
        # P2..P9 clockwise from north, as the paper numbers them
        return [g[x][y - 1], g[x + 1][y - 1], g[x + 1][y], g[x + 1][y + 1],
                g[x][y + 1], g[x - 1][y + 1], g[x - 1][y], g[x - 1][y - 1]]

    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            drop = []
            for x in range(1, w - 1):
                for y in range(1, h - 1):
                    if not g[x][y]:
                        continue
                    n = nb(x, y)
                    b = sum(n)
                    if b < 2 or b > 6:
                        continue
                    a = sum(1 for i in range(8) if n[i] == 0 and n[(i + 1) % 8] == 1)
                    if a != 1:
                        continue
                    p2, p4, p6, p8 = n[0], n[2], n[4], n[6]
                    if step == 0 and (p2 and p4 and p6):
                        continue
                    if step == 0 and (p4 and p6 and p8):
                        continue
                    if step == 1 and (p2 and p4 and p8):
                        continue
                    if step == 1 and (p2 and p6 and p8):
                        continue
                    drop.append((x, y))
            for x, y in drop:
                g[x][y] = 0
            if drop:
                changed = True
    return g


def components(g, w, h):
    seen = [[False] * h for _ in range(w)]
    out = []
    for x in range(w):
        for y in range(h):
            if g[x][y] and not seen[x][y]:
                stack, pts = [(x, y)], []
                seen[x][y] = True
                while stack:
                    cx, cy = stack.pop()
                    pts.append((cx, cy))
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            nx, ny = cx + dx, cy + dy
                            if (0 <= nx < w and 0 <= ny < h and g[nx][ny]
                                    and not seen[nx][ny]):
                                seen[nx][ny] = True
                                stack.append((nx, ny))
                out.append(pts)
    return out


def _adj(s):
    def neigh(p):
        x, y = p
        return [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if (dx or dy) and (x + dx, y + dy) in s]
    return neigh


def _diameter(s):
    """The longest run through a skeleton fragment: its main line."""
    neigh = _adj(s)
    start = min(s, key=lambda p: (p[0], p[1]))

    def bfs(src):
        prev, q, last = {src: None}, [src], src
        while q:
            nxt = []
            for p in q:
                for n in neigh(p):
                    if n not in prev:
                        prev[n] = p
                        nxt.append(n)
                        last = n
            q = nxt
        return last, prev

    far, _ = bfs(start)
    end, prev = bfs(far)
    path, p = [], end
    while p is not None:
        path.append(p)
        p = prev[p]
    return path


def _fragments(s):
    seen, out = set(), []
    neigh = _adj(s)
    for p in s:
        if p in seen:
            continue
        stack, grp = [p], []
        seen.add(p)
        while stack:
            c = stack.pop()
            grp.append(c)
            for n in neigh(c):
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        out.append(grp)
    return out


def decompose(pts):
    """One pen-down as a main line plus branches, none of them retracing.

    Returns (main, [(fraction_along_main, branch), ...]). The fraction is where
    the branch meets the main line, so a flourish can be drawn at the moment the
    pen passes it instead of after the whole word. Twelve separate runs drawn in
    sequence covered the skeleton without retracing but read as twelve pen-lifts;
    blooming each branch as the front goes by keeps the three real pen-downs and
    still never travels backwards.

    A single depth-first walk covering the whole skeleton did cover every pixel,
    but it came back out of each branch the way it went in. Even with the
    retraced runs given almost no time, the reveal front still travels backwards
    over ink it has already laid down, and that reads exactly as going back to
    trace over the letter again.

    So the skeleton is cut into runs that are each drawn once, forward: the main
    line first, then the branches in the order their attachment appears along it.
    That is also how the hand does it, writing the word joined up and coming back
    for the crossbars.
    """
    remaining = set(pts)
    main = _diameter(remaining)
    emitted = set(main)
    remaining -= emitted
    rank = {p: i for i, p in enumerate(main)}
    neigh_all = _adj(set(pts))
    branches = []

    while remaining:
        batch = []
        for frag in _fragments(remaining):
            attach, at = None, len(main)
            for p in frag:
                for n in neigh_all(p):
                    r = rank.get(n)
                    if r is not None and (attach is None or r < at):
                        attach, at = p, r
            if attach is None:
                # hangs off an earlier branch, so inherit that branch's place
                for p in frag:
                    for n in neigh_all(p):
                        if n in emitted:
                            attach = p
                            break
                    if attach:
                        break
                at = min((a for a, _ in branches), default=0)
            batch.append((at, frag, attach))
        batch.sort(key=lambda t: t[0])
        for at, frag, attach in batch:
            path = _diameter(set(frag))
            runs = [path]
            if attach is not None and attach in path:
                i = path.index(attach)
                if i == len(path) - 1:
                    runs = [path[::-1]]
                elif i:
                    runs = [path[i::-1], path[i:]]
            for r in runs:
                branches.append((at / max(1, len(main) - 1), r))
            emitted |= set(path)
            remaining -= set(frag)
    return main, branches


def simplify(path, tol):
    """Douglas-Peucker."""
    if len(path) < 3:
        return path

    def rdp(pts):
        if len(pts) < 3:
            return pts
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        dx, dy = x1 - x0, y1 - y0
        den = (dx * dx + dy * dy) ** 0.5
        worst, idx = -1.0, 0
        for i in range(1, len(pts) - 1):
            x, y = pts[i]
            if den < 1e-9:
                # a covering walk comes back to where it started, so the chord
                # can be a point; perpendicular distance to it is meaningless
                # and collapsed the whole stroke to two points
                dist = ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
            else:
                dist = abs(dy * (x - x0) - dx * (y - y0)) / den
            if dist > worst:
                worst, idx = dist, i
        if worst <= tol:
            return [pts[0], pts[-1]]
        return rdp(pts[:idx + 1])[:-1] + rdp(pts[idx:])

    return rdp(path)


def timing(path, near=2.6):
    """Map animation time to path length so retraced runs cost no time.

    The covering walk is about twice the length of the skeleton, because coming
    back out of a branch retraces it. Revealing at constant speed along path
    length would spend half the animation apparently stalled. A segment whose
    midpoint sits within `near` of any earlier segment is a retrace and gets a
    sliver of time; every other segment gets time in proportion to its length.
    Emitted as SMIL keyTimes against dashoffset values.
    """
    def seg_len(i):
        (x0, y0), (x1, y1) = path[i], path[i + 1]
        return ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5

    def mid(i):
        (x0, y0), (x1, y1) = path[i], path[i + 1]
        return ((x0 + x1) / 2, (y0 + y1) / 2)

    def dist_to_seg(p, i):
        (x0, y0), (x1, y1) = path[i], path[i + 1]
        px, py = p
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
        return ((px - (x0 + t * dx)) ** 2 + (py - (y0 + t * dy)) ** 2) ** 0.5

    n = len(path) - 1
    cum = [0.0]
    for i in range(n):
        cum.append(cum[-1] + seg_len(i))
    total = cum[-1] or 1.0

    weight = []
    for i in range(n):
        m = mid(i)
        retrace = any(dist_to_seg(m, j) <= near for j in range(i))
        weight.append(0.02 * seg_len(i) if retrace else seg_len(i))
    wsum = sum(weight) or 1.0

    keytimes, values, acc = ["0"], [f"{total:.2f}"], 0.0
    for i in range(n):
        acc += weight[i]
        keytimes.append(f"{acc / wsum:.5f}")
        values.append(f"{total - cum[i + 1]:.2f}")
    retraced = sum(seg_len(i) for i in range(n) if weight[i] < seg_len(i))
    return {"len": round(total, 2), "keyTimes": keytimes, "values": values,
            "retraced": round(retraced, 1)}


if __name__ == "__main__":
    grid, w, h, origin = load_bitmap()
    ink = sum(sum(col) for col in grid)
    zhang_suen(grid, w, h)
    thin = sum(sum(col) for col in grid)
    comps = [c for c in components(grid, w, h) if len(c) > 12]
    comps.sort(key=lambda c: min(p[0] for p in c))

    def prep(run):
        p = [[int(x), int(y)] for x, y in simplify(run, SIMPLIFY)]
        L = sum(((p[i + 1][0] - p[i][0]) ** 2 + (p[i + 1][1] - p[i][1]) ** 2) ** 0.5
                for i in range(len(p) - 1))
        return {"points": p, "len": round(L, 2)}

    groups = []
    for c in comps:
        main, branches = decompose(c)
        g = {"main": prep(main), "branches": []}
        for frac, run in branches:
            if len(run) < 3:
                continue      # a two-pixel spur is inside the mask width anyway
            b = prep(run)
            if b["len"] < 5:
                continue
            b["at"] = round(min(0.97, max(0.0, frac)), 4)
            g["branches"].append(b)
        g["branches"].sort(key=lambda b: b["at"])
        groups.append(g)
    strokes = groups

    json.dump({"size": [w, h], "origin": list(origin), "strokes": strokes},
              open(os.path.join(HERE, "centrelines.json"), "w"))
    print(f"mask {w}x{h}  ink {ink} px  skeleton {thin} px")
    tot = 0.0
    for i, g in enumerate(strokes):
        m = g["main"]
        xs = [p[0] for p in m["points"]]
        tot += m["len"]
        print(f"  pen-down {i + 1}: main {m['len']:6.0f}px  x {min(xs)}..{max(xs)}"
              f"  plus {len(g['branches'])} branch(es)")
        for b in g["branches"]:
            tot += b["len"]
            print(f"      branch at {b['at'] * 100:4.0f}% along  {b['len']:5.0f}px")
    print(f"  {len(strokes)} pen-downs, {tot:.0f}px total against a "
          f"{thin}px skeleton, nothing walked twice")
