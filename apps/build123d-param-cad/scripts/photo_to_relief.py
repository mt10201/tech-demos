#!/usr/bin/env python3
"""Photo → pet-portrait bas-relief in a memorial-stone frame (watertight STL, mm).

    python scripts/photo_to_relief.py dog.jpg dog_relief.stl --text "Dog"
    python scripts/photo_to_relief.py dog.jpg out.stl --relief 14 --detail 0.4 --crop 0.1,0.2,0.95,0.8 --preview out.png

Models (CPU, onnxruntime, downloaded once): BiRefNet-lite (MIT) + Depth Anything V2 Small (Apache-2.0).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import relief as R  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("out", help="output .stl")
    ap.add_argument("--relief", type=float, default=12.0, help="max relief above the niche floor, mm (12)")
    ap.add_argument("--detail", type=float, default=0.6, help="photo fine-detail amplitude, mm (0.6)")
    ap.add_argument("--compress", type=float, default=0.5, help="depth compression 0..4 (0.5)")
    ap.add_argument("--sharpen", type=float, default=1.5, help="mid-scale form boost (1.5)")
    ap.add_argument("--width", type=float, default=150.0)
    ap.add_argument("--height", type=float, default=140.0)
    ap.add_argument("--thickness", type=float, default=25.0)
    ap.add_argument("--niche-depth", type=float, default=6.0)
    ap.add_argument("--text", default="", help="engraved under the niche, e.g. 'Dog 2012-2026'")
    ap.add_argument("--no-texture", action="store_true", help="smooth border instead of hammered")
    ap.add_argument("--crop", help="x0,y0,x1,y1 as 0..1 fractions of the photo (default: auto head + chest)")
    ap.add_argument("--res", type=float, default=0.25, help="grid, mm (0.25)")
    ap.add_argument("--preview", help="also write a shaded front-view PNG")
    a = ap.parse_args(argv)
    p = R.ReliefParams(width=a.width, height=a.height, thickness=a.thickness, niche_depth=a.niche_depth,
                       relief_mm=a.relief, detail_mm=a.detail, compress=a.compress, sharpen=a.sharpen,
                       text=a.text, texture=not a.no_texture, res_mm=a.res,
                       crop=tuple(float(v) for v in a.crop.split(",")) if a.crop else None)
    mesh, rep, ex = R.photo_to_relief(a.photo, p)
    mesh.export(a.out)
    print(f"wrote {a.out}: {rep.faces} faces, {rep.extents_mm} mm, {rep.volume_cm3} cm³, watertight={rep.watertight}, "
          f"single shell={rep.pieces == 1}, Euler={rep.euler}, fits bed 225x225x245={rep.fits_bed}; {rep.timings}")
    if a.preview:
        R.shade(ex["z"], p.res_mm, ex["inside"]).save(a.preview)
        print(f"wrote {a.preview}")
    if not rep.fits_bed:
        print("warning: does not fit the 225x225x245 bed", file=sys.stderr)
    return 0 if rep.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
