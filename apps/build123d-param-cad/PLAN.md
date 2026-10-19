# PLAN: build123d-param-cad (revised: Rodin torus)

## Goal
Model the owner's SOLIDWORKS part: a **torus** (R = 1.39", r = 0.695") with **12 helical Rodin-style semicircle grooves** (depth 1/8–1/4"). Each groove reads as a **golden spiral from the top view**. Includes a live Streamlit preview, STL/STEP download, and a generated build123d snippet.

This replaces the earlier flat "Rodin coil card" assumption, which the owner corrected.

## MVP
1. `geometry.py`: torus/groove path math (golden-spiral top half, Rodin or mirror bottom half), inches.
2. `torus_mesh.py`: analytic watertight grooved mesh → Plotly preview + STL.
3. `rodin_torus.py`: build123d torus + 12 swept circular cutters + centre-lines → STEP.
4. `app.py`: sliders (R, r, depth, width, closure, handedness, rotation), 3D preview, top-view spiral plot, groove table, metrics, downloads, snippet.
5. Tests: path math (golden-spiral property, 150° Rodin chaining, semicircle profile), mesh depth/volume, B-rep cutter validity.
6. `capture.py` screenshots (no video; no live graph).

## Explicit outs
- No slicer / printer settings.
- No EM simulation of the wound coil.
- No in-OCC boolean subtraction for STEP. It is unreliable here, so the user does Combine ▸ Subtract in SOLIDWORKS.

## Revision 2: Photo replica (default)
- Measured from the owner's photo: 12 + 12 crisscross grooves, constant pitch, about 150° rim → hole.
- Kept the owner's R and r. Default depth 1/8" so walls stay positive (+0.030" at the hole).
- Preview at 160×640, STL export at 320×1280. Front view with rainbow tiles and copper grooves, plus a photo comparison in capture.py.

## Decisions
- Top half is exactly golden (radius ÷ φ per 90°). The bottom half either closes the Rodin 150° skip (default) or mirrors the golden spiral.
- Grooves start on the outer equator, where the spacing is roomy (1.09"). They cross the inner equator meridionally, 0.364" apart.

## Tasks
- [x] geometry + tests
- [x] analytic mesh + STL
- [x] build123d cutters + STEP
- [x] Streamlit UI
- [x] capture + media
- [x] README / PR update
