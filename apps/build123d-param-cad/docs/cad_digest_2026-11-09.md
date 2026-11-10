# CAD tech digest, Nov 9 2026: what was adopted

## OrcaSlicer 2.5.0 Texture Displacement: use it in Orca (no in-app copy)
It bakes a height-map texture into real mesh relief, and the baked relief exports as an ordinary STL. The app
does not reimplement it: the Moai v2 back already has a weathered-stone texture, the face is scan texture, and
a second texture on top would blur detail. Use Orca's tool on smooth masters (Rodin torus, tower,
plaques) when you want a stone or basalt surface on the casting.

How to use it on a mold master:
1. Import the master STL, select it, and open **Texture displacement** in the toolbar above the 3D view.
2. Pick a built-in texture or import a PNG/JPG (a stone/basalt photo in greyscale works). Paint the area,
   or click **Select whole model**. Keep it off the plate, the groove/lip, and fine details such as the face.
3. **Depth** 0.2-0.4 mm (silicone copies 0.1 mm detail; deeper relief traps silicone and slows demolding).
   **Tile size** 15-30 mm. Turn **Edge fade** on so the relief fades out at the painted edge. Use
   **Mirrored repeat** to hide tile seams. For fine textures, untick **Auto** resolution and raise **Budget**
   if Orca warns.
4. Click **Bake**, then **File > Export > Export Model > STL** to keep the textured master as a separate
   file. Leave the original untouched.
5. Before printing, check that relief did not create overhang pits or thin peaks. Do not texture the
   seating/lip surfaces, because they must stay smooth to seal.
Sources: https://www.orcaslicer.com/wiki/print_prepare/prepare_texture_displacement ,
https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/v2.5.0

## LibreDirect3DS2v11 (LibreYOLO repack of Direct3D-S2 v1.1, MIT): evaluated, not run
- Weights: 4.23 GB in the HF repo (dense 1.51 GB, sparse 512 and 1024 at 1.10 GB each, two refiners at
  0.27 GB each), plus DINOv2-large and BiRefNet, plus a CPU PyTorch install.
- Box: 8 CPU cores, no GPU, about 11 GB free RAM. The sparse 512/1024 stages are designed for GPU. On CPU, one image
  would plausibly take hours and could run out of memory, so it was not installed or run, to save time and usage.
- Even on a GPU, a single front photo cannot show the real back of a moai. The model would invent one, as
  the v2 back does, without the control a signed-distance build gives. It is still worth a try on Timothy's PC
  (if it has an NVIDIA GPU with 12 GB or more) for new subjects that have no scan. Nothing was installed
  on his PC. The app requirements are unchanged.
