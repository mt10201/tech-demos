"""Printable STL via a real mesh boolean (manifold3d).

1. Each groove's centre-line is traced on the torus surface (3D polyline,
   ``ds`` ≈ 0.02") and grooves that join end-to-start are chained into closed
   loops (the photo preset forms 4 seamless loops; open grooves get end caps).
2. The U-profile (semicircular bottom of radius w/2 + straight walls that rise
   ``CLEARANCE`` above the surface) is swept along each chain in a frame whose
   "up" axis is the exact torus normal, giving smooth watertight cutter tubes.
3. ``torus − ∪ cutters`` is computed with manifold3d's batch boolean, which is
   guaranteed to return a manifold (watertight, consistently oriented) mesh.

Chord error budget (all < 0.002"): profile arc 12 segments (≈0.0005" at
ρ = 1/16"), path step 0.04" (≈0.0004"), torus facets ≤ 0.001".
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np

from geometry import TorusParams, all_paths, cutter_radius, validate

CLEARANCE = 0.03  # U walls extend this far above the torus surface (in)
CHORD = 0.001  # torus facet chord error (in)
DS = 0.04  # path step (in): sagitta ≈ ds²·κ/8 ≈ 0.0004" for κ ≈ 2/in
N_ARC = 12  # profile arc segments: sagitta = ρ(1−cos(7.5°)) ≈ 0.0005" at ρ = 1/16"


def _segments_for(radius: float, chord: float) -> int:
    """Segments so a circle of ``radius`` has sagitta ≤ ``chord``."""
    return max(8, int(math.ceil(math.pi / math.acos(max(-1.0, 1.0 - chord / radius)))))


def torus_grid(p: TorusParams, chord: float = 0.001) -> Tuple[np.ndarray, np.ndarray]:
    """Plain torus, tessellated so facets deviate < ``chord`` from the surface."""
    n_t = _segments_for(p.tube_radius, chord)
    n_p = _segments_for(p.major_radius + p.tube_radius, chord)
    th = np.linspace(0, 2 * math.pi, n_t, endpoint=False)
    ph = np.linspace(0, 2 * math.pi, n_p, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    q = p.major_radius + p.tube_radius * np.cos(TH)
    v = np.stack([q * np.cos(PH), q * np.sin(PH), p.tube_radius * np.sin(TH)], -1).reshape(-1, 3)
    i = np.arange(n_t)[:, None]
    j = np.arange(n_p)[None, :]
    a = i * n_p + j
    b = ((i + 1) % n_t) * n_p + j
    c = ((i + 1) % n_t) * n_p + (j + 1) % n_p
    d = i * n_p + (j + 1) % n_p
    f = np.concatenate([np.stack([a, d, c], -1).reshape(-1, 3), np.stack([a, c, b], -1).reshape(-1, 3)])
    return v, f


def u_profile(p: TorusParams, n_arc: int = N_ARC, clearance: float = CLEARANCE) -> np.ndarray:
    """Closed CCW polygon (b, n) of the groove cutter cross-section.

    b = lateral offset, n = height along the surface normal (0 = surface).
    Semicircle / U bottom of radius ρ centred at n = −(d − ρ); walls straight
    up to +clearance.  For a shallow arc (d < w/2) the arc is clipped by the
    walls automatically.
    """
    rho = cutter_radius(p)
    cn = -(p.groove_depth - rho)  # circle centre height
    half = p.groove_width / 2.0
    if rho <= half + 1e-12:  # U or semicircle
        a = np.linspace(math.pi, 2 * math.pi, n_arc + 1)
        arc = np.column_stack([rho * np.cos(a), cn + rho * np.sin(a)])
    else:  # shallow arc spanning ±half
        a0 = math.asin(half / rho)
        a = np.linspace(-math.pi / 2 - a0, -math.pi / 2 + a0, n_arc + 1)
        arc = np.column_stack([rho * np.cos(a), cn + rho * np.sin(a)])
    top = np.array([[half, clearance], [-half, clearance]])
    return np.vstack([arc, top])  # arc goes −b → +b underneath, then back on top


def chain_paths(paths: List[np.ndarray], tol: float = 1e-6) -> List[Tuple[np.ndarray, bool]]:
    """Join grooves whose end meets another's start. Returns (points, closed)."""
    n = len(paths)
    nxt, prv = {}, {}
    for i in range(n):
        for j in range(n):
            if i != j and j not in prv and np.linalg.norm(paths[i][-1] - paths[j][0]) < tol:
                nxt[i], prv[j] = j, i
                break
    used, out = set(), []
    starts = [i for i in range(n) if i not in prv] + list(range(n))
    for s in starts:
        if s in used:
            continue
        chain, cur = [], s
        while cur is not None and cur not in used:
            used.add(cur)
            chain.append(cur)
            cur = nxt.get(cur)
        closed = cur == s
        P = np.vstack([paths[chain[0]]] + [paths[k][1:] for k in chain[1:]])
        if closed:
            P = P[:-1]  # last point == first
        out.append((P, closed))
    return out


def sweep_tube(p: TorusParams, P: np.ndarray, closed: bool, prof: np.ndarray):
    """Sweep ``prof`` along polyline P with the torus normal as the up axis."""
    m = len(P)
    if closed:
        T = np.roll(P, -1, 0) - np.roll(P, 1, 0)
    else:
        T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    phi = np.arctan2(P[:, 1], P[:, 0])
    C = np.column_stack([p.major_radius * np.cos(phi), p.major_radius * np.sin(phi), np.zeros(m)])
    N = P - C
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    B = np.cross(T, N)
    B /= np.linalg.norm(B, axis=1, keepdims=True)
    N = np.cross(B, T)
    k = len(prof)
    V = (P[:, None, :] + prof[None, :, 0:1] * B[:, None, :] + prof[None, :, 1:2] * N[:, None, :]).reshape(-1, 3)
    rings = m if closed else m - 1
    i = np.arange(rings)[:, None]
    j = np.arange(k)[None, :]
    a = i * k + j
    b = i * k + (j + 1) % k
    c = ((i + 1) % m) * k + (j + 1) % k
    d = ((i + 1) % m) * k + j
    F = np.concatenate([np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)])
    if not closed:  # convex profile → fan caps
        c0 = len(V)
        c1 = c0 + 1
        V = np.vstack([V, P[0] + 0 * P[0], P[-1]])
        # cap centres at the profile centroid
        cen = prof.mean(axis=0)
        V[c0] = P[0] + cen[0] * B[0] + cen[1] * N[0]
        V[c1] = P[-1] + cen[0] * B[-1] + cen[1] * N[-1]
        jj = np.arange(k)
        F0 = np.column_stack([np.full(k, c0), (jj + 1) % k, jj])
        last = (m - 1) * k
        F1 = np.column_stack([np.full(k, c1), last + jj, last + (jj + 1) % k])
        F = np.vstack([F, F0, F1])
    # orient outward
    v0, v1, v2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    if np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() < 0:
        F = F[:, ::-1]
    return V, F


def _to_manifold(V: np.ndarray, F: np.ndarray):
    import manifold3d as mf

    # float64 (Mesh64): float32 left ~1.5k zero-area slivers / coincident
    # vertices that became non-manifold edges once a slicer merged vertices.
    return mf.Manifold(mf.Mesh64(vert_properties=np.ascontiguousarray(V, dtype=np.float64),
                                 tri_verts=np.ascontiguousarray(F, dtype=np.uint64)))


def groove_tubes(p: TorusParams, ds: float = DS, n_arc: int = N_ARC):
    """Cutter meshes [(V, F)], one per chain of grooves."""
    validate(p)
    probe = all_paths(p, 2001, radius=p.tube_radius)[0]
    length = float(np.linalg.norm(np.diff(probe, axis=0), axis=1).sum())
    n = int(max(100, math.ceil(length / ds))) + 1
    paths = all_paths(p, n, radius=p.tube_radius)
    prof = u_profile(p, n_arc)
    return [sweep_tube(p, P, closed, prof) for P, closed in chain_paths(paths)]


def grooved_solid(p: TorusParams, chord: float = CHORD, ds: float = DS, n_arc: int = N_ARC):
    """Return (verts, faces) of torus − grooves via manifold3d (watertight)."""
    import manifold3d as mf

    tv, tf = torus_grid(p, chord)
    torus = _to_manifold(tv, tf)
    cutters = [_to_manifold(V, F) for V, F in groove_tubes(p, ds, n_arc)]
    for c in cutters:
        if c.status() != mf.Error.NoError:
            raise RuntimeError(f"cutter not manifold: {c.status()}")
    tool = mf.Manifold.batch_boolean(cutters, mf.OpType.Add)
    res = torus - tool
    if res.status() != mf.Error.NoError:
        raise RuntimeError(f"boolean failed: {res.status()}")
    mesh = res.to_mesh64()
    return np.asarray(mesh.vert_properties)[:, :3].astype(np.float64), np.asarray(mesh.tri_verts).astype(np.int64)


PREVIEW_KW = dict(chord=0.002, ds=0.05, n_arc=8)  # ~130k triangles, < 1 s
EXPORT_KW = dict(chord=CHORD / 2, ds=DS / 2, n_arc=2 * N_ARC)  # ~680k triangles, ~34 MB (cubit size)


def vertex_depth(p: TorusParams, V: np.ndarray) -> np.ndarray:
    """Depth of each vertex below the plain torus surface (0 on tiles)."""
    phi = np.arctan2(V[:, 1], V[:, 0])
    C = np.column_stack([p.major_radius * np.cos(phi), p.major_radius * np.sin(phi), np.zeros(len(V))])
    return np.clip(p.tube_radius - np.linalg.norm(V - C, axis=1), 0.0, None)


def section_width(p: TorusParams, V: np.ndarray, F: np.ndarray, S: np.ndarray, T: np.ndarray,
                  min_depth: float = 0.002) -> Tuple[float, float]:
    """Measure the groove on the *actual mesh*: slice it with the plane through
    S perpendicular to the groove tangent T, keep section points within 0.2"
    of S that lie ≥ ``min_depth`` below the torus surface, and return
    (width across the walls, max depth)."""
    import trimesh

    m = trimesh.Trimesh(vertices=V, faces=F, process=False)
    sec = m.section(plane_origin=S, plane_normal=T)
    pts = np.asarray(sec.vertices)
    near = np.linalg.norm(pts - S, axis=1) < 0.2
    pts = pts[near]
    dep = vertex_depth(p, pts)
    phi = math.atan2(S[1], S[0])
    c = np.array([p.major_radius * math.cos(phi), p.major_radius * math.sin(phi), 0.0])
    N = (S - c) / np.linalg.norm(S - c)
    B = np.cross(T, N)
    B /= np.linalg.norm(B)
    lat = (pts - S) @ B
    # only this groove's notch: stay inside 0.75 × width laterally so a
    # crossing groove of the other family isn't included
    sel = (dep > min_depth) & (np.abs(lat) < 0.75 * p.groove_width)
    return float(lat[sel].max() - lat[sel].min()), float(dep.max())


def drop_degenerate(V: np.ndarray, F: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Faces without zero-area slivers (manifold keeps a few; they break
    Plotly's lighting). For display only. The STL keeps the exact manifold mesh."""
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    return F[np.einsum("ij,ij->i", n, n) > eps * eps]


def display_mesh(V: np.ndarray, F: np.ndarray, crease_deg: float = 35.0):
    """Mesh for Plotly smooth shading: degenerate slivers dropped and vertices
    split along sharp creases (groove lips, wall/floor edges), so normals are
    averaged only across the curved surfaces. Display only; the STL is untouched."""
    import trimesh

    m = trimesh.Trimesh(V, drop_degenerate(V, F), process=True)
    s = trimesh.graph.smooth_shade(m, angle=math.radians(crease_deg))
    return np.asarray(s.vertices, float), np.asarray(s.faces, np.int64)


def crop_solid(V: np.ndarray, F: np.ndarray, centre, radius: float, segments: int = 96):
    """Clean close-up sample: boolean intersection of the solid with a ball.
    Gives a tidy round cut instead of ragged triangle-centroid cropping."""
    import manifold3d as mf

    ball = mf.Manifold.sphere(radius, segments).translate(tuple(float(c) for c in centre))
    m = (_to_manifold(V, F) ^ ball).to_mesh64()
    return np.asarray(m.vert_properties[:, :3], float), np.asarray(m.tri_verts, np.int64)
