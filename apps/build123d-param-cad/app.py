"""Streamlit playground: Rodin coil torus — photo-replica groove lattice."""

from __future__ import annotations

import colorsys
import math

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from code_snippet import generate_snippet
from geometry import (
    CUBIT_FRACTIONS,
    CUBIT_RING_FRACTION,
    CUBIT_TUBE_FRACTION,
    MM_PER_IN,
    ROYAL_CUBIT_MM,
    SOLIDWORKS_SIZE,
    bounding_box_mm,
    cubit_radius_in,
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
from boolean_mesh import EXPORT_KW, PREVIEW_KW, crop_solid, display_mesh, drop_degenerate, grooved_solid, section_width, vertex_depth
from torus_mesh import mesh_volume, stl_bytes

st.set_page_config(page_title="Rodin torus · build123d", page_icon="◎", layout="wide")

MM = MM_PER_IN


with st.sidebar:
    mode = st.radio("Mode", ["Torus", "Mold master", "Moai statue", "Photo → master"], horizontal=True,
                    help="Mold master: silicone mold positives (two halves) + pour frame for this torus. "
                         "Moai statue: a separate side part, a 6 in Rapa Nui moai. "
                         "Photo → master: repair any photo-to-3D or scan mesh into a printable mold master.")
if mode not in ("Moai statue", "Photo → master"):
    st.title("Rodin coil torus — groove lattice")
    st.caption(
        "Parametric CAD playground (**build123d** + Streamlit). Default preset **Photo replica**: "
        "12 + 12 constant-width U-grooves (1/8\" wide × 1/8\" deep) spiralling in both directions, leaving raised rhombus tiles "
        "like the rainbow Rodin coil frame. Default size: **royal-cubit harmonics** (tube circumference = ¼ cubit, "
        "ring circumference = ½ cubit → ≈125 mm across). **STL and STEP downloads are in millimetres.**"
    )

if mode == "Moai statue":
    import moai_page

    moai_page.render(moai_page.sidebar())
    st.stop()

if mode == "Photo → master":
    import photo_master_page

    photo_master_page.render(photo_master_page.sidebar())
    st.stop()

with st.sidebar:
    st.header("Preset")
    pattern = st.radio("Groove pattern", list(PATTERNS), format_func=PATTERN_LABELS.get)
    st.header("Torus size")
    size_mode = st.radio(
        "Sizing", ["Royal cubit harmonics", "SOLIDWORKS sketch (inches)", "Custom (mm)"],
        help=f"Royal cubit C = {ROYAL_CUBIT_MM / 10:.2f} cm. Each circumference is a harmonic fraction of C.",
    )
    fr_keys = list(CUBIT_FRACTIONS)
    if size_mode == "Royal cubit harmonics":
        tube_f = st.selectbox("Tube cross-section circumference (× cubit)", fr_keys,
                              index=fr_keys.index("1/4"))
        ring_f = st.selectbox("Ring centre-line circumference, top view (× cubit)", fr_keys,
                              index=fr_keys.index("1/2"))
        r = cubit_radius_in(CUBIT_FRACTIONS[tube_f])
        R = cubit_radius_in(CUBIT_FRACTIONS[ring_f])
        st.caption(
            f"C = {ROYAL_CUBIT_MM:.1f} mm · 2πr = {tube_f} C = {2 * math.pi * r * MM:.2f} mm → "
            f"r = {r * MM:.3f} mm · 2πR = {ring_f} C = {2 * math.pi * R * MM:.2f} mm → R = {R * MM:.3f} mm"
        )
    elif size_mode == "SOLIDWORKS sketch (inches)":
        R = st.number_input("Major radius R (in)", 0.5, 6.0, SOLIDWORKS_SIZE[0], 0.01, format="%.3f")
        r = st.number_input("Tube radius r (in)", 0.1, 3.0, SOLIDWORKS_SIZE[1], 0.005, format="%.3f")
    else:
        R = st.number_input("Major radius R (mm)", 10.0, 150.0, round(cubit_radius_in(CUBIT_RING_FRACTION) * MM, 3),
                            0.5, format="%.3f") / MM
        r = st.number_input("Tube radius r (mm)", 3.0, 75.0, round(cubit_radius_in(CUBIT_TUBE_FRACTION) * MM, 3),
                            0.5, format="%.3f") / MM
    st.header("Grooves")
    width = st.slider("Groove width (in, true 3D; 0.125\" = 3.175 mm)", 0.0625, 0.5, 0.125, 1 / 64, format="%.4f")
    depth = st.slider(
        "Groove depth (in; 0.125\" = 3.175 mm)", 0.03125, 0.25, 0.125, 1 / 64, format="%.4f",
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
    cam = st.radio("3D camera", ["Overview", "Zoom across the hole"], horizontal=False)
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

if mode == "Mold master":
    import mold_page

    mold_page.render(params, mold_page.sidebar())
    st.stop()


@st.cache_data(show_spinner="Meshing grooved torus…", max_entries=8)
def _mesh(p: TorusParams):
    v, f = grooved_solid(p, **PREVIEW_KW)  # real mesh boolean, smooth walls
    v, f = display_mesh(v, f)  # split at creases so smooth shading keeps edges crisp
    return v, f, vertex_depth(p, v)


@st.cache_data(show_spinner="Meshing high-res STL…", max_entries=2)
def _stl(p: TorusParams):
    v, f = _hires(p)
    return stl_bytes(v, f), len(f)


@st.cache_data(show_spinner="Boolean-subtracting grooves (high-res)…", max_entries=2)
def _hires(p: TorusParams):
    return grooved_solid(p, **EXPORT_KW)


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
bx, by, bz = bounding_box_mm(params)
u1, u2, u3, u4 = st.columns(4)
u1.metric("Export units", "millimetres")
u2.metric("Overall size (Ø × height)", f"{bx:.1f} × {bz:.1f} mm",
          help=f"Bounding box {bx:.1f} × {by:.1f} × {bz:.1f} mm (outer Ø × outer Ø × height)")
u3.metric("Tube circumference 2πr", f"{2 * math.pi * params.tube_radius * MM / 10:.2f} cm",
          help=f"= {2 * math.pi * params.tube_radius * MM / ROYAL_CUBIT_MM:.4f} royal cubit")
u4.metric("Ring circumference 2πR", f"{2 * math.pi * params.major_radius * MM / 10:.2f} cm",
          help=f"= {2 * math.pi * params.major_radius * MM / ROYAL_CUBIT_MM:.4f} royal cubit")
paths = all_paths(params, 241)
wall, wall_theta = _wall(params)

col_view, col_front = st.columns(2, gap="medium")

with col_view:
    st.subheader("3D preview")
    data = [
        go.Mesh3d(
            x=verts[:, 0] * MM, y=verts[:, 1] * MM, z=verts[:, 2] * MM,
            i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
            color="#c9a227", flatshading=False,
            lighting=dict(ambient=0.35, diffuse=0.85, specular=0.25, roughness=0.6, fresnel=0.1),
            lightposition=dict(x=3, y=4, z=6), name="torus", hoverinfo="skip",
        )
    ]
    if show_paths:
        for k, pth in enumerate(paths):
            data.append(go.Scatter3d(
                x=pth[:, 0] * MM, y=pth[:, 1] * MM, z=pth[:, 2] * MM, mode="lines",
                line=dict(color="#3b82f6", width=3), showlegend=False,
            ))
    fig = go.Figure(data=data)
    fig.update_layout(
        scene=dict(
            aspectmode="data", bgcolor="#0e1117",
            xaxis_title="X (mm)", yaxis_title="Y (mm)", zaxis_title="Z (mm)",
            camera=(dict(eye=dict(x=1.15, y=1.15, z=1.05)) if cam == "Overview" else
                    dict(eye=dict(x=0.0, y=-0.95, z=0.30), center=dict(x=0, y=-0.3, z=-0.02))),
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
    f"Profile: **{prof}**, {width:.4f}\" ({width * MM:.3f} mm) wide × {depth:.4f}\" ({depth * MM:.3f} mm) deep (bottom radius "
    f"{cutter_radius(params):.4f}\"{f', walls {h_wall:.4f}' + chr(34) if h_wall > 1e-9 else ''}). "
    "Width is measured in true 3D, so it is identical on the rim, top, hole and bottom."
)
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Solid volume", f"{mesh_volume(verts, faces) * MM**3 / 1000:.1f} cm³")
m2.metric("Grooves", f"{len(paths)}  ({' + '.join(str(params.n_grooves) for _ in families(params))})")
m3.metric("Sweep rim → hole", f"{math.degrees(top):.1f}°")
m4.metric("Advance per wrap", f"{wrap_advance_deg(params):.1f}°")
m5.metric("Min wall between grooves", f"{wall * MM:.2f} mm", help=f"{wall:.3f} in, at θ ≈ {wall_theta:.0f}° (180° = hole)")
if wall < 0:
    st.warning(
        f"Neighbouring grooves of the same direction **merge** near θ ≈ {wall_theta:.0f}° "
        f"(180° = the hole): centre-lines are {(wall + width) * MM:.2f} mm apart but grooves are "
        f"{width * MM:.2f} mm wide, so the wall between them is {wall * MM:.2f} mm (no tile left there). "
        "Reduce depth/width, use fewer grooves, or a smaller sweep."
    )
elif wall < 0.04:
    st.warning(
        f"Thinnest wall between neighbouring grooves is only **{wall * MM:.2f} mm** "
        f"(near θ ≈ {wall_theta:.0f}°, 180° = hole). It will print but be fragile; "
        "check your printer's minimum feature size."
    )

st.subheader("Close-up: rim vs hole at the same scale (high-res printable mesh)")


def _crop(v, f, centre, radius):
    return display_mesh(*crop_solid(v, f, centre, radius))


@st.cache_data(show_spinner="Rendering close-ups…", max_entries=4)
def _closeups(p: TorusParams):
    v, f = _hires(p)
    g0 = all_paths(p, 3601, radius=p.tube_radius)[0]
    out, crops = [], {}
    # 9° past a crossing with the other family (crossings every 180/(2k)° of θ)
    for label, th in (("Outer rim", 9.0), ("Top", 99.0), ("Inner hole", 189.0), ("Bottom", 279.0)):
        j = int(round(th / 360 * (len(g0) - 1)))
        S, T = g0[j], g0[j + 1] - g0[j - 1]
        T = T / np.linalg.norm(T)
        w, dmax = section_width(p, v, f, S, T)
        phi = math.atan2(S[1], S[0])
        c = np.array([p.major_radius * math.cos(phi), p.major_radius * math.sin(phi), 0.0])
        N = (S - c) / np.linalg.norm(S - c)
        out.append((label, S, T, N, w, dmax))
        if label in ("Outer rim", "Inner hole"):
            crops[label] = _crop(v, f, S, 0.32)
    return out, crops


cl, crops = _closeups(params)
cz = st.columns(3)
for col, (lab, S, T, N, w, dmax) in zip(cz[:2], [c for c in cl if c[0] in crops]):
    v, f = crops[lab]
    dp = vertex_depth(params, v)
    t = np.clip(dp / (0.35 * params.groove_depth), 0, 1)
    cols = (255 * ((1 - t)[:, None] * np.array([0.55, 0.62, 0.95]) + t[:, None] * np.array([0.80, 0.47, 0.22]))).astype(int)
    vv = v - S
    figp = go.Figure(go.Mesh3d(
        x=vv[:, 0], y=vv[:, 1], z=vv[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2],
        vertexcolor=[f"rgb({a},{b},{c})" for a, b, c in cols], flatshading=False,
        lighting=dict(ambient=0.45, diffuse=0.85, specular=0.2, roughness=0.7), hoverinfo="skip",
    ))
    noax = dict(visible=False, range=[-0.34, 0.34])
    eye = N * 0.9 + T * 0.55 + np.array([0, 0, 0.25])
    figp.update_layout(
        scene=dict(xaxis=noax, yaxis=noax, zaxis=noax, aspectmode="cube",
                   camera=dict(eye=dict(x=eye[0], y=eye[1], z=eye[2]), up=dict(x=N[0], y=N[1], z=N[2])),
                   bgcolor="#f4f4f4"),
        margin=dict(l=0, r=0, t=30, b=0), height=360, paper_bgcolor="#f4f4f4",
        title=dict(text=f"{lab}: {w * MM:.3f} mm wide", x=0.5, font=dict(color="#222", size=13)),
    )
    col.plotly_chart(figp, use_container_width=True)
with cz[2]:
    import trimesh

    hv, hf = _hires(params)
    hm = trimesh.Trimesh(vertices=hv, faces=hf, process=False)
    pf = go.Figure()
    for (lab, S, T, N, w, dmax), colr in zip(cl, ["#ef4444", "#22c55e", "#3b82f6", "#a855f7"]):
        sec = hm.section(plane_origin=S, plane_normal=T)
        B = np.cross(T, N)
        B /= np.linalg.norm(B)
        for ent in sec.entities:
            pts = sec.vertices[ent.points]
            near = np.linalg.norm(pts - S, axis=1) < 0.15
            if not near.any():
                continue
            pts = pts[near]
            pf.add_trace(go.Scatter(x=((pts - S) @ B) * MM, y=-vertex_depth(params, pts) * MM, mode="lines",
                                    line=dict(color=colr, width=2), name=f"{lab}: {w * MM:.3f} mm",
                                    legendgroup=lab, showlegend=bool(ent is sec.entities[0])))
    pf.update_layout(
        height=360, margin=dict(l=10, r=10, t=30, b=10),
        title=dict(text="Mesh section ⟂ path (actual STL)", x=0.5, font=dict(size=13)),
        xaxis_title="lateral offset (mm)", yaxis_title="depth (mm)",
        xaxis=dict(range=[-3.0, 3.0]), yaxis=dict(scaleanchor="x", range=[-3.8, 0.5]),
        legend=dict(orientation="h", y=-0.3),
    )
    st.plotly_chart(pf, use_container_width=True)

st.subheader("Downloads")
d1, d2 = st.columns(2)
with d1:
    if st.button("Prepare high-res STL (mesh boolean)", use_container_width=True):
        st.session_state["stl"] = (params, *_stl(params))
    if st.session_state.get("stl") and st.session_state["stl"][0] == params:
        _, data_bytes, ntri = st.session_state["stl"]
        st.download_button(f"Download STL (mm) — {ntri:,} triangles, {len(data_bytes)/1e6:.0f} MB",
                           data=data_bytes, file_name=f"rodin_torus_{pattern}_mm.stl",
                           mime="model/stl", use_container_width=True)
    st.caption(
        f"STL in **millimetres** ({bx:.1f} × {by:.1f} × {bz:.1f} mm): import at 100 % scale. "
        "Finished, watertight grooved solid from a manifold3d boolean "
        "(torus − swept U-groove cutters): smooth walls, facet chord error < 0.013 mm."
    )
with d2:
    if st.button("Prepare STEP — finished solid (build123d, several minutes)",
                 use_container_width=True):
        bar = st.progress(0.0, text="Subtracting grooves one at a time in OpenCascade…")
        try:
            from rodin_torus import finished_step_bytes

            data_b = finished_step_bytes(
                params, progress=lambda k, n: bar.progress(k / n, text=f"Groove {k}/{n} subtracted")
            )
            st.session_state["step_solid"] = (params, data_b)
        except Exception as exc:
            st.error(f"Finished-solid STEP failed ({exc}). Use the cutter-bodies STEP below "
                     "and Combine ▸ Subtract in SOLIDWORKS.")
    if st.session_state.get("step_solid") and st.session_state["step_solid"][0] == params:
        st.download_button("Download STEP (finished grooved solid)",
                           data=st.session_state["step_solid"][1],
                           file_name=f"rodin_torus_{pattern}_grooved_mm.step",
                           mime="application/step", use_container_width=True)
    st.caption(
        "Exact B-rep with the grooves already cut, in **millimetres**: opens in SOLIDWORKS as one solid body. "
        "Takes several minutes (24 sequential OpenCascade cuts); the file is ~90 MB."
    )
    if st.button("Build STEP tool bodies (fast fallback)", use_container_width=True):
        try:
            st.session_state["step"] = (params, _step(params))
        except Exception as exc:  # sweeps can fail on extreme settings
            st.error(f"STEP build failed: {exc}")
    if st.session_state.get("step") and st.session_state["step"][0] == params:
        st.download_button("Download STEP (torus + cutter bodies)", data=st.session_state["step"][1],
                           file_name=f"rodin_torus_{pattern}_bodies_mm.step", mime="application/step",
                           use_container_width=True)
    st.caption(
        "Fallback: torus + groove cutter bodies + centre-lines. In SOLIDWORKS: "
        "Insert ▸ Features ▸ Combine ▸ **Subtract** (main body = torus, bodies to subtract = all grooves)."
    )

with st.expander("Groove centre-line diagram (front view)"):
    tf = go.Figure()
    ring = np.linspace(0, 2 * math.pi, 361)
    for rad in ((R - r) * MM, (R + r) * MM):
        tf.add_trace(go.Scatter(x=rad * np.cos(ring), y=rad * np.sin(ring), mode="lines",
                                line=dict(color="#666", width=1), showlegend=False, hoverinfo="skip"))
    half = len(paths[0]) // 2
    colors = ["#3b82f6", "#f97316"]
    for k, pth in enumerate(paths):
        fam = k // params.n_grooves
        upper = pth[: half + 1]
        tf.add_trace(go.Scatter(x=upper[:, 0] * MM, y=upper[:, 1] * MM, mode="lines",
                                line=dict(color=colors[fam], width=2),
                                name=f"direction {'+' if families(params)[fam] > 0 else '−'} (front half)",
                                showlegend=k % params.n_grooves == 0, hoverinfo="skip"))
    if pattern != "photo":
        q_min, q_max = projected_limits(params)
        phi0 = math.radians(start_angles_deg(params)[0])
        dphi = np.linspace(0, top + 3 * math.pi, 800)
        qq = np.array([golden_spiral_radius(q_max, x) for x in dphi])
        ang = phi0 + hand * dphi
        tf.add_trace(go.Scatter(x=qq * MM * np.cos(ang), y=qq * MM * np.sin(ang), mode="lines",
                                line=dict(color="#f5c542", width=2, dash="dash"),
                                name="reference golden spiral (÷φ per 90°)"))
    lim = (R + r) * MM * 1.08
    tf.update_layout(
        height=520, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117", font_color="#ddd",
        xaxis=dict(range=[-lim, lim], scaleanchor="y", showgrid=False, zeroline=False, title="X (mm)"),
        yaxis=dict(range=[-lim, lim], showgrid=False, zeroline=False, title="Y (mm)"),
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
