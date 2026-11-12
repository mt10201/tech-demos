# Concrete test specimen silicone mold masters (basalt geopolymer strength tests)

All STLs in **mm**, origin centred, bottom on z = 0. Built by `apps/build123d-param-cad/specimen_molds.py`
(app Mode "Concrete test specimen molds"); rebuild with `scripts/build_specimen_molds.py`.

**Bed assumption:** Creality Ender 2, conservative usable 150 × 150 mm, Z 200 mm (owner profile notes;
older notes mention a larger bed, not relied on here).

| Set | Specimens | Master (plate L × W × H) | Pour frame (L × W × H) | Silicone (fill line) |
|---|---|---|---|---|
| Cube | 4 × 50 × 50 × 50 mm, 2 × 2 | 144.7 × 144.7 × 54.0 mm | 136.0 × 136.0 × 61.6 mm | **≈ 509 ml** (60 mm above plate) |
| Bar | 3 × 110 × 27.5 × 27.5 mm (1:1:4), 1 × 3 | 144.7 × 137.2 × 31.5 mm | 136.0 × 128.5 × 39.1 mm | **≈ 344 ml** (37.5 mm above plate) |

Silicone = frame cavity to the fill line − positives, before mixing/cup losses (add ~10 %).
Walls: 10 mm silicone between cavities, to the frame (9.99 mm at the rounded corners), and 10 mm over the tops.
The standard 40 × 40 × 160 prism cannot lie flat on a 150 bed (a single bar needs a 194.7 × 74.7 mm plate, too big
even at 45°). The app can stand 2 × 2 of them on end (124.7 mm plate, 164 mm tall master, 171.6 mm frame,
≈ 1018 ml), but that casts vertically, so it is not the default.

## Seating (electroculture tower v3, unchanged)
0.25 mm per side frame clearance (not tightened), 3.5 × 1.6 mm glue-bead groove, 3.0 mm frame wall, 4.0 mm
plate, 1.5 mm lip channel, 1.6 × 3.0 mm vertical outer sealing lip, 0.4 mm chamfers, swept around a rounded
rectangle (frame inner corner R10, plate R17.35) with identical cross-sections. The only change: the plate
ends 1.0 mm outside the lip (the tower had 4.8 mm) so the master fits 150 mm. No vents.
Seat the frame in the groove and run the glue bead in the channel against the lip, the same as on the tower.

## Which specimen face comes from where
Pour silicone over the master, cure, lift the frame off and peel the block off, then turn it over: each
positive leaves an open-top cavity.
- **Cavity bottom → specimen bottom face** = the positive's **printed top surface** (top skin, flattest).
- **4 cavity walls → specimen side faces** = the positive's **printed side walls** (layer lines run parallel to
  the specimen's cast top face).
- **Specimen top** = your open, screeded face.
Standard practice (ASTM C109 / EN 196-1) loads cubes on two opposite **molded side faces** (rotate the cube
90°, never on the screeded top). Flexural prisms are also supported and loaded on molded side faces. So the
side walls matter most: print them at fine layers with a slow outer wall, and smooth lightly before pouring
silicone (wet-sand 400–600 grit flat on a block, keeping edges sharp). Edges are crisp (no fillets). No draft:
0.5° would make a 50 mm cube 0.44 mm out of square, and flexible silicone releases straight walls fine.
For a stiffer mold that keeps cubes square, use Shore 30A or harder and cast with the mold resting on a flat board.

## Print notes (Orca, you slice; cold presets ~60 °F)
**Masters (cube_master.stl, bar_master.stl):** plate down exactly as exported, **no supports**, **no brim** (the
plate fills 144.7 mm and a 5 mm brim would run off a 150 bed; 2.65 mm margin per side; a 4 mm solid plate
holds well on its own; clean the bed and use glue stick if needed). Layer 0.12–0.16 mm; 4–5 walls;
outer wall 15–20 mm/s, outer wall acceleration ~300 mm/s²; top shells ≥ 7 (≥ 1.0 mm), monotonic top fill,
**ironing on, top surfaces only** (these become the cavity bottoms); seam aligned/rear so it lands on a
cube corner, not mid-face; 15–20 % infill is fine.
Nozzle 225 °C (230 °C first layer), bed 60 °C, fan 20–35 % (off first 3 layers), no draft shield, wipe on,
avoid crossing walls on, Z hop 0.
**Frames (cube_pour_frame.stl, bar_pour_frame.stl):** chamfered edge down, as exported, no supports, 5 mm brim
OK (146 mm). 4 walls; the same temperatures. Check that it drops into the groove before you glue it.

Files: cube_master.stl, cube_pour_frame.stl, bar_master.stl, bar_pour_frame.stl, verification.json,
renders (*_master.png, *_pour_frame.png, *_assembly.png, *_lip_channel_section.png, *_board.png).
