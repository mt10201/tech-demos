"""Fast analytic mesh of the grooved torus (preview + STL).

The torus is meshed on a periodic (θ, φ) grid.  Every vertex sits on the ray
from the tube centre through the torus surface; where that ray passes through a
groove cutter (a circular tube of radius ``cutter_r`` swept along the groove
axis) the vertex is pushed inward to the cutter wall:

    λ(θ, φ) = min(r, smallest root of |c + λn − A|² = cutter_r²)

where ``A`` runs over the nearest densely-sampled groove-axis points.  This
gives a watertight, exactly semicircular groove in seconds, so the sliders stay
interactive.  The build123d B-rep (``rodin_torus.py``) is the source for STEP.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Tuple

import numpy as np
from scipy.spatial import cKDTree

from geometry import TorusParams, all_paths, cutter_radius, path_radius, validate


def grooved_torus_mesh(
    p: TorusParams, n_theta: int = 160, n_phi: int = 640, path_samples: int = 1500
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (vertices (N,3), faces (M,3)) of the closed grooved torus."""
    validate(p)
    R, r = p.major_radius, p.tube_radius
    rho = cutter_radius(p)
    rp = path_radius(p)

    th = np.linspace(0.0, 2.0 * math.pi, n_theta, endpoint=False)
    ph = np.linspace(0.0, 2.0 * math.pi, n_phi, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")  # (n_theta, n_phi)
    nrm = np.stack(
        [np.cos(TH) * np.cos(PH), np.cos(TH) * np.sin(PH), np.sin(TH)], axis=-1
    )
    ctr = np.stack([R * np.cos(PH), R * np.sin(PH), np.zeros_like(PH)], axis=-1)

    axis_pts = np.vstack(all_paths(p, path_samples))
    tree = cKDTree(axis_pts)
    Q = (ctr + rp * nrm).reshape(-1, 3)
    n_flat = nrm.reshape(-1, 3)
    lam = np.full(Q.shape[0], r)
    # Check a few nearest axis samples per ray; the exact cutter wall is the
    # smallest λ with |c + λ n − A|² = cutter_r²  (u = λ − ρ_axis):
    #     u² + 2u (d·n) + |d|² − cutter_r² = 0,   d = Q − A
    _, idxs = tree.query(Q, k=6, distance_upper_bound=2.0 * rho)
    for col in range(idxs.shape[1]):
        idx = idxs[:, col]
        ok = idx < len(axis_pts)
        if not ok.any():
            continue
        diff = Q[ok] - axis_pts[idx[ok]]
        radial = np.einsum("ij,ij->i", diff, n_flat[ok])
        disc = radial**2 - np.einsum("ij,ij->i", diff, diff) + rho * rho
        hit = disc > 0
        cand = np.full(ok.sum(), r)
        cand[hit] = rp - radial[hit] - np.sqrt(disc[hit])
        sub = lam[ok]
        lam[ok] = np.minimum(sub, np.minimum(cand, r))
    lam = np.maximum(lam, 0.0)

    verts = ctr.reshape(-1, 3) + lam[:, None] * n_flat

    i = np.arange(n_theta)[:, None]
    j = np.arange(n_phi)[None, :]
    a = i * n_phi + j
    b = ((i + 1) % n_theta) * n_phi + j
    c = ((i + 1) % n_theta) * n_phi + (j + 1) % n_phi
    d = i * n_phi + (j + 1) % n_phi
    faces = np.concatenate(
        [np.stack([a, d, c], -1).reshape(-1, 3), np.stack([a, c, b], -1).reshape(-1, 3)]
    )
    return verts, faces


def mesh_volume(verts: np.ndarray, faces: np.ndarray) -> float:
    v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def stl_bytes(verts: np.ndarray, faces: np.ndarray) -> bytes:
    import trimesh

    m = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    return m.export(file_type="stl")


def write_stl(p: TorusParams, path: Path, **kw) -> Path:
    v, f = grooved_torus_mesh(p, **kw)
    Path(path).write_bytes(stl_bytes(v, f))
    return Path(path)
