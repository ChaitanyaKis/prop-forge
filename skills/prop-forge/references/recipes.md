# Construction notes by prop family

Parts in build order, the forge calls that make them, and the detail that sells each one. Sizes are in
`dimensions.md`. `examples/` holds complete scripts.

## Books
- **Page block**: `F.soft` slightly smaller than the cover (inset by the squares, 2-4 mm on three sides), its fore-edge
  pushed in a little (`F.deform`: a rounded spine makes the fore-edge concave by 2-4 mm). A paper material with a
  fine horizontal line texture or a plain cream with high roughness.
- **Boards**: two thin `F.box` (2-4 mm, bevel 1 mm) a little larger than the block. **Spine**: `F.extrude` of a curved
  cross-section (an arc standing 2-5 mm proud) joining the boards, or `F.lathe`-free: a half-cylinder `F.cyl` scaled.
- **Joint groove** where spine meets board, **raised bands** across the spine on old books (`F.box` 2-3 mm high),
  **headbands** (a small cylinder at the top and bottom of the spine), corners and clasps on precious books.
- Leather material at true scale (0.3-0.6 m photo); vary tint strongly between books (oxblood, brown, green, navy,
  black), wear the corners and the spine's ends lighter.
- Families: vary height, width and thickness inside the format ranges, and lean (0-4 degrees) when shelved. Many
  books: keep each book to a few hundred triangles; it is the variation that sells a shelf, not the detail.

## Tables and desks
- Top (with an edge profile: bevel 3-6 mm, or a moulding made with `F.extrude` along each side), aprons let into the
  legs, legs (square tapered: `F.box` then `F.deform` to taper; turned: `F.lathe`), stretchers on period pieces.
- Pedestal desks: carcass boxes, drawer fronts proud or inset by 2 mm with 2 mm gaps, knobs or pulls, a leather writing
  surface let into the top 2-4 mm from its edge.
- Sells it: tops overhang the aprons by 2-5 cm; grain on the top runs the long way; a slightly worn front edge.

## Chairs and stools
- Legs (splayed 5-10 degrees on stools: `rot=`), seat (board, rush or upholstered `F.soft`), stretchers at 15-20 cm,
  back posts continuing the rear legs, rails and slats (`F.extrude` for curved crest rails).
- Sells it: the seat dished or worn smooth; legs tapering toward the floor; stretchers worn on top where feet rest.

## Cabinets, cupboards, bookcases, dressers
- Carcass: sides, top, bottom, back (thin, 6-10 mm, often planks with gaps), shelves resting on the sides (sagging a
  little under load: `F.sag`), plinth or feet, cornice moulding.
- Doors as frame-and-panel: four `F.box` frame members and a thinner panel set 5-10 mm back; hinges (small `F.cyl`
  knuckles), a keyhole escutcheon.
- Drawers: fronts with 2 mm gaps, pulls or knobs at the centre or thirds.

## Chests, crates, barrels
- Chest: boards with 1-2 mm gaps, a lid slightly larger than the box, iron straps (`F.box` 3-5 mm thick) with rivet heads
  (`F.sphere` flattened), corner brackets, a hasp, handles at the ends.
- Crate: slats with gaps, corner battens, nail heads (2-3 per joint); boards not quite flush.
- Barrel: staves from `F.lathe` of the bulged profile (or 18-24 tapered `F.box` staves rotated around), hoops as thin
  `F.lathe` rings 4-5 cm wide standing 2-3 mm proud, heads inset 2-3 cm from the stave ends (the chime).

## Turned ware: bottles, jugs, cups, bowls, candlesticks
- One `F.lathe` profile going up the outside and back down the inside gives the wall thickness (2-6 mm for ceramics,
  1.5-3 for glass). Lip rounded with 2-3 extra profile points.
- Handles: `F.extrude` of a C outline, or a chain of short `F.cyl` along an arc, joined into the body.
- Sells it: a foot ring under bowls and cups; a slightly uneven rim (`F.lumps` with a small amplitude) on hand-thrown
  pottery; glaze stopping short of the foot.

## Soft goods: cushions, mattresses, bedding, sacks, folded cloth
- `F.soft` for the mass, then shape: `F.lumps` for stuffing, `F.sag` or a custom `F.deform` for where it rests or is sat
  on, a crease line pressed in along seams.
- Drapes and blankets over a bed or table: a subdivided plane (`F.soft` with a small thickness) shaped by a function that
  follows the support and falls off the edges in a catenary; add a few low-frequency folds (`F.lumps`). Don't rely on
  cloth simulation headless.
- Sells it: piping along the seams, buttons or tufting pulling the surface in, a folded edge rather than a cut one.

## Paper: sheets, letters, maps, scrolls
- Sheets: a thin `F.box` (0.3-1 mm) with a curl (`F.deform` lifting one corner 5-15 mm); stacks with jitter of 1-3 mm
  and 1-2 degrees per sheet.
- Scrolls and rolled maps: `F.cyl` with a spiral visible at the end (a lathe profile or a few nested thin rings), a
  ribbon tie; unrolled maps curl at the ends.

## Metal fittings
- Hinges, straps, brackets: `F.box` 2-5 mm thick, bevel 0.5-1 mm, rivet or nail heads at regular spacing with jitter.
- Handles and rings: a torus from `F.lathe` of a small circle profile offset from the axis, or `F.cyl` segments.
- Sells it: darker metal in crevices and lighter, smoother metal where handled.

## Lighting: candles, candlesticks, lanterns, oil lamps
- Candle: `F.lathe` with a slightly uneven top and a drip or two (`F.lumps` masked to the top); a wick (thin `F.cyl`),
  charred black.
- Lantern: frame from thin boxes or cylinders, glass panes as thin boxes with a glass material, a handle ring, a vented
  cap.

## Architecture pieces
- Doors: frame-and-panel or boarded with ledges and braces (the Z of a cottage door), strap hinges, a latch.
- Beams and posts: bevelled `F.box` with adze marks (`F.lumps` at a long scale on the faces) and checks (cracks) as thin
  grooves along the grain.
- Steps and sills: worn hollow in the middle where feet go (`F.deform`).
