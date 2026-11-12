"""Streamlit 'Concrete test specimen molds' page: cube / prism silicone mold masters + pour frame (mm)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import specimen_molds as S


def sidebar() -> S.SpecimenParams:
    sb = st.sidebar
    sb.header("Concrete specimen molds (mm)")
    kind = sb.radio("Specimen type", ["Cube (compressive)", "Bar (3-point flexural, 1:1:4)"])
    if kind.startswith("Cube"):
        a = sb.number_input("Cube edge", 20.0, 60.0, 50.0, 0.5, help="50 mm (2 in) is the standard compressive cube.")
        nx = sb.number_input("Cubes along X", 1, 4, 2); ny = sb.number_input("Cubes along Y", 1, 4, 2)
        length, upright = a, False
    else:
        a = sb.number_input("Prism width = height", 15.0, 40.0, 27.5, 0.5,
                            help="Length = 4 x width. 27.5 x 27.5 x 110 is the largest flat set that fits a 150 bed.")
        length = 4 * a
        upright = sb.checkbox("Stand prisms on end (vertical casting)", False,
                              help="Lets the standard 40x40x160 fit (2x2, 164 mm tall master) but casts vertically.")
        nx = sb.number_input("Prisms along X", 1, 4, 2 if upright else 1)
        ny = sb.number_input("Prisms along Y", 1, 5, 2 if upright else 3)
    gap = sb.slider("Silicone wall between cavities / to frame", 6.0, 20.0, 10.0, 0.5)
    cover = sb.slider("Silicone cover over tops", 5.0, 20.0, 10.0, 0.5)
    r = sb.slider("Frame inner corner radius", 8.0, 20.0, min(10.0, gap), 0.5,
                  help="Keep <= the wall so the corner silicone stays >= the wall.")
    return S.SpecimenParams("cube" if kind.startswith("Cube") else "bar", float(a), float(length), int(nx), int(ny),
                            float(gap), float(cover), float(r), bool(upright))


@st.cache_data(show_spinner="Building master + frame…", max_entries=8)
def _build(p: S.SpecimenParams):
    parts = S.build(p)
    return {k: (np.asarray(t.vertices), np.asarray(t.faces), S.stl_bytes(t), S.check(t)) for k, t in parts.items()}


def render(p: S.SpecimenParams) -> None:
    st.title("Concrete test specimen molds — silicone mold masters")
    d = S.dims(p)
    st.caption(
        f"{d.count} × {' × '.join(f'{x:g}' for x in d.specimen_mm)} mm {d.kind} positives ({d.layout}) on a "
        f"{d.plate_mm[0]:.1f} × {d.plate_mm[1]:.1f} mm plate; frame {d.frame_outer_mm[0]:.1f} × {d.frame_outer_mm[1]:.1f}"
        f" × {d.frame_height_mm:.1f} mm. Tower v3 seating: {d.clearance_per_side} mm/side, {d.groove_width} × "
        f"{d.groove_depth} mm glue-bead groove, {d.lip_channel} mm channel, {d.lip_width} × {d.lip_height} mm lip. "
        f"Silicone ≈ **{d.silicone_ml:.0f} ml** (fill {d.fill_above_plate_mm:g} mm above plate, before mixing losses). "
        f"Bed assumption {S.BED_XY:g} × {S.BED_XY:g} × {S.BED_Z:g} mm. **STL in millimetres.**")
    if not d.master_fits_bed:
        st.error(f"Master plate {d.plate_mm[0]:.1f} × {d.plate_mm[1]:.1f} mm / height {d.master_height_mm:g} mm "
                 f"exceeds the {S.BED_XY:g} mm bed or {S.BED_Z:g} mm Z.")
    elif not d.master_fits_with_5mm_brim:
        st.warning("Master fits, but a 5 mm brim would run off a 150 mm bed: print it without a brim.")
    b = _build(p)
    fig = go.Figure()
    for k, col, dz in (("master", "#a39e96", 0.0), ("pour_frame", "#5a8cc8", S.PLATE_T - S.GR_DEPTH)):
        v, f = b[k][0], b[k][1]
        fig.add_trace(go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2] + dz, i=f[:, 0], j=f[:, 1], k=f[:, 2], color=col,
                                opacity=1.0 if k == "master" else 0.35, name=k, flatshading=True))
    ax = dict(visible=False)
    fig.update_layout(height=600, margin=dict(l=0, r=0, t=0, b=0),
                      scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data"))
    st.plotly_chart(fig, width="stretch")
    c1, c2 = st.columns(2)
    for col, k in ((c1, "master"), (c2, "pour_frame")):
        col.download_button(f"Download {p.kind}_{k}.stl", b[k][2], f"{p.kind}_{k}.stl", "model/stl")
        col.json(b[k][3])
    st.json(S.dims_dict(p))
