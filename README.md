# prop-forge

An Agent Skill that lets Claude (Claude Code, or any agent that reads `SKILL.md` skills) model realistic, game-ready 3D
props from scratch, with code, in headless Blender:

- built at **real-world size** from the parts the real object is made of (boards, joints, gaps, bevels), from a build
  script you can re-run and vary with a seed;
- dressed in **CC0 photo materials** (Poly Haven, ambientCG) at their true scale, grain running along each part;
- aged with **baked wear** that follows the shape (rubbed edges, crevice grime, dirt near the floor, dust on top) into
  one texture set and one material;
- judged on **rendered review sheets** (Cycles: three-quarter, straight views, a close detail, the game's own view at
  true pixel size, a 1.75 m figure for scale) and **measured checks** (size, ground contact, floating and inside-out
  pieces, swapped textures, texel density, triangle budget), with a critique-and-fix loop;
- exported as **glTF** and verified on re-import, then handed to the engine (Unreal, Unity, Godot, web).

## Install

Copy `skills/prop-forge` into your skills folder:

```
# Claude Code, for all projects
cp -R skills/prop-forge ~/.claude/skills/
```

Requirements: Blender 5.2 or newer, Python 3. A GPU makes review renders faster but is optional. Fetching textures needs
the internet.

## Use

Ask for a prop: "model a weathered sea chest with iron straps for my Unity game, under 6k tris". The skill guides the
agent through a brief with sourced dimensions, a measured blockout, construction, materials, review rounds and export.

The scripts also work on their own:

```
python skills/prop-forge/scripts/fetch_cc0.py search oak planks
python skills/prop-forge/scripts/fetch_cc0.py texture oak_veneer_01 --res 2k --out textures
python skills/prop-forge/scripts/run.py my_build.py -- out/
python skills/prop-forge/scripts/run.py review.py -- out/prop.glb --out out/sheet.png --ruler --game 8,4,40,1080
python skills/prop-forge/scripts/run.py check.py -- out/prop.glb --expect 0.6,0.4,0.45 --max-tris 5000
python skills/prop-forge/scripts/run.py silhouette.py -- out/prop.glb --ref-image ref/front.png --view front
```

`skills/prop-forge/examples/books.py` builds a family of leather-bound books (rounded spines, raised bands, labels,
inset page blocks) at about a thousand triangles each.

## What's inside

| Path | |
|---|---|
| `SKILL.md` | the workflow the agent follows |
| `scripts/forge.py` | modelling library for build scripts: boxes, cylinders, lathes, extrusions, padded shapes, bevels, deformers, true-scale UVs, PBR materials from photo sets, glTF export with a manifest |
| `scripts/forge_bake.py` | `F.bake()`: unique UV atlas, materials and wear baked into one texture set and material |
| `scripts/measure.py` | a reference model's size and height profile |
| `scripts/review.py` | Cycles review sheets of an exported file |
| `scripts/check.py` | re-import checks |
| `scripts/silhouette.py` | outline comparison against a reference model or photo |
| `scripts/fetch_cc0.py` | CC0 texture and model search and download |
| `references/` | realism rules, real-world dimensions, material values, how to read a review sheet, construction notes by prop family, engine notes |

Works well alongside [EL4CTEO/blender-skills](https://github.com/EL4CTEO/blender-skills) (MIT), whose QA, baking and
export skills prop-forge mentions but does not need.

## Credits and licence

MIT licence (see LICENSE). Textures and models fetched by `fetch_cc0.py` come from
[Poly Haven](https://polyhaven.com) and [ambientCG](https://ambientcg.com), both CC0. Powered by the Poly Haven API.
