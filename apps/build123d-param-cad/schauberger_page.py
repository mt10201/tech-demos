"""Streamlit 'Schauberger vortex' page: hyperbolic funnel + kudu-horn whorl pipe + converging adapter (mm)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import schauberger as S

VIEWS = ["All three (mated)", "Mated side view (water path)", "Funnel", "Horn", "Adapter"]
COLORS = {"Funnel": "#4f8fbf", "Adapter": "#d9a441", "Horn": "#7a9a52"}
BG = "#eef2f4"


def sidebar():
    sb = st.sidebar
    sb.header("Schauberger vortex (mm)")
    view = sb.radio("View", VIEWS, index=0)
    with sb.expander("Funnel: hyperbola r = a/2 ÷ (h0 + t)", expanded=False):
        a_half = st.number_input("a/2 (mm²)", 1000.0, 30000.0, 9450.0, 10.0,
                                 help="9450 → inside Ø210 at t = 0 and Ø60 at t = 225 (a = 18900 mm²).")
        h0 = st.number_input("h0 (mm)", 10.0, 400.0, 90.0, 1.0)
        H = st.number_input("Hyperbola height H (mm)", 50.0, 240.0, 225.0, 1.0)
        collar = st.number_input("Freeboard collar (mm)", 0.0, 40.0, 15.0, 0.5, help="Owner-locked at 15 mm.")
        land = st.slider("Throat land (mm)", 0.0, 10.0, 5.0, 0.5,
                         help="225 + 15 + land ≤ 245 mm print height → 5 mm. The adapter cup matches it.")
        fwall = st.slider("Funnel wall T (mm)", 1.6, 4.0, 2.8, 0.1, help="Offset outward along the normal.")
    with sb.expander("Horn: kudu whorl pipe", expanded=False):
        lead_in = st.slider("Axial lead-in at the mouth", 15.0, 40.0, 30.0, 0.5,
                            help="Straight egg tube on the funnel axis; the egg socket is its first part.")
        turns = st.slider("Helix turns (scale φ^-turns)", 1.0, 2.0, 1.5, 0.05, help="Owner range 1.25–1.75.")
        R0 = st.slider("Helix start radius R0", 35.0, 70.0, 52.0, 0.5)
        height = st.slider("Helix height (helical portion)", 100.0, 190.0, 160.0, 1.0,
                           help="Pitch = height / turns. Total height = lead-in + bends + helix + run-out ≤ 245.")
        tip_runout = st.slider("Tip run-out (axial)", 0.0, 20.0, 4.0, 0.5)
        bend_r = st.slider("Lead-in bend radius", 22.0, 50.0, 32.0, 0.5)
        tip_bend_r = st.slider("Tip bend radius", 12.0, 40.0, 20.0, 0.5)
        A = st.slider("Mouth egg major A (inner)", 30.0, 58.0, 54.0, 0.5, help="Minor B = A / φ.")
        egg_w = st.slider("Egg asymmetry w/a (0 = ellipse)", 0.0, 0.4, 0.2, 0.01)
        ind = st.slider("Indent width (× A)", 0.0, 0.4, 0.25, 0.01, help="0.25 = quarter egg = 13.5 mm at A = 54.")
        ind_d = st.slider("Indent depth (× indent width)", 0.0, 0.5, 0.25, 0.01)
        hwall = st.slider("Pipe wall (mm)", 1.2, 3.0, 2.0, 0.1)
        socket = st.slider("Mouth socket (mm, inside the lead-in)", 6.0, 20.0, 12.0, 0.5)
    with sb.expander("Adapter: circle → egg", expanded=False):
        cup_c = st.slider("Cup clearance on Ø (mm)", 0.0, 0.8, 0.3, 0.05)
        cup_w = st.slider("Cup wall (mm)", 1.6, 3.0, 1.9, 0.1)
        loft = st.slider("Loft length (mm)", 10.0, 40.0, 20.0, 0.5)
        spig = st.slider("Spigot length (mm)", 6.0, 12.0, 11.0, 0.5)
        spig_c = st.slider("Spigot clearance on Ø (mm)", 0.0, 0.8, 0.3, 0.05)
    fp = S.FunnelParams(a_half=a_half, h0=h0, H=H, collar=collar, land=land, wall=fwall)
    hp = S.HornParams(R0=R0, turns=turns, height=height, egg_A=A, egg_w=egg_w, indent=ind, indent_depth=ind_d,
                      wall=hwall, socket=min(socket, lead_in), lead_in=lead_in, bend_r=bend_r,
                      tip_bend_r=tip_bend_r, tip_runout=tip_runout)
    r_th = a_half / (h0 + H)
    ap = S.AdapterParams(land_od=2 * (r_th + fwall), cup_clearance=cup_c, cup_wall=cup_w, cup_len=max(land, 1.0),
                         throat_id=2 * r_th, loft=loft, spigot=min(spig, max(socket - 0.5, 1.0)),
                         spigot_clearance=spig_c)
    return view, fp, hp, ap


def _preview(fp, hp, ap):
    return (replace(fp, samples=91, segments=96), replace(hp, rings_per_turn=48, segments=64),
            replace(ap, segments=64))


@st.cache_data(show_spinner="Building preview meshes…", max_entries=8)
def _preview_meshes(fp, hp, ap):
    pf, ph, pa = _preview(fp, hp, ap)
    f, a, h = S.assembly(pf, ph, pa)
    single = dict(Funnel=S.build_funnel(pf), Horn=S.build_horn(ph), Adapter=S.build_adapter(pa, ph))
    pack = lambda m: (np.asarray(m.vertices), np.asarray(m.faces))
    return dict(mated={"Funnel": pack(f), "Adapter": pack(a), "Horn": pack(h)},
                flow=S.flow_path(pf, ph, pa),
                single={k: pack(m) for k, m in single.items()})


@st.cache_data(show_spinner="Building full-resolution STLs and running checks…", max_entries=4)
def _export(fp, hp, ap):
    meshes = dict(Schauberger_Funnel=S.build_funnel(fp), Schauberger_Horn=S.build_horn(hp),
                  Schauberger_Adapter=S.build_adapter(ap, hp))
    return {k: (S.stl_bytes(m), S.check(m)) for k, m in meshes.items()}


def _cutaway(parts: dict) -> dict:
    """Half-section the funnel and adapter (drop the half facing the +x camera) so the axis shows."""
    out = {}
    for name, (v, f) in parts.items():
        if name != "Horn":
            f = f[v[f].mean(1)[:, 0] < 0]
        out[name] = (v, f)
    return out


def figure(parts: dict, eye, height=640, flow=None, ortho=False, opacity=None, light=None) -> go.Figure:
    fig = go.Figure()
    for name, (v, f) in parts.items():
        fig.add_trace(go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2],
                                color=COLORS[name], name=name, showlegend=len(parts) > 1, flatshading=False,
                                hoverinfo="name", opacity=(opacity or {}).get(name, 1.0),
                                lighting=dict(ambient=0.35, diffuse=0.85, specular=0.25, roughness=0.5),
                                lightposition=light or dict(x=-300, y=-400, z=600)))
    if flow is not None:
        fig.add_trace(go.Scatter3d(x=flow[:, 0], y=flow[:, 1], z=flow[:, 2], mode="lines", name="Water path",
                                   line=dict(color="#1d4ed8", width=7), hoverinfo="name"))
        zlo, zhi = float(flow[:, 2].min()), float(flow[:, 2].max())
        fig.add_trace(go.Scatter3d(x=[0, 0], y=[0, 0], z=[zlo - 10, zhi + 10], mode="lines", name="Funnel axis",
                                   line=dict(color="#111827", width=3, dash="dash"), hoverinfo="name"))
    ax = dict(visible=False)
    cam = dict(eye=eye, up=dict(x=0, y=0, z=1))
    if ortho:
        cam["projection"] = dict(type="orthographic")
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor=BG,
                      legend=dict(x=0.01, y=0.98),
                      scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data", bgcolor=BG, camera=cam))
    return fig


def render(choice) -> None:
    view, fp, hp, ap = choice
    st.title("Schauberger vortex set — hyperbolic funnel · kudu horn · adapter")
    hd = S.horn_dims(hp)
    ad = S.adapter_dims(ap, hp)
    ztot = fp.collar + fp.H + fp.land
    st.caption(
        f"Funnel wall **r = {fp.a_half:g} / ({fp.h0:g} + t)**, t = 0…{fp.H:g} (inside Ø{2 * fp.a_half / fp.h0:.1f} → "
        f"Ø{2 * fp.a_half / (fp.h0 + fp.H):.1f}), {fp.collar:g} mm freeboard collar, {fp.land:g} mm throat land. "
        f"Horn: {hp.lead_in:g} mm axial lead-in, then a right-hand helix R0 {hp.R0:g} → {hd['R_end']:.1f} mm "
        f"over {hp.turns:g} turns ({hd['pitch']:.0f} mm pitch), axial tip, egg "
        f"{hd['mouth_A']:.1f} × {hd['mouth_B']:.1f} → {hd['tip_A']:.1f} × {hd['tip_B']:.1f} mm (÷φ per turn), "
        f"quarter-egg indent on the axis-side flank. Adapter: the only circle → egg transition (converging), "
        "keyed egg spigot. **STL in millimetres**; print funnel collar-down, horn mouth-down, adapter cup-down."
    )
    pm = _preview_meshes(fp, hp, ap)
    see = dict(Funnel=0.35, Adapter=0.55, Horn=0.6)
    if view == VIEWS[0]:
        st.plotly_chart(figure(pm["mated"], dict(x=1.7, y=-1.7, z=0.6), flow=pm["flow"], opacity=see),
                        width="stretch")
        st.caption("Use position: funnel throat land in the adapter cup (land end on the cup shoulder), adapter "
                   "spigot in the horn socket, horn lead-in on the funnel axis. Blue = water path. Preview resolution.")
    elif view == VIEWS[1]:
        st.plotly_chart(figure(_cutaway(pm["mated"]), dict(x=2.4, y=0.0, z=0.0), height=760, flow=pm["flow"],
                               ortho=True, light=dict(x=2000, y=-600, z=1200)), width="stretch")
        st.caption(f"Orthographic side elevation, funnel and adapter cut away. Water runs straight down the funnel axis (dashed), through the "
                   f"adapter and {hp.lead_in:g} mm of axial lead-in, bends into {hp.turns:g} golden-tapered turns "
                   f"and leaves the open tip {hd['tip_axis_deg']:.0f}° from vertical, "
                   f"{hd['tip_offset_from_mouth_axis']:.0f} mm off the funnel axis.")
    else:
        eye = dict(x=1.6, y=-1.6, z=0.7) if view != "Adapter" else dict(x=1.3, y=-1.3, z=1.2)
        st.plotly_chart(figure({view: pm["single"][view]}, eye), width="stretch")
        st.caption("Print position (z = 0 is the bed). Preview resolution; downloads are full resolution.")

    c = st.columns(4)
    c[0].metric("Funnel H × OD", f"{ztot:.1f} × {2 * (fp.a_half / fp.h0 + fp.wall):.1f} mm")
    c[1].metric("Horn height / tip egg", f"{hd['centreline_height']:.0f} / {hd['tip_A']:.0f}×{hd['tip_B']:.0f} mm")
    c[2].metric("Adapter cup ID / length", f"Ø{ad['cup_id']:.1f} / {ad['length']:.1f} mm")
    c[3].metric("Spigot egg (outer)", f"{ad['spigot_egg_out_A']:.2f} × {ad['spigot_egg_out_B']:.2f} mm")

    st.subheader("Downloads (full resolution, checked)")
    if ztot > S.ENVELOPE_MM[2]:
        st.warning(f"Funnel is {ztot:.1f} mm tall, over the {S.ENVELOPE_MM[2]:.0f} mm envelope: shorten the land.")
    if hd["centreline_height"] > S.ENVELOPE_MM[2]:
        st.warning(f"Horn is {hd['centreline_height']:.1f} mm tall, over the {S.ENVELOPE_MM[2]:.0f} mm envelope.")
    if st.button("Build STLs", width="stretch"):
        st.session_state["schauberger_built"] = (fp, hp, ap)
    if st.session_state.get("schauberger_built") == (fp, hp, ap):
        out = _export(fp, hp, ap)
        cols = st.columns(3)
        for col, (name, (data, ck)) in zip(cols, out.items()):
            ok = ck["watertight"] and ck["bodies"] == 1 and ck["winding_consistent"] and ck["is_volume"]
            col.download_button(f"{name}.stl ({len(data) / 1e6:.1f} MB)", data=data, file_name=f"{name}.stl",
                                mime="model/stl", width="stretch")
            ex = ck["extents"]
            col.caption(f"{'✅' if ok else '⚠️'} watertight {ck['watertight']}, bodies {ck['bodies']}, "
                        f"Euler {ck['euler']} (open pipe = genus 1), {ck['volume_cm3']:.1f} cm³, "
                        f"{ex[0]:.1f} × {ex[1]:.1f} × {ex[2]:.1f} mm, "
                        f"{'fits' if ck['fits'] else 'does NOT fit'} the 225 × 225 × 245 mm envelope")
    else:
        st.caption("Click **Build STLs** to generate the three full-resolution meshes (a few seconds).")

    with st.expander("Key dimensions"):
        st.markdown(
            f"- **Funnel:** height {ztot:.1f} mm ({fp.collar:g} collar + {fp.H:g} hyperbola + {fp.land:g} land), "
            f"wall {fp.wall:g} mm normal offset, OD {2 * (fp.a_half / fp.h0 + fp.wall):.1f} mm at the collar, "
            f"land OD {ap.land_od:.1f} mm.\n"
            f"- **Horn:** lead-in {hp.lead_in:g} mm (socket {hp.socket:g}), bend r {hp.bend_r:g} through "
            f"{hd['bend_in_deg']:.0f}°, helix z {hd['helix_start_z']:.1f} → {hd['helix_end_z']:.1f}, pitch "
            f"{hd['pitch']:.1f} mm, helix angle {hd['helix_angle_deg']:.1f}° → {hd['helix_angle_end_deg']:.1f}°, "
            f"tip bend r {hp.tip_bend_r:g} + {hp.tip_runout:g} mm run-out, height {hd['centreline_height']:.1f} mm, "
            f"tip axis {hd['tip_axis_deg']:.1f}° from vertical, {hd['tip_offset_from_mouth_axis']:.1f} mm off the "
            f"funnel axis, "
            f"indent {hd['indent_width']:.1f} wide × {hd['indent_depth']:.2f} deep at the mouth → "
            f"{hd['tip_indent_width']:.1f} × {hd['tip_indent_depth']:.2f} at the tip, bore area "
            f"{hd['mouth_area_cm2']:.1f} → {hd['tip_area_cm2']:.2f} cm², Hügelschäffer egg w/a = {hp.egg_w:g}.\n"
            f"- **Adapter:** cup Ø{ad['cup_id']:.2f} ID × {ad['cup_len']:g} mm, loft {ad['loft']:g} mm, spigot "
            f"{ad['spigot_len']:g} mm, egg {ad['spigot_egg_out_A']:.2f} × {ad['spigot_egg_out_B']:.2f} outside / "
            f"{ad['spigot_egg_in_A']:.2f} × {ad['spigot_egg_in_B']:.2f} inside, overall {ad['length']:.1f} mm. "
            f"Bore: Ø{ap.throat_id:.1f} (flush with the funnel) converging to the spigot bore; "
            f"{ad['ledge_into_horn']:.2f} mm step out to the horn bore at the spigot tip."
        )
