"""Streamlit 'Tetrix brazing jig' page: positioning jigs for a Sierpinski tetrahedron of brazed copper rods (mm)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import tetrix_jig as T


def sidebar() -> T.TetrixParams:
    sb = st.sidebar
    sb.header("Tetrix brazing jig (mm)")
    edges = T.cubit_edges()
    labels = [f"{e:g} mm (cubit/{2 ** (i + 1)})" for i, e in enumerate(edges)]
    i = sb.selectbox("Outer edge (royal-cubit harmonic 523.6/2^n)", range(len(edges)), index=1,
                     format_func=lambda k: labels[k])
    level = sb.radio("Level", [1, 2], horizontal=True, help="Level 1 = 4 tetrahedra, 24 rods; level 2 = 16, 96 rods.")
    d = sb.number_input("Rod diameter (twisted pair envelope)", 1.0, 6.0, 1.88, 0.01,
                        help="Measure the stretched + twisted pair with calipers (Timothy's: 1.88 mm).")
    c = sb.number_input("Seat clearance (diametral)", 0.0, 1.0, 0.10, 0.01,
                        help="Seat diameter = rod + this. Raise if the rod won't sit down in the seat.")
    a = sb.number_input("Joint allowance (total per rod)", 0.0, 4.0, 1.0, 0.1,
                        help="Cut length = small edge − allowance; half comes off each end.")
    lip = sb.checkbox("Snap lips on jig channels", True)
    m = sb.number_input("Snap mouth width", 0.8, 6.0, 1.75, 0.01, disabled=not lip,
                        help="Opening between the lips. Interference per side = (rod − mouth)/2. "
                             "Too hard to press in → raise (e.g. 1.80); falls out → lower (e.g. 1.70).")
    gl = sb.checkbox("Snap lips on gauge measuring channels", True, disabled=not lip,
                     help="Straightening groove always stays open.")
    sb.caption(f"Seat Ø{d + c:.2f}, mouth {min(m, d + c) if lip else d + c:.2f} → interference "
               f"{max(0.0, (d - m) / 2) if lip else 0.0:.3f} mm per side")
    return T.TetrixParams(float(edges[i]), int(level), float(d), float(c), float(a), bool(lip), float(m), bool(lip and gl))


@st.cache_data(show_spinner="Building jigs…", max_entries=8)
def _build(p: T.TetrixParams):
    out, info = T.build(p)
    ver = T.verify(p, out, info)
    rods = {k: T.rods_mesh(v["rods"], p.rod_d) for k, v in info.items() if "rods" in v}
    pack = lambda tm: (np.asarray(tm.vertices), np.asarray(tm.faces))
    return ({k: (*pack(tm), T.stl_bytes(tm), ver[k]) for k, tm in out.items()},
            {k: pack(tm) for k, tm in rods.items()})


def _fig(parts):
    fig = go.Figure()
    for (v, f), col, name in parts:
        fig.add_trace(go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2], color=col,
                                name=name, flatshading=True))
    ax = dict(visible=False)
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=0, b=0),
                      scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data"))
    return fig


def render(p: T.TetrixParams) -> None:
    st.title("Tetrix brazing jig — Sierpinski tetrahedron in copper rod")
    d = T.dims(p)
    st.caption(
        f"Level-{d.level} tetrix, outer edge **{d.edge:g} mm**, height {d.height:g} mm: {4 ** d.level} tetrahedra of "
        f"{d.small_edge:g} mm, **{d.rod_count} rods cut to {d.rod_cut_length:g} mm**, {d.joint_count} joints. "
        f"Snap seats Ø{d.seat_d:g} for Ø{d.rod_d:g} rod, mouth {d.snap_mouth:g} ({d.interference_per_side:g} mm/side). Wire: {d.total_wire_mm_incl_3pct / 1000:.2f} m of single "
        f"strand (2 per rod, +3% for twisting). PLA only positions rods: tie joints with binding wire, lift out, "
        f"then braze. Every jig surface ≥ {T.MIN_JOINT_CLEAR:g} mm from every joint. **STL in millimetres.**")
    b, rods = _build(p)
    bad = [k for k, v in b.items() if v[3].get("ok") is False]
    if bad:
        st.error("Not printable/usable as configured: " + ", ".join(bad) +
                 " (bed > 225 mm, < 3 top posts, or a joint closer than 6 mm). Default 130.9 mm level 1 passes.")
    tabs = st.tabs(list(b.keys()))
    for tab, (k, (v, f, stl, ver)) in zip(tabs, b.items()):
        with tab:
            parts = [((v, f), "#5a8cc8" if k != "rods_reference" else "#c8743a", k)]
            if k in rods:
                parts.append((rods[k], "#c8743a", "rods"))
            st.plotly_chart(_fig(parts), width="stretch", key=f"fig_{k}")
            st.download_button(f"Download {k}.stl", stl, f"{k}.stl", "model/stl", key=f"dl_{k}")
            st.json(ver)
    st.subheader("Cut list")
    st.json(T.dims_dict(p))
