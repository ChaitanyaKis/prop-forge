"""A family of old leather-bound books (prop-forge example): rounded spines with raised bands, some with a title
label, page blocks inset by the squares with a hollow fore-edge, boards bevelled and covered.

  python <skill>/scripts/run.py examples/books.py -- OUT_DIR --tex TEXTURES [--count 12] [--unit]

TEXTURES holds Poly Haven's leather_white (python <skill>/scripts/fetch_cc0.py texture leather_white --res 1k
--out TEXTURES). Writes OUT_DIR/books.glb: every book its own object (book_00, book_01, ...), standing on the floor
side by side, origin at each book's bottom centre, spine toward -Y. With --unit, also OUT_DIR/book_unit.glb: one
octavo scaled into a 1 x 1 x 1 box (x -0.5..0.5 thickness, y -0.5..0.5 spine to fore-edge, z 0..1 height), for engines
that draw shelves of instanced books by scaling one mesh.

Sizes from references/dimensions.md (Books).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import forge as F  # noqa: E402

# ---- formats: (weight, thickness, depth, height) in metres. dimensions.md: octavo 20-25 x 13-16, quarto 24-30 x
# 18-24, folio 30-40 x 20-25, duodecimo 15-19 x 10-12; thickness 1.5-6 for most books
FORMATS = {"duodecimo": (2, 0.025, 0.11, 0.17), "octavo": (6, 0.035, 0.16, 0.235),
           "quarto": (3, 0.05, 0.21, 0.28), "folio": (1, 0.065, 0.25, 0.37)}
BOARD = 0.003         # board thickness: 2-4 mm
SQUARE = 0.003        # how far the boards stand past the page block: 2-4 mm
GROOVE = 0.002        # joint groove between spine and board
BAND_H, BAND_P = 0.006, 0.0025   # raised bands: 5-8 mm tall, 2-3 mm proud
# target leather colours (sRGB), divided by leather_white's mean colour to give tints
LEATHER_MEAN = (0.587, 0.575, 0.501)
COLOURS = {"oxblood": (0.30, 0.08, 0.06), "brown": (0.33, 0.2, 0.11), "tan": (0.5, 0.35, 0.2),
           "green": (0.13, 0.22, 0.14), "navy": (0.1, 0.13, 0.24), "black": (0.085, 0.08, 0.075),
           "maroon": (0.24, 0.07, 0.09), "olive": (0.27, 0.26, 0.13)}
LABELS = {"red": (0.42, 0.07, 0.05), "black": (0.06, 0.055, 0.05)}
PAPERS = [(0.44, 0.37, 0.26), (0.38, 0.31, 0.2), (0.31, 0.25, 0.16)]   # linear (sRGB 0.6-0.7), aged cream


class Mats:
    """One material per colour, shared by every book that uses it (fewer materials, fewer draw calls)."""

    def __init__(self, tex):
        self.tex, self.cache = tex, {}

    def leather(self, key, rgb):
        if key not in self.cache:
            tint = tuple(rgb[i] / LEATHER_MEAN[i] for i in range(3))
            self.cache[key] = F.pbr("leather_" + key, tex=self.tex, metres=0.3, tint=tint, rough_mul=1.1)
        return self.cache[key]

    def paper(self, i):
        key = "paper_%d" % i
        if key not in self.cache:
            self.cache[key] = F.flat(key, PAPERS[i], rough=0.92)
        return self.cache[key]


def arc(T, y_joint, bulge, offset=0.0, span=1.0, n=8):
    """The spine's curve from the left board to the right, as (x, y) points: a parabola standing `bulge` in front of
    the joint line, pushed out by `offset`. span < 1 keeps to the middle of the spine (labels)."""
    pts = []
    for i in range(n + 1):
        s = -span + 2 * span * i / n
        pts.append((s * (T / 2 + offset * 0.4), y_joint - bulge * (1 - s * s) - offset))
    return pts


def shell(name, outer, inner, height, z0, mat, bevel=0.0008, segs=1):
    """A strip following the spine: the outline goes along `outer` and back along `inner`, extruded `height` up."""
    outline = outer + list(reversed(inner))
    return F.extrude(name, outline, height, (0, 0, z0 + height / 2), mat, plane="XY", bevel=bevel, segs=segs,
                     grain=None)


def book(name, x, fmt, mats, rng, colour, label, paper, bands, detail="full"):
    """One book. detail="far" makes a light version for shelves seen from afar (fewer curve points, no bevels)."""
    far = detail == "far"
    n = 4 if far else 8
    bv = 0.0 if far else 1.0
    _, T, D, H = FORMATS[fmt]
    k = rng.uniform(0.95, 1.05)
    T, D, H = T * rng.uniform(0.85, 1.2), D * k, H * k
    bulge = min(max(0.15 * T, 0.003), 0.008)
    y_front = -D / 2                   # the spine's crown
    y_joint = y_front + bulge          # where spine meets the boards
    leather = mats.leather(colour, COLOURS[colour])
    parts = []
    # page block: inside the boards, inset by the squares; seen from above, its fore-edge is hollowed by the rounding
    # of the spine (a low-poly outline extruded up, not a subdivided box: a shelf holds hundreds of these)
    pw = T - 2 * BOARD - 0.0006
    y0, y1 = y_joint + 0.0005, D / 2 - SQUARE
    depth = min(0.6 * bulge, 0.004)
    fore = [(pw / 2 * (1 - 2 * i / 6), y1 - depth * (1 - (1 - 2 * i / 6) ** 2)) for i in range(7)]
    outline = [(-pw / 2, y0), (pw / 2, y0)] + fore
    parts.append(F.extrude(name + "_pages", outline, H - 2 * SQUARE, (0, 0, H / 2), mats.paper(paper), plane="XY",
                           bevel=0.0008 * bv, segs=1))
    # boards, covered: from the joint groove to the fore-edge
    for side in (-1, 1):
        parts.append(F.box("%s_board_%d" % (name, side), (BOARD, D - bulge - GROOVE, H),
                           (side * (T / 2 - BOARD / 2), y_joint + GROOVE + (D - bulge - GROOVE) / 2, H / 2),
                           leather, bevel=0.0009 * bv, segs=1, rng=rng))
    # spine: a rounded shell from board to board
    outer = arc(T, y_joint, bulge, n=n)
    inner = arc(T - 2 * 0.0015, y_joint + 0.0015, bulge * 0.8, n=n)
    parts.append(shell(name + "_spine", outer, inner, H, 0.0, leather, bevel=0.0008 * bv))
    # raised bands: panels between them, the bottom one taller (as binders spaced them)
    units = bands + 1 + 0.4
    z = H * 0.04
    unit = (H * 0.92) / units
    panel_tops = []
    for i in range(bands):
        z += unit * (1.4 if i == 0 else 1.0)
        parts.append(shell("%s_band_%d" % (name, i), arc(T, y_joint, bulge, BAND_P, n=n), arc(T, y_joint, bulge, -0.0004, n=n),
                           BAND_H, z - BAND_H / 2, leather, bevel=0.0006 * bv))
        panel_tops.append(z)
    # title label in the second panel from the top
    if label and not far:
        lab = mats.leather("label_" + label, LABELS[label])
        top, bottom = panel_tops[-1] - BAND_H / 2, panel_tops[-2] + BAND_H / 2
        h = (top - bottom) * 0.72
        parts.append(shell(name + "_label", arc(T, y_joint, bulge, 0.0006, span=0.82),
                           arc(T, y_joint, bulge, -0.0003, span=0.82), h, (top + bottom) / 2 - h / 2, lab,
                           bevel=0.0))
    b = F.join(parts, name)
    F.origin_bottom(b)
    b.location.x += x
    return b, T


def pick(rng, table):
    total = sum(w for w, *_ in table.values())
    r, acc = rng.uniform(0, total), 0.0
    for key, (w, *_rest) in table.items():
        acc += w
        if r <= acc:
            return key
    return key


def family(out, tex, count):
    rng = F.begin("books", out, seed=11, max_tex=1024)
    mats = Mats(tex)
    x = 0.0
    names = list(COLOURS)
    for i in range(count):
        fmt = pick(rng, FORMATS)
        colour = names[i % len(names)] if i < len(names) else rng.choice(names)
        label = rng.choice(list(LABELS)) if rng.random() < 0.6 else None
        b, T = book("book_%02d" % i, 0.0, fmt, mats, rng, colour, label, rng.randrange(len(PAPERS)),
                    rng.choice((4, 5, 5)))
        b.location.x = x + T / 2
        x += T + 0.012
    F.export("books", notes="%d books; leather_white (Poly Haven, CC0) tinted" % count)


def unit(out, tex, name="book_unit", bands=5, label="red", detail="full", fmt="GLB", seed=5):
    rng = F.begin(name, out, seed=seed, max_tex=1024)
    mats = Mats(tex)
    b, _ = book(name, 0.0, "octavo", mats, rng, "brown", label, 1, bands, detail=detail)
    lo, hi = F.bounds([b])
    size = hi - lo
    b.scale = (1 / size[0], 1 / size[1], 1 / size[2])
    F.bake_transform(b)
    F.origin_bottom(b)
    b.location = (0, 0, 0)
    F.export(name, fmt=fmt, notes="one octavo scaled into a unit box for instancing (%s, %d bands)" % (detail, bands))


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = a[0] if a else os.path.join(HERE, "out")
    tex = a[a.index("--tex") + 1] if "--tex" in a else os.path.join(out, "textures", "leather_white")
    count = int(a[a.index("--count") + 1]) if "--count" in a else 12
    family(out, tex, count)
    if "--unit" in a:
        unit(out, tex)
