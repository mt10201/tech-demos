"""Analytic mesh of the grooved torus (preview + STL), widths in true 3D.

Method
------
1. Each groove centre-line is traced **on the torus surface** and sampled as a
   3D polyline (spacing ≈ width/4).
2. The torus is meshed on a periodic (θ, φ) grid.  For every surface vertex P
   a KD-tree finds the nearby polyline vertices; for each candidate the two
   adjacent **segments** are checked, giving the exact 3D distance ``t`` from P
   to the nearest centre-line (nearest-segment search, round ends for open
   grooves).
3. The vertex is pushed in along its surface normal by the groove profile
   ``profile_depth(t)`` (U-groove / semicircle / shallow arc, see geometry.py);
   where grooves cross, the deepest cut wins.

Because ``t`` is a true 3D distance, the groove is the same width on the rim,
the top, the hole and the bottom — it no longer scales with R + r·cos θ.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from geometry import TorusParams, all_paths, profile_depth, validate

PREVIEW_GRID = (180, 720)  # live sliders (~259k triangles)
EXPORT_GRID = (400, 1600)  # STL download (1.28 M triangles)


class GrooveField:
    """Groove depth at arbitrary points on the torus surface."""

    def __init__(self, p: TorusParams, paths: list[np.ndarray] | None = None):
        validate(p)
        self.p = p
        if paths is None:
            # ~width/4 spacing along the longest groove
            n = int(max(400, 14.0 * p.major_radius * 4.0 / p.groove_width))
            paths = all_paths(p, n, radius=p.tube_radius)
        self.paths = paths
        self.pts = np.vstack(paths)
        gid = np.concatenate([np.full(len(q), g) for g, q in enumerate(paths)])
        start = np.cumsum([0] + [len(q) for q in paths])[:-1]
        self.first = start[gid]
        self.last = self.first + np.array([len(q) for q in paths])[gid] - 1
        self.tree = cKDTree(self.pts)
        seg = np.diff(self.pts, axis=0)
        self.max_seg = float(np.max(np.linalg.norm(seg, axis=1)[
            np.diff(gid) == 0])) if len(self.pts) > 1 else 0.0

    def distance(self, P: np.ndarray, k: int = 16) -> np.ndarray:
        """True 3D distance from each point to the nearest groove centre-line."""
        half_w = self.p.groove_width / 2.0
        bound = half_w + self.max_seg
        _, idxs = self.tree.query(P, k=k, distance_upper_bound=bound)
        best = np.full(len(P), np.inf)
        npts = len(self.pts)
        for col in range(idxs.shape[1]):
            idx = idxs[:, col]
            ok = idx < npts
            if not ok.any():
                continue
            rows = np.nonzero(ok)[0]
            j = idx[ok]
            Pj = P[rows]
            for nb in (-1, 1):
                jn = j + nb
                valid = (jn >= self.first[j]) & (jn <= self.last[j])
                jn = np.where(valid, jn, j)
                a, b = self.pts[j], self.pts[jn]
                ab = b - a
                L2 = np.einsum("ij,ij->i", ab, ab)
                u = np.where(L2 > 0, np.einsum("ij,ij->i", Pj - a, ab) / np.where(L2 > 0, L2, 1), 0)
                u = np.clip(u, 0.0, 1.0)
                c = a + u[:, None] * ab
                d = np.linalg.norm(Pj - c, axis=1)
                best[rows] = np.minimum(best[rows], d)
        return best

    def depth(self, P: np.ndarray) -> np.ndarray:
        t = self.distance(P)
        return np.where(np.isfinite(t), profile_depth(self.p, np.where(np.isfinite(t), t, 1e9)), 0.0)


def torus_frame(p: TorusParams, n_theta: int, n_phi: int):
    th = np.linspace(0.0, 2.0 * math.pi, n_theta, endpoint=False)
    ph = np.linspace(0.0, 2.0 * math.pi, n_phi, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    nrm = np.stack([np.cos(TH) * np.cos(PH), np.cos(TH) * np.sin(PH), np.sin(TH)], -1).reshape(-1, 3)
    ctr = np.stack([p.major_radius * np.cos(PH), p.major_radius * np.sin(PH),
                    np.zeros_like(PH)], -1).reshape(-1, 3)
    return ctr, nrm


def grid_faces(n_theta: int, n_phi: int) -> np.ndarray:
    i = np.arange(n_theta)[:, None]
    j = np.arange(n_phi)[None, :]
    a = i * n_phi + j
    b = ((i + 1) % n_theta) * n_phi + j
    c = ((i + 1) % n_theta) * n_phi + (j + 1) % n_phi
    d = i * n_phi + (j + 1) % n_phi
    return np.concatenate(
        [np.stack([a, d, c], -1).reshape(-1, 3), np.stack([a, c, b], -1).reshape(-1, 3)]
    )


def grooved_torus_mesh(
    p: TorusParams,
    n_theta: int = PREVIEW_GRID[0],
    n_phi: int = PREVIEW_GRID[1],
    return_depth: bool = False,
    field: GrooveField | None = None,
):
    """Return (vertices, faces[, depth]) of the closed, watertight grooved torus."""
    field = field or GrooveField(p)
    ctr, nrm = torus_frame(p, n_theta, n_phi)
    surf = ctr + p.tube_radius * nrm
    dep = field.depth(surf)
    verts = ctr + (p.tube_radius - dep)[:, None] * nrm
    faces = grid_faces(n_theta, n_phi)
    if return_depth:
        return verts, faces, dep
    return verts, faces


# ---- measurement helpers (tests / README) ---------------------------------

def surface_point(p: TorusParams, X: np.ndarray) -> np.ndarray:
    """Closest point on the plain torus surface to X."""
    X = np.atleast_2d(X)
    phi = np.arctan2(X[:, 1], X[:, 0])
    c = np.column_stack([p.major_radius * np.cos(phi), p.major_radius * np.sin(phi), np.zeros(len(X))])
    v = X - c
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return c + p.tube_radius * v


def measure_width(p: TorusParams, groove_pts: np.ndarray, j: int, field: GrooveField) -> float:
    """3D width of a groove across its centre-line at sample ``j``.

    Walk along the surface perpendicular to the groove (tangent-plane binormal,
    re-projected onto the torus) until the depth falls to zero on each side;
    return the 3D chord between the two edges.
    """
    S = groove_pts[j]
    T = groove_pts[j + 1] - groove_pts[j - 1]
    T /= np.linalg.norm(T)
    phi = math.atan2(S[1], S[0])
    c = np.array([p.major_radius * math.cos(phi), p.major_radius * math.sin(phi), 0.0])
    N = (S - c) / np.linalg.norm(S - c)
    B = np.cross(N, T)
    edges = []
    for sgn in (1, -1):
        lo, hi = 0.0, p.groove_width  # depth>0 at lo, 0 at hi
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            X = surface_point(p, S + sgn * mid * B)
            if field.depth(X)[0] > 1e-9:
                lo = mid
            else:
                hi = mid
        edges.append(surface_point(p, S + sgn * lo * B)[0])
    return float(np.linalg.norm(edges[0] - edges[1]))


def mesh_volume(verts: np.ndarray, faces: np.ndarray) -> float:
    v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def stl_bytes(verts: np.ndarray, faces: np.ndarray, scale: float = 25.4) -> bytes:
    """Binary STL. Geometry is in inches; ``scale`` = 25.4 writes **millimetres**
    (STL has no unit field and slicers assume mm)."""
    import trimesh

    m = trimesh.Trimesh(vertices=np.asarray(verts, float) * scale, faces=faces, process=False)
    return m.export(file_type="stl")


def write_stl(p: TorusParams, path: Path, **kw) -> Path:
    v, f = grooved_torus_mesh(p, **kw)
    Path(path).write_bytes(stl_bytes(v, f))
    return Path(path)


def patch_mesh(
    p: TorusParams, theta_c: float, phi_c: float, half: float = 0.3, n: int = 160,
    field: GrooveField | None = None,
):
    """High-res local patch (± ``half`` inches of surface) around (θ_c, φ_c).

    Returns (verts, faces, depth, centre, normal).  Used for the rim-vs-hole
    close-up, so both patches are rendered at the same physical scale.
    """
    field = field or GrooveField(p)
    q = p.major_radius + p.tube_radius * math.cos(theta_c)
    th = theta_c + np.linspace(-half, half, n) / p.tube_radius
    ph = phi_c + np.linspace(-half, half, n) / q
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    nrm = np.stack([np.cos(TH) * np.cos(PH), np.cos(TH) * np.sin(PH), np.sin(TH)], -1).reshape(-1, 3)
    ctr = np.stack([p.major_radius * np.cos(PH), p.major_radius * np.sin(PH),
                    np.zeros_like(PH)], -1).reshape(-1, 3)
    dep = field.depth(ctr + p.tube_radius * nrm)
    verts = ctr + (p.tube_radius - dep)[:, None] * nrm
    i = np.arange(n - 1)[:, None]
    j = np.arange(n - 1)[None, :]
    a, b, c, d = i * n + j, (i + 1) * n + j, (i + 1) * n + j + 1, i * n + j + 1
    faces = np.concatenate([np.stack([a, d, c], -1).reshape(-1, 3),
                            np.stack([a, c, b], -1).reshape(-1, 3)])
    nc = np.array([math.cos(theta_c) * math.cos(phi_c), math.cos(theta_c) * math.sin(phi_c),
                   math.sin(theta_c)])
    cc = np.array([p.major_radius * math.cos(phi_c), p.major_radius * math.sin(phi_c), 0.0])
    return verts, faces, dep, cc + p.tube_radius * nc, nc


def cross_profile(p: TorusParams, groove_pts: np.ndarray, j: int, field: GrooveField,
                  half: float | None = None, n: int = 201):
    """Depth across the groove at sample j vs true 3D lateral offset (for plots)."""
    half = half or 1.2 * p.groove_width
    S = groove_pts[j]
    T = groove_pts[j + 1] - groove_pts[j - 1]
    T /= np.linalg.norm(T)
    phi = math.atan2(S[1], S[0])
    c = np.array([p.major_radius * math.cos(phi), p.major_radius * math.sin(phi), 0.0])
    N = (S - c) / np.linalg.norm(S - c)
    B = np.cross(N, T)
    s = np.linspace(-half, half, n)
    X = surface_point(p, S[None, :] + s[:, None] * B[None, :])
    return s, field.depth(X)
