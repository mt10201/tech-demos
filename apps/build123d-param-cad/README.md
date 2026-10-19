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

- **3D preview, front view and STL:** an analytic, watertight mesh with **constant true-3D groove width** (`torus_mesh.py`):
  1. Each groove centre-line is traced on the torus surface and sampled as a 3D polyline, spaced about width/4.
  2. The torus is meshed on a periodic (θ, φ) grid. For every surface vertex, a KD-tree finds nearby polyline vertices, and a nearest-segment search over their adjacent segments gives the exact 3D distance `t` to the closest centre-line.
  3. The vertex is pushed in along its surface normal by `depth(t) = (d − ρ) + √(ρ² − t²)` for `|t| < w/2` (otherwise 0). Where grooves cross, the deepest cut wins.

  Width therefore no longer scales with the local circumference `R + r cos θ`. The measured width perpendicular to the path, 9° away from a crossing, is 0.1249" at the outer rim, 0.1249" on top, 0.1250" at the hole and 0.1249" on the bottom (`tests/test_geometry.py::test_groove_width_constant_in_3d`).
  - The live preview uses a 180×720 grid (259,200 triangles, about 7.6 samples per groove width at the rim).
  - **Prepare high-res STL** uses a 400×1600 grid: 1,280,000 triangles, a 64.0 MB binary STL, watertight and winding-consistent (trimesh). That's about 15 samples per 1/8" groove width around the 13.1" rim and about 11 across the tube.
- **Close-up section:** 0.6" patches at the outer rim and the inner hole at the same scale, plus overlaid cross-sections at rim, top, hole and bottom. All four profiles are identical.
- **Front view:** an orthographic view looking along the axis, like the photo. Tiles are rainbow-coloured by azimuth and grooves are copper.
- **STEP**: exact build123d B-rep **torus + swept groove cutter bodies + centre-line splines** (24 for the photo preset). The U profile is swept with an auxiliary spine, so its walls stay normal to the torus along the whole wrap. OpenCascade's own `torus − cutters` boolean is unreliable for these long helical pipes (it returns invalid solids), so do the subtraction in SOLIDWORKS: open the STEP → *Insert ▸ Features ▸ Combine ▸ Subtract* (main body = torus, subtract = all groove bodies).
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
pytest -q          # geometry math, mesh, and B-rep cutter smoke tests
REFERENCE_PHOTO=/path/to/photo.png python capture.py
# writes media/preview.png, front_view.png, compare_photo.png (needs REFERENCE_PHOTO),
#        preview_mirror.png, screenshot.png, snippet.png
```

## Make your own shapes

1. **Sliders first.** Everything in the sidebar is live: preset, R, r, depth, width, sweep (photo preset), handedness and start rotation. Check the *Min wall* metric before printing.
2. **Copy the generated snippet.** The *Generated build123d snippet* at the bottom of the page is a standalone script for the current settings. Run it with `python snippet.py` to get a STEP (torus plus cutter bodies) you can open in SOLIDWORKS and *Combine ▸ Subtract*.
3. **Edit the geometry functions.**
   - **[`geometry.py`](geometry.py)** holds all the shape maths.
     - `TorusParams` sets the defaults: `major_radius`, `tube_radius`, `n_grooves` (per direction), `groove_depth`, `groove_width`, `pattern`, `sweep_deg`, `handedness` and `rotation_deg`.
     - `azimuth_offset(p, θ)` is the function to change for a new winding law: how far around the axis a groove has travelled at tube angle θ.
     - `families(p)` decides whether one or both rotational directions are cut.
     - `groove_path` and `all_paths` turn that into 3D centre-lines.
     - To add a preset, add a name to `PATTERNS` and `PATTERN_LABELS` and a branch in `sweeps()` / `azimuth_offset()`.
   - **[`torus_mesh.py`](torus_mesh.py)** turns any set of centre-lines into the grooved STL. `PREVIEW_GRID` and `EXPORT_GRID` set the resolution.
   - **[`rodin_torus.py`](rodin_torus.py)** builds the build123d B-rep (`Solid.make_torus`, `Solid.sweep` of a `Circle` along `Edge.make_spline`) for STEP.
4. **Learn build123d** at the docs: https://build123d.readthedocs.io (Tutorials, then *Builders* vs *Algebra*). Swap `Circle` for another profile, e.g. `Rectangle` for square channels, or `Solid.make_torus` for any other base solid.
