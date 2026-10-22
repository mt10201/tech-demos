"""Turn any photo-to-3D / scan mesh into a printable silicone-mold master (mm).

The output of AI image-to-3D tools (TRELLIS, Hunyuan3D, UniForge3D, Meshy, ...) and of phone scans is
usually *not* printable as a mold master: holes, flipped or duplicated faces, floating debris, internal
bubbles, self-intersections, thin slots that form tunnels, an open or ragged bottom and arbitrary units.
`scan_to_master` runs the same volumetric pass used for the Moai head scan (scripts/build_moai_head_scan.py):

  orient (+Z up) -> scale to a target height (mm) -> patch large open boundary loops (fan fill)
  -> sample the surface on a voxel grid -> morphological closing (dilate, fill, erode: closes gaps
  narrower than ~2 x close_mm) -> flat base (cut base_cut_mm off the bottom) -> keep the largest
  piece, fill internal cavities, plug tunnels (genus 0: one continuous master, no holes or tunnels)
  -> marching cubes -> optional decimation (manifold3d) -> checks: watertight single shell, Euler 2,
  fits the Ender 2 bed.

No torch / GPU: numpy, scipy, scikit-image, trimesh and manifold3d (all already app requirements).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import trimesh
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

ENDER2_BED_MM = (150.0, 150.0, 200.0)
AXES = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}


@dataclass
class RepairReport:
    input_faces: int = 0
    input_watertight: bool = False
    input_pieces: int = 0
    input_boundary_loops: int = 0
    patched_loops: int = 0
    pieces_dropped: int = 0
    cavity_voxels_filled: int = 0
    tunnel_voxels_plugged: int = 0
    faces: int = 0
    watertight: bool = False
    is_volume: bool = False
    euler: int = 0
    extents_mm: tuple = ()
    volume_cm3: float = 0.0
    fits_bed: bool = False
    seconds: float = 0.0
    log: list = field(default_factory=list)

    def ok(self) -> bool:
        return self.watertight and self.is_volume and self.euler == 2


def load_mesh(path: str) -> trimesh.Trimesh:
    """Any trimesh-readable mesh (stl/obj/ply/glb/gltf/off), textures ignored, scene flattened."""
    m = trimesh.load(path, force="mesh", skip_materials=True, process=False)
    return trimesh.Trimesh(m.vertices, m.faces, process=False)


def default_up(path: str) -> str:
    """glTF is +Y up by spec; STL/OBJ/PLY from most tools are +Z up (pass --up to override)."""
    return "+y" if str(path).lower().endswith((".glb", ".gltf")) else "+z"


def _clean(m: trimesh.Trimesh) -> trimesh.Trimesh:
    m = trimesh.Trimesh(m.vertices, m.faces, process=False)
    m.merge_vertices(merge_tex=True, merge_norm=True)
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    return m


def boundary_loops(m: trimesh.Trimesh) -> list[np.ndarray]:
    """Closed loops of boundary edges (edges used by exactly one face), as vertex index arrays.
    Undirected walk, so flipped faces next to a hole don't break the loop."""
    e = np.sort(m.edges, axis=1)
    u, cnt = np.unique(e, axis=0, return_counts=True)
    b = u[cnt == 1]
    adj: dict[int, list[int]] = {}
    for a, c in b:
        adj.setdefault(int(a), []).append(int(c))
        adj.setdefault(int(c), []).append(int(a))
    loops, used = [], set()
    for start in adj:
        for first in adj[start]:
            if (min(start, first), max(start, first)) in used:
                continue
            loop, prev, v = [start], start, first
            used.add((min(start, first), max(start, first)))
            while v != start:
                loop.append(v)
                nx = [w for w in adj[v] if (min(v, w), max(v, w)) not in used]
                if not nx:
                    break
                prev, v = v, nx[0]
                used.add((min(prev, v), max(prev, v)))
            if v == start and len(loop) >= 3:
                loops.append(np.array(loop))
    return loops


def patch_holes(m: trimesh.Trimesh, max_loop_mm: float) -> tuple[trimesh.Trimesh, int]:
    """Fan-fill boundary loops up to max_loop_mm perimeter (centroid fan). Orientation is irrelevant here:
    the result is only used as a point cloud for the volumetric pass."""
    loops = boundary_loops(m)
    V = [m.vertices]; F = [m.faces]; n = len(m.vertices); k = 0
    for lp in loops:
        p = m.vertices[lp]
        if np.linalg.norm(np.diff(np.vstack([p, p[:1]]), axis=0), axis=1).sum() > max_loop_mm:
            continue
        V.append(p.mean(0)[None]); c = n; n += 1
        F.append(np.column_stack([lp, np.roll(lp, -1), np.full(len(lp), c)]))
        k += 1
    return trimesh.Trimesh(np.vstack(V), np.vstack(F), process=False), k


def _orient_scale(m: trimesh.Trimesh, up: str, height_mm: float, base_cut_mm: float) -> trimesh.Trimesh:
    up_v = np.array(AXES[up] if isinstance(up, str) else up, float)
    m = m.copy()
    m.apply_transform(trimesh.geometry.align_vectors(up_v, [0, 0, 1]))
    ext = m.extents[2]
    if ext <= 0:
        raise ValueError("mesh has no height along the chosen up axis")
    m.apply_scale((height_mm + base_cut_mm) / ext)
    b = m.bounds
    m.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2] - base_cut_mm])
    return m


def _decimate(mesh: trimesh.Trimesh, tol_mm: float) -> trimesh.Trimesh:
    import manifold3d as mf
    man = mf.Manifold(mf.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                              tri_verts=np.asarray(mesh.faces, np.uint32)))
    if man.status() != mf.Error.NoError:
        return mesh
    out = man.simplify(tol_mm).to_mesh()
    r = trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts), process=True)
    return r if (r.is_watertight and r.euler_number == mesh.euler_number) else mesh


def scan_to_master(mesh: trimesh.Trimesh, height_mm: float = 120.0, up: str = "+z", base_cut_mm: float = 2.0,
                   voxel_mm: float = 0.4, close_mm: float = 0.8, patch_loops_mm: float = 400.0,
                   simplify_mm: float = 0.05, log=None) -> tuple[trimesh.Trimesh, RepairReport]:
    """Return (master mesh in mm, base on z = 0, centred in XY; report). height_mm is the final height
    after base_cut_mm has been cut flat off the bottom."""
    t0 = time.time()
    rep = RepairReport()

    def say(*a):
        s = f"[{time.time() - t0:5.1f}s] " + " ".join(str(x) for x in a)
        rep.log.append(s)
        if log:
            log(s)

    m = _clean(mesh)
    rep.input_faces = len(m.faces)
    rep.input_watertight = bool(m.is_watertight)
    rep.input_pieces = len(m.split(only_watertight=False)) if len(m.faces) < 2_000_000 else -1
    m = _orient_scale(m, up, height_mm, base_cut_mm)
    loops = boundary_loops(m)
    rep.input_boundary_loops = len(loops)
    m, rep.patched_loops = patch_holes(m, patch_loops_mm)
    say(f"input {rep.input_faces} faces, watertight={rep.input_watertight}, pieces={rep.input_pieces}, "
        f"boundary loops={len(loops)} (patched {rep.patched_loops})")

    V = voxel_mm
    n_pts = int(min(6_000_000, max(200_000, m.area / (0.3 * V) ** 2)))
    pts, _ = trimesh.sample.sample_surface(m, n_pts, seed=1)
    pts = np.vstack([pts, m.vertices])
    pad = close_mm + 3 * V
    lo = pts.min(0) - pad - V / 3
    hi = pts.max(0) + pad
    shape = np.ceil((hi - lo) / V).astype(int) + 1
    say(f"{len(pts)} surface samples, grid {tuple(shape)} ({np.prod(shape) / 1e6:.1f} M voxels at {V} mm)")
    idx = np.floor((pts - lo) / V + 0.5).astype(int)
    occ = np.zeros(shape, bool)
    occ[tuple(idx.T)] = True
    edt = ndi.distance_transform_edt(~occ) * V
    band = edt < close_mm + 2 * V
    del edt, occ
    bi = np.argwhere(band)
    d, _ = cKDTree(pts).query(lo + bi * V, workers=-1)
    dist = np.full(shape, np.inf, np.float32)
    dist[tuple(bi.T)] = d
    del band, bi, d
    shell = dist < close_mm
    fill = ndi.binary_fill_holes(shell)
    if fill.sum() < 1.2 * shell.sum():          # shell still open somewhere: per-slice fill as fallback
        for k in range(shape[2]):
            fill[:, :, k] = ndi.binary_fill_holes(shell[:, :, k])
        fill = ndi.binary_fill_holes(fill)
        say("3D fill leaked (open shell) -> per-slice fill used")
    edt_in = ndi.distance_transform_edt(fill) * V
    f = np.where(fill, close_mm - edt_in, dist).astype(np.float32)
    f[~np.isfinite(f)] = close_mm + 2 * V
    del edt_in, dist, shell, fill
    f = ndi.gaussian_filter(f, 0.6)
    Z = (lo[2] + np.arange(shape[2]) * V).astype(np.float32)
    f = np.maximum(f, -Z[None, None, :])        # flat base at z = 0 (everything below cut off)
    say("closing + flat base done")

    solid = f < 0
    lab, n = ndi.label(solid)
    if n == 0:
        raise ValueError("nothing solid left: increase close_mm or check the up axis / base cut")
    sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
    keep = lab == (1 + int(np.argmax(sizes)))
    rep.pieces_dropped = int(n - 1)
    del lab
    filled = ndi.binary_fill_holes(keep)
    rep.cavity_voxels_filled = int((filled & ~keep).sum())
    keep = filled
    plugged = 0
    for axis in (2, 0, 1):                       # horizontal slices first (vertical tunnels), then x, y
        euler = _voxel_euler(keep)
        if euler == 2:
            break
        plug = np.zeros_like(keep)
        for k in range(shape[axis]):
            sl = [slice(None)] * 3; sl[axis] = k; sl = tuple(sl)
            plug[sl] = ndi.binary_fill_holes(keep[sl]) & ~keep[sl]
        plugged += int(plug.sum())
        keep |= plug
    rep.tunnel_voxels_plugged = plugged
    say(f"pieces dropped {rep.pieces_dropped}, cavity voxels filled {rep.cavity_voxels_filled}, "
        f"tunnel voxels plugged {plugged}")
    f = np.where(keep, np.minimum(f, -1e-3), np.maximum(f, 1e-3)).astype(np.float32)
    fp = np.pad(f, 1, constant_values=1.0)
    del f, keep
    verts, faces, _, _ = marching_cubes(fp, 0.0, spacing=(V,) * 3, allow_degenerate=False)
    del fp
    verts += lo - V
    out = trimesh.Trimesh(verts, faces, process=True)
    out = max(out.split(only_watertight=False), key=lambda q: len(q.faces))
    if simplify_mm and simplify_mm > 0:
        out = _decimate(out, simplify_mm)
    zl = out.vertices[:, 2].min()                 # snap the base rim flat
    v = out.vertices.copy(); v[v[:, 2] < zl + 0.25 * V, 2] = zl
    out = trimesh.Trimesh(v, out.faces, process=True)
    b = out.bounds
    out.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]])
    out.apply_scale(height_mm / out.extents[2])
    if out.volume < 0:
        out.invert()
    rep.faces = len(out.faces)
    rep.watertight = bool(out.is_watertight)
    rep.is_volume = bool(out.is_volume)
    rep.euler = int(out.euler_number)
    rep.extents_mm = tuple(round(float(x), 2) for x in out.extents)
    rep.volume_cm3 = round(float(out.volume) / 1000, 2)
    rep.fits_bed = fits_bed(out)
    rep.seconds = round(time.time() - t0, 1)
    say(f"master {rep.faces} faces, watertight={rep.watertight}, volume={rep.is_volume}, euler={rep.euler}, "
        f"extents {rep.extents_mm} mm, fits Ender 2: {rep.fits_bed}")
    return out, rep


def _voxel_euler(b: np.ndarray) -> int:
    """Euler characteristic of the boundary surface of a 6-connected voxel solid (2 = sphere)."""
    from skimage.measure import euler_number
    # Euler number of the 3D solid (26-connectivity of foreground) = components - tunnels + cavities;
    # surface Euler = 2 * solid Euler
    return 2 * int(euler_number(np.pad(b, 1), connectivity=1))


def fits_bed(m: trimesh.Trimesh, bed=ENDER2_BED_MM) -> bool:
    """Fits upright, or after a 90 deg turn about Z."""
    x, y, z = m.extents
    return bool(z <= bed[2] and ((x <= bed[0] and y <= bed[1]) or (y <= bed[0] and x <= bed[1])))


def damage_mesh(m: trimesh.Trimesh, seed: int = 0, holes: int = 4, hole_mm: float = 8.0) -> trimesh.Trimesh:
    """Simulate typical AI image-to-3D / scan defects on a clean mesh (for demos and tests): punched holes,
    flipped faces, duplicated faces, floating debris and an internal bubble."""
    rng = np.random.default_rng(seed)
    m = trimesh.Trimesh(m.vertices, m.faces, process=False)
    scale = float(np.max(m.extents))
    c = m.triangles_center
    drop = np.zeros(len(m.faces), bool)
    for i in rng.choice(len(c), holes, replace=False):
        drop |= np.linalg.norm(c - c[i], axis=1) < hole_mm / 2 * scale / 100
    F = m.faces[~drop].copy()
    flip = rng.random(len(F)) < 0.05
    F[flip] = F[flip][:, ::-1]
    F = np.vstack([F, F[rng.choice(len(F), len(F) // 50)]])
    parts = [trimesh.Trimesh(m.vertices, F, process=False)]
    ctr = m.bounds.mean(0)
    for _ in range(3):                           # debris floating outside
        s = trimesh.creation.icosphere(1, radius=scale * 0.015)
        p = m.bounds[0] + rng.random(3) * m.extents
        p[0] = m.bounds[1][0] + scale * 0.05      # just beside the part, not touching it
        s.apply_translation(p)
        parts.append(s)
    bub = trimesh.creation.icosphere(2, radius=scale * 0.04)   # internal bubble (inverted shell)
    bub.invert(); bub.apply_translation(m.centroid)
    parts.append(bub)
    return trimesh.util.concatenate(parts)
