"""Streamlit 'Moai statue' page: real-scan moai head (default), v1 blend, mold tooling, or parametric."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import moai_mold
import moai_scan
from moai import DEFAULT_HEIGHT_MM, ENDER2_BED_MM, MoaiParams, build, fits_bed, stl_bytes

SCAN = "Real scan: Quarry Moai head (original)"
BLEND = "Refined scan v1 (ear/top blend)"
MOLD = "Mold tooling v1 (master + frame)"
PARAMETRIC = "Parametric (full statue)"

STONE = "#8a7f73"
FRAME = "#55585e"
SKY = "#bcd4ea"
VIEWS = {
    "Front": dict(x=0.0, y=-2.6, z=0.15),
    "Side": dict(x=2.6, y=0.0, z=0.15),
    "3/4": dict(x=1.6, y=-2.1, z=0.55),
}
SCAN_VIEWS = {**VIEWS, "Back": dict(x=-1.3, y=2.3, z=0.35)}


def sidebar():
    st.sidebar.header("Moai statue (mm)")
    source = st.sidebar.radio(
        "Model",
        [SCAN, BLEND, MOLD, PARAMETRIC],
        index=0,
        help="Original scan is preserved. Refined v1 softens ear/top hard lines only. "
             "Mold tooling: integral circular plate + detachable cylindrical pour frame "
             "(tower v3 0.25 mm/side lip+channel).",
    )
    h = st.sidebar.number_input(
        "Overall height (mm)", 40.0, 200.0, float(DEFAULT_HEIGHT_MM), 0.1,
        format="%.1f", help="152.4 mm = 6 in. Includes the plinth if enabled (parametric only).",
    )
    plinth = False
    if source == PARAMETRIC:
        plinth = st.sidebar.checkbox(
            "Base plinth", value=False,
            help="A 6 mm block under the statue, 4 mm wider all round (better bed grip).",
        )
    return source, MoaiParams(height_mm=h, plinth=plinth)


@st.cache_data(show_spinner="Sculpting the moai (signed-distance model)…", max_entries=6)
def _mesh(p: MoaiParams, resolution: int):
    v, f = build(MoaiParams(p.height_mm, p.plinth, p.plinth_height_mm, p.plinth_margin_mm, resolution))
    return v, f


def figure(v, f, eye, height=560, light_back=False, color=STONE) -> go.Figure:
    fig = go.Figure(go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2], color=color,
        flatshading=False, hoverinfo="skip",
        lighting=dict(ambient=0.35, diffuse=0.9, specular=0.1, roughness=0.9),
        lightposition=dict(x=-300, y=400 if light_back else -400, z=500)))
    ax = dict(visible=False)
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor=SKY,
                      scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data", bgcolor=SKY,
                                 camera=dict(eye=eye, up=dict(x=0, y=0, z=1))))
    return fig


def render(choice) -> None:
    source, p = choice if isinstance(choice, tuple) else (PARAMETRIC, choice)
    if source == SCAN:
        render_scan(p.height_mm, refined=False)
        return
    if source == BLEND:
        render_scan(p.height_mm, refined=True)
        return
    if source == MOLD:
        render_mold()
        return
    st.title("Moai statue — Rapa Nui, Rano Raraku style")
    st.caption(
        "**Parametric** model: no CC0 / CC-BY moai scan could be downloaded without a login, so this "
        "statue is sculpted in Python from documented moai proportions: elongated head ≈ 45 % of the height, "
        "heavy brow, long concave-bridged nose with flared nostrils, pursed lips, projecting chin, long ears, "
        "arms along the sides with long fingers over the belly, flat base. Units: **mm**."
    )
    v, f = _mesh(p, 160)
    ext = v.max(0) - v.min(0)
    ok = fits_bed(v)
    c1, c2, c3 = st.columns(3)
    c1.metric("Size X × Y × Z (mm)", f"{ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f}",
              delta=f"fits Ender-2 {ENDER2_BED_MM[0]:.0f}×{ENDER2_BED_MM[1]:.0f}×{ENDER2_BED_MM[2]:.0f}"
              if ok else "too big for the bed", delta_color="normal" if ok else "inverse")
    c2.metric("Height", f"{ext[2]:.1f} mm", help=f"{ext[2] / 25.4:.2f} in")
    c3.metric("Plinth", "yes" if p.plinth else "no")
    cols = st.columns(3)
    for col, (name, eye) in zip(cols, VIEWS.items()):
        with col:
            st.caption(name)
            st.plotly_chart(figure(v, f, eye), width="stretch")

    st.subheader("Download (mm)")
    if st.button("Prepare high-res STL", width="stretch"):
        hv, hf = _mesh(p, 300)
        st.session_state["moai_stl"] = (p, stl_bytes(hv, hf), len(hf))
    got = st.session_state.get("moai_stl")
    if got and got[0] == p:
        name = f"moai_{p.height_mm:.0f}mm.stl"
        st.download_button(f"Download {name} — {got[2]:,} triangles, {len(got[1]) / 1e6:.1f} MB",
                           data=got[1], file_name=name, mime="model/stl", width="stretch")
    st.caption(
        "Watertight marching-cubes mesh (≈0.5 mm grid at 152 mm), standing on z = 0. STEP is not offered: "
        "the statue is an organic mesh, and a faceted STEP of ~200 k triangles is not a useful CAD file. "
        "Print upright, 0.12–0.16 mm layers, supports *touching build plate* off and *everywhere* on "
        "(or tree supports) for the overhangs under the brow, nose, lips and chin."
    )


def render_scan(height_mm: float, refined: bool = False) -> None:
    title = "Moai head — refined scan v1 (ear/top blend)" if refined else "Moai head — real scan (Rano Raraku quarry moai)"
    st.title(title)
    st.caption(
        f"**Source:** [{moai_scan.TITLE}]({moai_scan.URL}) by **{moai_scan.AUTHOR}**, licensed "
        f"[{moai_scan.LICENSE}]({moai_scan.LICENSE_URL}). {moai_scan.CHANGES}"
        + (" **v1 blend:** localized Laplacian soften of ear-front and crown hard creases only; "
           "protected face displacement = 0; original asset bytes preserved." if refined else "")
    )
    if refined:
        v, f = moai_scan.blend_mesh(height_mm, preview=True)
        data = moai_scan.blend_stl_bytes(height_mm)
        name = moai_scan.blend_file_name(height_mm)
    else:
        v, f = moai_scan.head_mesh(height_mm, preview=True)
        data = moai_scan.stl_bytes(height_mm)
        name = moai_scan.file_name(height_mm)
    ext = v.max(0) - v.min(0)
    ok = fits_bed(v)
    c1, c2, c3 = st.columns(3)
    c1.metric("Size X × Y × Z (mm)", f"{ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f}",
              delta=f"fits Ender-2 {ENDER2_BED_MM[0]:.0f}×{ENDER2_BED_MM[1]:.0f}×{ENDER2_BED_MM[2]:.0f}"
              if ok else "too big for the bed", delta_color="normal" if ok else "inverse")
    c2.metric("Height", f"{ext[2]:.1f} mm", help=f"{ext[2] / 25.4:.2f} in")
    c3.metric("Topology", "genus 0", help="Watertight, one solid, Euler characteristic 2: no through-holes or tunnels.")
    cols = st.columns(4)
    for col, (name_v, eye) in zip(cols, SCAN_VIEWS.items()):
        with col:
            st.caption(name_v)
            st.plotly_chart(figure(v, f, eye, light_back=name_v == "Back"), width="stretch")
    st.caption(f"Preview: decimated copy ({len(f):,} triangles). The download is the full mold master.")

    st.subheader("Download (mm)")
    st.download_button(f"Download {name} — {len(data) / 1e6:.1f} MB", data=data, file_name=name,
                       mime="model/stl", width="stretch")
    st.caption(
        "Mold master: flat base, sculpted weathered back modelled on real moai (the scan never captured it), closed nostrils "
        "and no tunnels, so silicone can't lock in. "
        "Large undercuts (brow, nose, chin) remain; use a soft silicone (Shore 10–20 A) or a two-part mold. "
        "Print upright on the base, 0.12 mm layers, tree supports under the brow, nose and chin; "
        "sand / prime the print before molding. Credit the scan author on anything you sell (CC BY 4.0)."
    )


def render_mold() -> None:
    st.title("Moai mold tooling v1 — circular plate + cylindrical frame")
    st.caption(
        f"Integral tooling base under the **refined** scan head, with the same leak-free seating as the "
        f"small round tower v3: **{moai_mold.CLR:.2f} mm/side** frame clearance, **{moai_mold.GR_DEPTH} mm** "
        f"groove, vertical outer sealing lip and **{moai_mold.LIP_CHANNEL} mm** glue-bead channel. "
        f"Plate is tooling only (not a cast pedestal). No vents. "
        f"Source scan: [{moai_scan.TITLE}]({moai_scan.URL}) by {moai_scan.AUTHOR}, {moai_scan.LICENSE}."
    )
    parts = moai_mold.build_parts()
    d = moai_mold.dims_for()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Plate Ø × t", f"{d.plate_d:.1f} × {d.plate_t:.1f} mm")
    c2.metric("Frame ID / OD / H", f"{d.frame_id:.1f} / {d.frame_od:.1f} / {d.frame_len:.1f} mm")
    c3.metric("Silicone side / top", f"{d.silicone_side_mm:.1f} / {d.top_cover_mm:.1f} mm")
    c4.metric("Silicone (est.)", f"{d.silicone_ml:.0f} ml",
              help=f"π·(ID/2)²·(H+{moai_mold.OVER_APEX}) − statue volume")
    st.caption(
        f"Groove {d.groove_width:.2f} × {d.groove_depth:.1f} mm (wall {d.wall:.1f} + 2×{d.clearance_per_side:.2f}). "
        f"Lip Ø {d.lip_d_in:.1f}–{d.lip_d_out:.1f} mm. Soft silicone Shore 10–20A; brow/nose/chin undercuts — "
        f"prefer a rear/side release slit or ear-line two-piece mold; do not assume one-piece demold is lock-free."
    )
    vm, fm = parts["master"]
    vf, ff = parts["pour_frame"]
    cols = st.columns(2)
    with cols[0]:
        st.caption("Master (statue + plate + lip)")
        st.plotly_chart(figure(vm, fm, dict(x=1.8, y=-2.0, z=0.9)), width="stretch")
    with cols[1]:
        st.caption("Pour frame")
        st.plotly_chart(figure(vf, ff, dict(x=1.8, y=-2.0, z=0.9), color=FRAME), width="stretch")

    st.subheader("Download (mm)")
    for part, label in (("statue", "Refined statue only"), ("master", "Master with tooling base"),
                        ("pour_frame", "Pour frame")):
        data = moai_mold.stl_bytes(part)
        st.download_button(
            f"{label}: {moai_mold.file_name(part)} — {len(data) / 1e6:.1f} MB",
            data=data, file_name=moai_mold.file_name(part), mime="model/stl", width="stretch",
            key=f"dl_{part}",
        )
