# Tetrix brazing jig set — level-1 Sierpinski tetrahedron, 130.9 mm (royal cubit / 4)

All STLs are in **millimetres**, single watertight bodies sitting on z = 0, already in print orientation.
Bed assumed 235 × 235 mm usable (parts kept ≤ 225 mm). Not sliced — slice in Orca yourself.

## The piece
| | |
|---|---|
| Outer edge | **130.9 mm** (523.6 / 4), height 106.9 mm |
| Small tetrahedra | 4 × 65.45 mm edge |
| Rods | **24 rods cut to 64.45 mm** (twisted pair of 16 AWG, ≈ Ø2.8 mm) |
| Joints | **10** (4 outer corners + 6 edge midpoints) |
| Wire | 24 × 64.45 = 1.55 m of twisted rod → **≈ 3.19 m of single 16 AWG strand** (2 strands/rod, +3 % for twist take-up) |

**Why 64.45 mm and not 65.45 mm (joint allowance 1.0 mm):** the corner-to-corner distance is 65.45 mm, but
round rods meeting at 60° touch each other about 2.4 mm before their centre lines meet. Cutting 0.5 mm off
each end lets the three rod ends at a corner butt and overlap slightly instead of propping each other apart,
so the tetrahedron closes to size and the ends are in contact for the braze to wick into. If your corners
crowd (twisted ends flare), try 1.5–2.0 mm allowance in the app; if they gap, 0.5 mm.
Cut and test-fit **one** tetrahedron before cutting all 24.

**18-rod option:** the 6 outer edges of the big tetrix can each be one continuous **129.9 mm** rod
(130.9 − 1.0) instead of two short rods — 12 short + 6 long = 18 rods, slightly more wire (≈ 3.20 m strand)
and the 3 outer-edge midpoints become rod-on-rod crossings to braze instead of butt joints. Row B of the gauge
cuts that length. The jigs below are drawn for the default 24-rod build.

## Files
| File | Size (mm) | Purpose |
|---|---|---|
| `rod_length_gauge.stl` | 135.9 × 32 × 8 | Row A: push rod against the end stop, flush-cut at the step face → 64.45. Row B: same for 129.9 (18-rod option). Row C: through-groove for rolling/pressing rods straight. |
| `single_tetra_jig.stl` | 53.6 × 51.6 × 53.3 | Holds the 6 rods of one 65.45 mm tetrahedron: 3 base cradles + 3 sloped cradles under the upper rods. |
| `assembly_plate_130.9mm.stl` | 137.6 × 122.1 × 70.0 | 9 cradles under the base rods of the 3 lower tetrahedra + 3 posts under the base rods of the top one. |
| `rods_reference.stl` | 132.8 × 115.6 × 108.7 | Finished tetrix as cut rods (unioned cylinders) — visualisation only, don't print. |
| `*.png`, `verification.json` | | Renders with rods in place; checks. |

Every channel is Ø3.1 (rod 2.8 + 0.3 clearance) and **open straight up**, so rods drop in without friction
and the tied piece lifts straight out. Rods are held only near their middles; the nearest jig surface is
**13.1 mm** from any joint in the single jig and **14.2 mm** in the assembly plate (requirement ≥ 6 mm), and the
plate has relief holes under the base joints, which sit 14 mm above the plate, for wrapping binding wire.

## Printing (PLA, your cold Orca presets)
- Nozzle 225 °C (230 °C first layer), bed 60 °C, fan 20–35 %, **no draft shield**, no supports, as exported (flat side down).
- 0.2 mm layers, 3–4 walls, 15–20 % infill. Gauge: 4 walls, 100 % is fine (small), so the end stop is rigid.
- Assembly plate: the three 8 × 8 × 70 mm posts are slender — 4 walls, outer wall ≤ 40 mm/s; no brim needed (they grow off the plate).

## Build steps
1. **Twist:** twist pairs of 16 AWG in ~410 mm strands (drill + hook); each twisted ~400 mm length gives 6 rods → 4 lengths (8 strands, ≈ 3.3 m). Roll each straight in gauge row C.
2. **Cut 24 rods:** row A, rod against the stop, flush-cut against the step face (flat side of the cutters on the face). Deburr; file ends square.
3. **One tetrahedron:** drop 3 rods in the base cradles, ends meeting at the 3 corners; lay 3 rods in the sloped cradles — they slide down until their feet meet the base corners and their tops meet at the apex. Tie each corner with a few turns of thin binding wire (steel/stainless), twist tight. Lift the tied tetrahedron straight up. Repeat ×4.
4. **Braze each tetrahedron** away from the jig (flux, Sil-Fos ≈ 700 °C), let cool, check edges with calipers (65.45 mm corner-to-corner).
5. **Assembly:** set 3 tetrahedra on the assembly plate cradles (their base corners meet in pairs at the 3 base midpoints). Set the 4th on top: its corners sit on the 3 lower apexes, its base rods drop into the 3 posts. Tie the 6 midpoint joints with binding wire, lift straight out, braze those 6 joints.
6. Pickle/clean, remove binding wire.

## Stiffness notes
Copper can't be hardened by heat treatment — heating anneals (softens) it, and brazing at ~700 °C will anneal
every rod near its joints regardless of the wire temper you buy. Stiffness here comes from the triangulation
(every face is a triangle, so the frame can't rack) and from the twist (twisting work-hardens the wire, which
survives away from the joints). If it's still too floppy: twist tighter, use 14 AWG, or buy hard-drawn copper /
brass / phosphor-bronze rod for the 6 long outer edges (18-rod option).

## Verification (from re-loaded STLs — see verification.json)
All four STLs: watertight, consistent winding, 1 body, min z = 0, fit 225 mm. Rods-in-place interference with
each jig: 0 mm³. Lifting the tied piece straight up 120 mm clears the jig: yes (both jigs).
