"""Parametric moai (Rapa Nui statue): signed-distance model → watertight mesh.

No freely licensed (CC0 / CC-BY / CC-BY-SA) moai scan could be downloaded
without a login (see README), so the statue is modelled here from documented
moai proportions, in the style of the Rano Raraku quarry statues.

Modelling space: height-normalised units (statue height = 1), z up, the face
looks toward −y, x is left/right.  Every part is a signed distance field (SDF,
negative inside), combined with smooth unions/subtractions:

* torso and head: lofted rounded-rectangle columns whose width, depth and
  front/back planes vary with z (like build123d lofts of cross-sections);
* face: heavy brow ridge, deep eye shadows, a long nose swept along a concave
  profile with flared nostril wings, pursed lips with a mouth line, a
  projecting chin, long ears in relief;
* body: arms in relief down the sides, forearms wrapping to the front, long
  fingers meeting over the belly, nipples and navel; a flat base at z = 0.

The SDF is sampled on a grid and meshed with marching cubes (scikit-image),
which gives a closed, watertight surface; the result is scaled to the
requested height in mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import numpy as np

MM_PER_IN = 25.4
DEFAULT_HEIGHT_MM = 6 * MM_PER_IN  # 152.4 mm
ENDER2_BED_MM = (150.0, 150.0, 200.0)

# Landmark heights (fraction of statue height), calibrated against the
# owner's Rano Raraku photo and front/side reference photos.
Z_SHOULDER = 0.52
Z_CHIN = 0.555
Z_MOUTH = 0.615
Z_NOSE_TIP = 0.665
Z_EYE = 0.852
Z_BROW = 0.902
Z_TOP = 1.0


@dataclass(frozen=True)
class MoaiParams:
    height_mm: float = DEFAULT_HEIGHT_MM  # overall printed height (incl. plinth)
    plinth: bool = False
    plinth_height_mm: float = 6.0
    plinth_margin_mm: float = 4.0
    resolution: int = 300  # grid cells over the statue height


# ---- SDF helpers (numpy, vectorised) ----------------------------------------

def smin(a, b, k):
    """Polynomial smooth minimum (smooth union), blend radius k."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def ellipsoid(x, y, z, c, r):
    """Approximate SDF of an axis-aligned ellipsoid (good near the surface)."""
    px, py, pz = (x - c[0]) / r[0], (y - c[1]) / r[1], (z - c[2]) / r[2]
    k0 = np.sqrt(px * px + py * py + pz * pz)
    k1 = np.sqrt((px / r[0]) ** 2 + (py / r[1]) ** 2 + (pz / r[2]) ** 2)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def round_box(x, y, z, c, h, r):
    qx = np.abs(x - c[0]) - (h[0] - r)
    qy = np.abs(y - c[1]) - (h[1] - r)
    qz = np.abs(z - c[2]) - (h[2] - r)
    outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
    return outside + np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0.0) - r


def capsule(x, y, z, a, b, r):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ba = b - a
    px, py, pz = x - a[0], y - a[1], z - a[2]
    t = np.clip((px * ba[0] + py * ba[1] + pz * ba[2]) / ba.dot(ba), 0.0, 1.0)
    dx, dy, dz = px - t * ba[0], py - t * ba[1], pz - t * ba[2]
    return np.sqrt(dx * dx + dy * dy + dz * dz) - r


def tube(x, y, z, pts, radii, sx=1.0):
    """Union of capsules along a polyline with linearly varying radius.

    ``sx`` stretches the tube in x (sx > 1 = wider than deep)."""
    xs = x / sx
    d = np.full(x.shape, np.inf, dtype=x.dtype)
    for i in range(len(pts) - 1):
        a, b = np.array(pts[i], float), np.array(pts[i + 1], float)
        a[0] /= sx
        b[0] /= sx
        ba = b - a
        px, py, pz = xs - a[0], y - a[1], z - a[2]
        t = np.clip((px * ba[0] + py * ba[1] + pz * ba[2]) / ba.dot(ba), 0.0, 1.0)
        dx, dy, dz = px - t * ba[0], py - t * ba[1], pz - t * ba[2]
        r = radii[i] + t * (radii[i + 1] - radii[i])
        d = np.minimum(d, np.sqrt(dx * dx + dy * dy + dz * dz) - r)
    return d


def column(x, y, z, half_w, y_front, y_back, corner):
    """Lofted rounded-rectangle column: per-z half width, front/back planes
    and corner radius (arrays broadcast against z)."""
    cy = 0.5 * (y_front + y_back)
    hy = 0.5 * (y_back - y_front)
    qx = np.abs(x) - (half_w - corner)
    qy = np.abs(y - cy) - (hy - corner)
    return (np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
            + np.minimum(np.maximum(qx, qy), 0.0) - corner)


def interp(z, zs, vs):
    return np.interp(z, zs, vs).astype(z.dtype)


# ---- the statue ----------------------------------------------------------------

def torso_sdf(x, y, z):
    zs = [0.0, 0.10, 0.22, 0.35, 0.45, Z_SHOULDER, 0.60]
    hw = interp(z, zs, [0.154, 0.158, 0.161, 0.162, 0.162, 0.158, 0.14])
    yf = interp(z, zs, [-0.098, -0.108, -0.113, -0.104, -0.100, -0.090, -0.06])  # belly bulge
    yb = interp(z, zs, [0.105, 0.105, 0.102, 0.100, 0.100, 0.098, 0.09])
    d = column(x, y, z, hw, yf, yb, 0.045)
    # rounded shoulders (front view): an x–z ellipse above z0, a slab below
    z0, ax, az = 0.43, 0.168, Z_SHOULDER + 0.02 - 0.43
    zz = np.maximum(z - z0, 0.0)
    shoulder = np.sqrt((x / ax) ** 2 + (zz / az) ** 2) - 1.0
    return smax(d, shoulder * 0.12, 0.01)


def head_sdf(x, y, z):
    zs = [0.38, Z_CHIN, 0.62, 0.72, 0.86, 0.94, Z_TOP]
    hw = interp(z, zs, [0.115, 0.132, 0.140, 0.145, 0.148, 0.148, 0.143])
    yf = interp(z, zs, [-0.070, -0.098, -0.102, -0.104, -0.108, -0.095, -0.070])  # face plane, forehead slopes back
    yb = interp(z, zs, [0.100, 0.105, 0.112, 0.118, 0.120, 0.116, 0.105])
    d = column(x, y, z, hw, yf, yb, 0.035)
    # top of the head: flat, sloping down a little toward the brow, rounded edges
    top = z - (Z_TOP - 0.03 * np.clip(-(y + 0.02) / 0.09, 0.0, 1.0))
    d = smax(d, top, 0.025)
    return smax(d, 0.38 - z, 0.01)  # hidden inside the torso: no seam at the back


def face_sdf(d, x, y, z):
    # heavy brow ridge across the forehead
    brow = round_box(x, y, z, (0.0, -0.106, Z_BROW), (0.136, 0.026, 0.024), 0.02)
    d = smin(d, brow, 0.012)
    # deep eye shadows under the brow, either side of the nose
    for sx in (-1, 1):
        eye = ellipsoid(x, y, z, (sx * 0.068, -0.120, Z_EYE), (0.054, 0.040, 0.042))
        d = smax(d, -eye, 0.012)
    # long nose: concave bridge, swept from the brow to the flared tip
    s = np.linspace(0.0, 1.0, 12)
    nz = Z_BROW - 0.01 - s * (Z_BROW - 0.01 - (Z_NOSE_TIP + 0.012))
    ny = -0.112 - 0.056 * s ** 1.8  # concave (scooped) bridge, projecting tip
    nr = 0.016 + 0.017 * s ** 1.3
    nose = tube(x, y, z, list(zip(np.zeros_like(s), ny, nz)), nr, sx=1.45)
    d = smin(d, nose, 0.014)
    # nostril wings (alae) and the underside of the nose
    # flat underside of the nose running back to the upper lip
    base = ellipsoid(x, y, z, (0.0, -0.138, Z_NOSE_TIP - 0.002), (0.046, 0.030, 0.014))
    d = smin(d, base, 0.010)
    for sx in (-1, 1):
        wing = ellipsoid(x, y, z, (sx * 0.042, -0.150, Z_NOSE_TIP + 0.010), (0.028, 0.030, 0.026))
        d = smin(d, wing, 0.008)
        hole = ellipsoid(x, y, z, (sx * 0.022, -0.163, Z_NOSE_TIP - 0.006), (0.010, 0.014, 0.008))
        d = smax(d, -hole, 0.004)
    # long upper lip, pursed lips pushed forward, a thin mouth line
    upper = ellipsoid(x, y, z, (0.0, -0.114, 0.640), (0.074, 0.028, 0.034))
    d = smin(d, upper, 0.020)
    lips = ellipsoid(x, y, z, (0.0, -0.128, Z_MOUTH), (0.068, 0.025, 0.019))
    d = smin(d, lips, 0.012)
    mouth = ellipsoid(x, y, z, (0.0, -0.160, Z_MOUTH + 0.002), (0.060, 0.034, 0.0030))
    d = smax(d, -mouth, 0.002)
    # projecting chin over the chest
    chin = ellipsoid(x, y, z, (0.0, -0.112, Z_CHIN + 0.018), (0.086, 0.034, 0.028))
    d = smin(d, chin, 0.018)
    # long ears in relief on the sides of the head: a low plate with a raised
    # rim running down the back edge into an elongated lobe
    for sx in (-1, 1):
        plate = round_box(x, y, z, (sx * 0.142, 0.018, 0.790), (0.012, 0.030, 0.100), 0.012)
        d = smin(d, plate, 0.010)
        rim = tube(x, y, z, [
            (sx * 0.154, -0.004, 0.885), (sx * 0.154, 0.034, 0.870), (sx * 0.154, 0.042, 0.760),
            (sx * 0.154, 0.030, 0.690), (sx * 0.154, 0.008, 0.672), (sx * 0.154, -0.004, 0.700),
        ], [0.0065] * 6)
        d = smin(d, rim, 0.004)
    return d


def body_details(d, x, y, z):
    for sx in (-1, 1):
        # upper arm down the side, elbow, forearm wrapping round to the front
        arm = tube(x, y, z, [
            (sx * 0.156, 0.020, 0.455), (sx * 0.166, 0.015, 0.36), (sx * 0.168, 0.005, 0.25),
            (sx * 0.150, -0.070, 0.195), (sx * 0.105, -0.110, 0.170), (sx * 0.060, -0.117, 0.160),
        ], [0.026, 0.024, 0.022, 0.020, 0.019, 0.018])
        d = smin(d, arm, 0.010)
        # long fingers pointing at the centre, meeting over the belly
        for k, dz in enumerate((-0.022, -0.008, 0.006, 0.020)):
            f = capsule(x, y, z, (sx * 0.070, -0.118, 0.162 + dz * 0.8),
                        (sx * 0.012, -0.114, 0.150 + dz), 0.0062)
            d = smin(d, f, 0.003)
        nipple = ellipsoid(x, y, z, (sx * 0.075, -0.104, 0.405), (0.012, 0.010, 0.012))
        d = smin(d, nipple, 0.004)
    navel = ellipsoid(x, y, z, (0.0, -0.118, 0.230), (0.010, 0.008, 0.010))
    return smin(d, navel, 0.003)


def moai_sdf(x, y, z):
    d = smin(torso_sdf(x, y, z), head_sdf(x, y, z), 0.02)
    d = face_sdf(d, x, y, z)
    d = body_details(d, x, y, z)
    return np.maximum(d, -z)  # flat base at z = 0


BOUNDS = ((-0.21, 0.21), (-0.22, 0.14), (-0.01, 1.01))  # normalised x, y, z


def statue_mesh(resolution: int = 300) -> Tuple[np.ndarray, np.ndarray]:
    """Watertight mesh of the statue, height-normalised (z 0 → 1)."""
    from skimage.measure import marching_cubes

    h = 1.0 / resolution
    # offset by h/3 so the flat base (z = 0) never lies exactly on a grid plane
    axes = [np.arange(lo, hi + h, h, dtype=np.float32) + np.float32(h / 3) for lo, hi in BOUNDS]
    X, Y, Z = np.meshgrid(*axes, indexing="ij")
    vol = moai_sdf(X, Y, Z)
    vol[np.abs(vol) < 1e-7] = 1e-7  # no exact zeros: they give coincident vertices
    pad = np.pad(vol, 1, constant_values=1.0)  # guarantees a closed surface
    v, f, _, _ = marching_cubes(pad, level=0.0, spacing=(h, h, h))
    v = v + np.array([b[0] for b in BOUNDS]) + h / 3 - h
    return v.astype(np.float64), f.astype(np.int64)


def build(p: MoaiParams) -> Tuple[np.ndarray, np.ndarray]:
    """Mesh in mm, standing on z = 0, centred in x/y."""
    v, f = statue_mesh(p.resolution)
    sink = 0.5  # statue sinks this far into the plinth (no coplanar faces)
    statue_h = p.height_mm - ((p.plinth_height_mm - sink) if p.plinth else 0.0)
    v = v * (statue_h / (v[:, 2].max() - v[:, 2].min()))
    v[:, 2] -= v[:, 2].min()
    cx, cy = (v[:, 0].max() + v[:, 0].min()) / 2, (v[:, 1].max() + v[:, 1].min()) / 2
    v[:, 0] -= cx
    v[:, 1] -= cy
    if not p.plinth:
        return v, f
    import manifold3d as mf

    from boolean_mesh import _to_manifold

    st = _to_manifold(v + np.array([0, 0, p.plinth_height_mm - sink]), f)
    lo, hi = v[:, :2].min(0) - p.plinth_margin_mm, v[:, :2].max(0) + p.plinth_margin_mm
    box = mf.Manifold.cube((hi[0] - lo[0], hi[1] - lo[1], p.plinth_height_mm)).translate((lo[0], lo[1], 0.0))
    m = (st + box).to_mesh64()
    return np.asarray(m.vert_properties)[:, :3].astype(float), np.asarray(m.tri_verts).astype(np.int64)


def stl_bytes(v: np.ndarray, f: np.ndarray) -> bytes:
    import trimesh

    return trimesh.Trimesh(v, f, process=False).export(file_type="stl")


def fits_bed(v: np.ndarray, bed=ENDER2_BED_MM) -> bool:
    ext = v.max(0) - v.min(0)
    return all(e <= b for e, b in zip(ext, bed))
