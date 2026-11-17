"""Build spiral wire jig sets (1/2 cubit even, 1/2 cubit golden, 1/4 cubit even), verify, render.
Usage: build_spiral_jig.py [OUT] [drive]   drive = teeth (v2 default -> /workspace/exports/spiral_jig/v2_four_tooth)
                                           or lugs (v1 -> pass /workspace/exports/spiral_jig explicitly)."""
import os, json, sys
from pathlib import Path
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, trimesh, pyrender
from PIL import Image, ImageDraw
import spiral_jig as S
from moai_render import look_at, board

DRIVE = sys.argv[2] if len(sys.argv) > 2 else "teeth"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/exports/spiral_jig/v2_four_tooth"); OUT.mkdir(parents=True, exist_ok=True)
BODY, DISC, HAND, CU, BRASS = (0.20, 0.36, 0.62), (0.62, 0.74, 0.88), (0.13, 0.25, 0.45), (0.80, 0.45, 0.22), (0.85, 0.68, 0.20)
_R = {}


def render(items, path, direction, title="", size=(900, 800), target=None, mag=None, up=(0, 0, 1)):
    allm = trimesh.util.concatenate([m for m, _ in items])
    target = allm.bounds.mean(0) if target is None else np.asarray(target)
    mag = mag or 0.62 * np.ptp(allm.bounds, 0).max()
    if size not in _R: _R[size] = pyrender.OffscreenRenderer(*size)
    sc = pyrender.Scene(bg_color=[0.93, 0.94, 0.96, 1], ambient_light=[0.25] * 3)
    for m, col in items:
        mat = pyrender.MetallicRoughnessMaterial(baseColorFactor=[*col, 1], metallicFactor=0.0, roughnessFactor=0.7)
        sc.add(pyrender.Mesh.from_trimesh(m, material=mat, smooth=False))
    d = np.asarray(direction, float); d /= np.linalg.norm(d)
    sc.add(pyrender.OrthographicCamera(xmag=mag * size[0] / size[1], ymag=mag, znear=1, zfar=3000), pose=look_at(target + d * 900, target, up))
    sc.add(pyrender.DirectionalLight(intensity=3.0), pose=look_at(target + 600 * (d + np.array([0.4, 0.2, 0.7])), target, up))
    sc.add(pyrender.DirectionalLight(intensity=1.2), pose=look_at(target + 600 * (d + np.array([-0.6, 0, -0.2])), target, up))
    c, _ = _R[size].render(sc)
    im = Image.fromarray(c); ImageDraw.Draw(im).text((10, 10), title, fill=(0, 0, 0)); im.save(path)
    return path


CASES = {"half_cubit_even": S.preset_params("1/2 cubit (261.8 mm)", drive=DRIVE),
         "half_cubit_golden": S.preset_params("1/2 cubit (261.8 mm)", spacing="golden", drive=DRIVE),
         "quarter_cubit_even": S.preset_params("1/4 cubit (130.9 mm)", drive=DRIVE)}
ISO = (1, -1.3, 1.0)
summary, imgs = {}, []
for name, p in CASES.items():
    out, info = S.build(p)
    L = info["L"]; sol = L["sol"]
    files = {}
    for k, tm in out.items():
        f = OUT / f"{name}_{k}.stl"; tm.export(f); files[k] = str(f)
    re = {k: trimesh.load(f) for k, f in files.items()}
    ver = S.verify(p, re, info)
    rep = S.report(p, sol)
    summary[name] = dict(params=S.params_dict(p), coil=rep, parts=ver, files=files)
    A = S.assembled(p, re, info)
    zc = L["z_floor_top"] + p.wire_w / 2
    coil = S.wire_mesh(p, S.all_arms(p, sol.wind), zc)
    relaxed = S.wire_mesh(p, S.all_arms(p, S.rebend(sol.wind, sol.n_hook, -p.dk)), 0.0)
    t = f"{name}: {p.wire_length:g} mm wire, {rep['turns_per_arm']:.2f} turns/arm, wound OD {rep['wound_od_on_jig_mm']:.1f} -> relaxed {rep['predicted_relaxed_od_mm']:.1f} mm"
    imgs.append(render([(A["winding_disc"], DISC), (A["pins"], BRASS), (coil, CU)], OUT / f"{name}_coil_top.png", (0.12, -0.35, 1),
                       t, size=(800, 800), up=(0, 1, 0)))
    render([(relaxed, CU)], OUT / f"{name}_relaxed_coil_top.png", (0, 0, 1), f"{name}: released coil (predicted), OD {rep['predicted_relaxed_od_mm']:.1f} mm",
           size=(700, 700), up=(0, 1, 0), mag=0.62 * (p.coil_od + 6))
    if name == "half_cubit_golden":
        continue  # body/handle identical to the even set; disc differs
    render([(A["body"], BODY), (A["winding_disc"], DISC), (A["handle"], HAND), (A["pins"], BRASS), (coil, CU)],
           OUT / f"{name}_assembly.png", ISO, f"{name} assembly: body + winding disc + brass pins + T-handle, coil wound")
    straight = S.straight_wire(p, L, 2 * L["R_body"] + 30)
    render([(A["body"], BODY), (A["winding_disc"], DISC), (A["handle"], HAND), (A["pins"], BRASS), (straight, CU)],
           OUT / f"{name}_assembly_start.png", ISO, f"{name}: start - straight wire through the slot and between the pins")
    if name == "half_cubit_even":
        ex = lambda m, dz: m.copy().apply_translation((0, 0, dz))
        render([(A["body"], BODY), (ex(A["winding_disc"], 28), DISC), (ex(A["pins"], 28), BRASS), (ex(A["handle"], -30), HAND)],
               OUT / f"{name}_exploded.png", (1, -1.3, 0.55), f"exploded: winding disc + pins (top), body, winged T-handle (bottom, {'4 teeth' if DRIVE == 'teeth' else '2 lugs'} key into disc)",
               size=(900, 1000))
        render([(A["handle"].copy().apply_translation((0, 0, 0)), HAND)], OUT / "handle_from_below.png", (0.8, -1.0, -0.9),
               "winged T-handle seen from below (where your fingers go)")
        for k, col in (("body", BODY), ("winding_disc", DISC), ("handle", HAND)):
            render([(re[k], col)], OUT / f"{name}_{k}.png", ISO, f"{name}_{k}.stl (print pose)")
        render([(re["body"], BODY)], OUT / f"{name}_body_top.png", (0, 0, 1), "body top: flared entry ports (mouth on the start axis, fan to the tangent exit)", up=(0, 1, 0))
        if DRIVE == "teeth":
            hz = re["handle"].bounds[1, 2]
            render([(re["handle"], HAND)], OUT / "handle_teeth_closeup.png", (0.9, -1.1, 1.2),
                   "handle: four-tooth dog clutch on the journal (60 deg teeth, 4 mm tall, chamfered tips)",
                   target=(0, 0, hz - 3), mag=17)
            dflip = re["winding_disc"].copy(); dflip.apply_transform(trimesh.transformations.rotation_matrix(np.pi, (1, 0, 0)))
            pins_flip = A["pins"].copy(); pins_flip.apply_translation((0, 0, -L["z_disc"]))
            pins_flip.apply_transform(trimesh.transformations.rotation_matrix(np.pi, (1, 0, 0)))
            render([(dflip, DISC), (pins_flip, BRASS)], OUT / "disc_underside_sockets.png", (0.5, -0.6, 1.2),
                   "winding disc underside: 4 tooth sockets (0.2/side + lead-in) clear of the pin holes", size=(800, 800))
            render([(dflip, DISC), (pins_flip, BRASS)], OUT / "disc_underside_sockets_flat.png", (0, 0, 1),
                   f"disc underside (flat view): sockets >= {summary[name]['parts']['clearance']['socket_to_pin_hole_min_mm']:.2f} mm from pin holes",
                   size=(800, 800), up=(0, 1, 0))
imgs += [OUT / "half_cubit_even_assembly.png", OUT / "half_cubit_even_exploded.png"]
if DRIVE == "teeth":
    imgs += [OUT / "handle_teeth_closeup.png", OUT / "disc_underside_sockets.png", OUT / "disc_underside_sockets_flat.png"]
board([str(i) for i in imgs], OUT / "spiral_jig_board.png", f"Spiral wire jig - review renders (not for sale), drive: {S.DRIVES[DRIVE]}", cols=3)
summary["pins"] = S.PIN_PART
summary["drive"] = dict(selected=DRIVE, strength=S.drive_strength(CASES["half_cubit_even"]))
(OUT / "verification.json").write_text(json.dumps(summary, indent=1, default=str))
for n, s in summary.items():
    if n not in ("pins", "drive"):
        print(n, json.dumps(s["coil"]), all(v.get("ok") for v in s["parts"].values()))
