# build123d-param-cad — Rodin coil torus

Parametric CAD playground: a **torus (donut) with 12 helical semicircle grooves** wound Rodin-style, where every groove is an exact **golden spiral when viewed from above**. Built with [build123d](https://build123d.readthedocs.io/) + Streamlit, previewed with Plotly.

Bookmark source: [gregisenberg hardware/robotics tooling list](https://x.com/gregisenberg/status/2100229768385822812). Dimensions come from the owner's SOLIDWORKS sketch.

This is **not** a 3D-printer settings app. It designs the shape; slice the STL elsewhere.

## Units and defaults (inches, matching SOLIDWORKS)

| Parameter | Default |
|---|---|
| Major radius R (axis → tube centre) | **1.39** |
| Tube radius r | **0.695** (so the hole radius R − r = 0.695 and outer radius = 2.085) |
| Grooves | **12**, starting at poles 30° apart on the outer equator |
| Groove depth | **0.1875** (3/16"), slider 1/8"–1/4" |
| Groove width | **0.375** = 2 × depth → true semicircle; wider = shallower circular arc |

## How the grooves are built

Torus coordinates: `point(θ, φ) = ((R + ρ cos θ) cos φ, (R + ρ cos θ) sin φ, ρ sin θ)`, with θ around the tube (0 = outer equator, 90° = top) and φ around the main axis.

1. **Profile.** Each groove is a circle of radius `cutter_r = (w²/4 + d²)/(2d)` (= depth for a semicircle) whose centre-line runs at tube radius `ρ_axis = r − d + cutter_r`, so the groove bottom is exactly `d` below the surface.
2. **Path: one helical wrap per groove.** θ goes 0 → 360° once around the tube while φ advances around the main axis.
3. **Top half = golden spiral.** On θ 0 → 180° (outer equator → over the top → inner equator) the azimuth is
   `φ = φ₀ + (π/2)·log_φ(q_max / q)`, `q = R + ρ_axis cos θ`,
   so the projected radius shrinks by φ ≈ 1.618 for every 90° of azimuth. From 2.085" down to 0.695" (ratio 3) that's a **205.5°** golden-spiral sweep.
4. **Bottom half (closure option).**
   - **Rodin (default):** the bottom half sweeps 510° − 205.5° so each wrap advances 360° + 150° (the classic Rodin 5-of-12 pole skip). Groove *i* ends exactly where groove *i+5* starts, so the 12 grooves chain into **one continuous closed winding**.
   - **Mirror:** the bottom half is the mirror golden spiral (205.5°), giving 12 open grooves and the crossing rosette you see in the SOLIDWORKS top view.
5. **Handedness** and **start-pole rotation** are sliders.

Note: at the inner equator the 12 grooves are 0.364" apart centre-to-centre (2π·0.695/12). A 3/16"-deep semicircle is 0.375" wide, so neighbouring grooves just merge at the hole; the app warns about this. ≤ 0.18" depth keeps them separate.

## Outputs

- **3D preview + STL**: an analytic, watertight mesh. Each vertex on the tube-radial ray is pushed in to the exact cutter wall (`|c + λn − A|² = cutter_r²` against the nearest groove-axis samples). It's checked against Pappus' theorem for a ring groove (within about 1%) and is fast enough for live sliders.
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
python capture.py  # writes media/preview.png, preview_mirror.png, screenshot.png, snippet.png
```
