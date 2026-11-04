"""Photo -> Idol (free hosted Hugging Face Space) -> raw splat centres -> printable mold master STL (mm).

    python scripts/photo_to_idol_master.py photo.jpg out.stl --height 120
    python scripts/photo_to_idol_master.py photo.jpg out.stl --height 90 --voxel 0.3 --keep-splat photo.ply
    python scripts/photo_to_idol_master.py --splat photo.ply out.stl --height 120     # reuse a splat, offline

Calls speridlabs/idol in 'Real photo' mode via gradio_client (no torch / GPU here), keeps the opaque Gaussian
centres, voxelises them, then runs scan_repair.scan_to_master (same as scripts/photo_to_master.py): watertight,
single shell, genus 0 (Euler 2), checked against the 225x225x245 mm bed.
Licence: castings made via the hosted Space are OK (Idol Apache-2.0); the photo must be yours or cleared.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import idol_photo as ip  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo", nargs="?", help="input photo (jpg/png/webp)")
    ap.add_argument("out", help="output STL (mm)")
    ap.add_argument("--splat", help="use this Idol .ply instead of calling the Space")
    ap.add_argument("--keep-splat", help="save the Idol splat .ply here")
    ap.add_argument("--height", type=float, default=120.0, help="master height in mm (default 120)")
    ap.add_argument("--voxel", type=float, default=0.4, help="voxel size mm (smaller = finer, slower; default 0.4)")
    ap.add_argument("--close", type=float, default=0.8, help="closing radius mm (default 0.8)")
    ap.add_argument("--base-cut", type=float, default=2.0, help="mm cut flat off the bottom (default 2)")
    ap.add_argument("--gaussians", default=ip.DEFAULT_GAUSSIANS, choices=ip.GAUSSIANS)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(argv)
    if not a.photo and not a.splat:
        ap.error("give a photo or --splat")
    try:
        out, rep, info, _ = ip.photo_to_master(a.photo, a.splat, a.height, a.voxel, a.close, a.base_cut,
                                               a.gaussians, a.seed, a.keep_splat, log=print)
    except ip.IdolSpaceError as exc:
        print(f"IDOL SPACE ERROR: {exc}", file=sys.stderr)
        return 2
    if not rep.ok():
        print("FAILED: result is not a closed genus-0 single shell", file=sys.stderr)
        return 1
    out.export(a.out)
    print(f"wrote {a.out}: {rep.faces} triangles, {rep.extents_mm} mm, {rep.volume_cm3} cm3, watertight "
          f"{rep.watertight}, Euler {rep.euler}, fits bed 225x225x245: {rep.fits_bed}, {info}")
    if not rep.fits_bed:
        print("WARNING: does not fit the 225x225x245 mm bed; lower --height", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
