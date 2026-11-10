"""Moai v2 hi-res master: rebuild of "Quarry Moai - Rapa Nui/Easter Island" (Ryan Shackleton, CC BY 4.0)
from the ORIGINAL Sketchfab scan at 0.25 mm (v1/original: 0.3 mm), with a new back of head.

    python3 scripts/build_moai_v2.py [path/to/quarry-moai-rapa-nuieaster-island.zip] [out.stl]

Why v2: mapping every vertex of the shipped head against the raw scan showed the straight vertical
line behind each ear and the line across the crown are NOT smoothing artefacts: they are the
hillside/soil contact of the half-buried quarry statue. The scan stops there (the back was never
captured), v1 cut the scan with a straight plane at that contact and added a synthetic back that was
as wide as the ears, so the ear's rear edge was a ruler-straight planar cut flush with a slab.

v2 changes (face untouched: nothing in front of the cut band is modified):
- no hard cut: a 4 mm signed-distance MORPH (smoothstep) centred on a slightly wavy (+/-0.8 mm) contact line
  turns the scan into the new back, so there is no crease, groove or planar facet;
- the new back is NARROWER than the ears (2 mm inset over the ear zone), so the ears keep a soft,
  sloped rear edge and stand proud of the head as on real moai (v1: flush slab, hard straight line);
- the back's top continues the scanned crown height and rounds over with a 9 mm smooth radius, so
  the crown has no step/line where the scan ends;
- plan section superellipse n = 2.5 (rounder rear corners than v1 n = 4); weathered-stone noise
  faded in from the cut so texture is continuous;
- 0.25 mm voxel SDF -> marching cubes -> quadric decimation to ~740k triangles (no faceting at 152.4 mm).
Height 152.4 mm (unchanged), base on z = 0, watertight genus 0.
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
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "assets/moai_v2_hires_152mm.stl"
H_MM = 152.4
Z_TOP, Z_CHIN, Z_SOIL = 3.169, 1.09, 1.30     # oriented scan units (same as v1 build)
S = H_MM / (Z_TOP - Z_CHIN)
# rigid alignment raw(mm) -> frame of assets/moai_head_scan_152mm.stl (ICP on the face, median 0.41 mm)
T_RAW = np.array([[0.99999747, -0.00204174, 0.00094901, -4.53090088],
                  [0.00204487, 0.99999246, -0.00330254, 12.1160689],
                  [-0.00094226, 0.00330447, 0.9999941, 0.04221433], [0, 0, 0, 1.0]])
YB0, YB1 = 34.830, -0.1634   # soil-contact plane in that frame: y = YB0 + YB1*z (v1 BACK fit, BACK_IN applied)
V = 0.25                      # mm voxel
R_CLOSE = 0.75                # mm closing radius (gaps < ~1.5 mm closed, as v1)
CUT_WOB, CUT_WOB_SIG, CUT_BOW = 0.8, 8.0, 0.8
EAR_INSET, EAR_Z = 2.0, (46.0, 146.0)   # new back 2 mm narrower than the ears -> soft ear rear edge
BLEND_T, BLEND_BACK, TOP_K, PLAN_N = 4.0, 2.0, 9.0, 2.5   # 4 mm SDF morph centred on the cut
BACK_Y = ((0, 11.9), (20, 9.4), (40, 5.7), (55, 5.4), (75, 6.1), (100, 6.7), (125, 6.7), (152.4, 6.7))
BACK_MIN = 1.5
DISH_MM, DISH_W, DISH_Z = 1.5, 0.7, (55.0, 135.0)
STONE_AMP, SEED = 0.6, 7
TARGET_FACES = 740_000
CROWN_SMOOTH_DZ, CROWN_SMOOTH_IT = 10.0, 40       # mm below the crown where the terrace smoothing starts
t0 = time.time()
def log(*a): print(f"[{time.time()-t0:6.1f}s]", *a, flush=True)


def smax(a, b, k):
    h = np.clip(k - np.abs(a - b), 0, None) / k
    return np.maximum(a, b) + h * h * k * 0.25


def smin(a, b, k):
    h = np.clip(k - np.abs(a - b), 0, None) / k
    return np.minimum(a, b) - h * h * k * 0.25


def load_raw_mm(zip_path):
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
    v = m.vertices.copy(); v[:, 2] -= Z_CHIN; v *= S
    v = (np.c_[v, np.ones(len(v))] @ T_RAW.T)[:, :3]
    return trimesh.Trimesh(v, m.faces, process=False)


def main():
    m = load_raw_mm(SRC)
    pts, _ = trimesh.sample.sample_surface(m, 7_000_000, seed=1)
    pts = np.vstack([pts, m.vertices])
    keep = (pts[:, 2] > -3) & (pts[:, 2] < H_MM + 4) & (np.abs(pts[:, 0]) < 46) & \
           (pts[:, 1] < YB0 + YB1 * pts[:, 2] + 6)
    pts = pts[keep]; del m
    lo = pts.min(0) - 3.0 - V / 3; hi = pts.max(0) + 3.0
    hi[1] = max(hi[1], 48.0)                         # room for the new back
    shape = np.ceil((hi - lo) / V).astype(int) + 1
    log("points", len(pts), "grid", shape, round(np.prod(shape) / 1e6, 1), "M")
    X = lo[0] + np.arange(shape[0]) * V; Y = lo[1] + np.arange(shape[1]) * V; Z = lo[2] + np.arange(shape[2]) * V
    idx = np.floor((pts - lo) / V + 0.5).astype(int)
    occ = np.zeros(shape, bool); occ[tuple(idx.T)] = True
    band = ndi.distance_transform_edt(~occ).astype(np.float32) * V < R_CLOSE + 2 * V
    del occ
    bi = np.argwhere(band); del band
    d, _ = cKDTree(pts).query(lo + bi * V, workers=-1)
    del pts
    dist = np.full(shape, R_CLOSE + 2 * V, np.float32); dist[tuple(bi.T)] = d; del bi, d
    dil = dist < R_CLOSE
    yb = (YB0 + YB1 * Z).astype(np.float32)
    # close the open back with the contact plane before filling (sections become closed loops)
    dil |= (Y[None, :, None] >= yb[None, None, :] - 0.5) & (Y[None, :, None] <= yb[None, None, :] + 2 * V) & \
           (ndi.binary_dilation(dil.any(1), iterations=2)[:, None, :])
    for k in range(shape[2]):
        dil[:, :, k] = ndi.binary_fill_holes(dil[:, :, k])
    fill = ndi.binary_fill_holes(dil); del dil
    edt_in = ndi.distance_transform_edt(fill).astype(np.float32) * V
    f = np.where(fill, R_CLOSE - edt_in, dist).astype(np.float32); del edt_in, dist, fill
    f = ndi.gaussian_filter(f, 0.6 * 0.3 / V)
    log("closing field done")
    # ---- soft, slightly wavy cut at the soil contact (no ruler-straight planar facet) ----
    rng = np.random.default_rng(SEED)
    wob = ndi.gaussian_filter(rng.standard_normal((shape[0], shape[2])).astype(np.float32), CUT_WOB_SIG / V)
    wob *= CUT_WOB / (2.0 * wob.std())
    nb = 1 / np.hypot(1, YB1)
    bow = CUT_BOW * np.clip(np.sin(np.pi * (Z - EAR_Z[0]) / (EAR_Z[1] - EAR_Z[0])), 0, None)
    yc = yb[None, :] - 0.4 - bow[None, :] + wob                                    # (nx, nz)
    j0 = int(np.searchsorted(Y, yb.min() - CUT_BOW - BLEND_T - 4))       # everything in front of j0 untouched
    sl = np.s_[:, j0:, :]
    Ys = Y[j0:]
    # the closing field is clamped at R_CLOSE + 2V away from the scan; the morph below needs a real
    # distance there (a clamped plateau gives pin-prick pits), so extend it with an exterior EDT
    fs0 = f[sl]
    dout = ndi.distance_transform_edt(fs0 >= 0).astype(np.float32) * V
    f[sl] = np.where(fs0 >= R_CLOSE + V, np.maximum(fs0, dout), fs0); del fs0, dout
    cut = ((Ys[None, :, None] - yc[:, None, :]) * nb).astype(np.float32)
    # notch fill in front of the cut (ragged hillside contact), as v1
    solid = f < 0
    sil = solid.any(1)
    jb = np.where(sil, shape[1] - 1 - np.argmax(solid[:, ::-1, :], axis=1), 0); del solid
    yback = Y[np.minimum(jb, shape[1] - 1)]
    g = np.where(sil, yb[None, :] - yback, 1e3)
    go_ = np.minimum(ndi.grey_opening(g, size=(int(9 / V),) * 2), g)
    go_ = ndi.gaussian_filter(go_, 1.0)
    ynb = yb[None, :] - np.maximum(go_, 0.0)
    fill_cols = sil & (ynb > yback + 0.5 * V)
    slab = np.maximum(Ys[None, :, None] - ynb[:, None, :], (yback - 2.0)[:, None, :] - Ys[None, :, None]).astype(np.float32)
    slab = np.where(fill_cols[:, None, :], slab, np.float32(10))
    fs = np.minimum(f[sl], slab); del slab
    del cut
    f[sl] = fs; del fs
    # soil: below Z_SOIL keep only the head footprint taken just above it
    ks = int(round(((Z_SOIL + 0.03 - Z_CHIN) * S - lo[2]) / V))
    foot = ndi.binary_dilation(ndi.binary_fill_holes(f[:, :, ks] < 0), iterations=int(np.ceil(1.0 / V)))
    fsoil = ((ndi.distance_transform_edt(~foot) - ndi.distance_transform_edt(foot)) * V).astype(np.float32)
    zsoil = (Z_SOIL - Z_CHIN) * S
    kz = Z < zsoil
    f[:, :, kz] = np.maximum(f[:, :, kz], fsoil[:, :, None])
    f = np.maximum(f, -Z[None, None, :].astype(np.float32))
    log("cut / notch / soil / base done")
    # ---- new back of head ----
    solid = f < 0
    bandm = (Y[None, :] > yb[:, None] - 4.0) & (Y[None, :] <= yb[:, None] - 1.0)
    edge = (solid & bandm.T[None, :, :]).any(1)
    has = edge.any(0)
    xl = np.where(has, X[np.argmax(edge, 0)], np.nan); xr = np.where(has, X[len(X) - 1 - np.argmax(edge[::-1], 0)], np.nan)
    for arr in (xl, xr):
        good = ~np.isnan(arr); arr[~good] = np.interp(np.where(~good)[0], np.where(good)[0], arr[good])
    xls = ndi.gaussian_filter1d(xl, 10.0 / V, mode="nearest"); xrs = ndi.gaussian_filter1d(xr, 10.0 / V, mode="nearest")
    xc = 0.5 * (xls + xrs)
    ear = np.clip((Z - EAR_Z[0]) / 12.0, 0, 1) * np.clip((EAR_Z[1] - Z) / 12.0, 0, 1)
    A = np.maximum(0.5 * (xrs - xls) - 0.5 - EAR_INSET * ear, 4.0)
    # crown height near the back (scan) -> top of the new back
    crown = solid[:, :, :] & ((Y[None, :] > yb[:, None] - 10) & (Y[None, :] < yb[:, None] - 3)).T[None, :, :]
    ztop_scan = Z[solid.any((0, 1))].max()
    ztop_back = Z[crown.any((0, 1))].max() - 0.3
    del crown, solid, edge
    log(f"crown {ztop_scan:.2f}, back top {ztop_back:.2f}, half-width range {A.min():.1f}-{A.max():.1f}")
    zb = np.array([p[0] for p in BACK_Y]); ob = np.array([p[1] for p in BACK_Y])
    y_ref = YB0 + YB1 * 60.0
    y_t = y_ref + PchipInterpolator(zb, ob)(np.clip(Z, 0, zb[-1]))
    y0 = yb - 0.4                                  # superellipse starts at the cut: tangent to the scan sides
    D = np.maximum(y_t, yb + BACK_MIN) - y0
    dx = np.abs(X[:, None, None] - xc[None, None, :]) / A[None, None, :]
    dy = np.maximum(Ys[None, :, None] - y0[None, None, :], 0) / D[None, None, :]
    r = (dx ** PLAN_N + dy ** PLAN_N) ** (1 / PLAN_N); del dx, dy
    B = ((r - 1) * np.minimum(A, D)[None, None, :]).astype(np.float32); del r
    B = smax(B, (Z - ztop_back)[None, None, :].astype(np.float32), TOP_K)   # rounded top-back edge
    u = (X[:, None] - xc[None, :]) / A[None, :]
    zf = np.clip((Z - DISH_Z[0]) / 15.0, 0, 1) * np.clip((DISH_Z[1] - Z) / 15.0, 0, 1)
    dish = (DISH_MM * np.clip(1 - (u / DISH_W) ** 2, 0, None) ** 2 * zf[None, :]).astype(np.float32)
    B += dish[:, None, :] * (Ys[None, :, None] > yb[None, None, :])
    B = ndi.gaussian_filter(B, 0.3 / V)
    gn = np.sqrt(sum(q * q for q in np.gradient(B, V)))
    B = (B / np.maximum(gn, 0.3)).astype(np.float32); del gn
    n = np.zeros(B.shape, np.float32)
    for sig, wgt in ((3.0, 1.0), (1.2, 0.45), (0.7, 0.3)):
        q = ndi.gaussian_filter(rng.standard_normal(B.shape).astype(np.float32), sig / V); n += wgt * q / q.std(); del q
    n *= STONE_AMP / (2.5 * n.std())
    n *= np.clip((ztop_back - 4.0 - Z) / 6.0, 0, 1)[None, None, :].astype(np.float32)  # smooth crown, like the scan's
    t = np.clip((Ys[None, :, None] - (yc[:, None, :] + BLEND_BACK - BLEND_T)) / BLEND_T, 0, 1)
    wb = (t * t * (3 - 2 * t)).astype(np.float32); del t      # smoothstep: scan -> new back over BLEND_T mm
    B += wb * n; del n
    fs = (1 - wb) * f[sl] + wb * B; del B, wb                 # SDF morph: no crease, no groove, no planar facet
    f[sl] = np.maximum(fs, np.minimum(f[sl], (Z - ztop_scan)[None, None, :]).astype(np.float32)); del fs
    f = np.maximum(f, -Z[None, None, :].astype(np.float32))
    log("back done")
    lab, nlab = ndi.label(f < 0); sizes = ndi.sum(np.ones(lab.shape, np.uint8), lab, range(1, nlab + 1))
    keep = lab == (1 + int(np.argmax(sizes))); del lab
    keep = ndi.binary_fill_holes(keep)
    plug = np.zeros_like(keep)
    for k in range(shape[2]):
        plug[:, :, k] = ndi.binary_fill_holes(keep[:, :, k]) & ~keep[:, :, k]
    log("pieces", nlab, "tunnel voxels plugged", int(plug.sum()))
    keep |= plug
    f = np.where(plug, np.float32(-0.5 * V), f); del plug
    f = np.where(keep, np.minimum(f, -1e-3), np.maximum(f, 1e-3)).astype(np.float32); del keep
    verts, faces, _, _ = marching_cubes(np.pad(f, 1, constant_values=1.0), 0.0, spacing=(V,) * 3, allow_degenerate=False)
    del f
    verts += lo - V
    out = trimesh.Trimesh(verts, faces, process=True)
    out = max(out.split(only_watertight=False), key=lambda q: len(q.faces))
    log("mc", len(out.faces), "wt", out.is_watertight, "euler", out.euler_number)
    # local Laplacian smoothing of the upward-facing crown only (removes marching-cubes contour terraces);
    # weight ramps 0 -> 1 between z = CROWN_SMOOTH_Z and +4 mm; the face/eyes/ears are untouched
    vv = out.vertices.copy(); ztop = vv[:, 2].max()
    wz = np.clip((vv[:, 2] - (ztop - CROWN_SMOOTH_DZ)) / 4.0, 0, 1)[:, None]
    if (wz > 0).any():
        import scipy.sparse as sp
        e = out.edges_unique
        A = sp.coo_matrix((np.ones(2 * len(e)), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(len(vv),) * 2).tocsr()
        deg = np.asarray(A.sum(1)).ravel()[:, None]
        up = np.zeros(len(vv)); np.add.at(up, out.faces.ravel(), np.repeat(out.face_normals[:, 2], 3))
        wz = wz * np.clip((up / np.bincount(out.faces.ravel(), minlength=len(vv)) - 0.3) / 0.4, 0, 1)[:, None]
        for _ in range(6):                                     # diffuse the mask so pin-prick pit walls are included
            wz = np.maximum(wz, A @ wz / deg)
        for _ in range(CROWN_SMOOTH_IT):                       # upward-facing crown only
            vv += 0.5 * wz * (A @ vv / deg - vv)
        out = trimesh.Trimesh(vv, out.faces, process=False)
    import fast_simplification
    red = max(0.0, 1 - TARGET_FACES / len(out.faces))
    v2, f2 = fast_simplification.simplify(out.vertices.astype(np.float64), out.faces, target_reduction=red, agg=7)
    zl = v2[:, 2].min(); zb_ = np.median(v2[v2[:, 2] < zl + 0.05, 2]); v2[v2[:, 2] < zb_, 2] = zb_
    fin = trimesh.Trimesh(v2, f2, process=True)
    fin.apply_translation([-fin.bounds.mean(0)[0], -fin.bounds.mean(0)[1], -fin.bounds[0][2]])
    fin.apply_scale(H_MM / fin.extents[2])
    ok = fin.is_watertight and fin.is_volume and fin.euler_number == 2
    fin.export(OUT if ok else OUT.with_suffix(".FAILED.stl"))
    assert ok, f"not a closed genus-0 solid (euler {fin.euler_number})"
    log("final", len(fin.faces), "tris", fin.extents.round(2), "vol ml", round(fin.volume / 1000, 2), "->", OUT)


if __name__ == "__main__":
    main()
