"""Streamlit 'Photo → relief' page: pet photo -> bas-relief portrait in a memorial-stone frame (STL, mm)."""

from __future__ import annotations

import io
import os

import numpy as np
import streamlit as st
from PIL import Image

import relief as R
import scan_repair as sr
from photo_master_page import GOOD, _fig


def sidebar():
    st.sidebar.header("Photo → relief")
    up = st.sidebar.file_uploader("Pet photo (face the camera)", type=["jpg", "jpeg", "png", "webp"],
                                  help="Front-facing, sharp, even light. The background is removed automatically.")
    auto = st.sidebar.toggle("Auto crop (head + chest)", value=True)
    crop = None
    if not auto:
        x0, x1 = st.sidebar.slider("Crop left / right (fraction)", 0.0, 1.0, (0.1, 0.9), 0.01)
        y0, y1 = st.sidebar.slider("Crop top / bottom (fraction)", 0.0, 1.0, (0.05, 0.7), 0.01)
        crop = (x0, y0, x1, y1)
    relief = st.sidebar.slider("Relief height (mm)", 4.0, 20.0, 12.0, 0.5,
                               help="Highest point of the portrait above the niche floor.")
    detail = st.sidebar.slider("Fine detail (mm)", 0.0, 1.5, 0.6, 0.05,
                               help="Photo-derived eyes/nose/fur detail. 0 = smooth sculpted look.")
    compress = st.sidebar.slider("Depth compression", 0.0, 4.0, 0.5, 0.1,
                                 help="Higher flattens the nose/muzzle relative to the face.")
    w = st.sidebar.slider("Frame width (mm)", 80.0, 220.0, 150.0, 1.0)
    h = st.sidebar.slider("Frame height (mm)", 80.0, 220.0, 140.0, 1.0)
    t = st.sidebar.slider("Frame thickness (mm)", 12.0, 40.0, 25.0, 1.0)
    text = st.sidebar.text_input("Engraved text", "", max_chars=28, help="e.g. a name and dates; empty = none")
    tex = st.sidebar.toggle("Hammered stone texture", value=True)
    res = st.sidebar.select_slider("Grid (mm)", [0.2, 0.25, 0.35, 0.5], value=0.25,
                                   help="Height-map cell size; 0.25 mm ≈ 250k triangles.")
    p = R.ReliefParams(width=w, height=h, thickness=t, relief_mm=relief, detail_mm=detail, compress=compress,
                       text=text.strip(), texture=tex, res_mm=res, crop=crop)
    return up, p


@st.cache_data(show_spinner="Removing background (BiRefNet) and estimating depth (Depth Anything V2 Small) on CPU…",
               max_entries=4)
def _analyse(data: bytes, crop, aspect: float):
    tm: dict = {}
    ci, cm, disp, box = R.analyse(Image.open(io.BytesIO(data)), crop, aspect, tm)
    return ci, cm, disp, box, tm


@st.cache_data(show_spinner="Building the relief and frame…", max_entries=6)
def _build(data: bytes, p: R.ReliefParams):
    _, _, a, b = R.niche_box(p)
    ci, cm, disp, box, tm = _analyse(data, p.crop, b / a)
    mesh, rep, ex = R.photo_to_relief(None, p, analysed=(ci, cm, disp, box), log=lambda *_: None)
    rep.timings = {**tm, **rep.timings}
    prev = sr._decimate(mesh, 0.06)
    return (np.asarray(prev.vertices), np.asarray(prev.faces)), mesh.export(file_type="stl"), rep, \
        R.shade(ex["z"], p.res_mm, ex["inside"]), ci


def render(choice) -> None:
    up, p = choice
    st.title("Photo → relief — pet portrait in a memorial-stone frame")
    st.caption("Background removal + monocular depth on CPU (onnxruntime), then a gradient-compressed bas-relief "
               "placed in a parametric stone frame with an arch niche, optional hammered texture and engraved text. "
               "Flat back, no undercuts, watertight single shell. Same code as `scripts/photo_to_relief.py`.")
    st.info(R.LICENCE_NOTE, icon="⚖️")
    if up is None:
        st.info("Upload a pet photo in the sidebar.")
        st.stop()
    try:
        prev_vf, stl, rep, shaded, ci = _build(up.getvalue(), p)
    except Exception as exc:
        st.error(f"Could not build a relief from this photo: {exc}")
        st.stop()
    x, y, z = rep.extents_mm
    c = st.columns(5)
    c[0].metric("Watertight", "yes" if rep.watertight else "NO")
    c[1].metric("Single shell", "yes" if rep.pieces == 1 else f"NO ({rep.pieces})")
    c[2].metric("Euler number", rep.euler, delta="genus 0" if rep.euler == 2 else "has tunnels",
                delta_color="normal" if rep.euler == 2 else "inverse")
    c[3].metric("Size X × Y × Z (mm)", f"{x:.0f} × {y:.0f} × {z:.0f}",
                delta="fits bed 225×225×245" if rep.fits_bed else "too big for the bed",
                delta_color="normal" if rep.fits_bed else "inverse")
    c[4].metric("Volume", f"{rep.volume_cm3:.0f} cm³",
                help=f"{rep.faces:,} triangles; " + ", ".join(f"{k} {v}" for k, v in rep.timings.items()))
    a, b, d = st.columns([1, 1, 2.2], gap="medium")
    with a:
        st.image(up.getvalue(), caption="Input photo", width="stretch")
    with b:
        st.image(ci, caption="Crop used", width="stretch")
    with d:
        st.image(shaded, caption="Front, raking light (full-resolution height map)", width="stretch")
    V, F = prev_vf
    st.plotly_chart(_fig(V, F, GOOD, height=560, eye=dict(x=0.35, y=-1.25, z=1.25)), width="stretch")
    st.caption("3D preview (decimated). Lies flat on its back; print face-up.")
    st.download_button(f"Download relief STL ({len(stl) / 1e6:.1f} MB, mm)", data=stl,
                       file_name=f"{os.path.splitext(up.name)[0]}_relief_{p.width:.0f}x{p.height:.0f}.stl",
                       mime="model/stl", width="stretch", disabled=not rep.ok())
