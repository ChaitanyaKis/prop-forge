# Materials

## Finding CC0 photo materials
- `python scripts/fetch_cc0.py search <words>` searches Poly Haven textures (most-downloaded first) and prints each
  one's real size; add `--models` to search 3D scans instead. Good words: oak, walnut, planks, bark, leather, linen,
  wool, canvas, rope, paper, parchment, plaster, brick, cobblestone, slate, marble, rust, iron, copper, brass, gold,
  painted, peeling, worn.
- `fetch_cc0.py texture <id> --res 2k` downloads colour, OpenGL normal and ARM maps plus `info.json` with `metres`.
- ambientCG (`fetch_cc0.py ambientcg <AssetId> --res 2K`, e.g. `Wood049`, `Leather037`, `Fabric045`) has more fabrics and
  paints, but no physical size: judge the repeat from the photo (count planks, weave threads, bricks).
- Both are CC0: free for any use, no attribution needed for the assets themselves. Keep `info.json` with the textures
  so the source stays on record.

## Scale and density
Pass `metres` to `F.pbr`. Keep texel density (pixels of texture per metre of surface) even across an asset; `check.py`
reports it per material and warns at 2x apart.

| Seen as | Texel density |
|---|---|
| Hero, fills the screen, first-person close-ups | 1024-2048 px/m |
| Room-scale prop at 3-10 m on a 1080p screen | 512-1024 px/m |
| Background, distant set dressing | 256-512 px/m |

Texture size per material is usually 1k-2k; share one material across a family (all the books, all the crates).

## Grain direction
Wood grain, cloth weave and brushed metal run one way in the photo. Look at the albedo once and pass `grain="u"`
(runs across) or `grain="v"` (runs up). forge lays it along each box part's longest side and along turned parts' axes.
Pass `grain=None` to a shape to leave the projection unturned, or an axis number (0, 1, 2) to force one.

## Roughness (0 mirror, 1 chalk)
| Surface | Roughness |
|---|---|
| Glass, polished glaze | 0.0-0.1 |
| Polished brass, silver | 0.15-0.3 |
| Varnished or waxed wood | 0.3-0.5 |
| Worn handled wood (handles, arm rests) | 0.35-0.5 |
| Leather, smooth / worn | 0.4-0.55 / 0.55-0.7 |
| Wrought or cast iron | 0.5-0.75 (rusty 0.8-0.95) |
| Raw wood | 0.65-0.85 |
| Unglazed clay, terracotta | 0.75-0.9 |
| Linen, wool, canvas, paper | 0.8-0.95 |
| Candle wax | 0.3-0.5 |
| Stone, plaster | 0.6-0.9 |

Photo sets bring their own roughness map; adjust with `rough_mul` (for example 0.8 for a polished version).

## Plain values for small parts (`F.flat`)
Base colour here is linear (what Blender's Base Color takes). Metals use metal=1.0.

| Material | Base colour (linear) | Metal | Roughness |
|---|---|---|---|
| Iron, steel | 0.56, 0.57, 0.58 | 1 | 0.4-0.7 |
| Silver | 0.97, 0.96, 0.92 | 1 | 0.15-0.35 |
| Gold | 1.00, 0.77, 0.34 | 1 | 0.15-0.35 |
| Copper | 0.96, 0.64, 0.54 | 1 | 0.25-0.45 |
| Brass | 0.91, 0.78, 0.42 | 1 | 0.25-0.45 (aged: multiply by 0.7) |
| Bronze (aged) | 0.45, 0.32, 0.18 | 1 | 0.45-0.6 |
| Pewter | 0.45, 0.45, 0.44 | 1 | 0.4-0.55 |
| Black iron paint | 0.02, 0.02, 0.02 | 0 | 0.5-0.7 |
| Candle wax (cream) | 0.62, 0.55, 0.40 | 0 | 0.35 |
| White glaze | 0.70, 0.68, 0.63 | 0 | 0.08 |
| Paper (aged) | 0.55, 0.48, 0.35 | 0 | 0.9 |

To convert an sRGB value to linear, raise it to the power 2.2 (sRGB 0.5 is linear 0.22).

## Baked wear (`F.bake`)
| Preset | edges | grime | ground | dust | variation | For |
|---|---|---|---|---|---|---|
| `light` | 0.3 | 0.3 | 0.15 | 0.1 | 0.06 | kept things: a study's desk, a lady's candlestick |
| `worn` | 0.55 | 0.55 | 0.3 | 0.2 | 0.1 | things in daily use: tavern furniture, tools, crates |
| `old` | 0.8 | 0.8 | 0.5 | 0.35 | 0.14 | neglected things: cellars, ruins, attics |

- `density` (px per metre, default 768) sets the atlas size from the prop's surface area, rounded to a power of two
  between 512 and 4096; or pass `size`. The result reports the density it reached.
- `edge_width` (metres, default 0.006) is how wide the rubbed band along convex edges is; `ground_height` how high
  floor dirt climbs (default 30% of the height, at most 0.25 m); `dust_colour` sRGB.
- Metal parts keep their metal channel; their edges brighten like rubbed metal and dust dulls them.

## Engines and maps
- forge writes albedo, ARM (G roughness, B metal: glTF's metallicRoughness layout) and an OpenGL normal map. Don't use
  DirectX normal maps (`nor_dx`) in Blender; engines that want DirectX flip on import.
- Colour images are sRGB; roughness, metal and normal maps are non-colour. forge sets this; `check.py` looks at the
  pixels to catch a swap.
- Power-of-two sizes are needed for mipmaps on many platforms; forge resizes.
