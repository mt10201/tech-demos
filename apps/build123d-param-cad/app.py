"""Streamlit playground: Rodin coil torus — photo-replica groove lattice."""

from __future__ import annotations

import colorsys
import math

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from code_snippet import generate_snippet
from geometry import (
    wall_height,
    PATTERN_LABELS,
    PATTERNS,
    PHI,
    PHOTO_SWEEP_DEG,
    TorusParams,
    all_paths,
    cutter_radius,
    describe_formula,
    families,
    golden_spiral_radius,
    min_wall,
    projected_limits,
    start_angles_deg,
    sweeps,
    wrap_advance_deg,
)
from torus_mesh import (
    EXPORT_GRID,
    PREVIEW_GRID,
    GrooveField,
    cross_profile,
    grooved_torus_mesh,
    measure_width,
    mesh_volume,
    patch_mesh,
    stl_bytes,
)

st.set_page_config(page_title="Rodin torus · build123d", page_icon="◎", layout="wide")

st.title("Rodin coil torus — groove lattice")
st.caption(
    "Parametric CAD playground (**build123d** + Streamlit). Default preset **Photo replica**: "
    "12 + 12 constant-width U-grooves (1/8\" wide × 1/8\" deep) spiralling in both directions, leaving raised rhombus tiles "
    "like the rainbow Rodin coil frame. Units: **inches** (SOLIDWORKS sketch: R = 1.39, r = 0.695)."
)

with st.sidebar:
    st.header("Preset")
    pattern = st.radio("Groove pattern", list(PATTERNS), format_func=PATTERN_LABELS.get)
    st.header("Torus (in)")
    R = st.number_input("Major radius R (axis → tube centre)", 0.5, 6.0, 1.39, 0.01, format="%.3f")
    r = st.number_input("Tube radius r", 0.1, 3.0, 0.695, 0.005, format="%.3f")
    st.header("Grooves")
    width = st.slider("Groove width (in, true 3D)", 0.0625, 0.5, 0.125, 1 / 64, format="%.4f")
    depth = st.slider(
        "Groove depth (in)", 0.03125, 0.25, 0.125, 1 / 64, format="%.4f",
        help="depth > width/2 → U-groove (semicircle bottom + straight walls); "
             "depth = width/2 → semicircle; depth < width/2 → shallow arc.",
    )
    sweep = PHOTO_SWEEP_DEG
    if pattern == "photo":
        sweep = st.slider(
            "Sweep rim → hole (°)", 60.0, 240.0, PHOTO_SWEEP_DEG, 15.0,
            help="How far around the axis each groove travels between the outer rim and the "
                 "hole. ≈150° measured from the photo. Multiples of 15° keep every groove "
                 "joined end-to-start into closed loops.",
        )
    hand = st.radio("Handedness", [1, -1],
                    format_func=lambda h: "Counter-clockwise" if h == 1 else "Clockwise",
                    horizontal=True)
    rotation = st.slider("Start-pole rotation (°)", 0.0, 30.0, 0.0, 0.5)
    show_paths = st.checkbox("Overlay groove centre-lines (3D)", value=False)
    st.markdown(f"**φ** = `(1+√5)/2` ≈ `{PHI:.6f}`")

try:
    params = TorusParams(
        major_radius=R, tube_radius=r, groove_depth=depth, groove_width=width,
        pattern=pattern, sweep_deg=sweep, handedness=hand, rotation_deg=rotation,
    )
    top, bottom = sweeps(params)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

with st.sidebar.expander("Formula"):
    st.code(describe_formula(params))


@st.cache_data(show_spinner="Meshing grooved torus…", max_entries=8)
def _mesh(p: TorusParams):
    return grooved_torus_mesh(p, *PREVIEW_GRID, return_depth=True)


@st.cache_data(show_spinner="Meshing high-res STL…", max_entries=2)
def _stl(p: TorusParams):
    v, f = grooved_torus_mesh(p, *EXPORT_GRID)
    return stl_bytes(v, f), len(f)


@st.cache_data(show_spinner="Sweeping groove cutters in build123d…", max_entries=2)
def _step(p: TorusParams) -> bytes:
    from rodin_torus import step_bytes

    return step_bytes(p)


@st.cache_data(max_entries=16)
def _wall(p: TorusParams):
    return min_wall(p)


def rainbow_colors(verts: np.ndarray, gdepth: np.ndarray, p: TorusParams) -> np.ndarray:
    """Tiles: rainbow by azimuth (purple at top, like the photo). Grooves: copper."""
    az = np.degrees(np.arctan2(verts[:, 1], verts[:, 0]))  # 0 = right, 90 = top
    hue = ((az - 90.0) / 360.0 + 0.78) % 1.0
    rgb = np.array([colorsys.hsv_to_rgb(h, 0.7, 0.95) for h in np.round(hue, 3)])
    t = np.clip(gdepth / (0.35 * p.groove_depth), 0.0, 1.0)[:, None]  # 0 tile → 1 groove
    copper = np.array([0.80, 0.47, 0.22])
    return (255 * ((1 - t) * rgb + t * copper)).astype(int)


verts, faces, gdepth = _mesh(params)
paths = all_paths(params, 241)
wall, wall_theta = _wall(params)

col_view, col_front = st.columns(2, gap="medium")

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
                line=dict(color="#3b82f6", width=3), showlegend=False,
            ))
    fig = go.Figure(data=data)
    fig.update_layout(
        scene=dict(
            aspectmode="data", bgcolor="#0e1117",
            xaxis_title="X (in)", yaxis_title="Y (in)", zaxis_title="Z (in)",
            camera=dict(eye=dict(x=1.15, y=1.15, z=1.05)),
        ),
        margin=dict(l=0, r=0, t=0, b=0), height=560, paper_bgcolor="#0e1117",
    )
    st.plotly_chart(fig, use_container_width=True)

with col_front:
    st.subheader("Front view (along the axis, photo-style)")
    front = go.Figure(go.Mesh3d(
        x=verts[:, 0], y=verts[:, 1], z=verts[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        vertexcolor=[f"rgb({a},{b},{c})" for a, b, c in rainbow_colors(verts, gdepth, params)],
        flatshading=False,
        lighting=dict(ambient=0.55, diffuse=0.7, specular=0.45, roughness=0.35, fresnel=0.2),
        lightposition=dict(x=-3, y=5, z=10), hoverinfo="skip",
    ))
    noax = dict(visible=False, showbackground=False)
    front.update_layout(
        scene=dict(
            aspectmode="data", xaxis=noax, yaxis=noax, zaxis=noax, bgcolor="#f4f4f4",
            camera=dict(eye=dict(x=0, y=0, z=2.0), up=dict(x=0, y=1, z=0),
                        projection=dict(type="orthographic")),
            dragmode="orbit",
        ),
        margin=dict(l=0, r=0, t=0, b=0), height=560, paper_bgcolor="#f4f4f4",
    )
    st.plotly_chart(front, use_container_width=True)

h_wall = wall_height(params)
prof = ("U-groove" if h_wall > 1e-9 else
        "semicircle" if abs(depth - width / 2) < 1e-9 else "shallow arc")
st.caption(
    f"Profile: **{prof}**, {width:.4f}\" wide × {depth:.4f}\" deep (bottom radius "
    f"{cutter_radius(params):.4f}\"{f', walls {h_wall:.4f}' + chr(34) if h_wall > 1e-9 else ''}). "
    "Width is measured in true 3D, so it is identical on the rim, top, hole and bottom."
)
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Solid volume", f"{mesh_volume(verts, faces):.3f} in³")
m2.metric("Grooves", f"{len(paths)}  ({' + '.join(str(params.n_grooves) for _ in families(params))})")
m3.metric("Sweep rim → hole", f"{math.degrees(top):.1f}°")
m4.metric("Advance per wrap", f"{wrap_advance_deg(params):.1f}°")
m5.metric("Min wall between grooves", f"{wall:.3f} in", help=f"at θ ≈ {wall_theta:.0f}° (180° = hole)")
if wall < 0:
    st.warning(
        f"Neighbouring grooves of the same direction **merge** near θ ≈ {wall_theta:.0f}° "
        f"(180° = the hole): centre-lines are {wall + width:.3f}\" apart but grooves are "
        f"{width:.3f}\" wide, so the wall between them is {wall:.3f}\" (no tile left there). "
        "Reduce depth/width, use fewer grooves, or a smaller sweep."
    )
elif wall < 0.04:
    st.warning(
        f"Thinnest wall between neighbouring grooves is only **{wall:.3f}\"** "
        f"(near θ ≈ {wall_theta:.0f}°, 180° = hole). It will print but be fragile; "
        "check your printer's minimum feature size."
    )

st.subheader("Close-up: rim vs hole at the same scale")


@st.cache_data(show_spinner="Rendering close-ups…", max_entries=4)
def _closeups(p: TorusParams):
    field = GrooveField(p)
    g0 = field.paths[0]
    n = len(g0)
    out = []
    # 9° past a crossing with the other family (crossings every 180/(2k)° of θ)
    for label, th in (("Outer rim", 9.0), ("Top", 99.0), ("Inner hole", 189.0), ("Bottom", 279.0)):
        j = int(round(th / 360 * (n - 1)))
        S = g0[j]
        theta_c = math.atan2(S[2], math.hypot(S[0], S[1]) - p.major_radius)
        phi_c = math.atan2(S[1], S[0])
        w = measure_width(p, g0, j, field)
        s, dep = cross_profile(p, g0, j, field)
        out.append((label, theta_c, phi_c, w, s, dep))
    patches = {lab: patch_mesh(p, tc, pc, half=0.3, n=170, field=field)
               for lab, tc, pc, *_ in (out[0], out[2])}
    return out, patches


cl, patches = _closeups(params)
cz = st.columns(3)
for col, lab in zip(cz[:2], ("Outer rim", "Inner hole")):
    v, f, dp, ctrp, nc = patches[lab]
    t = np.clip(dp / (0.35 * params.groove_depth), 0, 1)
    cols = (255 * ((1 - t)[:, None] * np.array([0.55, 0.62, 0.95]) + t[:, None] * np.array([0.80, 0.47, 0.22]))).astype(int)
    vv = v - ctrp
    figp = go.Figure(go.Mesh3d(
        x=vv[:, 0], y=vv[:, 1], z=vv[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2],
        vertexcolor=[f"rgb({a},{b},{c})" for a, b, c in cols], flatshading=False,
        lighting=dict(ambient=0.5, diffuse=0.8, specular=0.3), hoverinfo="skip",
    ))
    rng = [-0.32, 0.32]
    noax = dict(visible=False, range=rng)
    eye = nc * 1.1 + np.array([0, 0, 0.35])
    figp.update_layout(
        scene=dict(xaxis=noax, yaxis=noax, zaxis=noax, aspectmode="cube",
                   camera=dict(eye=dict(x=eye[0], y=eye[1], z=eye[2]), up=dict(x=0, y=0, z=1),
                               projection=dict(type="orthographic")),
                   bgcolor="#f4f4f4"),
        margin=dict(l=0, r=0, t=30, b=0), height=360, paper_bgcolor="#f4f4f4",
        title=dict(text=f"{lab} (0.6\" patch)", x=0.5, font=dict(color="#222", size=13)),
    )
    col.plotly_chart(figp, use_container_width=True)
with cz[2]:
    pf = go.Figure()
    for (lab, _, _, w, s_, dep_), colr in zip(cl, ["#ef4444", "#22c55e", "#3b82f6", "#a855f7"]):
        pf.add_trace(go.Scatter(x=s_, y=-dep_, mode="lines", line=dict(color=colr, width=2),
                                name=f"{lab}: {w:.4f}\" wide"))
    pf.update_layout(
        height=360, margin=dict(l=10, r=10, t=30, b=10),
        title=dict(text="Cross-section ⟂ path (true 3D)", x=0.5, font=dict(size=13)),
        xaxis_title="lateral offset (in)", yaxis_title="depth (in)",
        yaxis=dict(scaleanchor="x"), legend=dict(orientation="h", y=-0.3),
    )
    st.plotly_chart(pf, use_container_width=True)

st.subheader("Downloads")
d1, d2 = st.columns(2)
with d1:
    if st.button(f"Prepare high-res STL ({EXPORT_GRID[0]}×{EXPORT_GRID[1]} grid)",
                 use_container_width=True):
        st.session_state["stl"] = (params, *_stl(params))
    if st.session_state.get("stl") and st.session_state["stl"][0] == params:
        _, data_bytes, ntri = st.session_state["stl"]
        st.download_button(f"Download STL — {ntri:,} triangles, {len(data_bytes)/1e6:.0f} MB",
                           data=data_bytes, file_name=f"rodin_torus_{pattern}.stl",
                           mime="model/stl", use_container_width=True)
    st.caption("STL = finished, watertight grooved solid, ready to slice.")
with d2:
    if st.button("Build STEP bodies with build123d", use_container_width=True):
        try:
            st.session_state["step"] = (params, _step(params))
        except Exception as exc:  # sweeps can fail on extreme settings
            st.error(f"STEP build failed: {exc}")
    if st.session_state.get("step") and st.session_state["step"][0] == params:
        st.download_button("Download STEP", data=st.session_state["step"][1],
                           file_name=f"rodin_torus_{pattern}.step", mime="application/step",
                           use_container_width=True)
    st.caption(
        "STEP = exact B-rep **torus + groove cutter bodies + centre-lines**. In SOLIDWORKS: "
        "Insert ▸ Features ▸ Combine ▸ **Subtract** (torus minus all grooves)."
    )

with st.expander("Groove centre-line diagram (front view)"):
    tf = go.Figure()
    ring = np.linspace(0, 2 * math.pi, 361)
    for rad in (R - r, R + r):
        tf.add_trace(go.Scatter(x=rad * np.cos(ring), y=rad * np.sin(ring), mode="lines",
                                line=dict(color="#666", width=1), showlegend=False, hoverinfo="skip"))
    half = len(paths[0]) // 2
    colors = ["#3b82f6", "#f97316"]
    for k, pth in enumerate(paths):
        fam = k // params.n_grooves
        upper = pth[: half + 1]
        tf.add_trace(go.Scatter(x=upper[:, 0], y=upper[:, 1], mode="lines",
                                line=dict(color=colors[fam], width=2),
                                name=f"direction {'+' if families(params)[fam] > 0 else '−'} (front half)",
                                showlegend=k % params.n_grooves == 0, hoverinfo="skip"))
    if pattern != "photo":
        q_min, q_max = projected_limits(params)
        phi0 = math.radians(start_angles_deg(params)[0])
        dphi = np.linspace(0, top + 3 * math.pi, 800)
        qq = np.array([golden_spiral_radius(q_max, x) for x in dphi])
        ang = phi0 + hand * dphi
        tf.add_trace(go.Scatter(x=qq * np.cos(ang), y=qq * np.sin(ang), mode="lines",
                                line=dict(color="#f5c542", width=2, dash="dash"),
                                name="reference golden spiral (÷φ per 90°)"))
    lim = (R + r) * 1.08
    tf.update_layout(
        height=520, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117", font_color="#ddd",
        xaxis=dict(range=[-lim, lim], scaleanchor="y", showgrid=False, zeroline=False, title="X (in)"),
        yaxis=dict(range=[-lim, lim], showgrid=False, zeroline=False, title="Y (in)"),
        legend=dict(orientation="h", y=-0.08, font=dict(color="#e5e7eb")),
    )
    st.plotly_chart(tf, use_container_width=True)

st.subheader("Groove table")
st.dataframe(
    [
        {
            "groove": k,
            "direction": "+" if fam > 0 else "−",
            "start φ₀ (°)": round(a, 1),
            "ends at (°)": round((a + fam * wrap_advance_deg(params)) % 360, 1),
            "front sweep (°)": round(math.degrees(top), 1),
            "back sweep (°)": round(math.degrees(bottom), 1),
        }
        for k, (fam, a) in enumerate(
            (fam, a) for fam in families(params) for a in start_angles_deg(params)
        )
    ],
    hide_index=True, use_container_width=True,
)

st.subheader("Generated build123d snippet")
st.code(generate_snippet(params), language="python")
