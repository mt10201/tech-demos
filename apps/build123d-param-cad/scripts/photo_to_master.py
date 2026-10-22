"""Photo-to-3D (or scan) mesh -> printable silicone-mold master STL, in mm.

    python scripts/photo_to_master.py model.glb out.stl --height 120
    python scripts/photo_to_master.py model.obj out.stl --height 90 --up +z --base-cut 3 --voxel 0.3

Takes the mesh from ANY image-to-3D tool (TRELLIS.2, Hunyuan3D, UniForge3D, Meshy, Tripo, ...) or a
photogrammetry scan and runs scan_repair.scan_to_master: orient + scale to --height mm, patch holes,
volumetric closing, flat base, single piece, no cavities, tunnels plugged (genus 0), marching cubes,
manifold3d simplify; then checks watertight single shell, Euler 2 and the Ender 2 bed (150x150x200).
No GPU / torch needed. Check the generator's licence before selling castings (see docs/photo_to_3d.md).

--damage-demo first punches holes, flips faces and adds debris + an internal bubble (to show the repair
on a clean source mesh).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan_repair as sr  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mesh", help="input mesh: glb/gltf/obj/ply/stl/off")
    ap.add_argument("out", help="output STL (mm)")
    ap.add_argument("--height", type=float, default=120.0, help="final master height in mm (default 120)")
    ap.add_argument("--up", default=None, choices=sorted(sr.AXES), help="input up axis (default: +y for glTF, else +z)")
    ap.add_argument("--base-cut", type=float, default=2.0, help="mm cut flat off the bottom (default 2)")
    ap.add_argument("--voxel", type=float, default=0.4, help="voxel size mm (smaller = finer, slower; default 0.4)")
    ap.add_argument("--close", type=float, default=0.8, help="closing radius mm: gaps < ~2x this close (default 0.8)")
    ap.add_argument("--simplify", type=float, default=0.05, help="manifold3d simplify tolerance mm (0 = off)")
    ap.add_argument("--damage-demo", action="store_true", help="simulate AI-mesh defects first (demo)")
    ap.add_argument("--preview", help="also write a decimated PLY preview here")
    a = ap.parse_args(argv)

    m = sr.load_mesh(a.mesh)
    if a.damage_demo:
        m = sr.damage_mesh(m, seed=0)
        print(f"damage demo: watertight={m.is_watertight}, {len(m.faces)} faces")
    out, rep = sr.scan_to_master(m, height_mm=a.height, up=a.up or sr.default_up(a.mesh), base_cut_mm=a.base_cut,
                                 voxel_mm=a.voxel, close_mm=a.close, simplify_mm=a.simplify, log=print)
    if not rep.ok():
        print("FAILED: result is not a closed genus-0 single shell", file=sys.stderr)
        return 1
    out.export(a.out)
    print(f"wrote {a.out}: {rep.faces} triangles, {rep.extents_mm} mm, {rep.volume_cm3} cm3, "
          f"Euler {rep.euler}, fits Ender 2: {rep.fits_bed}")
    if not rep.fits_bed:
        print("WARNING: does not fit the Ender 2 bed (150x150x200); lower --height", file=sys.stderr)
    if a.preview:
        sr._decimate(out, 0.15).export(a.preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
