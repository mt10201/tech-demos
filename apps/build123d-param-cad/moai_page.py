"""Streamlit 'Moai statue' page: parametric Rapa Nui moai, STL in mm."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from moai import DEFAULT_HEIGHT_MM, ENDER2_BED_MM, MoaiParams, build, fits_bed, stl_bytes

STONE = "#8a7f73"
SKY = "#bcd4ea"
VIEWS = {
    "Front": dict(x=0.0, y=-2.6, z=0.15),
    "Side": dict(x=2.6, y=0.0, z=0.15),
    "3/4": dict(x=1.6, y=-2.1, z=0.55),
}


def sidebar() -> MoaiParams:
    st.sidebar.header("Moai statue (mm)")
    h = st.sidebar.number_input("Overall height (mm)", 40.0, 200.0, float(DEFAULT_HEIGHT_MM), 0.1,
                                format="%.1f", help="152.4 mm = 6 in. Includes the plinth if enabled.")
    plinth = st.sidebar.checkbox("Base plinth", value=False,
                                 help="A 6 mm block under the statue, 4 mm wider all round (better bed grip).")
    return MoaiParams(height_mm=h, plinth=plinth)


@st.cache_data(show_spinner="Sculpting the moai (signed-distance model)…", max_entries=6)
def _mesh(p: MoaiParams, resolution: int):
    v, f = build(MoaiParams(p.height_mm, p.plinth, p.plinth_height_mm, p.plinth_margin_mm, resolution))
    return v, f


def figure(v, f, eye, height=560) -> go.Figure:
    fig = go.Figure(go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2], color=STONE,
        flatshading=False, hoverinfo="skip",
        lighting=dict(ambient=0.35, diffuse=0.9, specular=0.1, roughness=0.9),
        lightposition=dict(x=-300, y=-400, z=500)))
    ax = dict(visible=False)
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor=SKY,
                      scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data", bgcolor=SKY,
                                 camera=dict(eye=eye, up=dict(x=0, y=0, z=1))))
    return fig


def render(p: MoaiParams) -> None:
    st.subheader("Moai statue — Rapa Nui, Rano Raraku style")
    st.caption(
        "**Parametric** model: no CC0 / CC-BY moai scan could be downloaded without a login, so this "
        "statue is sculpted in Python from documented moai proportions: elongated head ≈ 45 % of the height, "
        "heavy brow, long concave-bridged nose with flared nostrils, pursed lips, projecting chin, long ears, "
        "arms along the sides with long fingers over the belly, flat base. Units: **mm**."
    )
    v, f = _mesh(p, 160)  # live preview
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
            st.plotly_chart(figure(v, f, eye), use_container_width=True)

    st.subheader("Download (mm)")
    if st.button("Prepare high-res STL", use_container_width=True):
        hv, hf = _mesh(p, 300)
        st.session_state["moai_stl"] = (p, stl_bytes(hv, hf), len(hf))
    got = st.session_state.get("moai_stl")
    if got and got[0] == p:
        name = f"moai_{p.height_mm:.0f}mm.stl"
        st.download_button(f"Download {name} — {got[2]:,} triangles, {len(got[1]) / 1e6:.1f} MB",
                           data=got[1], file_name=name, mime="model/stl", use_container_width=True)
    st.caption(
        "Watertight marching-cubes mesh (≈0.5 mm grid at 152 mm), standing on z = 0. STEP is not offered: "
        "the statue is an organic mesh, and a faceted STEP of ~200 k triangles is not a useful CAD file. "
        "Print upright, 0.12–0.16 mm layers, supports *touching build plate* off and *everywhere* on "
        "(or tree supports) for the overhangs under the brow, nose, lips and chin."
    )
