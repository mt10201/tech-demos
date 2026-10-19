"""Streamlit playground: Rodin torus with 12 golden-spiral semicircle grooves."""

from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from code_snippet import generate_snippet
from geometry import (
    PHI,
    TorusParams,
    all_paths,
    cutter_radius,
    describe_formula,
    golden_spiral_radius,
    min_strand_gap,
    projected_limits,
    start_angles_deg,
    sweeps,
    wrap_advance_deg,
)
from torus_mesh import grooved_torus_mesh, mesh_volume, stl_bytes

st.set_page_config(page_title="Rodin torus · build123d", page_icon="◎", layout="wide")

st.title("Rodin coil torus — 12 golden-spiral grooves")
st.caption(
    "Parametric CAD playground (**build123d** + Streamlit). A torus with **12 helical "
    "semicircle grooves**: each wraps once around the tube Rodin-style, and its top "
    "half is an exact **golden spiral** when viewed from above. Units: **inches** "
    "(matches the SOLIDWORKS sketch: R = 1.39, r = 0.695)."
)

with st.sidebar:
    st.header("Torus (in)")
    R = st.number_input("Major radius R (axis → tube centre)", 0.5, 6.0, 1.39, 0.01, format="%.3f")
    r = st.number_input("Tube radius r", 0.1, 3.0, 0.695, 0.005, format="%.3f")
    st.header("Grooves")
    depth = st.slider("Groove depth (in)", 0.125, 0.25, 0.1875, 1 / 64, format="%.4f")
    width = st.slider(
        "Groove width (in) — 2×depth = true semicircle",
        float(2 * depth), 0.75, float(2 * depth), 1 / 64, format="%.4f",
    )
    closure = st.radio(
        "Bottom half / closure",
        ["rodin", "mirror"],
        format_func=lambda c: {
            "rodin": "Rodin 150° skip — 12 grooves chain into one closed winding",
            "mirror": "Mirror golden spiral — 12 open grooves",
        }[c],
    )
    hand = st.radio("Handedness (from above)", [1, -1],
                    format_func=lambda h: "Counter-clockwise" if h == 1 else "Clockwise",
                    horizontal=True)
    rotation = st.slider("Start-pole rotation (°)", 0.0, 30.0, 0.0, 0.5)
    show_paths = st.checkbox("Overlay groove centre-lines", value=False)
    res = st.select_slider("Preview mesh", ["coarse", "medium", "fine"], value="fine")
    st.markdown(f"**φ** = `(1+√5)/2` ≈ `{PHI:.6f}`")
    with st.expander("Formula"):
        st.code(describe_formula())

try:
    params = TorusParams(
        major_radius=R, tube_radius=r, groove_depth=depth, groove_width=width,
        closure=closure, handedness=hand, rotation_deg=rotation,
    )
    top, bottom = sweeps(params)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

GRID = {"coarse": (96, 384), "medium": (150, 600), "fine": (220, 880)}


@st.cache_data(show_spinner="Meshing grooved torus…")
def _mesh(p: TorusParams, nt: int, nphi: int):
    return grooved_torus_mesh(p, n_theta=nt, n_phi=nphi)


@st.cache_data(show_spinner="Building STL…")
def _stl(p: TorusParams) -> bytes:
    v, f = grooved_torus_mesh(p, n_theta=240, n_phi=960)
    return stl_bytes(v, f)


@st.cache_data(show_spinner="Sweeping 12 groove cutters in build123d…")
def _step(p: TorusParams) -> bytes:
    from rodin_torus import step_bytes

    return step_bytes(p)


verts, faces = _mesh(params, *GRID[res])
paths = all_paths(params, 241)
q_min, q_max = projected_limits(params)
gap = min_strand_gap(params)

col_view, col_top = st.columns([3, 2], gap="large")

with col_view:
    st.subheader("3D preview")
    data = [
        go.Mesh3d(
            x=verts[:, 0], y=verts[:, 1], z=verts[:, 2],
            i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
            color="#c9a227", flatshading=False,
            lighting=dict(ambient=0.35, diffuse=0.85, specular=0.4, roughness=0.45, fresnel=0.2),
            lightposition=dict(x=3, y=4, z=6), name="torus", hoverinfo="skip",
        )
    ]
    if show_paths:
        for k, pth in enumerate(paths):
            data.append(go.Scatter3d(
                x=pth[:, 0], y=pth[:, 1], z=pth[:, 2], mode="lines",
                line=dict(color="#3b82f6", width=3), name=f"groove {k}", showlegend=False,
            ))
    fig = go.Figure(data=data)
    fig.update_layout(
        scene=dict(
            aspectmode="data", bgcolor="#0e1117",
            xaxis_title="X (in)", yaxis_title="Y (in)", zaxis_title="Z (in)",
            camera=dict(eye=dict(x=1.2, y=1.2, z=1.1)),
        ),
        margin=dict(l=0, r=0, t=0, b=0), height=560, paper_bgcolor="#0e1117",
    )
    st.plotly_chart(fig, use_container_width=True)

with col_top:
    st.subheader("Top view — golden spirals")
    tf = go.Figure()
    ring = np.linspace(0, 2 * math.pi, 361)
    for rad in (R - r, R + r):
        tf.add_trace(go.Scatter(x=rad * np.cos(ring), y=rad * np.sin(ring), mode="lines",
                                line=dict(color="#666", width=1), showlegend=False, hoverinfo="skip"))
    half = len(paths[0]) // 2  # samples 0..half = top half (θ 0→180°)
    for k, pth in enumerate(paths):
        lower = pth[half:]
        tf.add_trace(go.Scatter(x=lower[:, 0], y=lower[:, 1], mode="lines",
                                line=dict(color="#94a3b8", width=1.3, dash="dot"),
                                name="bottom half (hidden)", showlegend=k == 0, hoverinfo="skip"))
    for k, pth in enumerate(paths):
        upper = pth[: half + 1]
        tf.add_trace(go.Scatter(x=upper[:, 0], y=upper[:, 1], mode="lines",
                                line=dict(color="#3b82f6", width=2.5),
                                name="top half (golden spiral)", showlegend=k == 0, hoverinfo="skip"))
    # reference golden spiral (dashed), same start as groove 0, continued to the centre
    phi0 = math.radians(start_angles_deg(params)[0])
    dphi = np.linspace(0, top + 3 * math.pi, 800)
    qq = np.array([golden_spiral_radius(q_max, x) for x in dphi])
    ang = phi0 + hand * dphi
    tf.add_trace(go.Scatter(x=qq * np.cos(ang), y=qq * np.sin(ang), mode="lines",
                            line=dict(color="#f5c542", width=2, dash="dash"),
                            name="reference golden spiral (÷φ per 90°)"))
    lim = (R + r) * 1.08
    tf.update_layout(
        height=560, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117", font_color="#ddd",
        xaxis=dict(range=[-lim, lim], scaleanchor="y", showgrid=False, zeroline=False, title="X (in)"),
        yaxis=dict(range=[-lim, lim], showgrid=False, zeroline=False, title="Y (in)"),
        legend=dict(orientation="h", y=-0.08, font=dict(color="#e5e7eb")),
    )
    st.plotly_chart(tf, use_container_width=True)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Solid volume", f"{mesh_volume(verts, faces):.3f} in³")
m2.metric("Golden sweep (top half)", f"{math.degrees(top):.1f}°")
m3.metric("Advance per wrap", f"{wrap_advance_deg(params):.1f}°")
m4.metric("Cutter radius", f"{cutter_radius(params):.4f} in")
m5.metric("Strand gap at hole", f"{gap:.3f} in", delta=f"{gap - width:+.3f} vs width",
          delta_color="normal")
if gap < width:
    st.warning(
        f"At the inner equator neighbouring grooves are {gap:.3f}\" apart (centre-to-centre) "
        f"but {width:.3f}\" wide, so their edges merge slightly around the hole. "
        "Use a shallower depth (≤ ~0.18\") if every groove must stay separate."
    )

st.subheader("Downloads")
d1, d2 = st.columns(2)
with d1:
    st.download_button("Download STL (240×960 mesh)", data=_stl(params),
                       file_name="rodin_torus.stl", mime="model/stl", use_container_width=True)
with d2:
    if st.button("Build STEP bodies with build123d", use_container_width=True):
        try:
            st.session_state["step"] = (params, _step(params))
        except Exception as exc:  # sweeps can fail on extreme settings
            st.error(f"STEP build failed: {exc}")
    if st.session_state.get("step") and st.session_state["step"][0] == params:
        st.download_button("Download STEP", data=st.session_state["step"][1],
                           file_name="rodin_torus.step", mime="application/step",
                           use_container_width=True)
    st.caption(
        "STEP = exact B-rep **torus + 12 groove cutter bodies + centre-lines**. In SOLIDWORKS: "
        "Insert ▸ Features ▸ Combine ▸ **Subtract** (torus minus the 12 grooves). "
        "STL is the finished grooved part, ready to slice."
    )

st.subheader("Groove table")
st.dataframe(
    [
        {
            "groove": i,
            "start φ₀ (°)": round(a, 1),
            "ends at (°)": round((a + hand * wrap_advance_deg(params)) % 360, 1),
            "top sweep (°)": round(math.degrees(top), 1),
            "bottom sweep (°)": round(math.degrees(bottom), 1),
        }
        for i, a in enumerate(start_angles_deg(params))
    ],
    hide_index=True, use_container_width=True,
)

st.subheader("Generated build123d snippet")
st.code(generate_snippet(params), language="python")
