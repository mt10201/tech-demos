"""Streamlit playground: Rodin coil card with 12 golden-ratio spanning grooves."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from code_snippet import generate_snippet
from geometry import PHI, CardParams, describe_formula, groove_specs
from rodin_card import build_rodin_coil_card, export_files, tessellate_mesh

st.set_page_config(
    page_title="Rodin coil card · build123d",
    page_icon="◎",
    layout="wide",
)

st.title("Rodin coil card")
st.caption(
    "Parametric CAD playground powered by **build123d**. "
    "A flat disk with **12 golden-ratio spanning grooves** on a Rodin-style "
    "12-pole / 30° layout — useful as a template card for geodesic-dome / "
    "toroidal coil experiments. Not a 3D-printer settings app."
)

with st.sidebar:
    st.header("Parameters")
    diameter = st.slider("Outer diameter D (mm)", 40.0, 200.0, 100.0, 1.0)
    thickness = st.slider("Thickness T (mm)", 1.0, 12.0, 4.0, 0.5)
    groove_width = st.slider("Groove width (mm)", 0.5, 10.0, 3.0, 0.1)
    groove_depth = st.slider(
        "Groove depth (mm)", 0.5, float(thickness), min(2.0, thickness), 0.1
    )
    phi_scale = st.slider("φ scale (L0 / band)", 0.30, 1.00, 0.85, 0.01)
    coil_factor = st.slider("Coil / vortex drift", 0.0, 1.0, 0.55, 0.01)
    rotation = st.slider("Global rotation θ₀ (°)", 0.0, 30.0, 0.0, 0.5)
    rim_fillet = st.slider("Rim fillet (mm)", 0.0, 2.0, 0.5, 0.1)
    st.markdown(f"**φ** = `(1+√5)/2` ≈ `{PHI:.6f}`")
    with st.expander("Formula"):
        st.code(describe_formula())

params = CardParams(
    diameter=diameter,
    thickness=thickness,
    groove_width=groove_width,
    groove_depth=groove_depth,
    phi_scale=phi_scale,
    coil_factor=coil_factor,
    rotation_deg=rotation,
    rim_fillet=rim_fillet,
)


@st.cache_data(show_spinner="Building Rodin coil card…")
def _cached_build(key: str, p: CardParams):
    part = build_rodin_coil_card(p)
    verts, faces = tessellate_mesh(part, linear_deflection=0.4)
    tmp = Path(tempfile.mkdtemp(prefix="rodin_ui_"))
    stl_path, step_path = export_files(part, tmp)
    return verts, faces, stl_path.read_bytes(), step_path.read_bytes(), part.volume


param_key = hashlib.sha256(repr(params).encode()).hexdigest()[:16]
verts, faces, stl_bytes, step_bytes, volume = _cached_build(param_key, params)
specs = groove_specs(params)

col_view, col_meta = st.columns([3, 2], gap="large")

with col_view:
    st.subheader("3D preview")
    i, j, k = faces[:, 0], faces[:, 1], faces[:, 2]
    fig = go.Figure(
        data=[
            go.Mesh3d(
                x=verts[:, 0],
                y=verts[:, 1],
                z=verts[:, 2],
                i=i,
                j=j,
                k=k,
                color="#c9a227",
                flatshading=True,
                lighting=dict(ambient=0.45, diffuse=0.8, specular=0.35, roughness=0.5),
                lightposition=dict(x=80, y=120, z=200),
                name="Rodin coil card",
            )
        ]
    )
    fig.update_layout(
        scene=dict(
            aspectmode="data",
            xaxis_title="X (mm)",
            yaxis_title="Y (mm)",
            zaxis_title="Z (mm)",
            bgcolor="#0e1117",
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=560,
        paper_bgcolor="#0e1117",
    )
    st.plotly_chart(fig, use_container_width=True)

with col_meta:
    st.subheader("Downloads")
    st.download_button(
        "Download STL",
        data=stl_bytes,
        file_name="rodin_coil_card.stl",
        mime="model/stl",
        use_container_width=True,
    )
    st.download_button(
        "Download STEP",
        data=step_bytes,
        file_name="rodin_coil_card.step",
        mime="application/step",
        use_container_width=True,
    )
    st.metric("Solid volume", f"{volume:.1f} mm³")
    st.subheader("Groove table")
    st.dataframe(
        [
            {
                "i": g.index,
                "θ°": round(g.angle_deg, 1),
                "r_start": round(g.r_start, 2),
                "r_end": round(g.r_end, 2),
                "span": round(g.span, 2),
                "φ^": round(g.phi_power, 3),
            }
            for g in specs
        ],
        hide_index=True,
        use_container_width=True,
    )

st.subheader("Generated build123d snippet")
st.code(generate_snippet(params), language="python")
