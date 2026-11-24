# Taking props into an engine

First look for the project's own pipeline (CLAUDE.md, README, an import script) and use it. These notes are for
projects without one. Whatever the engine, a prop is done when it has been seen in the engine at the game's camera.

## Unreal Engine 5
- Import the `.glb` (Interchange reads glTF): scale converts from metres to centimetres and Y-up to Z-up. glTF normal
  maps are OpenGL-style and Unreal's are DirectX-style; the importer is meant to handle this, but check one prop under a
  raking light (bumps should not look dented) and set "Flip Green Channel" on the normal texture if they do. Check the
  orientation too (forge: front faces -Y in Blender).
- Nanite suits dense static props; small or alpha-tested ones can stay non-Nanite. Collision: simple boxes for
  furniture (or UCX_ meshes), complex-as-simple for walk-on props only.
- Textures should be power of two for mipmaps (forge resizes). The ARM image maps to Unreal's packed ORM channels
  (R occlusion, G roughness, B metal).
- Budget for a 60 fps PC game: props 500-15k triangles (Nanite lifts this), 1-3 materials each.

## Unity
- glTF needs the glTFast package (or export FBX from Blender instead). Scale is metres already.
- URP/HDRP materials: base map, normal map, and a mask map (HDRP: R metal, G occlusion, A smoothness = 1 - roughness;
  convert from ARM if the importer does not).
- Budget: mobile props 300-3k triangles, PC 1k-15k.

## Godot 4
- Drop the `.glb` into the project: it imports natively, metres, Y-up. Name suffixes in Blender give collision on import
  (`-col`, `-colonly`).
- ORM maps are supported in StandardMaterial3D.

## Web (three.js, Babylon, model-viewer)
- `.glb` loads directly. Keep textures to 1k-2k, consider KTX2/Basis compression and meshopt for size.
- Validate with the Khronos glTF validator when something renders wrong.

## Roblox
- Use the blender-* skills' `blender-export-pipelines` (FBX presets, MeshPart limits of 20k triangles, single UV set).
