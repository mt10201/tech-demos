"""Golden-ratio / Rodin-coil groove math (pure Python, no CAD deps)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

PHI = (1.0 + math.sqrt(5.0)) / 2.0  # ≈ 1.6180339887


@dataclass(frozen=True)
class GrooveSpec:
    """One radial groove on the Rodin coil card."""

    index: int
    angle_deg: float
    r_start: float
    r_end: float
    span: float
    phi_power: float


@dataclass(frozen=True)
class CardParams:
    """Parametric inputs for the Rodin coil card."""

    diameter: float = 100.0  # mm
    thickness: float = 4.0  # mm
    groove_width: float = 3.0  # mm
    groove_depth: float = 2.0  # mm
    phi_scale: float = 0.85  # multiplies available radial band → L0
    coil_factor: float = 0.55  # 0 = concentric starts; 1 = strong vortex drift
    rotation_deg: float = 0.0  # global θ₀
    inner_ratio: float = 0.18  # r_inner / (D/2)
    outer_ratio: float = 0.92  # r_outer / (D/2)
    rim_fillet: float = 0.5  # mm; 0 disables
    n_grooves: int = 12


def phi_powers(n: int = 12, cycle: int = 4) -> List[float]:
    """φ^(i % cycle) for i in 0..n-1."""
    return [PHI ** (i % cycle) for i in range(n)]


def normalized_spans(l0: float, n: int = 12, cycle: int = 4) -> List[float]:
    """
    Groove radial lengths.

    span_i = L0 * φ^(i % cycle) / max_k φ^(k % cycle)

    So the longest groove in each cycle equals L0; shorter ones follow φ ratios.
    """
    powers = phi_powers(n, cycle)
    peak = max(powers)
    return [l0 * p / peak for p in powers]


def groove_specs(params: CardParams) -> List[GrooveSpec]:
    """Compute 12 (or n) groove placements from CardParams."""
    if params.n_grooves < 1:
        raise ValueError("n_grooves must be >= 1")
    if not (0.0 < params.inner_ratio < params.outer_ratio <= 1.0):
        raise ValueError("need 0 < inner_ratio < outer_ratio <= 1")
    if params.diameter <= 0 or params.thickness <= 0:
        raise ValueError("diameter and thickness must be positive")
    if params.groove_depth > params.thickness + 1e-9:
        raise ValueError("groove_depth cannot exceed thickness")
    if not (0.0 <= params.coil_factor <= 1.0):
        raise ValueError("coil_factor must be in [0, 1]")
    if not (0.0 < params.phi_scale <= 1.0):
        raise ValueError("phi_scale must be in (0, 1]")

    r_outer = 0.5 * params.diameter * params.outer_ratio
    r_inner = 0.5 * params.diameter * params.inner_ratio
    band = r_outer - r_inner
    l0 = params.phi_scale * band
    spans = normalized_spans(l0, params.n_grooves)
    powers = phi_powers(params.n_grooves)
    step = 360.0 / params.n_grooves

    specs: List[GrooveSpec] = []
    for i, span in enumerate(spans):
        # Vortex / coil drift: later grooves walk outward (Rodin-inspired spiral).
        slack = max(0.0, band - span)
        drift = params.coil_factor * (i / params.n_grooves) * slack
        r_start = r_inner + drift
        r_end = r_start + span
        # Clamp into band if float noise pushes past r_outer.
        if r_end > r_outer + 1e-9:
            r_end = r_outer
            r_start = r_end - span
            if r_start < r_inner:
                r_start = r_inner
                r_end = r_start + min(span, band)
        angle = params.rotation_deg + i * step
        specs.append(
            GrooveSpec(
                index=i,
                angle_deg=angle % 360.0,
                r_start=r_start,
                r_end=r_end,
                span=r_end - r_start,
                phi_power=powers[i],
            )
        )
    return specs


def describe_formula() -> str:
    """Human-readable formula for UI / README."""
    return (
        "Rodin layout: 12 grooves at 30° (classic 12-pole spacing).\n"
        f"φ = (1+√5)/2 ≈ {PHI:.10f}\n"
        "span_i = L0 · φ^(i mod 4) / φ³   with L0 = φ_scale · (r_outer − r_inner)\n"
        "         (equivalent: normalize by max power so longest span = L0)\n"
        "r_start_i = r_inner + coil_factor · (i/12) · slack_i\n"
        "r_end_i   = r_start_i + span_i\n"
        "Note: classic Rodin winding uses a 5:12 ratio (musical fourth), not φ;\n"
        "this card keeps 12-around geometry and applies φ to radial groove spans."
    )
