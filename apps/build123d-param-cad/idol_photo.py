"""Photo -> 3D with Idol (hosted Hugging Face Space) -> printable silicone-mold master (mm).

Idol (speridlabs/idol, Apache-2.0 code + weights) turns one photo into a 3D Gaussian splat. We call the free
official Space with gradio_client (no torch / GPU here), keep the splat *centres* of the reasonably opaque
Gaussians, voxelise them into a rough surface and hand that to scan_repair.scan_to_master, which makes it
watertight, a single shell and genus 0 (Euler 2). In the Nov 2026 test on a CC0 photo of the Hayes bust this
kept more face / beard detail than splat2stl's visual hull, took ~1 s instead of ~3 min on CPU and needs no torch.
"""
from __future__ import annotations

import os
import shutil
import time

import numpy as np
import trimesh
from scipy import ndimage as ndi
from skimage.measure import marching_cubes

import scan_repair as sr

SPACE = "speridlabs/idol"
GAUSSIANS = ("65,536", "131,072", "262,144", "524,288", "1,048,576")
DEFAULT_GAUSSIANS = "524,288"
LICENCE_NOTE = ("Licence: Idol's code and weights are Apache-2.0 and its image encoders (DINOv3, FLUX.2 VAE) "
                "allow commercial use, so selling castings made through the hosted Space is OK. The input "
                "photo must be your own or cleared for commercial use (e.g. CC0); a customer's photo needs "
                "their permission.")
_PLY_TYPES = {b"float": "<f4", b"float32": "<f4", b"double": "<f8", b"uchar": "u1", b"int": "<i4", b"uint": "<u4"}


class IdolSpaceError(RuntimeError):
    """The hosted Idol Space is down, sleeping, out of free GPU quota, queued too long or returned nothing."""


def run_idol(photo: str, out_ply: str | None = None, gaussians: str = DEFAULT_GAUSSIANS, seed: int = 42,
             steps: int = 50, timeout_s: float = 300.0, client=None) -> str:
    """Send `photo` to the Idol Space ('Real photo' mode) and return the path of the downloaded splat .ply."""
    if gaussians not in GAUSSIANS:
        raise ValueError(f"gaussians must be one of {GAUSSIANS}")
    try:
        from gradio_client import Client, handle_file
    except ImportError as exc:  # pragma: no cover
        raise IdolSpaceError("gradio_client is not installed: pip install gradio_client") from exc
    try:
        client = client or Client(SPACE, verbose=False)
    except Exception as exc:
        raise IdolSpaceError(f"Could not reach the Idol Space ({SPACE}): it may be down, sleeping or "
                             f"restarting. Try again in a few minutes. Details: {exc}") from exc
    try:
        job = client.submit(handle_file(photo), "Real photo", steps, 3.0, 3.0, int(seed), False, gaussians,
                            api_name="/run")
        res = job.result(timeout=timeout_s)
    except TimeoutError as exc:
        raise IdolSpaceError(f"The Idol Space did not answer within {timeout_s:.0f} s (long queue or no free "
                             "GPU right now). Try again later or with fewer Gaussians.") from exc
    except Exception as exc:
        msg = str(exc) or type(exc).__name__
        hint = " (free GPU quota used up, try again later)" if "quota" in msg.lower() else ""
        raise IdolSpaceError(f"The Idol Space returned an error{hint}: {msg}") from exc
    ply = res[0] if isinstance(res, (list, tuple)) else res
    if not ply or not os.path.exists(str(ply)):
        raise IdolSpaceError("The Idol Space returned no splat file.")
    if out_ply:
        shutil.copy(ply, out_ply)
        return out_ply
    return str(ply)


def read_splat(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Gaussian centres (N, 3) and opacities in 0..1 from a standard 3DGS binary PLY (numpy only)."""
    with open(path, "rb") as f:
        if f.readline().strip() != b"ply":
            raise ValueError("not a PLY file")
        n, props, cur, first = 0, [], None, None
        while True:
            line = f.readline()
            if not line:
                raise ValueError("truncated PLY header")
            w = line.split()
            if w[:1] == [b"format"] and w[1] != b"binary_little_endian":
                raise ValueError("only binary_little_endian splat PLYs are supported")
            if w[:1] == [b"element"]:
                cur = w[1]
                first = first or cur
                if cur == b"vertex":
                    n = int(w[2])
            elif w[:1] == [b"property"] and cur == b"vertex":
                props.append((w[2].decode(), _PLY_TYPES[w[1]]))
            elif w[:1] == [b"end_header"]:
                break
        if first != b"vertex" or not n:
            raise ValueError("PLY has no leading vertex element")
        data = np.frombuffer(f.read(n * np.dtype(props).itemsize), dtype=props, count=n)
    xyz = np.stack([data["x"], data["y"], data["z"]], 1).astype(np.float64)
    op = 1.0 / (1.0 + np.exp(-data["opacity"].astype(np.float64))) if "opacity" in data.dtype.names \
        else np.ones(n)
    return xyz, op


def splat_to_mesh(xyz: np.ndarray, opacity: np.ndarray, height_mm: float = 120.0, min_opacity: float = 0.3,
                  point_voxel_mm: float | None = None) -> trimesh.Trimesh:
    """Raw splat-centres route: opaque Gaussian centres -> +Z up, scaled to height_mm -> occupancy grid
    (one dilation) -> marching cubes. Rough and often in many pieces; scan_to_master fixes that.
    Idol's splats are -Y up; the output is +Z up in mm."""
    p = xyz[opacity > min_opacity]
    if len(p) < 1000:
        raise ValueError(f"only {len(p)} opaque Gaussians: the splat looks empty")
    p = np.c_[p[:, 0], p[:, 2], -p[:, 1]]                       # -Y up -> +Z up (right-handed)
    lo, hi = np.percentile(p, 0.2, axis=0), np.percentile(p, 99.8, axis=0)
    p = p[((p >= lo) & (p <= hi)).all(1)]                       # drop stray floaters
    p = (p - p.min(0)) * (height_mm / np.ptp(p[:, 2]))
    vox = point_voxel_mm or max(0.5, height_mm / 120.0)
    idx = np.floor(p / vox).astype(int) + 2
    g = np.zeros(idx.max(0) + 3, bool)
    g[tuple(idx.T)] = True
    g = ndi.binary_dilation(g, iterations=1)
    v, f, _, _ = marching_cubes(g.astype(np.float32), 0.5)
    return trimesh.Trimesh(v * vox, f, process=False)


def photo_to_master(photo: str | None = None, splat: str | None = None, height_mm: float = 120.0,
                    voxel_mm: float = 0.4, close_mm: float = 0.8, base_cut_mm: float = 2.0,
                    gaussians: str = DEFAULT_GAUSSIANS, seed: int = 42, keep_splat: str | None = None, log=None):
    """Photo (via the Space) or an existing splat .ply -> (master, RepairReport, info dict, rough mesh)."""
    say = log or (lambda *_: None)
    info = {}
    t = time.time()
    if splat is None:
        if photo is None:
            raise ValueError("give a photo or a splat")
        say(f"sending {os.path.basename(photo)} to the Idol Space ({gaussians} Gaussians)...")
        splat = run_idol(photo, keep_splat, gaussians=gaussians, seed=seed)
        info["idol_seconds"] = round(time.time() - t, 1)
        say(f"splat received in {info['idol_seconds']} s")
    xyz, op = read_splat(splat)
    info["gaussians"] = len(xyz)
    raw = splat_to_mesh(xyz, op, height_mm)
    info["raw_faces"] = len(raw.faces)
    say(f"splat centres -> rough mesh: {len(raw.faces)} faces")
    out, rep = sr.scan_to_master(raw, height_mm=height_mm, up="+z", base_cut_mm=base_cut_mm, voxel_mm=voxel_mm,
                                 close_mm=close_mm, log=say)
    info["total_seconds"] = round(time.time() - t, 1)
    return out, rep, info, raw


def write_test_splat(path: str, n: int = 20000, seed: int = 0) -> None:
    """Write a small synthetic 3DGS PLY (an egg standing on a disc, -Y up) for tests and offline demos."""
    rng = np.random.default_rng(seed)
    d = rng.normal(size=(n, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    egg = d * [0.25, 0.4, 0.25] - [0, 0.05, 0]   # bottom sinks into the disc
    m = n // 4
    disc = np.c_[rng.uniform(-0.3, 0.3, m), np.full(m, 0.3), rng.uniform(-0.3, 0.3, m)]
    xyz = np.vstack([egg, disc]).astype("<f4")
    names = ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity"]
    arr = np.zeros(len(xyz), dtype=[(k, "<f4") for k in names])
    arr["x"], arr["y"], arr["z"] = xyz.T
    arr["opacity"] = 3.0
    hdr = f"ply\nformat binary_little_endian 1.0\nelement vertex {len(arr)}\n" + \
        "".join(f"property float {k}\n" for k in names) + "end_header\n"
    with open(path, "wb") as f:
        f.write(hdr.encode())
        f.write(arr.tobytes())
