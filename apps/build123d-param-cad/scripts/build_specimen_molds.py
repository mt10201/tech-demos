"""Build the concrete specimen mold sets, verify, render, zip -> /workspace/exports/specimen_molds/."""
import json, math, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, trimesh, manifold3d as mf
import specimen_molds as S
from moai_render import render, board

OUT = Path("/workspace/exports/specimen_molds"); OUT.mkdir(parents=True, exist_ok=True)
ver = {"bed_assumption": f"Ender 2 conservative usable bed {S.BED_XY:g} x {S.BED_XY:g} mm, Z {S.BED_Z:g} mm",
       "seating": dict(clearance_per_side=S.CLR, groove_w=S.U_GR_OUT - S.U_GR_IN, groove_depth=S.GR_DEPTH,
                       frame_wall=S.FRAME_WALL, plate_t=S.PLATE_T, lip_channel=S.LIP_CHANNEL,
                       lip_w=S.LIP_WIDTH, lip_h=S.LIP_HEIGHT, chamfer=S.LIP_CH, plate_margin_beyond_lip=S.PLATE_MARGIN)}
GREY, BLUE = (0.62, 0.60, 0.57), (0.35, 0.55, 0.78)

def seated(master, frame):
    f = frame.copy(); f.vertices = f.vertices + [0, 0, S.PLATE_T - S.GR_DEPTH]
    return f

for name, p in (("cube", S.CUBE_DEFAULT), ("bar", S.BAR_DEFAULT)):
    parts = S.build(p); m, f = parts["master"], parts["pour_frame"]
    m.export(OUT / f"{name}_master.stl"); f.export(OUT / f"{name}_pour_frame.stl")
    rm = trimesh.load(OUT / f"{name}_master.stl"); rf = trimesh.load(OUT / f"{name}_pour_frame.stl")
    fs = seated(rm, rf)
    inter = S._man(rm) ^ S._man(fs)
    d = S.dims_dict(p)
    ver[name] = dict(dims=d, master=S.check(rm), pour_frame=S.check(rf),
                     seated_interference_mm3=round(float(inter.volume()), 4),
                     frame_bottom_on_groove_floor=bool(abs(fs.bounds[0, 2] - (S.PLATE_T - S.GR_DEPTH)) < 1e-6),
                     frame_top_z_above_plate_top=round(float(fs.bounds[1, 2] - S.PLATE_T), 3))
    # renders
    t = rm.bounds.mean(0)
    render(rm, OUT / f"{name}_master.png", (1, -1.3, 0.9), title=f"{name}_master.stl", color=GREY, size=(900, 800))
    render(rf, OUT / f"{name}_pour_frame.png", (1, -1.3, 0.9), title=f"{name}_pour_frame.stl", color=BLUE, size=(900, 800))
    asm = trimesh.util.concatenate([rm, fs])
    asm.visual.face_colors = np.vstack([np.tile([158, 153, 145, 255], (len(rm.faces), 1)),
                                        np.tile([90, 140, 200, 255], (len(fs.faces), 1))])
    # cut away front half of the frame so the positives show
    cut = fs.slice_plane([0, -d["frame_inner_mm"][1] / 2 + 15, 0], [0, 1, 0], cap=True)
    asm2 = trimesh.util.concatenate([rm, cut])
    import pyrender
    render(asm2, OUT / f"{name}_assembly.png", (1, -1.3, 0.9), title=f"{name}: master + seated frame (front of frame cut away)", color=(0.55, 0.62, 0.70), size=(900, 800))
    # section close-up at +x side, plane y=0
    W = d["frame_inner_mm"][0]
    sec_m = rm.slice_plane([0, 0, 0], [0, 1, 0], cap=True); sec_f = fs.slice_plane([0, 0, 0], [0, 1, 0], cap=True)
    sec = trimesh.util.concatenate([sec_m, sec_f])
    tgt = np.array([W / 2 + 3, 0, 4.0])
    render(sec, OUT / f"{name}_lip_channel_section.png", (0, -1, 0), target=tgt, mag=9, size=(900, 800),
           title=f"{name}: section y=0 at +x edge (groove 3.5x1.6, 0.25/side, 1.5 channel, 1.6x3.0 lip)", color=(0.6, 0.6, 0.62))
    board([OUT / f"{name}_master.png", OUT / f"{name}_pour_frame.png", OUT / f"{name}_assembly.png", OUT / f"{name}_lip_channel_section.png"],
          OUT / f"{name}_board.png", f"{name} set", cols=2)

alt = S.SpecimenParams("bar", 40.0, 160.0, 2, 2, upright=True)
ver["alt_bar_40x40x160_upright_2x2"] = S.dims_dict(alt)
# flat 40x40x160 feasibility: needs inner (160+20) x (n*40+(n+1)*10) -> even n=1: plate
pw, pd = 180 + 2 * S.U_PLATE, 60 + 2 * S.U_PLATE
ver["flat_40x40x160_single_bar_plate_mm"] = [pw, pd]
ver["flat_40x40x160_fits_150_at_45deg"] = (pw + pd) / math.sqrt(2) <= S.BED_XY
(OUT / "verification.json").write_text(json.dumps(ver, indent=2))
with zipfile.ZipFile(OUT / "specimen_molds_STLs.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for fn in ["cube_master.stl", "cube_pour_frame.stl", "bar_master.stl", "bar_pour_frame.stl", "README.md",
               "verification.json", "cube_board.png", "bar_board.png"]:
        if (OUT / fn).exists(): z.write(OUT / fn, fn)
print(json.dumps({k: v for k, v in ver.items() if k in ("cube", "bar")}, indent=1))
