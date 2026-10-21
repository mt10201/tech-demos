"""Streamlit 'Mold master' page: silicone mold masters + pour frame (mm)."""

from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from boolean_mesh import display_mesh
from geometry import TorusParams
from mold import (
    ENDER2_BED_MM,
    MoldParams,
    above_floor_volume,
    fits_bed,
    frame_dims,
    half_height_mm,
    halves_identical,
    key_offset,
    key_torus_gap,
    masters,
    part_sizes,
    plate_thickness_b,
    silicone_volume_cm3,
    stl_bytes_mm,
    to_arrays,
    validate_mold,
)

PLATE = "#c3c7ce"  # light grey master (like the photo)
FRAME = "#55585e"  # dark grey pour frame


def sidebar() -> MoldParams:
    st.sidebar.header("Mold master (mm)")
    style = st.sidebar.radio(
        "Pour frame", ["around", "ledge"],
        format_func={"around": "Box around the plate (like the photo)",
                     "ledge": "Sits on a ledge of the plate (self-locating)"}.get,
        help="'around': one-piece wall standing on the table around the plate, clearance from its "
             "edge. 'ledge': the plate gets a raised pour floor and a perimeter ledge; the frame drops "
             "over the floor and rests on the ledge (same footprint, self-locating, better seal).",
    )
    margin = st.sidebar.slider("Plate margin: torus edge → frame wall", 3.0, 30.0, 7.0, 0.5,
                               help="This is also the thickness of the silicone side wall.")
    plate_t = st.sidebar.slider("Plate thickness (master A)", 2.5, 10.0, 4.0, 0.5)
    key_r = st.sidebar.slider("Key radius (hemispheres)", 3.0, 12.0, 8.0, 0.5)
    clearance = st.sidebar.slider("Frame clearance", 0.0, 1.0, 0.3, 0.05)
    cover = st.sidebar.slider("Silicone cover above the torus", 3.0, 30.0, 10.0, 0.5)
    wall = st.sidebar.slider("Frame wall thickness", 1.2, 6.0, 3.0, 0.2)
    return MoldParams(margin=margin, plate_thickness=plate_t, key_radius=key_r,
                      clearance=clearance, cover=cover, wall=wall, frame_style=style)


@st.cache_data(show_spinner="Building mold masters…", max_entries=4)
def _preview(t: TorusParams, m: MoldParams):
    parts = masters(t, m, hires=False, key_segments=64)
    out = {k: display_mesh(*to_arrays(v)) for k, v in parts.items()}
    sil = {k: silicone_volume_cm3(t, m, above_floor_volume(parts[k])) for k in ("master_A", "master_B")}
    return out, sil


@st.cache_data(show_spinner="Building high-res mold STLs…", max_entries=2)
def _stls(t: TorusParams, m: MoldParams):
    parts = masters(t, m, hires=True)
    return {k: (stl_bytes_mm(v), v.num_tri()) for k, v in parts.items()}


@st.cache_data(max_entries=8)
def _symmetry(t: TorusParams):
    return halves_identical(t)


def _mesh(V, F, color, name=""):
    return go.Mesh3d(x=V[:, 0], y=V[:, 1], z=V[:, 2], i=F[:, 0], j=F[:, 1], k=F[:, 2],
                     color=color, flatshading=False, name=name, hoverinfo="skip",
                     lighting=dict(ambient=0.45, diffuse=0.8, specular=0.15, roughness=0.8, fresnel=0.1),
                     lightposition=dict(x=-60, y=-120, z=200))


def _scene(eye):
    noax = dict(visible=False, showbackground=False)
    return dict(aspectmode="data", xaxis=noax, yaxis=noax, zaxis=noax, bgcolor="#d9c7a3",
                camera=dict(eye=eye, up=dict(x=0, y=0, z=1)))


def section_figure(t: TorusParams, m: MoldParams, meshes) -> go.Figure:
    """Cross-section through two diagonal keys (vertical plane x = y)."""
    import trimesh

    n = np.array([1.0, -1.0, 0.0]) / math.sqrt(2)
    u = np.array([1.0, 1.0, 0.0]) / math.sqrt(2)
    fig = go.Figure()
    fo, fi, fh = frame_dims(t, m)
    z0 = -m.ledge_height if m.frame_style == "ledge" else -m.plate_thickness
    d = fi / 2 * math.sqrt(2)  # frame inner corner along the diagonal
    fig.add_trace(go.Scatter(x=[-d, d, d, -d, -d], y=[0, 0, z0 + fh, z0 + fh, 0], fill="toself",
                             fillcolor="rgba(120,170,255,0.25)", line=dict(width=0),
                             name="silicone pour"))
    for key, color, label in (("pour_frame", FRAME, "pour frame"), ("master_A", "#8a92a3", "master A")):
        V, F = meshes[key]
        sec = trimesh.Trimesh(V, F, process=False).section(plane_origin=(0, 0, 0), plane_normal=n)
        if sec is None:
            continue
        first = True
        for ent in sec.entities:
            p = sec.vertices[ent.points]
            fig.add_trace(go.Scatter(x=p @ u, y=p[:, 2], mode="lines", fill="toself",
                                     line=dict(color=color, width=1.5), fillcolor=color,
                                     name=label, legendgroup=label, showlegend=first))
            first = False
    fig.update_layout(height=330, margin=dict(l=10, r=10, t=30, b=10),
                      title=dict(text="Diagonal section through 2 keys", x=0.5, font=dict(size=13)),
                      xaxis_title="along the diagonal (mm)", yaxis_title="z (mm)",
                      yaxis=dict(scaleanchor="x"), legend=dict(orientation="h", y=-0.35))
    return fig


def render(t: TorusParams, m: MoldParams) -> None:
    try:
        validate_mold(t, m)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    st.subheader("Mold master — silicone mold positives + pour frame")
    st.caption(
        "Master A = plate + top half of the grooved torus + 4 hemisphere key bumps. "
        "Master B = plate + bottom half (turned over) + 4 key sockets, so the two silicone halves register. "
        "The plate runs under the donut hole, so the silicone fills it. All parts in **mm**, print pose flat side down."
    )
    meshes, sil = _preview(t, m)
    sizes = part_sizes(t, m)
    bed = ENDER2_BED_MM
    cols = st.columns(3)
    names = {"master_A": "Master A", "master_B": "Master B", "pour_frame": "Pour frame"}
    for col, (k, s) in zip(cols, sizes.items()):
        ok = fits_bed(s, bed)
        col.metric(f"{names[k]} X × Y × Z (mm)", f"{s[0]:.1f} × {s[1]:.1f} × {s[2]:.1f}",
                   delta=f"fits Ender-2 {bed[0]:.0f}×{bed[1]:.0f}" if ok else "too big for the bed",
                   delta_color="normal" if ok else "inverse")
    same, rel = _symmetry(t)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Silicone per half", f"≈{sil['master_A']:.0f} cm³",
              help=f"A {sil['master_A']:.0f} / B {sil['master_B']:.0f} cm³")
    c2.metric("Silicone side wall", f"{m.margin + m.clearance:.1f} mm")
    c3.metric("Key ↔ torus gap", f"{key_torus_gap(t, m):.1f} mm",
              help=f"keys at (±{key_offset(t, m):.1f}, ±{key_offset(t, m):.1f}) mm")
    c4.metric("Top half vs flipped bottom", "identical" if same else "different",
              help=f"symmetric-difference volume / half volume = {rel:.1e}")
    if plate_thickness_b(m) > m.plate_thickness:
        st.caption(f"Master B's plate is {plate_thickness_b(m):.1f} mm thick (key radius + 2 mm) so the "
                   f"{m.key_radius:.1f} mm sockets keep a floor.")
    if not all(fits_bed(s, bed) for s in sizes.values()):
        st.warning("A part is larger than the Ender-2's 150 × 150 mm print area: reduce the plate margin, "
                   "the frame wall or the clearance.")

    left, right = st.columns([3, 2], gap="medium")
    with left:
        va, fa = meshes["master_A"]
        vf, ff = meshes["pour_frame"]
        fig = go.Figure([_mesh(va, fa, PLATE, "master A"), _mesh(vf, ff, FRAME, "frame")])
        fig.update_layout(scene=_scene(dict(x=0.35, y=-1.45, z=1.55)), height=520,
                          margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#d9c7a3", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Master A in its pour frame (like the reference photo).")
    with right:
        vb, fb = meshes["master_B"]
        fig_b = go.Figure([_mesh(vb, fb, PLATE)])
        fig_b.update_layout(scene=_scene(dict(x=0.9, y=-1.3, z=1.5)), height=300,
                            margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#d9c7a3")
        st.plotly_chart(fig_b, use_container_width=True)
        st.caption("Master B: bottom half turned over, key sockets.")
        st.plotly_chart(section_figure(t, m, meshes), use_container_width=True)

    st.subheader("Mold downloads (mm)")
    d1, d2 = st.columns(2)
    with d1:
        if st.button("Prepare high-res mold STLs", use_container_width=True):
            st.session_state["mold_stl"] = ((t, m), _stls(t, m))
        got = st.session_state.get("mold_stl")
        if got and got[0] == (t, m):
            for k, fname in (("master_A", "mold_master_A_mm.stl"), ("master_B", "mold_master_B_mm.stl"),
                             ("pour_frame", "pour_frame_mm.stl")):
                data, ntri = got[1][k]
                st.download_button(f"Download {fname} — {ntri:,} triangles, {len(data) / 1e6:.1f} MB",
                                   data=data, file_name=fname, mime="model/stl",
                                   use_container_width=True, key=f"dl_{k}")
        st.caption("Same smooth manifold3d torus mesh as the torus STL, split at the equator. "
                   "Watertight, in mm, each part flat side down.")
    with d2:
        if st.button("Prepare mold STEPs (exact B-rep, ~5 min)", use_container_width=True):
            bar = st.progress(0.0, text="Cutting grooves in OpenCascade…")
            try:
                from mold import master_step_bytes

                st.session_state["mold_step"] = ((t, m), master_step_bytes(
                    t, m, progress=lambda k, n: bar.progress(k / n, text=f"Groove {k}/{n} subtracted")))
            except Exception as exc:
                st.error(f"Mold STEP failed ({exc}). Use the STLs.")
        got = st.session_state.get("mold_step")
        if got and got[0] == (t, m):
            for fname, data in got[1].items():
                st.download_button(f"Download {fname} ({len(data) / 1e6:.0f} MB)", data=data,
                                   file_name=fname, mime="application/step",
                                   use_container_width=True, key=f"dl_{fname}")
        st.caption("Finished grooved torus (24 sequential OpenCascade cuts) split at z = 0 and fused "
                   "with the plate and keys. Opens in SOLIDWORKS as one solid per part.")
    st.markdown(
        f"**Pour depth:** {half_height_mm(t) + m.cover:.1f} mm of silicone above the pour floor "
        f"({half_height_mm(t):.2f} mm half torus + {m.cover:.1f} mm cover): fill to the top of the frame."
    )
