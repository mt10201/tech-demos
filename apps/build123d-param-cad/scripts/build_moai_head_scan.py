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
-> rounded back: behind that plane, a smooth superellipse back of head / neck (depth 10 mm at the base to
   ~36 mm at ear height, rounding over into the crown) with low-amplitude weathered-stone noise, joined by a
   4 mm smooth-min; nothing more than ~8 mm in front of the old flat face changes (the face is the raw scan)
-> largest piece, cavities filled, horizontal-slice tunnels plugged -> marching cubes
-> decimate 50 % (quadric) -> check watertight + Euler characteristic 2.
"""
import io, sys, time, zipfile
from pathlib import Path
import numpy as np, trimesh
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from scipy.interpolate import PchipInterpolator
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


# ---- rounded natural back of the head (replaces the flat cut back) ----
BACK_OVERLAP = 4.0   # mm: the new back volume starts this far inside the scan, in front of the old flat face
BACK_K = 4.0         # mm: smooth-union radius (no seam between the scan sides and the new back)
BACK_N = 2.3         # superellipse exponent of the back-of-head plan shape (2 = ellipse)
# depth (mm) added behind the old flat face, per height (mm above the base): gives a near-vertical,
# slightly convex back of head and neck; head depth at ear height ~0.8 x head width (real moai proportion)
BACK_DEPTH = ((0, 10.0), (40, 20.0), (80, 30.0), (110, 35.0), (140, 36.0), (152.4, 36.0))
CROWN_R0 = 112.0     # mm: above this the back rounds over into the crown (quarter ellipse)
BACK_SMOOTH = 12.0   # mm: sigma for smoothing the back width along the height (gradual taper, no ledges)
CROWN_GAP = 3.0      # mm: the rounding ends this far below the crown edge (stays within the scan height)
STONE_AMP = 0.7     # mm: peak-ish amplitude of the weathered-stone texture on the new back
STONE_SEED = 7


def round_back(f, X, Y, Z, yb, V, log=print):
    """f: SDF (mm, <0 inside) with a flat back at y = yb(z). Returns f with a rounded, weathered back.
    Nothing in front of y = yb - BACK_OVERLAP - BACK_K is changed (the face is the untouched scan)."""
    solid = f < 0
    nz = len(Z)
    # per height: x-extent of the old flat back face (band 1.5 mm in front of the plane)
    band = (Y[None, :] > yb[:, None] - 1.5) & (Y[None, :] <= yb[:, None])          # (nz, ny)
    edge = (solid & band.T[None, :, :]).any(1)                                    # (nx, nz)
    has = edge.any(0)
    xl = np.where(has, X[np.argmax(edge, 0)], np.nan)
    xr = np.where(has, X[len(X) - 1 - np.argmax(edge[::-1], 0)], np.nan)
    kz = np.where(has)[0]; k0, k1 = kz.min(), kz.max()
    zc = Z[k1]                                    # crown height at the back edge
    for arr in (xl, xr):                          # fill tiny gaps, smooth along z (sigma 4 mm)
        good = ~np.isnan(arr)
        arr[~good] = np.interp(np.where(~good)[0], np.where(good)[0], arr[good])
    xls = ndi.gaussian_filter1d(xl, BACK_SMOOTH / V, mode="nearest")
    xrs = ndi.gaussian_filter1d(xr, BACK_SMOOTH / V, mode="nearest")
    xc = 0.5 * (xls + xrs); a = 0.5 * (xrs - xls) - 0.5
    zb = np.array([p[0] for p in BACK_DEPTH]); db = np.array([p[1] for p in BACK_DEPTH])
    d = PchipInterpolator(zb, db, extrapolate=True)(np.clip(Z, 0, zb[-1]))
    zt = zc - CROWN_GAP                           # top of the rounded back
    t = np.clip((Z - CROWN_R0) / (zt - CROWN_R0), 0, 1)
    d = d * np.sqrt(1 - t ** 2)                   # quarter-ellipse round-over into the crown
    y0 = yb - BACK_OVERLAP
    D = d + BACK_OVERLAP
    # smooth analytic implicit (no voxel terraces): per-height superellipse behind y0 (plan view),
    # its depth rounding over into the crown above CROWN_R0
    A = np.maximum(a, 2.0)
    dx = np.abs(X[:, None, None] - xc[None, None, :]) / A[None, None, :]
    dy = np.maximum(Y[None, :, None] - y0[None, None, :], 0) / D[None, None, :]
    r = (dx ** BACK_N + dy ** BACK_N) ** (1 / BACK_N)
    del dx, dy
    g = (r - 1) * np.minimum(A, D)[None, None, :]
    g = np.maximum(g, (y0[None, None, :] - Y[None, :, None]))   # nothing in front of y0
    g = np.maximum(g, (Z - (zc - 0.5))[None, None, :])           # nothing above the crown
    del r
    g = ndi.gaussian_filter(g.astype(np.float32), 1.0)
    gn = np.sqrt(sum(q * q for q in np.gradient(g, V)))
    B = (g / np.maximum(gn, 0.3)).astype(np.float32)          # ~ signed distance in mm near the surface
    del g, gn
    # weathered-stone texture: smooth band-limited noise (sigma 3 mm + 1.2 mm + 0.7 mm), no spikes,
    # faded in from zero at the old face so the scan sides join without a seam
    rng = np.random.default_rng(STONE_SEED)
    n1 = ndi.gaussian_filter(rng.standard_normal(f.shape).astype(np.float32), 3.0 / V)
    n2 = ndi.gaussian_filter(rng.standard_normal(f.shape).astype(np.float32), 1.2 / V)
    n3 = ndi.gaussian_filter(rng.standard_normal(f.shape).astype(np.float32), 0.7 / V)
    n = n1 / n1.std() + 0.45 * n2 / n2.std() + 0.3 * n3 / n3.std()
    del n1, n2, n3
    n *= STONE_AMP / (2.5 * n.std())              # ~2.5 sigma ≈ STONE_AMP
    w = np.clip((Y[None, :, None] - yb[None, None, :]) / 6.0, 0, 1).astype(np.float32)
    B = B + w * n
    del n, w
    # smooth union (polynomial smooth-min) with the scan
    h = np.clip(BACK_K - np.abs(f - B), 0, None) / BACK_K
    out = np.minimum(f, B) - (h * h * BACK_K * 0.25).astype(np.float32)
    ztop = Z[solid.any((0, 1))].max()
    # never higher than the scan's crown (keeps the 152.4 mm height and scale): only clips added material
    out = np.maximum(out, np.minimum(f, (Z - ztop)[None, None, :]))
    changed = np.abs(out - f) > 1e-6
    ci = np.argwhere(changed & (np.abs(out) < 2))
    if len(ci):
        dy_ch = (Y[ci[:, 1]] - yb[ci[:, 2]]).min()
        log(f"back: added depth max {d.max():.1f} mm; changes start {dy_ch:.1f} mm relative to the old flat face")
    return out.astype(np.float32), d, a, xc


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
# rounded, weathered back of head and neck in place of the flat back (the face is not touched)
f, _, _, _ = round_back(f, X, Y, Z, yb, VOX, log)
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
# decimation can nudge a few base-rim vertices microns below the base plane: snap them back (flat base)
zl = v2[:, 2].min(); zb = np.median(v2[v2[:, 2] < zl + 0.05, 2]); v2[v2[:, 2] < zb, 2] = zb
final = trimesh.Trimesh(v2, f2, process=True)
final.apply_translation([-final.bounds.mean(0)[0], -final.bounds.mean(0)[1], -final.bounds[0][2]])
final.apply_scale(H_MM / final.extents[2])
assert final.is_watertight and final.is_volume and final.euler_number == 2, "not a closed genus-0 solid"
final.export(HERE / "assets/moai_head_scan_152mm.stl")
pv, pf = fast_simplification.simplify(final.vertices, final.faces, target_reduction=0.85, agg=7)
trimesh.Trimesh(pv, pf, process=True).export(HERE / "assets/moai_head_scan_preview.ply")
log("final", len(final.faces), "triangles, euler", final.euler_number, "extents", final.extents.round(2))
