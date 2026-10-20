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
- The scan's back (the ragged contact with the hillside, not statue surface) was replaced by a flat back
  plane; narrow notches in front of it were filled.
- Rebuilt as a solid on a 0.3 mm voxel grid with a 0.75 mm morphological closing: gaps and holes narrower
  than ~1.5 mm, the nostrils and the texture-seam cracks of the scan were closed; internal cavities and
  tunnels were filled, so the part is watertight and genus 0 (Euler characteristic 2) for use as a
  silicone mold master.
- Decimated to ~427k triangles and scaled to 152.4 mm (6 in) tall, units mm.

Processing script: `scripts/build_moai_head_scan.py`.

Suggested credit line on products / listings:

> Moai head after "Quarry Moai - Rapa Nui/Easter Island" by Ryan Shackleton (sketchfab.com), CC BY 4.0, modified.
