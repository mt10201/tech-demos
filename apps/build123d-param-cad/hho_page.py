"""Streamlit 'HHO vortex nozzle ring' page: 4 swirled, downward-tilted brass tips (PLA cold-gas fixture + metal STEP)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import hho_ring as H

ORCA = """**Orca (you slice — not sliced here).** Start from your `Ender2_RodinFrame_cold` / `rodin_frame_PLA_cold` presets:
- **Orientation:** as exported — flat bottom on the bed, barb pointing **up**. No supports (teardrop channels, 30° inner cone, 45° barb catches).
- **Layer height 0.16 mm**; **5 walls** (perimeters) so the gas channels and sockets are solid plastic all round; top/bottom shells **6 / 5**.
- **Infill 100 %** (or a 100 % modifier over the whole ring and boss) — no infill voids next to the gas paths. Gyroid or rectilinear.
- Detect thin walls **off**, ironing off, 3 mm brim (cold room), retraction at your original setting (not higher), nozzle 225 °C unchanged.
- **Leak test before use:** cap the 4 sockets with tape, blow gently into the tube under water — no bubbles from the plastic.
- **Heat-set the tips:** warm each brass tube (heat gun / soldering iron on the tube, not the ring), push straight in along the socket until it stops on the shoulder (all 4 at the same depth), then trim them to the same stick-out."""


def sidebar() -> H.RingParams:
    sb = st.sidebar
    sb.header("HHO vortex nozzle ring (mm)")
    sb.error("PLA print = COLD-GAS TEST FIXTURE ONLY. Never light it.")
    tip = sb.selectbox("Nozzle tip", list(H.TIPS), index=0, format_func=lambda k: H.TIPS[k]["name"])
    od = sb.number_input("Tip shank OD", 0.5, 4.0, float(H.TIPS[tip]["od"]), 0.005, format="%.4f", key=f"od_{tip}",
                         help="Measure your tips with calipers and type the real OD here.")
    inter = sb.number_input("Heat-set interference per side", 0.0, 0.4, 0.15, 0.01,
                            help="Socket bore = shank OD − 2 × this. The hot brass melts its way in and the plastic grips it.")
    depth = sb.slider("Insertion depth to stop shoulder", 3.0, 8.0, 5.0, 0.25)
    feed = sb.number_input("Feed hole Ø (behind the shoulder)", 0.5, 3.0, 1.0, 0.05,
                           help="Must be ≥0.2 mm smaller than the socket bore so the tube stops on the shoulder.")
    sb.markdown("**Vortex aim**")
    tilt = sb.slider("Downward tilt below horizontal (°)", 10.0, 45.0, 30.0, 1.0,
                     help="Ring held horizontal, flame BELOW. More tilt = the jets meet further below the ring.")
    swirl = sb.slider("Swirl (tangential offset, °)", 0.0, 30.0, 12.0, 0.5,
                      help="0 = all 4 jets hit one point on the axis; more swirl = wider spinning core.")
    prot = sb.slider("Tip stick-out past the socket (for the jet maths)", 0.0, 10.0, 3.0, 0.5)
    sb.markdown("**Gas path**")
    tube = sb.radio("Clear vinyl tube", list(H.BARBS), index=0)
    man = sb.radio("Manifold", list(H.MANIFOLDS), format_func=lambda k: H.MANIFOLDS[k], index=0)
    with sb.expander("Ring size / channels"):
        Rp = st.slider("Plenum centre radius", 14.0, 22.0, 17.0, 0.5)
        pr = st.slider("Plenum teardrop radius", 1.5, 3.0, 2.0, 0.1)
        dr = st.slider("Distribution / runner radius", 1.2, 2.5, 1.6, 0.1)
        wall = st.slider("Wall round gas channels", 2.0, 4.0, 2.2, 0.1)
        nb = st.slider("Barbs", 2, 3, 3)
    return H.RingParams(tip=tip, shank_od=float(od), interference=float(inter), insert_depth=float(depth),
                        protrusion=float(prot), swirl_deg=float(swirl), tilt_deg=float(tilt), plenum_r=float(pr),
                        dist_r=float(dr), feed_d=float(feed), R_plenum=float(Rp), wall=float(wall), tube=tube,
                        manifold=man, n_barbs=int(nb))


@st.cache_data(show_spinner="Building ring…", max_entries=6)
def _build(p: H.RingParams):
    res = H.build(p)
    ver = H.verify(p, res)
    pack = lambda tm: (np.asarray(tm.vertices), np.asarray(tm.faces))
    ring, cav = H.to_mesh(res["ring"]), H.to_mesh(res["cavity"])
    return (pack(ring), pack(cav), pack(H.tip_meshes(p, res["L"])), [ln.tolist() for ln in H.jet_lines(p, res["L"], 2.0)],
            H.stl_bytes(res["ring"]), H.step_bytes(res["ring"]), ver)


def _mesh(fig, vf, col, name, op=1.0):
    v, f = vf
    fig.add_trace(go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2], color=col, opacity=op,
                            name=name, flatshading=True))


def render(p: H.RingParams) -> None:
    st.title("HHO vortex nozzle ring — 4 swirled tips aimed down into a tornado")
    st.error("⚠️ " + H.SAFETY)
    try:
        rep = H.report(p)
    except ValueError as e:
        st.error(str(e)); return
    st.caption("Ring held horizontal, flame below. Four straight brass tips are heat-set into angled sockets, all at the "
               "same depth (stop shoulder). Each points inward, tilted down and offset sideways, so the jets spin round a "
               "common core below the ring. **STL + STEP in millimetres. Not sliced.**")
    j, pb = rep["jets"], rep["path_balance"]
    c = st.columns(5)
    c[0].metric("Ring OD × height", f"{rep['ring_od_mm']:.0f} × {rep['ring_height_mm']:.1f}")
    c[1].metric("Socket bore", f"Ø{rep['socket_bore_mm']:.3f}", help=f"shank Ø{p.shank_od:g} − 2×{p.interference:g}")
    c[2].metric("Vortex core", f"Ø{2 * j['vortex_core_radius_mm']:.1f} mm", help="Closest approach of the 4 jets to the axis")
    c[3].metric("Core depth below ring", f"{j['focal_depth_below_ring_mm']:.1f} mm")
    c[4].metric("Path spread", f"{pb['max_minus_min_mm']:.2f} mm", help="Barb → each tip shoulder, centre-line")
    ring, cav, tips, jl, stl, step, ver = _build(p)
    if not ver["ok"]:
        st.error("Check failed — see the verification JSON below.")
    show_gas = st.toggle("Show the gas cavity (ring see-through)", value=False)
    fig = go.Figure()
    _mesh(fig, ring, "#5a8cc8", "ring", 0.25 if show_gas else 1.0)
    if show_gas:
        _mesh(fig, cav, "#f08c26", "gas path")
    _mesh(fig, tips, "#d4a017", "brass tips")
    for ln in jl:
        a = np.asarray(ln)
        fig.add_trace(go.Scatter3d(x=a[:, 0], y=a[:, 1], z=a[:, 2], mode="lines", line=dict(color="red", width=6), name="jet"))
    ax = dict(visible=False)
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                      scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data"))
    st.plotly_chart(fig, width="stretch", key="hho3d")
    d0, d1 = st.columns(2)
    d0.download_button("Download STL (PLA cold-gas test fixture)", stl, "hho_vortex_ring.stl", "model/stl", key="dl_stl")
    d1.download_button("Download STEP (metal: machine in brass / cast bronze)", step, "hho_vortex_ring.step",
                       "application/step", key="dl_step")
    st.subheader("Tips to buy")
    for k, t in H.TIPS.items():
        st.markdown(f"- {'**(selected)** ' if k == p.tip else ''}[{t['name']}]({t['url']}) — {t['vendor']}, "
                    f"${t['price_usd']:.2f} ({t['pack']}). Shank Ø{t['od']:g} mm, orifice ≈Ø{t['orifice']:g} mm. "
                    f"_{t['verified']}_")
    st.markdown("**Metal head:** fit a **flashback arrestor** and a **check valve** at the tube inlet (HHO generators "
                "also need their own bubbler). Machine the STEP in brass, or print it as a casting master and "
                "investment-cast it in bronze (opening the gas passages after casting).")
    st.subheader("Orca settings"); st.markdown(ORCA)
    st.subheader("Numbers"); st.json(rep)
    st.subheader("Verification"); st.json(ver)
