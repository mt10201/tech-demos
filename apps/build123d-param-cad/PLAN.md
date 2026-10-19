# PLAN: build123d-param-cad

## Goal
A Streamlit playground that lets you parametrically design a **Rodin coil card** — a flat disk with **12 golden-ratio spanning grooves** inspired by Marko Rodin’s 12-pole toroidal coil layout — using [build123d](https://build123d.readthedocs.io/), preview the solid in 3D, and download STL/STEP plus the generated Python snippet.

## MVP (single user)
1. Hero preset: **Rodin coil card** with live sliders.
2. 3D mesh preview (Plotly `Mesh3d` from tessellated build123d solid).
3. STL + STEP download buttons.
4. Side panel showing the generated build123d Python for current params.
5. Unit tests for φ / groove span math only.
6. Screenshot(s) in `media/` via Playwright `capture.py`.

## Explicit outs
- No 3D-printer settings / slicer UI.
- No LLM “describe a part” prompts.
- No real toroidal wire winding simulation or EM field calc.
- Optional second preset (gear / box) deferred unless coil card is solid early.

## Geometry assumptions (owner can tweak later)

Rodin’s classic coil places **12 poles at 30°** around a torus and connects wraps at **150°** (5:12 winding). The musical 5/12 ratio is *not* φ; the owner asked for **golden-ratio spanning grooves**, so this card keeps the Rodin **12-around / 30°** layout and uses **φ ≈ 1.6180339887** for radial groove spans.

**Part:** circular plate (disk), diameter `D`, thickness `T`.

**12 grooves:** equally spaced at angles `θ_i = i · 30° + θ₀` (`i = 0…11`), optional global rotation `θ₀` (coil offset).

**Radial span (golden ratio):** for groove `i`, define a base span fraction of the available radial band `(r_outer − r_inner)`:

```
φ = (1 + √5) / 2
span_i = L0 · φ^(i mod 4) / φ³     # cycles every 4 grooves; normalized so max = L0
```

More precisely (what the code implements):

```
powers = [φ^(i % 4) for i in 0..11]
span_i = L0 * powers[i] / max(powers)   # L0 = φ_scale · (r_outer − r_inner)
r_start_i = r_inner + (1 − coil_factor) · drift_i
r_end_i   = r_start_i + span_i
```

- `r_inner = D/2 · inner_ratio` (default 0.18)
- `r_outer = D/2 · outer_ratio` (default 0.92)
- `L0 = φ_scale · (r_outer − r_inner)` with `φ_scale ∈ [0.3, 1.0]`
- Optional **coil drift**: each groove’s start radius is shifted by `coil_factor · (i/12) · (r_outer − r_inner − span_i)` so successive grooves walk outward like a vortex / doubling-circuit spiral (Rodin-inspired “coil” look).
- Groove cross-section: rectangular slot of width `groove_width`, depth `groove_depth` (≤ `T`), cut from the top face; optional edge fillet on the disk rim.

Boolean: start with extruded disk, subtract 12 radial slot solids (thin boxes or rounded slots oriented along each `θ_i`).

## Vertical slices
1. Pure math module: φ spans, angles, radii → testable.
2. build123d solid builder + STL/STEP export.
3. Streamlit UI: sliders, Plotly preview, code snippet, downloads.
4. Tests + capture.py + README + tracking update + PR.

## Stack
| Piece | Why |
|---|---|
| build123d | BREP CAD in Python; STEP/STL export native |
| Streamlit | Fast parametric UI |
| Plotly Mesh3d | Installs cleanly; interactive 3D without Qt |
| Playwright | Screenshot capture (same pattern as other demos) |
| pytest | Critical φ/groove math only |

## Folder layout
```
apps/build123d-param-cad/
  PLAN.md
  README.md
  requirements.txt
  app.py              # Streamlit UI
  geometry.py         # φ math + groove params
  rodin_card.py       # build123d solid + exports
  code_snippet.py     # generate Python source from params
  capture.py          # Playwright screenshots
  media/              # screenshot.png, …
  tests/test_geometry.py
```

## Deferred
- Second preset (gear / project box).
- Exact geodesic-dome shelter mating features (bolt holes, dome hub sockets) until drawings arrive.
- True 150° wrap path as 3D wire path (card is a flat template, not the wound coil).

## Tasks
- [x] geometry.py + tests
- [x] rodin_card.py (build123d)
- [x] Streamlit app + snippet + downloads
- [ ] capture.py + media
- [x] README, tracking, PR
