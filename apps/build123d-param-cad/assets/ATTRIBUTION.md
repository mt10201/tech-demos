# Attribution: moai_head_scan_152mm.stl, moai_head_scan_preview.ply

These files are an adaptation of:

**"Quarry Moai - Rapa Nui/Easter Island"** by **Ryan Shackleton**
https://sketchfab.com/3d-models/quarry-moai-rapa-nuieaster-island-dd6027d79fe14549ab7b2eae0d94de5d
licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)**:
https://creativecommons.org/licenses/by/4.0/ (full legal code: https://creativecommons.org/licenses/by/4.0/legalcode)

The original scan is not included in this repository. Commercial use (e.g. selling castings) is
permitted by CC BY 4.0, provided this attribution is kept and the changes are indicated.

## Changes made (this is a modified version)

- Re-oriented: head axis made vertical, face toward −Y.
- Cropped to the head at the underside of the chin; the soil/hillside the quarry statue is buried in was
  removed; a flat base was added at the chin.
- The scan's back (the ragged contact with the hillside, not statue surface) was cut to a plane, narrow
  notches in front of it filled, and a sculpted (not scanned) back of head and neck modelled on real moai
  was added behind it: broad and nearly vertical just behind the ears, rounded rear edges and top-back
  corner, a ~1 mm hollow in the centre, a shallow concave nape, with a low-amplitude (~0.7 mm)
  weathered-stone noise texture, blended into the scan's sides with a 4 mm smooth union. The face is the
  unchanged scan.
- Rebuilt as a solid on a 0.3 mm voxel grid with a 0.75 mm morphological closing: gaps and holes narrower
  than ~1.5 mm, the nostrils and the texture-seam cracks of the scan were closed; internal cavities and
  tunnels were filled, so the part is watertight and genus 0 (Euler characteristic 2) for use as a
  silicone mold master.
- Decimated to ~471k triangles and scaled to 152.4 mm (6 in) tall, units mm.

Processing script: `scripts/build_moai_head_scan.py`.

Suggested credit line on products / listings:

> Moai head after "Quarry Moai - Rapa Nui/Easter Island" by Ryan Shackleton (sketchfab.com), CC BY 4.0, modified.

---

# Attribution: hayes_bust_npg_cc0.ply (Photo → master sample)

**"Rutherford B. Hayes"**, plaster bust by **Olin Levi Warner**, 1876 (27.3 × 24.8 × 12.7 cm),
National Portrait Gallery, Smithsonian Institution, object NPG.76.27
(record `edanmdm:npg_NPG.76.27`, https://npg.si.edu/object/npg_NPG.76.27).
3D model from Smithsonian 3D (Smithsonian Open Access), usage: **CC0** (public domain dedication, as listed on the Smithsonian 3D / Open Access record,
checked 2026-10-22). No attribution is
legally required; the credit above is a courtesy. Commercial use and derivatives (e.g. selling castings)
are permitted. The Smithsonian name and logo are not licensed and must not be used to imply endorsement.

Changes: the 150k-face GLB (`rutherford-b-150k-4096.glb`) was loaded without its texture, rotated to +Z up
(mm, original size) and decimated with manifold3d to ~37k triangles (watertight, Euler 2). In the app's
Photo → master mode it is damaged on purpose ("simulate AI / scan defects") and rebuilt by `scan_repair.py`.

---

# Attribution & License Audit: black_madonna_101.6mm.stl, black_madonna_preview.ply, black_madonna_calib.npz

**Subject:** **"Black Madonna de Sous-Terre"** (*Notre-Dame de Sous-Terre* / *Virgo Paritura*, 11th/12th-century
Romanesque *Sedes Sapientiae* venerated in the crypt of Chartres Cathedral, France), modelled from multi-angle
orthographic and 3/4 studio photographs of the Sacred Source `#BMT` (`SS-BMT`) dark-stone-finish statue
(8.5" H × 3.0" W × 3.5" D).

## 3D Scan License Audit (Commercial Casting & Derivatives Check)

Because the owner sells physical castings from silicone molds, **only `CC0`, `CC-BY`, `CC-BY-SA`, or Public Domain**
3D assets are permitted (`NC` and `ND` licenses are strictly excluded):

- **Sacred Source `#BMT` Chartres *Madonna de Sous-Terre*:** No 3D scan exists online (and the medieval wooden
  original at Chartres was destroyed in 1793 during the French Revolution).
- **Musée du Cinquantenaire (Brussels) *Sedes Sapientiae* by Geoffrey Marchal**
  (`https://www.myminifactory.com/object/3d-print-sedes-sapientiae-113611` /
  Sketchfab `85b36edb44c04511ad7ebe0848322624`): **CC BY-NC 4.0 / NoAI (Non-Commercial)** — **EXCLUDED**.
- **Scan The World *Sedes Sapientiae*** (`https://www.myminifactory.com/object/3d-print-sedes-sapientiae-45452`):
  **CC BY-NC-SA 4.0 (Non-Commercial)** — **EXCLUDED**.
- ***Vierge noire de Walcourt*** (Sketchfab `e0cc9ecd4d3c4793935af0b5b73e7243`) and ***Black Madonna of Halle***
  (Sketchfab `5f5f38733d9d4608bba11ab2b6e7648c`): **All Rights Reserved / Not Downloadable** — **EXCLUDED**.
- **The Hunt Museum *Figure Sculpture (Sedes Sapentia)* (CG 003)** (`819f51e0724e41119b1c126ce08f6396`, **CC0 1.0**)
  and ***Romanesque Enthroned Madonna* (HCM 001)** (`0b7518ec12904e44929a5e62960becd4`, **CC0 1.0**): Public Domain,
  but depict different, heavily weathered medieval carvings (Child on left knee or missing, open chair legs) and
  require a Sketchfab login to download.

## How This Model Was Built (`madonna.py`, `scripts/build_black_madonna.py`)

This mesh was constructed clean-room in Python (`madonna.py`, **CC0 1.0 Public Domain dedication** — free for
commercial casting and derivatives without restriction) calibrated directly against multi-angle studio reference
views of the Chartres *Madonna de Sous-Terre* statue:

1. **Multi-angle silhouette & landmark calibration (`assets/black_madonna_calib.npz`):**
   - Aligned orthographic studio views (full front, left profile, right profile, back, 3/4 views, and upper-body
     close-up) establish exact proportional landmarks across `z ∈ [0, 1]` (>93% front & side silhouette IoU):
     - Rounded rectangular base plinth (`z = 0..0.146`) with sloped front footrest step (`z = 0.135..0.220`).
     - Four-post Romanesque throne with trapezoidal plan: wider lower front posts (`x = ±0.177`, ball finials at
       `z = 0.476`), narrower taller rear posts (`x = ±0.142`, ball finials at `z = 0.704` so all four finials are
       visible from the front), concave side panels, and a solid backrest with vertical post-seam grooves and a
       small raised rectangular maker's plaque near the bottom (`z = 0.08..0.14`).
     - Seated Madonna in frontal majesty (*Sedes Sapientiae*): six-peak trefoil/fleur-de-lis crown (`z = 0.872..1.000`)
       with jewelled band, serene oval face, veil with vertical back pleats (`z = 0.665..0.880`), horizontally
       pleated U-draped mantle across chest and shoulders, hands with sculpted fingers encircling the Child's waist,
       knees, vertical/catenary V-fold skirt drapery, and shoe tips at the hem.
     - Christ Child seated frontally on her lap (`z = 0.360..0.692`): round halo-less head with short curly hair,
       V-collared tunic with vertical pleats, right hand raised in blessing (connected via a solid relief web so no
       fragile detached fingers or tunnels exist), left hand holding an orb against the chest, and two bare feet
       resting on the mother's lap folds.
2. **Genus-0 mold-master rebuild:**
   - Evaluated on a 240-step grid (`~0.42 mm` voxel pitch at `101.6 mm` height), smoothed (`σ = 0.55`), clamped to
     `z ≥ 0` for a flat base, 3D cavity-filled and 2D slice tunnel-plugged across all three axes, extracted with
     marching cubes, and decimated with `manifold3d` (`simplify_mm = 0.025`) to **68,246 triangles** (`41.93 × 45.92 × 101.60 mm`,
     watertight, single body, **Euler characteristic 2 / genus 0**).
