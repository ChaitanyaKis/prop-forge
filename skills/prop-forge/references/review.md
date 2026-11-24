# Reading a review sheet

Look at the sheet with the Read tool after every round. Open single tiles too when something is small (they are saved
beside the sheet as `<sheet>_<view>.png`). Go through the checklist in order, because the earlier items make the later
ones moot.

## Checklist
1. **Silhouette** (three-quarter and game tiles): is the object recognisable from its outline alone? Is the outline
   interesting, with no long dead straight runs where the real thing would break or curve?
2. **Proportions** (front, side, scale tiles): compare each main measurement with the brief, by eye against the 1.75 m
   figure, and by number from `check.py`. Thickness of boards, legs, rims, covers.
3. **Construction**: could this be built? Does every part join something? Are there the seams, reveals and fixings
   the real object has (see `realism.md` 7)?
4. **Edges**: a thin line of light on every edge in the detail tile? Bevel widths match the material?
5. **Surfaces**: grain or weave true to scale and running along parts? No visible repeat, no stretching, no same patch
   on neighbours? Roughness plausible (metal shines, cloth doesn't)? Value and hue variation between parts?
6. **Contact**: shadows tight under the prop and between parts; nothing hovers; nothing sinks into the floor.
7. **Readability at game size** (game tile): main forms separate in value; nothing important under 2 px; no shimmering
   fine detail; it reads in the game's light (`--light warm` or `dim`).
8. **Wear** (after `F.bake`): does it fall where use and weather would put it (rubbed edges at hand height, grime in
   corners, dirt low down, dust on top)? Too even reads as a filter; too strong reads as a pattern. Look close and in
   the game tile.
9. **Family consistency**: variants side by side look related but not copied; the prop fits the set it goes into
   (period, wear, palette).

## Writing the critique
One defect per line: severity, the tile, what is wrong, a measurement, the fix as a change to the script.

- **major**: breaks the illusion at game distance (wrong proportion, floating part, missing major part, wrong scale
  texture, unreadable in the game tile).
- **minor**: visible on close inspection (a repeat, a bevel too small, too little variation).
- **note**: a choice to mention in the report, not a defect.

```
1. [major] side: seat is 0.06 m thick, a rush seat is 0.03-0.04 (dimensions.md). SEAT_T 0.06 -> 0.035.
2. [major] three_quarter: back slats float 4 mm in front of the top rail. Move them back 6 mm into the rail.
3. [minor] detail: all four legs show the same knot at the same height. Pass rng= to the legs.
4. [note] game tile: stretchers are 1 px and read as noise; kept for close views, cheap.
```

## When to stop
Stop when a full pass finds nothing above minor, or after six passes. Fix minors that are cheap. In the report, list
what remains and why. Never call a prop done from the build scene alone: the sheet and `check.py` must both come from
the exported file.

## Comparing with a reference
When there is a reference (a CC0 scan or the user's picture), add `silhouette.py` from the same side to each round.
Blockout gate IoU 0.85 or more with every band within 0.05; finished gate 0.9 and 0.03. Write mismatches as numbers:
"band 7 (the top) is 0.06 wider than the reference: the top overhangs too far".
