"""Rebuild the "Quarry Moai - Rapa Nui/Easter Island" scan (Ryan Shackleton, CC BY 4.0) into a
watertight, genus-0 head mold master, 152.4 mm tall, in mm.

    python scripts/build_moai_head_scan.py path/to/quarry-moai-rapa-nuieaster-island.zip

Needs the original OBJ download from
https://sketchfab.com/3d-models/quarry-moai-rapa-nuieaster-island-dd6027d79fe14549ab7b2eae0d94de5d
(Sketchfab login). Writes assets/moai_head_scan_152mm.stl and assets/moai_head_scan_preview.ply.
Extra dependency for this script only: fast-simplification (decimation).

Steps: orient (head axis -> +Z by PCA of the upper scan, nose -> -Y) -> scale so chin..crown = 152.4 mm
-> sample the surface (5 M points) on a 0.3 mm grid -> dilate 0.75 mm, fill (2D per slice + 3D),
erode 0.75 mm (morphological closing: gaps/holes < ~1.5 mm, nostril slits and texture-seam cracks close)
-> flat back plane (the scan's back is the ragged hillside contact, not statue) with narrow notches filled
-> soil removed (below the jaw only the head footprint is kept) -> flat base at the chin
-> largest piece, cavities filled, horizontal-slice tunnels plugged -> marching cubes
-> decimate 50 % (quadric) -> check watertight + Euler characteristic 2.
"""
import io, sys, time, zipfile
from pathlib import Path
import numpy as np, trimesh
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

HERE = Path(__file__).resolve().parents[1]
SRC = sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / "Downloads/quarry-moai-rapa-nuieaster-island.zip")


def load_oriented(zip_path):
    """Original OBJ -> upright (+Z), face toward -Y, centred, base of the scan at z = 0 (scan units ≈ m)."""
    outer = zipfile.ZipFile(zip_path)
    inner = zipfile.ZipFile(io.BytesIO(outer.read("source/model.zip")))
    m = trimesh.load(io.BytesIO(inner.read("model.obj")), file_type="obj", force="mesh")
    v = m.vertices; z = v[:, 2]; z0, z1 = z.min(), z.max()
    u = v[z > z0 + 0.45 * (z1 - z0)]
    w, vec = np.linalg.eigh(np.cov((u - u.mean(0)).T)); up = vec[:, -1] * np.sign(vec[2, -1])
    m.apply_transform(trimesh.geometry.align_vectors(up, [0, 0, 1]))
    v = m.vertices; z = v[:, 2]; z0, z1 = z.min(), z.max()
    band = v[(z > z0 + 0.55 * (z1 - z0)) & (z < z0 + 0.85 * (z1 - z0))]
    ax = np.median(band[:, :2], axis=0)
    tip = band[np.argmax(np.linalg.norm(band[:, :2] - ax, axis=1))]
    ang = np.arctan2(*(tip[:2] - ax)[::-1])
    m.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2 - ang, [0, 0, 1]))
    m.apply_translation(-np.array([*m.bounds.mean(0)[:2], m.bounds[0][2]]))
    return m


H_MM = 152.4
Z_TOP = 3.169        # oriented scan units (≈ m)
Z_CHIN = 1.09        # underside of the chin; soil below
Z_SOIL = 1.30        # below this, keep only the head footprint (soil flares out at the sides)
BACK = (0.496, -0.160)  # back closure: y = a + b*z (5th percentile of the ragged hillside contact)
BACK_IN = 0.012      # cut this much (scan units) in front of that fit -> clean flat back
VOX = 0.3            # mm voxel
R_CLOSE = 0.75       # mm: closing radius -> fills gaps / holes narrower than ~1.5 mm
t0 = time.time()
def log(*a): print(f"[{time.time()-t0:6.1f}s]", *a, flush=True)

m = load_oriented(SRC)
s = H_MM / (Z_TOP - Z_CHIN)
v = m.vertices.copy(); v[:, 2] -= Z_CHIN; v *= s
m = trimesh.Trimesh(v, m.faces, process=False)
# drop soil-only geometry far below the crop to keep the grid small
lo = np.array([v[:, 0].min(), v[:, 1].min(), -3.0]); hi = np.array([v[:, 0].max(), v[:, 1].max(), H_MM + 3])
pts, _ = trimesh.sample.sample_surface(m, 5_000_000, seed=1)
pts = np.vstack([pts, v]); pts = pts[(pts[:, 2] > lo[2]) & (pts[:, 2] < hi[2])]
log('points', len(pts), 'scale', s)

pad = 3.0
lo = pts.min(0) - pad; hi = pts.max(0) + pad
lo = lo - VOX / 3  # offset grid (avoid planes landing exactly on samples)
shape = np.ceil((hi - lo) / VOX).astype(int) + 1
log('grid', shape, np.prod(shape) / 1e6, 'M')
idx = np.floor((pts - lo) / VOX + 0.5).astype(int)
occ = np.zeros(shape, bool); occ[tuple(idx.T)] = True
edt = ndi.distance_transform_edt(~occ) * VOX
band = edt < R_CLOSE + 2 * VOX
bi = np.argwhere(band)
tree = cKDTree(pts)
d, _ = tree.query(lo + bi * VOX, workers=-1)
dist = np.full(shape, np.inf, np.float32); dist[tuple(bi.T)] = d
del edt
dil = dist < R_CLOSE
log('band voxels', len(bi))
# fill: per z-slice 2D hole fill (sections are closed loops), then 3D
fill = dil.copy()
for k in range(shape[2]):
    fill[:, :, k] = ndi.binary_fill_holes(dil[:, :, k])
fill = ndi.binary_fill_holes(fill)
area = fill.sum((0, 1)); log('slice fill area min/med', area[area > 0].min(), np.median(area))
# erosion of the dilated solid by R_CLOSE (morphological closing), as a field
edt_in = ndi.distance_transform_edt(fill) * VOX
f = np.where(fill, R_CLOSE - edt_in, dist).astype(np.float32)
f[~np.isfinite(f)] = R_CLOSE + 2 * VOX
del edt_in
f = ndi.gaussian_filter(f, 0.6)
log('closing field done')

X = lo[0] + np.arange(shape[0]) * VOX
Y = lo[1] + np.arange(shape[1]) * VOX
Z = lo[2] + np.arange(shape[2]) * VOX
Zs = Z / s + Z_CHIN  # back in scan units
yb = (BACK[0] + BACK[1] * Zs - BACK_IN) * s  # back plane y(mm) per z
nb = 1 / np.hypot(1, BACK[1])
back = (Y[None, :, None] - yb[None, None, :]) * nb            # >0 behind the back plane
f = np.maximum(f, back.astype(np.float32))
# back notches: the ragged hillside contact leaves narrow notches in front of the plane.
# Per (x, z) column, gap g = plane - backmost solid; a 2D grey opening removes narrow gap peaks
# (notches) but keeps the broad curvature of the head sides. Fill each column up to the opened gap.
solid = f < 0
sil = solid.any(1)
jb = np.where(sil, shape[1] - 1 - np.argmax(solid[:, ::-1, :], axis=1), 0)
yback = Y[jb]
g = np.where(sil, yb[None, :] - yback, 1e3)
NOTCH = int(round(9.0 / VOX))  # notches narrower than ~9 mm are filled
go_ = ndi.grey_opening(g, size=(NOTCH, NOTCH))
go_ = np.minimum(go_, g)
go_ = ndi.gaussian_filter(go_, 1.0)
ynb = yb[None, :] - np.maximum(go_, 0.0)
fill_cols = sil & (ynb > yback + 0.5 * VOX)
slab = np.maximum(Y[None, :, None] - ynb[:, None, :], (yback - 2.0)[:, None, :] - Y[None, :, None]).astype(np.float32)
slab = np.where(fill_cols[:, None, :], slab, np.float32(10))
f = np.minimum(f, slab)
f = np.maximum(f, back.astype(np.float32))
log('notch columns filled', int(fill_cols.sum()), 'of', int(sil.sum()))
# soil: below Z_SOIL keep only the head footprint taken just above it
ks = int(round(((Z_SOIL + 0.03 - Z_CHIN) * s - lo[2]) / VOX))
foot = ndi.binary_fill_holes(f[:, :, ks] < 0)
foot = ndi.binary_dilation(foot, iterations=int(np.ceil(1.0 / VOX)))
fs = (ndi.distance_transform_edt(~foot) - ndi.distance_transform_edt(foot)) * VOX
zsoil = (Z_SOIL - Z_CHIN) * s
f = np.where(Z[None, None, :] < zsoil, np.maximum(f, fs[:, :, None].astype(np.float32)), f)
# flat base at z = 0
f = np.maximum(f, -Z[None, None, :].astype(np.float32))
# keep the largest solid piece, fill internal cavities
lab, n = ndi.label(f < 0); sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
keep = lab == (1 + int(np.argmax(sizes)))
keep = ndi.binary_fill_holes(keep)
# plug tunnels: any hole fully enclosed within a horizontal slice is a vertical tunnel (e.g. the slot
# behind an ear once the back is closed) -> fill it, so the part stays genus 0 for the mold
plug = np.zeros_like(keep)
for k in range(shape[2]):
    plug[:, :, k] = ndi.binary_fill_holes(keep[:, :, k]) & ~keep[:, :, k]
pi = np.argwhere(plug); log('tunnel voxels plugged', len(pi), 'at mm', (lo + pi.min(0)*VOX).round(1) if len(pi) else '', (lo + pi.max(0)*VOX).round(1) if len(pi) else '')
keep |= plug
f = np.where(plug, np.float32(-0.5 * VOX), f)
log('pieces', n, 'kept voxels', keep.sum())
f = np.where(keep, np.minimum(f, -1e-3), np.maximum(f, 1e-3))
f[f == 0] = 1e-7
fp = np.pad(f, 1, constant_values=1.0)
verts, faces, _, _ = marching_cubes(fp, 0.0, spacing=(VOX,) * 3, allow_degenerate=False)
verts += lo - VOX
out = trimesh.Trimesh(verts, faces, process=True)
cc = out.split(only_watertight=False)
out = max(cc, key=lambda q: len(q.faces))
out.apply_translation([-out.bounds.mean(0)[0], -out.bounds.mean(0)[1], -out.bounds[0][2]])
out.apply_scale(H_MM / out.extents[2])
log('mesh', len(out.faces), 'wt', out.is_watertight, 'euler', out.euler_number, 'ext', out.extents.round(2), 'pieces', len(cc))


import fast_simplification  # noqa: E402

v2, f2 = fast_simplification.simplify(out.vertices.astype(np.float64), out.faces, target_reduction=0.5, agg=7)
final = trimesh.Trimesh(v2, f2, process=True)
final.apply_translation([-final.bounds.mean(0)[0], -final.bounds.mean(0)[1], -final.bounds[0][2]])
final.apply_scale(H_MM / final.extents[2])
assert final.is_watertight and final.is_volume and final.euler_number == 2, "not a closed genus-0 solid"
final.export(HERE / "assets/moai_head_scan_152mm.stl")
pv, pf = fast_simplification.simplify(final.vertices, final.faces, target_reduction=0.85, agg=7)
trimesh.Trimesh(pv, pf, process=True).export(HERE / "assets/moai_head_scan_preview.ply")
log("final", len(final.faces), "triangles, euler", final.euler_number, "extents", final.extents.round(2))
