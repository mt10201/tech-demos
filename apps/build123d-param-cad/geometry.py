"""Rodin torus groove math (pure Python + numpy, no CAD deps).

Units: **inches** (matches the owner's SOLIDWORKS sketch).

Torus coordinates
-----------------
    φ  (phi)   – azimuth around the main Z axis
    θ  (theta) – angle around the tube, 0 = outer equator, +90° = top
    point(θ, φ) = ((R + ρ cos θ) cos φ, (R + ρ cos θ) sin φ, ρ sin θ)

Each groove is one full wrap around the tube (θ: 0 → 360°) that also travels
around the main axis.  On the **top half** (θ 0 → 180°, outer equator → inner
equator) the azimuth is chosen so that the path, seen from directly above, is
an exact **golden logarithmic spiral**: its projected radius shrinks by φ for
every 90° of azimuth,

    q(θ)   = R + ρ cos θ                       (projected radius)
    φ(θ)   = φ₀ + (π/2) · log_φ(q_max / q(θ))
    Δ_top  = (π/2) · log_φ(q_max / q_min)      (≈ 205.5° for 1.39 / 0.695)

The **bottom half** (θ 180 → 360°) climbs back out to the outer equator with
the same log profile, sweeping Δ_bottom:

    * "rodin"  – Δ_bottom = 510° − Δ_top, so each wrap advances 150° (5 of 12
                 poles, the classic Rodin skip) and the 12 grooves chain
                 end-to-start into one continuous closed winding.
    * "mirror" – Δ_bottom = Δ_top, so the bottom is the mirror golden spiral
                 too (12 open-ended grooves, ends land between poles).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

PHI = (1.0 + math.sqrt(5.0)) / 2.0  # ≈ 1.6180339887
RODIN_ADVANCE_DEG = 510.0  # 360° + 150° (skip 5 of 12 poles)
CLOSURES = ("rodin", "mirror")


@dataclass(frozen=True)
class TorusParams:
    """Parametric inputs (inches / degrees)."""

    major_radius: float = 1.39  # axis → tube centre
    tube_radius: float = 0.695  # minor radius
    n_grooves: int = 12
    groove_depth: float = 0.1875  # 3/16"
    groove_width: float = 0.375  # = 2 × depth → true semicircle
    closure: str = "rodin"  # "rodin" | "mirror"
    handedness: int = 1  # +1 counter-clockwise from above, -1 clockwise
    rotation_deg: float = 0.0  # start pole of groove 0


def validate(p: TorusParams) -> None:
    if p.major_radius <= 0 or p.tube_radius <= 0:
        raise ValueError("radii must be positive")
    if p.tube_radius >= p.major_radius:
        raise ValueError("tube_radius must be < major_radius (no self-intersecting torus)")
    if p.n_grooves < 1:
        raise ValueError("n_grooves must be >= 1")
    if not (0.0 < p.groove_depth < p.tube_radius):
        raise ValueError("groove_depth must be in (0, tube_radius)")
    if p.groove_width < 2.0 * p.groove_depth - 1e-9:
        raise ValueError(
            "groove_width must be >= 2 × depth (narrower would undercut the semicircle)"
        )
    if p.closure not in CLOSURES:
        raise ValueError(f"closure must be one of {CLOSURES}")
    if p.handedness not in (1, -1):
        raise ValueError("handedness must be +1 or -1")


def cutter_radius(p: TorusParams) -> float:
    """Radius of the circular groove profile.

    width = 2·depth gives a true semicircle (radius = depth).  A wider groove of
    the same depth is a shallower circular arc with radius (w²/4 + d²) / (2d).
    """
    d, w = p.groove_depth, p.groove_width
    return (w * w / 4.0 + d * d) / (2.0 * d)


def path_radius(p: TorusParams) -> float:
    """Tube-radius at which the cutter axis runs (r − depth + cutter radius)."""
    return p.tube_radius - p.groove_depth + cutter_radius(p)


def projected_limits(p: TorusParams) -> Tuple[float, float]:
    """(q_min, q_max): projected radius of the cutter axis at inner / outer equator."""
    rp = path_radius(p)
    return p.major_radius - rp, p.major_radius + rp


def spiral_sweep(q_min: float, q_max: float) -> float:
    """Azimuth (radians) a golden spiral needs to grow from q_min to q_max."""
    return (math.pi / 2.0) * math.log(q_max / q_min) / math.log(PHI)


def golden_spiral_radius(q_max: float, dphi: float) -> float:
    """Projected radius after dphi radians of a golden spiral shrinking from q_max."""
    return q_max * PHI ** (-2.0 * dphi / math.pi)


def sweeps(p: TorusParams) -> Tuple[float, float]:
    """(Δ_top, Δ_bottom) in radians."""
    validate(p)
    q_min, q_max = projected_limits(p)
    top = spiral_sweep(q_min, q_max)
    if p.closure == "rodin":
        bottom = math.radians(RODIN_ADVANCE_DEG) - top
        if bottom <= 0:
            raise ValueError("torus too fat for a 510° Rodin wrap")
    else:
        bottom = top
    return top, bottom


def wrap_advance_deg(p: TorusParams) -> float:
    top, bottom = sweeps(p)
    return math.degrees(top + bottom)


def start_angles_deg(p: TorusParams) -> List[float]:
    step = 360.0 / p.n_grooves
    return [(p.rotation_deg + i * step) % 360.0 for i in range(p.n_grooves)]


def azimuth_offset(p: TorusParams, theta: np.ndarray) -> np.ndarray:
    """Azimuth travelled (radians, ≥0) at tube angle θ ∈ [0, 2π] along one wrap."""
    theta = np.asarray(theta, dtype=float)
    top, bottom = sweeps(p)
    q_min, q_max = projected_limits(p)
    q = p.major_radius + path_radius(p) * np.cos(theta)
    s = np.log(q_max / q) / math.log(q_max / q_min)  # 0 at outer, 1 at inner
    s = np.clip(s, 0.0, 1.0)
    return np.where(theta <= math.pi, s * top, top + (1.0 - s) * bottom)


def groove_path(p: TorusParams, index: int, n: int = 241) -> np.ndarray:
    """(n, 3) points of the cutter axis for groove ``index`` (one full wrap)."""
    theta = np.linspace(0.0, 2.0 * math.pi, n)
    phi0 = math.radians(start_angles_deg(p)[index])
    phi = phi0 + p.handedness * azimuth_offset(p, theta)
    rp = path_radius(p)
    q = p.major_radius + rp * np.cos(theta)
    return np.column_stack([q * np.cos(phi), q * np.sin(phi), rp * np.sin(theta)])


def all_paths(p: TorusParams, n: int = 241) -> List[np.ndarray]:
    return [groove_path(p, i, n) for i in range(p.n_grooves)]


def min_strand_gap(p: TorusParams) -> float:
    """Centre-to-centre spacing of neighbouring grooves at the inner equator.

    Paths cross the inner equator meridionally (dφ/dθ = 0 there), so the gap is
    simply the arc between crossings on the cutter-axis circle.  Compare it with
    the groove width: if gap < width, neighbouring grooves merge at the hole.
    """
    q_min, _ = projected_limits(p)
    return 2.0 * math.pi * q_min / p.n_grooves


def describe_formula() -> str:
    return (
        "Units: inches.  φ = (1+√5)/2 ≈ 1.6180339887\n"
        "point(θ,φ) = ((R + ρ cos θ) cos φ, (R + ρ cos θ) sin φ, ρ sin θ)\n"
        "ρ_axis   = r − depth + cutter_r      cutter_r = (w²/4 + d²)/(2d)\n"
        "Top half (θ 0→180°): φ = φ₀ + (π/2)·log_φ(q_max / q)   q = R + ρ_axis cos θ\n"
        "  → seen from above, each groove is a golden spiral (radius ÷ φ per 90°)\n"
        "Δ_top = (π/2)·log_φ(q_max/q_min)\n"
        "Bottom half: rodin → Δ_bot = 510° − Δ_top (150° pole skip, closed winding)\n"
        "             mirror → Δ_bot = Δ_top (mirror golden spiral, open ends)\n"
        "12 grooves start at φ₀ = rotation + i·30° on the outer equator."
    )
