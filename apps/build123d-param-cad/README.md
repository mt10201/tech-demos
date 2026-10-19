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
| Groove depth | **0.125** (1/8"); slider 1/8"–1/4" |
| Groove width | **0.25** = 2 × depth → true semicircle; wider = shallower circular arc |

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

**Wall thickness:** neighbours in the same direction come closest at the hole (θ = 180°). Their perpendicular spacing there is `(2π q/N)·sin α`, with `q = R − ρ` and `tan α = ρ/(q·k)`, `k = sweep/180°`. Subtracting the groove width gives the wall. The app computes this numerically for every pattern (closest approach of the centre-lines) and warns when the wall drops below 0.04" or goes negative (grooves merge):

| Depth (semicircle) | Width | Min wall at the hole |
|---|---|---|
| 1/8" (default) | 0.25" | **+0.030"** |
| 5/32" | 0.3125" | −0.033" (merge) |
| 3/16" | 0.375" | −0.095" (merge) |
| 1/4" | 0.5" | −0.220" (merge) |

**Golden-spiral presets:** these are the earlier variants, described below.

1. **Profile.** Each groove is a circle of radius `cutter_r = (w²/4 + d²)/(2d)` (= depth for a semicircle) whose centre-line runs at tube radius `ρ_axis = r − d + cutter_r`, so the groove bottom is exactly `d` below the surface.
2. **Path: one helical wrap per groove.** θ goes 0 → 360° once around the tube while φ advances around the main axis.
3. **Top half = golden spiral.** On θ 0 → 180° (outer equator → over the top → inner equator) the azimuth is
   `φ = φ₀ + (π/2)·log_φ(q_max / q)`, `q = R + ρ_axis cos θ`,
   so the projected radius shrinks by φ ≈ 1.618 for every 90° of azimuth. From 2.085" down to 0.695" (ratio 3) that's a **205.5°** golden-spiral sweep.
4. **Bottom half (closure option).**
   - **Rodin (default):** the bottom half sweeps 510° − 205.5° so each wrap advances 360° + 150° (the classic Rodin 5-of-12 pole skip). Groove *i* ends exactly where groove *i+5* starts, so the 12 grooves chain into **one continuous closed winding**.
   - **Mirror:** the bottom half is the mirror golden spiral (205.5°), giving 12 open grooves and the crossing rosette you see in the SOLIDWORKS top view.
5. **Handedness** and **start-pole rotation** are sliders.

For these presets, the numeric minimum-wall check also flags merging at 3/16" depth.

## Outputs

- **3D preview, front view and STL:** an analytic, watertight mesh. Each vertex on the tube-radial ray is pushed in to the exact cutter wall (`|c + λn − A|² = cutter_r²` against the nearest groove-axis samples). It's checked against Pappus' theorem for a ring groove (within about 1%).
  - The live preview uses a 160×640 grid (205k triangles).
  - **Prepare high-res STL** uses a 320×1280 grid: 819,200 triangles, about 41 MB binary STL, watertight and winding-consistent (verified with trimesh).
- **Front view:** an orthographic view looking along the axis, like the photo. Tiles are rainbow-coloured by azimuth and grooves are copper.
- **STEP**: exact build123d B-rep **torus + 12 swept groove cutter bodies + 12 centre-line splines**. OpenCascade's own `torus − cutters` boolean is unreliable for these long helical pipes (it returns invalid solids), so do the subtraction in SOLIDWORKS: open the STEP → *Insert ▸ Features ▸ Combine ▸ Subtract* (main body = torus, subtract = the 12 grooves).
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
