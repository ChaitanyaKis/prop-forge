# Why props look computer-made, and the fixes

Read before the first construction pass. Each item is a cause you can see on a review sheet, why the eye catches it,
and what to do in the build script.

## 1. Knife edges
Real edges are never perfectly sharp: they are sanded, worn, cast or chipped, and the round catches a thin line of
light that tells the eye the object is solid. A model without it looks like a paper cut-out.

| Material | Bevel width | Segments |
|---|---|---|
| Hardwood furniture, boards | 2-4 mm | 2-3 |
| Worn tops, handrails, arm rests, steps | 5-10 mm | 3-4 |
| Softwood, rough-sawn timber | 1-3 mm, uneven | 2 |
| Machined metal | 0.3-1 mm | 2 |
| Cast or forged metal | 1-2 mm | 2-3 |
| Stone blocks, masonry | 3-15 mm, chipped | 2-3 |
| Book boards (covered) | 1-2 mm | 2 |
| Glazed ceramic rims | 1-2 mm | lathe profile |
| Padded cloth, cushions | 15-40% of the thickness | `F.soft` |

## 2. Wrong thickness and proportion
Models built by guess are too thick almost everywhere ("chunky game furniture"): 8 cm table tops, 10 cm legs. Real
pieces are thinner than you expect. Check against `dimensions.md` and write the source in the script. If the game
needs thicker parts to read at distance, thicken on purpose and note it in the brief.

## 3. Floating and intersecting parts
Things rest on things. A part that hovers 2 mm over its support shows a light gap and a detached shadow; one sunk
into another shows a hard intersection line. Join parts as they are joined in life: a tenon goes into the leg (the
overlap is hidden inside), a book rests on the shelf with its bottom at the shelf's top, a lid's rim sits on the box.
The prop's lowest point is at z=0 exactly. `check.py` reports floating pieces and ground contact.

## 4. Perfect regularity
Rows of identical, perfectly aligned parts read as copies. Hands and time make every piece a little different.

| What | Variation |
|---|---|
| Position of hand-placed parts | 1-3 mm |
| Angle of hand-placed parts | 0.2-1 degree (books on a shelf: 0-4 degrees lean) |
| Size of repeated parts (planks, books, stones) | 3-10% |
| Colour value between parts | 5-15% |
| Nails, rivets, stitches | 0.5-1 mm off their line |

Keep function: legs still reach the floor, drawers still fit. Vary inside the joint, not across it.

## 5. One material, one patch
The same texture patch on every board shows the same knot twice. Give each part a random offset (`rng=` in forge
shapes), and vary tint between parts. Different boards of one piece of furniture differ in hue a little; the panels of
a door differ more than its frame.

## 6. Texture at the wrong scale
A wood photo stretched so the grain is 3 cm wide on a chair leg, or a brick texture with bricks the size of a hand,
breaks scale at once. Use the photo's real width (`metres` from `fetch_cc0.py`), and keep texel density even across the
asset (`check.py` warns at 2x apart). Lay grain along the part's length.

## 7. No construction detail
An assembled object has seams: a 1-3 mm reveal around a drawer, a groove where a panel meets its frame, pegs through a
joint, hinges, nail heads, stitching along leather, headbands on a book, a lid's overhang. These lines are what make
an object read as made rather than poured. Model them when they are larger than about 2 px at the game camera;
smaller, leave them to the normal map.

## 8. No wear and no gravity
Objects have a history. Edges where hands go are rounder and smoother (lower roughness, a little lighter or darker);
the bottom 10 cm of furniture is scuffed; corners collect grime. Gravity acts: shelves sag 2-5 mm per metre under
load, cushions and mattresses bulge and dip, page blocks swell at the fore-edge, cloth hangs in catenaries, leather
covers warp. `F.sag`, `F.lumps` and `F.deform` do this. A little goes a long way: 1-3% of the part's size.
The colour side of wear (rubbed edges, crevice grime, dirt near the floor, dust on top) follows the shape, so a tiling
photo can't hold it: `F.bake("worn")` bakes it from the geometry into the prop's own texture (SKILL.md step 5).

## 9. Faceted curves
A curve shows its facets on the silhouette first. Pick segments by size on screen: peg 8-12, leg 16-24, bowl 32-48,
barrel or large drum 48-64. Shade smooth with sharp edges kept (forge does).

## 10. Judged under the wrong light
A model judged only in bright, even studio light can fall apart in the game's dark interior: forms with similar values
merge, and fine detail vanishes. Review under the game's mood too (`review.py --light warm` or `dim`) and at the
game's pixel size (`--game`). Parts that must read separately need about 10-20% difference in value.

## 11. Colour too clean
Real surfaces are darker and less saturated than they look. Pure white and pure black don't occur. Typical albedo
(sRGB): fresh snow 0.8-0.9, white paint 0.75-0.85, linen 0.6-0.75, concrete 0.35-0.5, light wood 0.4-0.55, dark
wood 0.15-0.3, dark leather 0.08-0.2, charcoal 0.03-0.05. Age lowers saturation and pushes colour toward grey-brown.

## 12. The object lacks a reason
Ask what the object is for and who used it, then let that show: a writing desk has an ink stain and a worn front edge;
a tavern bench is polished where people sit and dented where tankards landed; a ship's chest has iron corners because
it was dropped. One or two such details per prop are enough and are what people remember.
