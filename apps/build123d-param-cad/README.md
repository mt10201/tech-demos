# build123d-param-cad — Rodin coil card

Parametric CAD playground: a **Rodin coil card** (flat disk with **12 golden-ratio spanning grooves**) built with [build123d](https://build123d.readthedocs.io/) and previewed in Streamlit.

Bookmark source: [gregisenberg hardware/robotics tooling list](https://x.com/gregisenberg/status/2100229768385822812).

This is **not** a 3D-printer settings / slicer app. It designs the shape; export STL/STEP and slice elsewhere.

## Geometry (documented assumptions)

Marko Rodin’s classic coil places **12 poles at 30°** and winds wraps at **150°** (5:12 ratio — a musical fourth, not φ). This card keeps the **12-around / 30°** layout and applies the **golden ratio** to radial groove spans, as requested for the geodesic-dome shelter card.

```
φ = (1 + √5) / 2 ≈ 1.6180339887

L0      = φ_scale · (r_outer − r_inner)
span_i  = L0 · φ^(i mod 4) / max_k φ^(k mod 4)   # longest in cycle = L0
r_start = r_inner + coil_factor · (i/12) · slack_i
r_end   = r_start + span_i
θ_i     = rotation + i · 30°
```

- `r_inner = (D/2) · inner_ratio` (default 0.18)
- `r_outer = (D/2) · outer_ratio` (default 0.92)
- Grooves are rectangular slots cut from the top face (width × depth).
- `coil_factor` adds a vortex-style outward drift so successive grooves walk like a coiled / doubling-circuit pattern.

See `PLAN.md` for outs and deferred mating features (bolt holes, dome hubs).

## Run

```bash
cd apps/build123d-param-cad
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

## Tests

```bash
pytest -q
```

## Screenshots

```bash
# with the app already running on :8501, or capture.py will start it
python capture.py
```

Media lands in `media/screenshot.png` (and siblings).

## Exports

UI buttons download `rodin_coil_card.stl` and `rodin_coil_card.step`. The page also shows the generated build123d Python for the current slider values.
