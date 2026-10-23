"""Streamlit 'Photo → master' page: repair a photo-to-3D / scan mesh into a printable mold master (mm)."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import scan_repair as sr

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "assets", "hayes_bust_npg_cc0.ply")
SAMPLE_NAME = "Sample: Rutherford B. Hayes plaster bust (Smithsonian NPG, CC0)"
MADONNA_SAMPLE = os.path.join(HERE, "assets", "black_madonna_preview.ply")
MADONNA_NAME = "Sample: Black Madonna de Sous-Terre (Chartres Sedes Sapientiae, CC0)"
UPLOAD = "Upload a mesh (STL / OBJ / PLY / GLB)"
BG = "#d9c7a3"
RAW = "#b08060"
GOOD = "#c3c7ce"
BAD = "#d04040"


@dataclass(frozen=True)
class PhotoParams:
    source: str = SAMPLE_NAME
    damage: bool = True
    height_mm: float = 120.0
    up: str = "+z"
    voxel_mm: float = 0.6
    close_mm: float = 0.8
    base_cut_mm: float = 2.0


def sidebar():
    st.sidebar.header("Photo → master (mm)")
    source = st.sidebar.radio("Mesh", [SAMPLE_NAME, MADONNA_NAME, UPLOAD], index=0)
    upload = None
    if source == UPLOAD:
        upload = st.sidebar.file_uploader("Mesh file", type=["stl", "obj", "ply", "glb", "gltf", "off"],
                                          help="E.g. the GLB from an image-to-3D tool or a phone scan.")
    damage = st.sidebar.checkbox("Simulate AI / scan defects", value=source in (SAMPLE_NAME, MADONNA_NAME),
                                 help="Punch 4 holes, flip 5 % of faces, duplicate 2 %, add floating debris "
                                      "and an internal bubble, i.e. what typical image-to-3D output looks like.")
    default_h = 101.6 if source == MADONNA_NAME else 120.0
    h = st.sidebar.slider("Master height (mm)", 30.0, 190.0, float(default_h), 0.2)
    up_default = "+y" if (upload is not None and upload.name.lower().endswith((".glb", ".gltf"))) else "+z"
    up = st.sidebar.selectbox("Up axis of the input", list(sr.AXES), index=list(sr.AXES).index(up_default))
    vox = st.sidebar.select_slider("Voxel size (mm)", [0.3, 0.4, 0.5, 0.6, 0.8, 1.0], value=0.6,
                                   help="Smaller = finer detail but slower (0.4 mm ≈ 12 s, 0.6 mm ≈ 4 s for 120 mm).")
    close = st.sidebar.slider("Close gaps narrower than (mm)", 0.4, 3.0, 0.8, 0.1,
                              help="Morphological closing radius: slots narrower than ~2× this are filled, "
                                   "so the silicone can't make thin fins.")
    base = st.sidebar.slider("Flat base cut (mm)", 0.0, 10.0, 0.5 if source == MADONNA_NAME else 2.0, 0.5)
    name = source if source in (SAMPLE_NAME, MADONNA_NAME) else (upload.name if upload is not None else "")
    return PhotoParams(name, damage, h, up, vox, close, base), upload


@st.cache_data(show_spinner="Loading mesh…", max_entries=4)
def _load(name: str, data: bytes | None):
    if data is None:
        return sr.load_mesh(MADONNA_SAMPLE if name == MADONNA_NAME else SAMPLE)
    ext = os.path.splitext(name)[1] or ".stl"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(data)
    try:
        return sr.load_mesh(f.name)
    finally:
        os.unlink(f.name)


@st.cache_data(show_spinner="Rebuilding as a watertight genus-0 master…", max_entries=4)
def _repair(p: PhotoParams, data: bytes | None):
    raw = _load(p.source, data)
    src = sr.damage_mesh(raw, seed=1) if p.damage else raw
    out, rep = sr.scan_to_master(src, height_mm=p.height_mm, up=p.up, base_cut_mm=p.base_cut_mm,
                                 voxel_mm=p.voxel_mm, close_mm=p.close_mm)
    prev = sr._decimate(out, 0.15)
    # show the input at the same scale and orientation as the output
    s = sr._orient_scale(src, p.up, p.height_mm, 0.0)
    return (np.asarray(s.vertices), np.asarray(s.faces)), (np.asarray(prev.vertices), np.asarray(prev.faces)), \
        out.export(file_type="stl"), rep


def _fig(V, F, color, height=460, eye=dict(x=1.3, y=-1.6, z=0.5), extra=()):
    tr = [go.Mesh3d(x=V[:, 0], y=V[:, 1], z=V[:, 2], i=F[:, 0], j=F[:, 1], k=F[:, 2], color=color,
                    flatshading=False, hoverinfo="skip",
                    lighting=dict(ambient=0.4, diffuse=0.85, specular=0.15, roughness=0.85),
                    lightposition=dict(x=-200, y=-300, z=400))]
    tr += list(extra)
    fig = go.Figure(tr)
    ax = dict(visible=False)
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor=BG, showlegend=False,
                      scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data", bgcolor=BG,
                                 camera=dict(eye=eye, up=dict(x=0, y=0, z=1))))
    return fig


def _boundary_trace(V, F):
    import trimesh

    m = trimesh.Trimesh(V, F, process=False)
    loops = sr.boundary_loops(m)
    xs, ys, zs = [], [], []
    for lp in loops:
        p = m.vertices[np.r_[lp, lp[:1]]]
        xs += list(p[:, 0]) + [None]; ys += list(p[:, 1]) + [None]; zs += list(p[:, 2]) + [None]
    return go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=BAD, width=6), hoverinfo="skip"), len(loops)


def render(choice) -> None:
    p, upload = choice
    st.title("Photo → master — printable silicone-mold master from any mesh")
    st.caption(
        "For the output of image-to-3D tools (TRELLIS.2, Hunyuan3D, Meshy, UniForge3D…) and phone scans: "
        "orient, scale to mm, patch holes, drop debris, fill bubbles, close thin slots, plug tunnels, cut a flat "
        "base, then check **watertight single shell, genus 0, fits the Ender 2**. CPU only (numpy / scipy / "
        "scikit-image / manifold3d); the same code runs as `scripts/photo_to_master.py`.")
    if not p.source:
        st.info("Choose a mesh file in the sidebar.")
        st.stop()
    data = upload.getvalue() if upload is not None else None
    try:
        raw_vf, prev_vf, stl, rep = _repair(p, data)
    except Exception as exc:  # unreadable mesh etc.
        st.error(f"Could not rebuild this mesh: {exc}")
        st.stop()
    c = st.columns(5)
    c[0].metric("Result", "printable master" if rep.ok() else "needs attention",
                delta="watertight · 1 shell · genus 0" if rep.ok() else f"euler {rep.euler}",
                delta_color="normal" if rep.ok() else "inverse")
    x, y, z = rep.extents_mm
    c[1].metric("Size X × Y × Z (mm)", f"{x:.1f} × {y:.1f} × {z:.1f}",
                delta="fits Ender-2 150×150×200" if rep.fits_bed else "too big for the bed",
                delta_color="normal" if rep.fits_bed else "inverse")
    c[2].metric("Volume", f"{rep.volume_cm3:.0f} cm³", help="≈ resin / plaster per casting")
    c[3].metric("Input defects", f"{rep.input_boundary_loops} holes · {rep.input_pieces} pieces",
                help=f"{rep.input_faces:,} faces, watertight: {rep.input_watertight}")
    c[4].metric("Rebuild time", f"{rep.seconds:.1f} s", help=f"{rep.faces:,} output faces")
    a, b = st.columns(2, gap="medium")
    with a:
        V, F = raw_vf
        bt, n = _boundary_trace(V, F)
        st.plotly_chart(_fig(V, F, RAW, extra=[bt]), use_container_width=True)
        st.caption(f"Input{' with simulated defects' if p.damage else ''}: {n} open boundary loops in red, "
                   "floating debris beside it.")
    with b:
        V, F = prev_vf
        st.plotly_chart(_fig(V, F, GOOD), use_container_width=True)
        st.caption("Rebuilt master (preview decimated), flat base on z = 0.")
    with st.expander("Repair log"):
        st.code("\n".join(rep.log) or "(no log)")
    st.download_button(f"Download master STL ({len(stl) / 1e6:.1f} MB, mm)", data=stl,
                       file_name=f"photo_master_{p.height_mm:.0f}mm.stl", mime="model/stl",
                       use_container_width=True, disabled=not rep.ok())
    st.caption("Licensing: only sell castings of meshes whose licence allows commercial use and derivatives "
               "(e.g. CC0 / CC BY). UniForge3D's weights are CC BY-NC 4.0 (see docs/photo_to_3d.md).")
