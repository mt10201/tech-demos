# build123d-param-cad — Rodin coil torus

Parametric CAD playground: a **torus (donut) with Rodin-style semicircle grooves**, built with [build123d](https://build123d.readthedocs.io/) + Streamlit and previewed with Plotly. The default preset, **Photo replica**, reproduces the crisscross groove lattice of a real rainbow Rodin coil frame: 12 + 12 grooves spiralling in both directions, with raised rhombus tiles between them. The earlier **Rodin golden spiral** and **Mirror golden spiral** presets are still available.

Bookmark source: [gregisenberg hardware/robotics tooling list](https://x.com/gregisenberg/status/2100229768385822812). Dimensions come from the owner's SOLIDWORKS sketch.

This is **not** a 3D-printer settings app. It designs the shape; slice the STL elsewhere.

## Units and defaults (inches, matching SOLIDWORKS)

| Parameter | Default |
|---|---|
| Major radius R (axis → tube centre) | **1.39** |
| Tube radius r | **0.695**: outer Ø 4.17, hole Ø 1.39 (hole/OD = 0.333) |
| Pattern | **Photo replica**: 12 grooves per direction, both directions |
| Sweep rim → hole | **150°** (measured from the photo) |
| Groove width | **0.125** (1/8"), measured in true 3D; slider 1/16"–1/2" |
| Groove depth | **0.125** (1/8"); slider 1/32"–1/4" |
| Profile | **U-groove**: semicircular bottom of radius 1/16" plus straight walls 1/16" tall. depth = width/2 is a pure semicircle; depth < width/2 is a shallow arc |

## Photo replica: what was measured

These numbers come from a polar unwrap and copper-colour mask of the photo:

- **Counts:** the angular period of the copper channels is 29–30° at three radii, so **12 grooves per direction**, 24 in total. There are about 24 tiles per ring.
- **Pitch:** the dominant family's azimuth grows almost **linearly with tube angle θ**, with dφ/dθ ≈ 0.84–0.87. It is *not* a golden spiral: a golden spiral would need about 190° over the measured radius range, but the photo shows about 85°. Extrapolated rim → hole, that's about **150°** (5 of the 12 poles, the Rodin skip), or about 300° per full wrap.
- **Directions:** the two directions look mirror-symmetric, judging by the diamond tiles. The second, thinner family was hard to isolate automatically.
- **Channel width:** each channel holds **one twisted multi-strand bundle**. One direction's bundles are about twice as thick as the other's. Scaled to a 4.17" OD, the channels are only about 0.06–0.11" wide.
- **Proportions:** the photo's hole is about 138 px against an OD of about 603 px, so hole/OD ≈ **0.23** and r/R ≈ 0.63. The owner's part is 0.333 and 0.50: a noticeably bigger hole and a slimmer tube.

## How the grooves are built

Torus coordinates: `point(θ, φ) = ((R + ρ cos θ) cos φ, (R + ρ cos θ) sin φ, ρ sin θ)`, with θ around the tube (0 = outer equator/rim, 90° = front face, 180° = hole) and φ around the main axis.

**Photo replica (default):** `φ = φ₀ ± (sweep/180°)·θ`, with θ going 0 → 360°, `φ₀ = rotation + i·30°`, and 12 grooves for each sign. Each groove is a constant-pitch helix that wraps the full torus. With sweep = 150°, a wrap advances 300° (10 poles), so the grooves join end-to-start into seamless closed loops. Any multiple of 15° does the same.

**Wall thickness:** grooves of *opposite* direction are meant to cross. In the photo preset they cross every 18° of θ along each groove, and on the inner equator both families cross at the same 12 points, 30° (0.364") apart. Neighbours in the *same* direction come closest at the hole (θ ≈ 187°). Their perpendicular centre-line spacing there is `(2π q/N)·sin α`, with `q = R − r`, `tan α = r/(q·k)` and `k = sweep/180°`, which comes to **0.280"**. Subtracting the groove width gives the wall. The app computes this numerically for every pattern (3D closest approach of the surface centre-lines) and warns when the wall drops below 0.04" or goes negative (grooves merge):

| Width | Min wall at the hole |
|---|---|
| 1/8" (default) | **+0.155"** |
| 3/16" | +0.092" |
| 1/4" | +0.030" |
| 5/16" | −0.033" (merge) |
| 3/8" | −0.095" (merge) |

The wall depends only on width, not depth. A U-groove keeps the same width at any depth.

**Golden-spiral presets:** these are the earlier variants, described below.

1. **Profile.** This is the same true-3D profile as the photo preset (see *Outputs*).
2. **Path: one helical wrap per groove.** θ goes 0 → 360° once around the tube while φ advances around the main axis.
3. **Top half = golden spiral.** On θ 0 → 180° (outer equator → over the top → inner equator) the azimuth is
   `φ = φ₀ + (π/2)·log_φ(q_max / q)`, `q = R + r cos θ` (surface centre-line),
   so the projected radius shrinks by φ ≈ 1.618 for every 90° of azimuth. From 2.085" down to 0.695" (ratio 3) that's a **205.5°** golden-spiral sweep.
4. **Bottom half (closure option).**
   - **Rodin (default):** the bottom half sweeps 510° − 205.5° so each wrap advances 360° + 150° (the classic Rodin 5-of-12 pole skip). Groove *i* ends exactly where groove *i+5* starts, so the 12 grooves chain into **one continuous closed winding**.
   - **Mirror:** the bottom half is the mirror golden spiral (205.5°), giving 12 open grooves and the crossing rosette you see in the SOLIDWORKS top view.
5. **Handedness** and **start-pole rotation** are sliders.

For these presets, the numeric minimum-wall check also flags merging at 3/16" depth.

## Outputs

- **3D preview, front view and STL: real mesh boolean** (`boolean_mesh.py`, [manifold3d](https://github.com/elalish/manifold)). This replaces the earlier heightfield, whose grid aliasing caused stair-stepped groove walls.
  1. The torus is tessellated from its chord error: segment counts around the axis and the tube are chosen so that no facet deviates more than `chord` from the true surface.
  2. Each groove's centre-line is traced on the surface. Grooves that join end-to-start are chained into closed loops: the photo preset gives 4 loops, 2 per direction.
  3. The U profile (straight walls plus a semicircular floor of radius w/2, extended 0.03" above the surface) is swept along each loop. The sweep uses a frame built from the torus normal, so the walls stay normal to the surface.
  4. `torus − union(all cutter tubes)` is evaluated by manifold3d. The result is guaranteed manifold, and every wall and floor is a swept surface, not a grid.

  | | chord error | step along path | arc segments | triangles | binary STL | time |
  |---|---|---|---|---|---|---|
  | Live preview | 0.002" | 0.05" | 8 | ~130 k | — | ~0.6 s |
  | **Prepare high-res STL** | **0.0005"** | 0.02" | 24 | **579,960** | **29.0 MB** | ~2 s |

  The high-res STL is watertight and winding-consistent (trimesh), with volume 10.926 in³. Width, measured on the actual STL by slicing it with a plane perpendicular to the path 9° away from a crossing: **0.12500" at the rim, 0.12499" on top, 0.12500" at the hole, 0.12500" on the bottom**. The floor is 0.125" deep at all four (`tests/test_geometry.py::test_boolean_mesh_groove_width_and_depth`). For display only, the preview drops zero-area slivers and splits vertices at creases sharper than 35°, so smooth shading keeps the groove lips crisp.
- **Close-up section:** 0.64"-diameter samples of the high-res STL at the outer rim and the inner hole, at the same scale. Each is cut out with a manifold ball intersection. Alongside them are cross-sections of the actual STL at rim, top, hole and bottom; all four profiles are identical. The sidebar's *3D camera ▸ Zoom across the hole* gives a close-up of the groove walls.
- **Front view:** an orthographic view looking along the axis, like the photo. Tiles are rainbow-coloured by azimuth and grooves are copper.
- **Prepare STEP — finished solid:** a true B-rep with the grooves already subtracted (`rodin_torus.finished_solid`). The torus and 24 swept U cutters come from build123d. The U profile uses an auxiliary spine, so the walls stay normal to the torus. Cutting everything in one OpenCascade boolean, or cutting a union of all cutters, returns invalid shapes. **Sequential fuzzy cuts work**: one `BRepAlgoAPI_Cut` per groove with fuzzy value 1e-4 (retried at 1e-3), and after each cut the result is checked to be a valid solid with decreasing volume. For the photo preset the result is a valid solid of 10.9447 in³ with 1693 faces, and it re-imports as 1 valid solid. It takes about 4–5 min and the STEP is about 92 MB (about 26 MB zipped), which is why it is built on demand rather than committed.
- **Build STEP tool bodies (fast fallback):** the torus, cutter bodies and centre-lines, in seconds. In SOLIDWORKS: open the STEP → *Insert ▸ Features ▸ Combine* → *Operation type: Subtract* → *Main body*: the torus → *Bodies to subtract*: all 24 groove bodies → ✓.
- **Generated build123d snippet** for the current slider values (it produces the same STEP bodies).

## Run

macOS / Linux:

```bash
cd apps/build123d-param-cad
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Windows PowerShell:

```powershell
cd apps\build123d-param-cad
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Tests / screenshots

```bash
pytest -q          # geometry math, boolean mesh width/depth/watertight, B-rep cutter smoke tests
REFERENCE_PHOTO=/path/to/photo.png python capture.py
# writes media/preview.png, front_view.png, closeup_rim_vs_hole.png, zoom_groove_walls.png,
#        mesh_wireframe_rim.png (actual STL triangles), preview_mirror.png, screenshot.png,
#        snippet.png, and compare_photo.png (only when REFERENCE_PHOTO is set)
```

## Make your own shapes

1. **Sliders first.** Everything in the sidebar is live: preset, R, r, depth, width, sweep (photo preset), handedness and start rotation. Check the *Min wall* metric before printing.
2. **Copy the generated snippet.** The *Generated build123d snippet* at the bottom of the page is a standalone script for the current settings. Run it with `python snippet.py` to get a STEP (torus plus cutter bodies) you can open in SOLIDWORKS and *Combine ▸ Subtract*. Or use **Prepare STEP — finished solid** in the app.
3. **Edit the geometry functions.**
   - **[`geometry.py`](geometry.py)** holds all the shape maths.
     - `TorusParams` sets the defaults: `major_radius`, `tube_radius`, `n_grooves` (per direction), `groove_depth`, `groove_width`, `pattern`, `sweep_deg`, `handedness` and `rotation_deg`.
     - `azimuth_offset(p, θ)` is the function to change for a new winding law: how far around the axis a groove has travelled at tube angle θ.
     - `families(p)` decides whether one or both rotational directions are cut.
     - `groove_path` and `all_paths` turn that into 3D centre-lines.
     - To add a preset, add a name to `PATTERNS` and `PATTERN_LABELS` and a branch in `sweeps()` / `azimuth_offset()`.
   - **[`boolean_mesh.py`](boolean_mesh.py)** turns any set of centre-lines into the grooved STL by mesh boolean. `u_profile()` is the cutter cross-section, so change it for square or V channels. `PREVIEW_KW` and `EXPORT_KW` set the resolution.
   - **[`rodin_torus.py`](rodin_torus.py)** builds the build123d B-rep (`Solid.make_torus`, `Solid.sweep` of the U face along `Edge.make_spline`) and `finished_solid()` for the subtracted STEP.
   - `torus_mesh.py` is the older heightfield mesher, kept for comparison and tests.
4. **Learn build123d** at the docs: https://build123d.readthedocs.io (Tutorials, then *Builders* vs *Algebra*). Swap `Circle` for another profile, e.g. `Rectangle` for square channels, or `Solid.make_torus` for any other base solid.
