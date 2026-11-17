"""Streamlit 'Spiral wire jig' page: spin-to-wind jig for an open-spaced flat copper spiral (mm)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import spiral_jig as S


def sidebar() -> S.SpiralParams:
    sb = st.sidebar
    sb.header("Spiral wire jig (mm)")
    names = list(S.PRESETS) + ["Custom"]
    pre = sb.selectbox("Wire length (royal cubit 523.6 mm)", names, index=0)
    if pre == "Custom":
        L = sb.number_input("Wire length (total wound)", 60.0, 1000.0, 261.8, 0.1)
        od0 = 46.0
    else:
        L, od0 = S.PRESETS[pre]
    od = sb.slider("Target coil OD after release", 25.0, 60.0, float(od0), 0.5, key=f"od_{pre}",
                   help="Outer edge of the wire. Auto-switches with the preset (46 for 1/2 cubit, 33 for 1/4). "
                        "Measure your muffin-cup bottom and set this a couple of mm smaller.")
    spacing = sb.radio("Spacing", ["even", "golden"], horizontal=True,
                       format_func=lambda s: "Even (Archimedean)" if s == "even" else "Golden (x1.618 per turn)")
    arms = sb.radio("Spiral type", [2, 1], horizontal=True, format_func=lambda n: "Double (S)" if n == 2 else "Single")
    wire = sb.number_input("Wire envelope (twisted pair)", 1.0, 3.5, 2.0, 0.05)
    ch = sb.slider("Channel width", 2.2, 2.4, 2.3, 0.05)
    wh = sb.slider("Wall height", 2.0, 5.0, 3.0, 0.25)
    wt = sb.slider("Wall thickness", 1.2, 1.6, 1.4, 0.05)
    sb.markdown("**Springback**")
    dk = sb.number_input("Δκ compensation (1/mm)", 0.0, 0.02, float(round(S.DK_SOFT_CU, 5)), 0.0001, format="%.5f",
                         key="dk", help="Jig radius r_wind = 1/(1/r_target + Δκ). Default = 3.4·σy/(E·d) for annealed "
                                        "copper (70 MPa, 117 GPa, 0.98 mm strand) ≈ 0.0021.")
    with sb.expander("Calibrate Δκ from a test coil"):
        wound = st.number_input("Wound OD on the jig you used", 10.0, 80.0, 44.0, 0.1)
        meas = st.number_input("Measured OD after release", 10.0, 90.0, 46.0, 0.1)
        if meas > wound:
            st.write(f"Material Δκ = **{S.calibrate_dk(meas, wound, wire):.5f} /mm** — type it into Δκ above.")
        else:
            st.write("Measured OD must be larger than the wound OD.")
    with sb.expander("Pins, fits, handle"):
        pd = st.number_input("Pin diameter", 2.0, 6.5, 3.175, 0.005, format="%.3f")
        pl = st.number_input("Pin length", 8.0, 20.0, 12.7, 0.1)
        pg = st.number_input("Gap between pins", 1.5, 3.5, 2.3, 0.05)
        pf = st.number_input("Pin hole fit (hole = pin + this)", -0.2, 0.2, -0.05, 0.01,
                             help="-0.05 = press fit (FDM holes print ~0.1 undersize too). +0.1 for heat-pressing.")
        rc = st.number_input("Running clearance per side", 0.1, 0.6, 0.3, 0.05)
        kc = st.number_input("Drive-lug clearance per side", 0.1, 0.4, 0.2, 0.05)
        hs = st.number_input("Handle span", 50.0, 110.0, 70.0, 1.0)
    drive = sb.selectbox("Handle → disc drive", list(S.DRIVES), index=0, format_func=lambda k: S.DRIVES[k],
                         help="v2: four 60° teeth on the handle journal (≈2.6× the root area of one v1 lug). "
                              "v1: the original two Ø5 lugs, geometry unchanged.")
    return S.SpiralParams(float(L), float(od), spacing, int(arms), float(wire), float(ch), float(wh), float(wt), float(dk),
                          float(pd), float(pl), float(pg), 6.0, float(pf), float(rc), float(kc), 12.0, float(hs), drive)


@st.cache_data(show_spinner="Building jig…", max_entries=8)
def _build(p: S.SpiralParams):
    out, info = S.build(p)
    ver = S.verify(p, out, info)
    L = info["L"]
    A = S.assembled(p, out, info)
    coil = S.wire_mesh(p, S.all_arms(p, L["sol"].wind), L["z_floor_top"] + p.wire_w / 2)
    pack = lambda tm: (np.asarray(tm.vertices), np.asarray(tm.faces))
    return ({k: (*pack(tm), S.stl_bytes(tm), ver[k]) for k, tm in out.items()},
            {k: pack(tm) for k, tm in A.items()}, pack(coil), ver["clearance"],
            [a.tolist() for a in S.all_arms(p, L["sol"].target)], [a.tolist() for a in S.all_arms(p, L["sol"].wind)])


def _fig(parts, h=520):
    fig = go.Figure()
    for (v, f), col, name in parts:
        fig.add_trace(go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2], color=col,
                                name=name, flatshading=True))
    ax = dict(visible=False)
    fig.update_layout(height=h, margin=dict(l=0, r=0, t=0, b=0), scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data"))
    return fig


def render(p: S.SpiralParams) -> None:
    st.title("Spiral wire jig — spin-to-wind, open-spaced flat spiral")
    try:
        rep = S.report(p)
    except ValueError as e:
        st.error(str(e)); return
    st.caption("Thread the straight wire through both ports and between the brass pins, then turn the T-handle "
               "(counter-clockwise seen from the top). Each arm hooks round a pin and wraps against the outside of "
               "its scroll wall. Keep the wire seated in its channel with a fingertip as it winds; lift the coil out "
               "of the open top. **STL in millimetres. Not sliced.**")
    c = st.columns(4)
    c[0].metric("Turns per arm", f"{rep['turns_per_arm']:.2f}")
    if p.spacing == "even":
        c[1].metric("Gap between rounds", f"{rep['gap_mm']:.2f} mm", help=f"pitch {rep['pitch_per_arm_turn_mm']:.2f} mm per arm turn")
    else:
        c[1].metric("Gap inner → outer", f"{rep['gap_inner_mm']:.2f} → {rep['gap_outer_mm']:.2f} mm")
    c[2].metric("Wound OD on jig", f"{rep['wound_od_on_jig_mm']:.1f} mm")
    c[3].metric("Predicted relaxed OD", f"{rep['predicted_relaxed_od_mm']:.1f} mm",
                help=f"Uncompensated it would relax to {rep['relaxed_od_if_uncompensated_mm']:.1f} mm")
    if rep["rounds_overlap"]:
        st.error(f"Innermost rounds overlap (gap {rep['innermost_gap_mm']:.2f} mm): increase the OD, shorten the wire "
                 "or use Even spacing.")
    elif rep["center_hand_bend_needed"]:
        st.warning(f"Innermost gap {rep['innermost_gap_mm']:.2f} mm < {S.GOLDEN_MIN_GAP} mm: the centre round has no "
                   "wall — give it a small hand bend after winding.")
    b, A, coil, clr, tgt, wnd = _build(p)
    bad = [k for k, v in b.items() if not v[3]["ok"]] + ([] if clr["ok"] else ["clearance"])
    if bad:
        st.error("Check failed: " + ", ".join(bad))
    t0, t1 = st.columns([3, 2])
    with t0:
        st.plotly_chart(_fig([(A["body"], "#3f6fb5", "body"), (A["winding_disc"], "#8fb3e0", "disc"),
                              (A["handle"], "#2c4f86", "handle"), (A["pins"], "#d4a017", "brass pins"),
                              (coil, "#c8743a", "coil")]), width="stretch", key="asm")
    with t1:
        fig = go.Figure()
        for a in wnd:
            a = np.asarray(a); fig.add_trace(go.Scatter(x=a[:, 0], y=a[:, 1], mode="lines", line=dict(color="#c8743a", width=5), name="on jig"))
        for a in tgt:
            a = np.asarray(a); fig.add_trace(go.Scatter(x=a[:, 0], y=a[:, 1], mode="lines", line=dict(color="black", dash="dash", width=1), name="relaxed"))
        fig.update_layout(height=420, showlegend=False, margin=dict(l=0, r=0, t=20, b=0),
                          yaxis=dict(scaleanchor="x"), title="Coil top view (dashed = relaxed target)")
        st.plotly_chart(fig, width="stretch", key="top")
    tabs = st.tabs(list(b.keys()))
    for tab, (k, (v, f, stl, ver)) in zip(tabs, b.items()):
        with tab:
            st.plotly_chart(_fig([((v, f), "#5a8cc8", k)], 420), width="stretch", key=f"fig_{k}")
            st.download_button(f"Download {k}.stl", stl, f"spiral_{k}.stl", "model/stl", key=f"dl_{k}")
            st.json(ver)
    st.subheader("Coil numbers"); st.json(rep)
    st.subheader("Clearance checks"); st.json(clr)
    st.subheader("Drive strength (estimate)"); st.json(S.drive_strength(p))
    pp = S.PIN_PART
    st.subheader("Buy: centre pins")
    st.markdown(f"2 × {pp['desc']} — {pp['vendor']} [{pp['part']}]({pp['url']}) (pack of {pp['pack']}). "
                f"Press in until {p.pin_protrude:g} mm stands above the disc floor (they bottom out in the blind holes). "
                f"Alternative: {pp['alt']}.")
