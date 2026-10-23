"""Streamlit 'Black Madonna' page: Chartres Black Madonna de Sous-Terre (Sedes Sapientiae), STL in mm."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

import madonna
from madonna import DEFAULT_HEIGHT_MM, ENDER2_BED_MM, MadonnaParams, build, fits_bed, stl_bytes

MASTER = "Photo-calibrated master: Chartres Madonna de Sous-Terre"
PARAMETRIC = "Custom parametric SDF (live rebuild)"

EBONY = "#3c3f46"
BG = "#e6e1d6"
VIEWS = {
    "Front": dict(x=0.0, y=-2.5, z=0.18),
    "3/4": dict(x=-1.55, y=-2.1, z=0.45),
    "Side": dict(x=2.5, y=0.0, z=0.15),
    "Back": dict(x=0.0, y=2.5, z=0.20),
}


def sidebar():
    st.sidebar.header("Black Madonna (mm)")
    source = st.sidebar.radio(
        "Model",
        [MASTER, PARAMETRIC],
        index=0,
        help="Photo-calibrated master: prebuilt high-resolution genus-0 mold master calibrated to "
             "front, profile, 3/4, and back studio photos of the Chartres Madonna de Sous-Terre. "
             "Custom parametric SDF: live signed-distance rebuild with adjustable relief, crown, and throne.",
    )
    h = st.sidebar.slider(
        "Overall height (mm)",
        40.0,
        200.0,
        float(DEFAULT_HEIGHT_MM),
        0.2,
        format="%.1f",
        help="101.6 mm = 4.0 in (default). Fits upright on the 150×150×200 mm Ender-2 bed.",
    )
    st.sidebar.caption(f"Height: **{h:.1f} mm** ({h / 25.4:.2f} in)")
    relief = 1.0
    crown = 1.0
    flare = 1.0
    plinth = False
    if source == PARAMETRIC:
        relief = st.sidebar.slider(
            "Photo-relief depth scale",
            0.0,
            1.8,
            1.0,
            0.1,
            help="Blend weight of the multi-angle studio photo relief map on the drapery, crown, and veil.",
        )
        crown = st.sidebar.slider(
            "Crown peak height scale",
            0.6,
            1.4,
            1.0,
            0.05,
            help="Relative height of the six trefoil / fleur-de-lis Romanesque crown peaks.",
        )
        flare = st.sidebar.slider(
            "Front throne-post flare",
            0.0,
            1.6,
            1.0,
            0.1,
            help="Outward trapezoidal splay of the front throne posts so all four finials are visible from the front.",
        )
        plinth = st.sidebar.checkbox(
            "Extra sub-plinth",
            value=False,
            help="Add an extra 5 mm rectangular block under the integral statue plinth (3 mm wider all round).",
        )
    return source, MadonnaParams(
        height_mm=h,
        relief_scale=relief,
        crown_height_scale=crown,
        throne_flare=flare,
        plinth=plinth,
    )


@st.cache_data(show_spinner="Sculpting Black Madonna (signed-distance model)…", max_entries=6)
def _mesh(p: MadonnaParams, resolution: int):
    return build(
        MadonnaParams(
            height_mm=p.height_mm,
            relief_scale=p.relief_scale,
            crown_height_scale=p.crown_height_scale,
            throne_flare=p.throne_flare,
            plinth=p.plinth,
            plinth_height_mm=p.plinth_height_mm,
            plinth_margin_mm=p.plinth_margin_mm,
            resolution=resolution,
        )
    )


def figure(v, f, eye, height=520, light_back=False) -> go.Figure:
    fig = go.Figure(
        go.Mesh3d(
            x=v[:, 0],
            y=v[:, 1],
            z=v[:, 2],
            i=f[:, 0],
            j=f[:, 1],
            k=f[:, 2],
            color=EBONY,
            flatshading=False,
            hoverinfo="skip",
            lighting=dict(ambient=0.36, diffuse=0.88, specular=0.22, roughness=0.55, fresnel=0.15),
            lightposition=dict(x=-260, y=380 if light_back else -380, z=480),
        )
    )
    ax = dict(visible=False)
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=BG,
        scene=dict(
            xaxis=ax,
            yaxis=ax,
            zaxis=ax,
            aspectmode="data",
            bgcolor=BG,
            camera=dict(eye=eye, up=dict(x=0, y=0, z=1)),
        ),
    )
    return fig


def render(choice) -> None:
    source, p = choice if isinstance(choice, tuple) else (MASTER, choice)
    if source == MASTER:
        render_master(p.height_mm)
        return

    st.title("Black Madonna de Sous-Terre — Custom Parametric SDF")
    st.caption(
        "**Live signed-distance sculpture** of the Chartres Cathedral *Notre-Dame de Sous-Terre* "
        "(*Sedes Sapientiae* / Throne of Wisdom): rounded rectangular base plinth with sloped footrest step, "
        "four-post Romanesque throne with spherical finials and solid backrest, seated Madonna with six-peak "
        "trefoil crown, pleated chest mantle, and hands encircling the Christ Child (blessing hand + orb). "
        "All overhangs and gaps are bridged into a single **genus-0 (`euler_number == 2`)** solid. Units: **mm**."
    )
    v, f = _mesh(p, 150)
    ext = v.max(0) - v.min(0)
    ok = fits_bed(v)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Size X × Y × Z (mm)",
        f"{ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f}",
        delta=f"fits Ender-2 {ENDER2_BED_MM[0]:.0f}×{ENDER2_BED_MM[1]:.0f}×{ENDER2_BED_MM[2]:.0f}"
        if ok
        else "too big for the bed",
        delta_color="normal" if ok else "inverse",
    )
    c2.metric("Height", f"{ext[2]:.1f} mm", delta=f"{ext[2] / 25.4:.2f} in", delta_color="off")
    c3.metric("Topology", "genus 0 (Euler 2)", help="Watertight single shell with zero through-holes or tunnels.")
    c4.metric("Extra sub-plinth", "yes" if p.plinth else "no")

    cols = st.columns(4)
    for col, (name, eye) in zip(cols, VIEWS.items()):
        with col:
            st.caption(name)
            st.plotly_chart(figure(v, f, eye, light_back=name == "Back"), use_container_width=True)

    st.subheader("Download (mm)")
    if st.button("Prepare high-res STL", use_container_width=True):
        hv, hf = _mesh(p, 220)
        st.session_state["madonna_stl"] = (p, stl_bytes(hv, hf), len(hf))
    got = st.session_state.get("madonna_stl")
    if got and got[0] == p:
        name = madonna.file_name(p.height_mm)
        st.download_button(
            f"Download {name} — {got[2]:,} triangles, {len(got[1]) / 1e6:.2f} MB",
            data=got[1],
            file_name=name,
            mime="model/stl",
            use_container_width=True,
        )


def render_master(height_mm: float) -> None:
    st.title("Black Madonna de Sous-Terre — Chartres Cathedral (Sedes Sapientiae)")
    st.caption(
        "**Subject:** 11th/12th-century Romanesque *Notre-Dame de Sous-Terre* (*Virgo Paritura* / *Sedes Sapientiae*, "
        "Chartres Cathedral crypt), modelled from multi-angle studio views (front, left/right profiles, 3/4, and back) "
        "of the Sacred Source `#BMT` statue. **License:** **CC0 1.0 Public Domain** (commercial casting & derivatives "
        "permitted; existing Brussels/Scan-The-World *Sedes Sapientiae* scans are CC BY-NC and were excluded)."
    )
    v, f = madonna.master_mesh(height_mm, preview=True)
    ext = v.max(0) - v.min(0)
    ok = fits_bed(v)
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Size X × Y × Z (mm)",
        f"{ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f}",
        delta=f"fits Ender-2 {ENDER2_BED_MM[0]:.0f}×{ENDER2_BED_MM[1]:.0f}×{ENDER2_BED_MM[2]:.0f}"
        if ok
        else "too big for the bed",
        delta_color="normal" if ok else "inverse",
    )
    c2.metric("Height", f"{ext[2]:.1f} mm", delta=f"{ext[2] / 25.4:.2f} in", delta_color="off")
    c3.metric(
        "Topology",
        "genus 0",
        delta="watertight · 1 shell · Euler 2",
        help="Watertight single manifold shell with Euler characteristic 2: zero through-holes or silicone-trapping tunnels.",
    )

    cols = st.columns(4)
    for col, (name, eye) in zip(cols, VIEWS.items()):
        with col:
            st.caption(name)
            st.plotly_chart(figure(v, f, eye, light_back=name == "Back"), use_container_width=True)
    st.caption(
        f"Interactive 4-angle preview ({len(f):,} triangles). The download below is the full high-resolution mold master."
    )

    comp_img = Path(__file__).resolve().parent / "media" / "black_madonna_compare.png"
    if comp_img.exists():
        with st.expander("Multi-angle studio reference vs. 3D mold master (Front · 3/4 · Profile · Back)"):
            st.image(
                str(comp_img),
                caption="Top row: multi-angle studio photos (Front, 3/4, Profile, Back). "
                        "Bottom row: 101.6 mm (4.0 in) watertight genus-0 mold master.",
                use_container_width=True,
            )

    st.subheader("Download (mm)")
    data = madonna.master_stl_bytes(height_mm)
    name = madonna.file_name(height_mm)
    st.download_button(
        f"Download {name} — 68,246 triangles, {len(data) / 1e6:.2f} MB",
        data=data,
        file_name=name,
        mime="model/stl",
        use_container_width=True,
    )
    st.caption(
        "Mold-master geometry: flat base on z = 0 (seals cleanly on a mold board), solid four-post Romanesque throne "
        "with spherical ball finials and smooth backrest, relief-sculpted crown and blessing hand with no open tunnels "
        "so poured silicone cannot lock or tear."
    )
