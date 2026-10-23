#!/usr/bin/env python3
"""Build the 4-inch (101.6 mm) Black Madonna de Sous-Terre STL mold master, preview PLY, and studio renders."""

from __future__ import annotations

import math
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image
import trimesh

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import madonna
import scan_repair as sr


def render_mesh_view(v, f, yaw_deg=0.0, pitch_deg=6.0, img_w=640, img_h=840):
    """High-resolution Z-buffer studio renderer for basalt/ebony cast-resin surface."""
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)

    x0, y0, z0 = v[:, 0], v[:, 1], v[:, 2] - 50.8
    x1 = x0 * cy - y0 * sy
    y1 = x0 * sy + y0 * cy
    z1 = z0

    vx = x1
    vy = z1 * cp - y1 * sp
    vz = y1 * cp + z1 * sp

    scale = img_h * 0.84 / 101.6
    px = vx * scale + img_w * 0.5
    py = img_h * 0.52 - vy * scale
    pz = -vz

    t0 = np.stack([px[f[:, 0]], py[f[:, 0]], pz[f[:, 0]]], axis=-1)
    t1 = np.stack([px[f[:, 1]], py[f[:, 1]], pz[f[:, 1]]], axis=-1)
    t2 = np.stack([px[f[:, 2]], py[f[:, 2]], pz[f[:, 2]]], axis=-1)

    fn = np.cross(t1 - t0, t2 - t0)
    fn_norm = np.linalg.norm(fn, axis=-1, keepdims=True) + 1e-12
    fn = fn / fn_norm
    vis = np.where(fn[:, 2] < 0)[0]

    zbuf = np.full((img_h, img_w), -1e9, dtype=np.float32)
    img = np.full((img_h, img_w, 3), 246, dtype=np.uint8)

    l1 = np.array([-0.38, -0.32, -0.86])
    l1 /= np.linalg.norm(l1)
    l2 = np.array([0.55, -0.15, -0.82])
    l2 /= np.linalg.norm(l2)
    l3 = np.array([0.0, 0.78, -0.62])
    l3 /= np.linalg.norm(l3)

    d1 = np.clip(np.sum(fn * l1, axis=-1), 0.0, 1.0)
    d2 = np.clip(np.sum(fn * l2, axis=-1), 0.0, 1.0)
    d3 = np.clip(np.sum(fn * l3, axis=-1), 0.0, 1.0)
    rim = np.clip(1.0 - np.abs(fn[:, 2]), 0.0, 1.0) ** 2.2
    spec = (
        np.clip(np.sum(fn * np.array([-0.18, -0.25, -0.95]), axis=-1), 0.0, 1.0) ** 22.0
    ) * 0.35

    shade = 0.14 + 0.50 * d1 + 0.24 * d2 + 0.12 * d3 + 0.16 * rim + spec
    fc_r = np.clip(shade * 78.0, 14, 235).astype(np.uint8)
    fc_g = np.clip(shade * 82.0, 15, 240).astype(np.uint8)
    fc_b = np.clip(shade * 90.0, 17, 248).astype(np.uint8)

    for idx in vis:
        x_a, y_a, z_a = t0[idx]
        x_b, y_b, z_b = t1[idx]
        x_c, y_c, z_c = t2[idx]
        min_x = max(0, int(min(x_a, x_b, x_c)))
        max_x = min(img_w - 1, int(max(x_a, x_b, x_c)) + 1)
        min_y = max(0, int(min(y_a, y_b, y_c)))
        max_y = min(img_h - 1, int(max(y_a, y_b, y_c)) + 1)
        if min_x > max_x or min_y > max_y:
            continue
        denom = (y_b - y_c) * (x_a - x_c) + (x_c - x_b) * (y_a - y_c)
        if abs(denom) < 1e-6:
            continue
        inv_d = 1.0 / denom
        gx, gy = np.meshgrid(
            np.arange(min_x, max_x + 1, dtype=np.float32),
            np.arange(min_y, max_y + 1, dtype=np.float32),
        )
        w0 = ((y_b - y_c) * (gx - x_c) + (x_c - x_b) * (gy - y_c)) * inv_d
        w1 = ((y_c - y_a) * (gx - x_c) + (x_a - x_c) * (gy - y_c)) * inv_d
        w2 = 1.0 - w0 - w1
        mask = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not np.any(mask):
            continue
        zz = w0 * z_a + w1 * z_b + w2 * z_c
        sub_z = zbuf[min_y : max_y + 1, min_x : max_x + 1]
        upd = mask & (zz > sub_z)
        if np.any(upd):
            sub_z[upd] = zz[upd]
            sub_img = img[min_y : max_y + 1, min_x : max_x + 1]
            sub_img[upd, 0] = fc_r[idx]
            sub_img[upd, 1] = fc_g[idx]
            sub_img[upd, 2] = fc_b[idx]

    return img


def main():
    print("Building 4-inch (101.6 mm) Black Madonna mold master at resolution=240...")
    v_norm, f = madonna.statue_mesh(resolution=240, simplify_mm=0.025)
    v_mm = v_norm * madonna.DEFAULT_HEIGHT_MM
    v_mm[:, 2] -= v_mm[:, 2].min()
    v_mm[v_mm[:, 2] < 0.04, 2] = 0.0
    cx = 0.5 * (v_mm[:, 0].max() + v_mm[:, 0].min())
    cy = 0.5 * (v_mm[:, 1].max() + v_mm[:, 1].min())
    v_mm[:, 0] -= cx
    v_mm[:, 1] -= cy

    m = trimesh.Trimesh(v_mm, f, process=True)
    assert m.is_watertight, "Master STL must be watertight"
    assert m.is_volume, "Master STL must be a valid volume"
    assert m.body_count == 1, f"Expected 1 body, got {m.body_count}"
    assert m.euler_number == 2, f"Expected Euler 2 (genus 0), got {m.euler_number}"
    assert abs(m.extents[2] - madonna.DEFAULT_HEIGHT_MM) < 0.05

    madonna.MASTER_STL.parent.mkdir(parents=True, exist_ok=True)
    m.export(madonna.MASTER_STL)

    exports_dir = Path("/workspace/exports")
    exports_dir.mkdir(parents=True, exist_ok=True)
    export_stl = exports_dir / "black_madonna_4in_101.6mm.stl"
    shutil.copy2(madonna.MASTER_STL, export_stl)

    print(
        f"Saved {madonna.MASTER_STL} ({madonna.MASTER_STL.stat().st_size / 1e6:.2f} MB) "
        f"and {export_stl}: verts={len(m.vertices)}, faces={len(m.faces)}, "
        f"watertight={m.is_watertight}, bodies={m.body_count}, euler={m.euler_number}, "
        f"extents={np.round(m.extents, 2)} mm, volume={m.volume / 1000:.2f} cm^3"
    )

    # Build lightweight preview PLY for instant 4-view interactive display
    m_prev = sr._decimate(m, 0.065)
    zl = m_prev.vertices[:, 2].min()
    vp = m_prev.vertices.copy()
    vp[vp[:, 2] < zl + 0.05, 2] = 0.0
    m_prev = trimesh.Trimesh(vp, m_prev.faces, process=True)
    m_prev.export(madonna.PREVIEW_PLY)
    print(
        f"Saved {madonna.PREVIEW_PLY} ({madonna.PREVIEW_PLY.stat().st_size / 1e3:.1f} KB): "
        f"faces={len(m_prev.faces)}, watertight={m_prev.is_watertight}, euler={m_prev.euler_number}"
    )

    # Render multi-angle studio images into media/
    media_dir = ROOT / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    views = [
        ("front", 0.0, 4.0),
        ("three_quarter", -28.0, 6.0),
        ("side", 90.0, 3.0),
        ("back", 180.0, 4.0),
    ]
    rendered = []
    for name, yaw, pitch in views:
        im = render_mesh_view(m.vertices, m.faces, yaw_deg=yaw, pitch_deg=pitch, img_w=620, img_h=820)
        out_path = media_dir / f"black_madonna_{name}.png"
        Image.fromarray(im).save(out_path)
        rendered.append(im)
        print(f"Rendered {out_path}")

    grid_4 = np.concatenate(rendered, axis=1)
    angles_path = media_dir / "black_madonna_angles.png"
    Image.fromarray(grid_4).save(angles_path)
    print(f"Saved 4-angle studio sheet: {angles_path}")


if __name__ == "__main__":
    main()
