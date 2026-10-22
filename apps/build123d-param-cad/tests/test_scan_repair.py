"""Photo/scan mesh -> printable mold master (scan_repair + scripts/photo_to_master.py)."""
import os
import subprocess
import sys

import numpy as np
import pytest
import trimesh

import scan_repair as sr

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _capsule():
    return trimesh.creation.capsule(height=40, radius=15, count=[24, 24])


def test_boundary_loops_counts_punched_holes():
    m = sr.damage_mesh(_capsule(), seed=3, holes=2, hole_mm=12)
    assert len(sr.boundary_loops(m)) >= 1          # holes may merge
    assert sr.boundary_loops(_capsule()) == []


def test_damaged_capsule_becomes_a_master():
    src = sr.damage_mesh(_capsule(), seed=0)
    assert not src.is_watertight
    out, rep = sr.scan_to_master(src, height_mm=50, voxel_mm=0.6)
    assert rep.ok() and rep.fits_bed
    assert out.is_watertight and out.is_volume and out.euler_number == 2
    assert len(out.split(only_watertight=False)) == 1
    assert abs(out.extents[2] - 50) < 0.5
    assert abs(out.bounds[0][2]) < 1e-6
    assert rep.pieces_dropped >= 1          # the debris (neighbouring spheres may merge)
    # flat base: lots of area at z = 0 facing down
    down = (out.face_normals[:, 2] < -0.99) & (out.triangles_center[:, 2] < 0.05)
    assert out.area_faces[down].sum() > 100


def test_torus_tunnel_is_plugged_to_genus_0():
    tor = trimesh.creation.torus(major_radius=20, minor_radius=6)
    out, rep = sr.scan_to_master(tor, height_mm=40, up="+y", voxel_mm=0.6)
    assert rep.ok() and rep.tunnel_voxels_plugged > 0
    assert out.euler_number == 2


def test_fits_bed_allows_a_quarter_turn():
    assert sr.fits_bed(trimesh.creation.box((160, 100, 50))) is False
    assert sr.fits_bed(trimesh.creation.box((100, 140, 190)))
    assert not sr.fits_bed(trimesh.creation.box((100, 100, 210)))


def test_bundled_sample_is_cc0_hayes_and_loads():
    p = os.path.join(HERE, "assets", "hayes_bust_npg_cc0.ply")
    m = sr.load_mesh(p)
    assert len(m.faces) > 10000 and m.is_watertight
    att = open(os.path.join(HERE, "assets", "ATTRIBUTION.md")).read()
    assert "NPG.76.27" in att and "CC0" in att


def test_cli_on_a_small_mesh(tmp_path):
    src = tmp_path / "in.stl"
    sr.damage_mesh(_capsule(), seed=2).export(src)
    out = tmp_path / "out.stl"
    r = subprocess.run([sys.executable, os.path.join(HERE, "scripts", "photo_to_master.py"), str(src), str(out),
                        "--height", "40", "--voxel", "0.8"], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    m = trimesh.load(out)
    assert m.is_watertight and m.euler_number == 2 and abs(m.extents[2] - 40) < 0.5
