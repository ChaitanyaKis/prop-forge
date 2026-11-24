"""Build script for <prop>. Copy, rename to build_<name>.py, and fill in.

  python <skill>/scripts/run.py build_<name>.py -- <out_dir> [--variants N]

Metres, Z up, front toward -Y, origin on the floor at the middle of the footprint, rotations in degrees.
Every size below names its source (the brief, dimensions.md, a measured scan).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_SCRIPTS = os.environ.get("PROP_FORGE", r"<skill>/scripts")   # set to the skill's scripts folder
sys.path.insert(0, SKILL_SCRIPTS)
import forge as F  # noqa: E402

# ---- sizes (source in each comment)
W, D, H = 0.60, 0.40, 0.45          # overall: brief
TOP_T = 0.025                       # top thickness: dimensions.md, tables 2.5-4 cm
LEG = 0.035                         # leg section: dimensions.md, stools 3-4 cm

# ---- materials: CC0 folders fetched with fetch_cc0.py (info.json gives metres)
TEX = os.path.join(HERE, "textures")


def materials():
    wood = F.pbr("wood", tex=os.path.join(TEX, "<polyhaven_id>"), metres=1.0, grain="u")
    iron = F.flat("iron", (0.56, 0.57, 0.58), rough=0.6, metal=1.0)
    return wood, iron


def top(wood, rng):
    return F.box("top", (W, D, TOP_T), (0, 0, H - TOP_T / 2), wood, bevel=0.004, rng=rng)


def legs(wood, rng):
    out = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (W / 2 - 0.05), sy * (D / 2 - 0.05)
            leg = F.box("leg_%d_%d" % (sx, sy), (LEG, LEG, H - TOP_T), (x, y, (H - TOP_T) / 2), wood,
                        bevel=0.003, rng=rng)
            out.append(F.jitter(leg, rng, move=0.001, turn=0.4))
    return out


def build(out_dir, seed=0, name="prop"):
    rng = F.begin(name, out_dir, seed=seed)
    wood, iron = materials()
    top(wood, rng)
    legs(wood, rng)
    return F.export(name)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = args[0] if args else os.path.join(HERE, "out")
    n = int(args[args.index("--variants") + 1]) if "--variants" in args else 1
    for v in range(n):
        build(out, seed=v, name="prop" if n == 1 else "prop_%02d" % v)
