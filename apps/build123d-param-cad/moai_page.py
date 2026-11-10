"""Streamlit 'Moai statue' page: real-scan moai head (default), v1 blend, mold tooling, or parametric."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import moai_mold
import moai_scan
import moai_v2
from moai import DEFAULT_HEIGHT_MM, ENDER2_BED_MM, MoaiParams, build, fits_bed, stl_bytes

SCAN = "Real scan: Quarry Moai head (original)"
V2 = "Moai v2 hi-res master + mold base (rebuilt back, organic ear/crown join)"
BLEND = "Ear/top blend v1 — SUPERSEDED by v2 (not recommended for reprinting)"
MOLD = "Mold tooling v1 — SUPERSEDED by v2 (not recommended for reprinting)"
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
        [SCAN, V2, BLEND, MOLD, PARAMETRIC],
        index=0,
        help="Original scan is the default and is preserved. v2 = hi-res rebuild with the integral round tooling base and pour frame. v1 blend/tooling are superseded REVIEW CANDIDATES, not recommended for reprinting until the ear transition is reviewed. "
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
    if source == V2:
        render_v2()
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
    title = "Moai head — v1 blend, SUPERSEDED by v2" if refined else "Moai head — real scan (Rano Raraku quarry moai)"
    st.title(title)
    st.caption(
        f"**Source:** [{moai_scan.TITLE}]({moai_scan.URL}) by **{moai_scan.AUTHOR}**, licensed "
        f"[{moai_scan.LICENSE}]({moai_scan.LICENSE_URL}). {moai_scan.CHANGES}"
        + (" **v1 blend:** localized Laplacian soften of ear-front and crown hard creases only; "
           "hard face mask, both eye masks and eyelid mask displacement = 0 (not the whole face); original asset bytes preserved." if refined else "")
    )
    if refined:
        st.warning("REVIEW CANDIDATE — not recommended for reprinting until the ear transition is reviewed. The straight ear join remains visible; reduced crease counts do not establish a successful organic blend. Eye photo needed to diagnose the reported print defect; no cause is assigned.")
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
    st.title("Moai mold tooling v1 — SUPERSEDED by v2")
    st.warning("REVIEW CANDIDATE — blend and integral master are not recommended for reprinting until the ear transition is reviewed. Straight ear joins remain visible. Tooling geometry is for review, not a print-ready approval.")
    st.caption(
        f"Integral tooling base under the **review-candidate** scan head, using the same seating geometry as the "
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
    c3.metric("Silicone side / top", f"{d.silicone_side_mm:.1f} / {d.top_cover_mm:.1f} mm",
              help=f"Actual top cover above exposed head {d.exposed_head_mm:.1f} mm (statue {d.statue_height_mm:.1f} with {d.statue_sink_mm:.1f} mm plate sink); fill {d.fill_above_plate_mm:.1f} mm. OVER_APEX param={d.over_apex_param_mm:.1f}.")
    c4.metric("Silicone (est.)", f"{d.silicone_ml:.0f} ml",
              help="Estimated cavity above the plate minus exposed statue volume (0.5 mm embed excluded); mixing/cup losses excluded.")
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
    for part, label in (("statue", "REVIEW CANDIDATE statue only"), ("master", "REVIEW CANDIDATE master with tooling base"),
                        ("pour_frame", "Pour frame")):
        data = moai_mold.stl_bytes(part)
        st.download_button(
            f"{label}: {moai_mold.file_name(part)} — {len(data) / 1e6:.1f} MB",
            data=data, file_name=moai_mold.file_name(part), mime="model/stl", width="stretch",
            key=f"dl_{part}",
        )


def render_v2() -> None:
    st.title("Moai v2 hi-res master — integral round mold base + pour frame")
    st.caption(
        f"Rebuilt from the original scan [{moai_scan.TITLE}]({moai_scan.URL}) by **{moai_scan.AUTHOR}** "
        f"([{moai_scan.LICENSE}]({moai_scan.LICENSE_URL}), modified) on a 0.25 mm grid, 740k triangles, 152.4 mm. "
        "The straight lines behind the ears and across the crown were where the half-buried quarry statue met the "
        "soil (the scan ends there); v2 morphs the scan into a new rounded back (4 mm signed-distance blend, back 2 mm "
        "narrower than the ears) instead of cutting it with a plane. The face is the same scan, re-meshed finer. "
        "Tooling: tower v3 seating, **0.25 mm/side**, groove 3.5 × 1.6 mm, vertical outer lip + 1.5 mm glue channel. No vents."
    )
    st.info("Verified on the box: watertight, one body, genus 0, no self-intersecting triangle pairs. Not yet printed — "
            "review the renders (ears, crown) before printing. Eye defect from the last print is not diagnosed (photo pending).")
    d = moai_v2.dims()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Plate Ø × t", f"{d.plate_d:.1f} × {d.plate_t:.1f} mm")
    c2.metric("Frame ID / OD / H", f"{d.frame_id:.1f} / {d.frame_od:.1f} / {d.frame_len:.1f} mm")
    c3.metric("Silicone side / top", f"≥10.0 / {d.top_cover_mm:.1f} mm",
              help="Side measured to the flat faces of the 192-sided frame bore; top = cover over the exposed head.")
    c4.metric("Silicone (est.)", f"{d.silicone_ml:.0f} ml", help="Cavity above the plate minus the exposed statue; mixing/cup losses excluded.")
    v, f = moai_v2.preview_mesh()
    cols = st.columns(4)
    for col, (name_v, eye) in zip(cols, SCAN_VIEWS.items()):
        with col:
            st.caption(name_v)
            st.plotly_chart(figure(v, f, eye, light_back=name_v == "Back"), width="stretch", key=f"v2_{name_v}")
    st.caption(f"Preview: decimated copy ({len(f):,} triangles). Downloads are full resolution.")
    st.subheader("Download (mm)")
    if st.button("Prepare v2 master + frame STLs (builds the tooling, ~20 s)", width="stretch"):
        st.session_state["moai_v2"] = {k: moai_v2.stl_bytes(k) for k in ("master", "pour_frame")}
    data = moai_v2.stl_bytes("statue")
    st.download_button(f"Statue only: {moai_v2.FILES['statue']} — {len(data) / 1e6:.1f} MB", data=data,
                       file_name=moai_v2.FILES["statue"], mime="model/stl", width="stretch", key="dl_v2_statue")
    got = st.session_state.get("moai_v2")
    if got:
        for part, label in (("master", "Master with integral base"), ("pour_frame", "Pour frame")):
            st.download_button(f"{label}: {moai_v2.FILES[part]} — {len(got[part]) / 1e6:.1f} MB", data=got[part],
                               file_name=moai_v2.FILES[part], mime="model/stl", width="stretch", key=f"dl_v2_{part}")
    st.caption("Soft silicone Shore 10–20A. Brow/nose/chin undercuts remain: plan a rear release slit "
               "(down the back centre-line) or an ear-line two-piece mold. Print the master upright on the plate.")
