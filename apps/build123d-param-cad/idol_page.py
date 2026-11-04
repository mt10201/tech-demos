"""Streamlit 'Photo → 3D (Idol)' page: one photo -> Idol splat (hosted Space) -> printable mold master (mm)."""

from __future__ import annotations

import os
import tempfile

import numpy as np
import streamlit as st

import idol_photo as ip
import scan_repair as sr
from photo_master_page import GOOD, RAW, _fig


def sidebar():
    st.sidebar.header("Photo → 3D (Idol)")
    up = st.sidebar.file_uploader("Photo of one object", type=["jpg", "jpeg", "png", "webp"],
                                  help="One object, whole and in focus; the Space removes the background.")
    h = st.sidebar.slider("Master height (mm)", 30.0, 245.0, 120.0, 1.0)
    vox = st.sidebar.select_slider("Detail: voxel size (mm)", [0.3, 0.4, 0.5, 0.6, 0.8, 1.0], value=0.4,
                                   help="Smaller = finer detail but slower (0.4 mm ≈ 10 s for 120 mm).")
    gs = st.sidebar.selectbox("Gaussians (Idol detail)", ip.GAUSSIANS, index=ip.GAUSSIANS.index(ip.DEFAULT_GAUSSIANS))
    seed = int(st.sidebar.number_input("Seed", 0, 2**31 - 1, 42, help="Same photo + seed = same object."))
    return up, h, vox, gs, seed


@st.cache_data(show_spinner="Idol is generating the 3D splat on the hosted Space (≈30 s, longer if queued)…",
               max_entries=4)
def _splat(data: bytes, name: str, gaussians: str, seed: int) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, os.path.basename(name) or "photo.jpg")
        with open(p, "wb") as f:
            f.write(data)
        with open(ip.run_idol(p, gaussians=gaussians, seed=seed), "rb") as f:
            return f.read()


@st.cache_data(show_spinner="Rebuilding as a watertight genus-0 master…", max_entries=4)
def _master(splat: bytes, h: float, vox: float):
    with tempfile.NamedTemporaryFile(suffix=".ply", delete=False) as f:
        f.write(splat)
    try:
        out, rep, info, raw = ip.photo_to_master(splat=f.name, height_mm=h, voxel_mm=vox)
    finally:
        os.unlink(f.name)
    r, prev = sr._decimate(raw, 0.3), sr._decimate(out, 0.15)
    return (np.asarray(r.vertices), np.asarray(r.faces)), (np.asarray(prev.vertices), np.asarray(prev.faces)), \
        out.export(file_type="stl"), rep, info


def render(choice) -> None:
    up, h, vox, gs, seed = choice
    st.title("Photo → 3D (Idol) — one photo to a printable mold master")
    st.caption("Sends the photo to the free official [Idol Space](https://huggingface.co/spaces/speridlabs/idol) "
               "(single image → 3D Gaussian splat, 'Real photo' mode), keeps the opaque splat centres, then runs "
               "the **Photo → master** repair: watertight, single shell, genus 0, flat base. No GPU or torch here; "
               "same code as `scripts/photo_to_idol_master.py`.")
    st.info(ip.LICENCE_NOTE, icon="⚖️")
    if up is None:
        st.info("Upload a photo in the sidebar.")
        st.stop()
    try:
        splat = _splat(up.getvalue(), up.name, gs, seed)
    except ip.IdolSpaceError as exc:
        st.error(f"Idol Space unavailable: {exc}")
        st.stop()
    try:
        raw_vf, prev_vf, stl, rep, info = _master(splat, h, vox)
    except Exception as exc:
        st.error(f"Could not turn this splat into a master: {exc}")
        st.stop()
    x, y, z = rep.extents_mm
    single = rep.watertight and rep.is_volume
    c = st.columns(5)
    c[0].metric("Watertight", "yes" if rep.watertight else "NO")
    c[1].metric("Single shell", "yes" if single else "NO")
    c[2].metric("Euler number", rep.euler, delta="genus 0" if rep.euler == 2 else "has tunnels",
                delta_color="normal" if rep.euler == 2 else "inverse")
    c[3].metric("Size X × Y × Z (mm)", f"{x:.1f} × {y:.1f} × {z:.1f}",
                delta="fits bed 225×225×245" if rep.fits_bed else "too big for the bed",
                delta_color="normal" if rep.fits_bed else "inverse")
    c[4].metric("Volume", f"{rep.volume_cm3:.0f} cm³", help=f"{rep.faces:,} triangles, rebuild {rep.seconds} s")
    a, b = st.columns([1, 2], gap="medium")
    with a:
        st.image(up.getvalue(), caption="Input photo", width="stretch")
    with b:
        V, F = prev_vf
        st.plotly_chart(_fig(V, F, GOOD, height=520, eye=dict(x=1.7, y=0.9, z=0.4)), width="stretch")
        st.caption("Rebuilt master (preview decimated), flat base on z = 0.")
    with st.expander("Rough splat-centre mesh (before repair)"):
        V, F = raw_vf
        st.plotly_chart(_fig(V, F, RAW, height=380, eye=dict(x=1.7, y=0.9, z=0.4)), width="stretch")
        st.caption(f"{info['gaussians']:,} Gaussians → {info['raw_faces']:,} faces, usually many pieces.")
    with st.expander("Repair log"):
        st.code("\n".join(rep.log) or "(no log)")
    st.download_button(f"Download master STL ({len(stl) / 1e6:.1f} MB, mm)", data=stl,
                       file_name=f"{os.path.splitext(up.name)[0]}_idol_master_{h:.0f}mm.stl", mime="model/stl",
                       width="stretch", disabled=not rep.ok())
