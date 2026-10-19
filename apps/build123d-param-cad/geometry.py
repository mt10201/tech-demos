"""Rodin torus groove math (pure Python + numpy, no CAD deps).

Units: geometry is computed in **inches** (groove sizes are 1/8" fractions);
every export (STL / STEP) is scaled to **millimetres** with ``MM_PER_IN`` so
slicers and CAD import it at true size.

Default size = royal-cubit harmonics
------------------------------------
    C = royal cubit = 523.6 mm (52.36 cm)
    tube cross-section circumference 2πr = C/4  →  r = C/(8π) ≈ 20.834 mm
    ring centre-line circumference  2πR = C/2  →  R = C/(4π) ≈ 41.667 mm
    outer Ø = 2(R + r) ≈ 125.0 mm, height = 2r ≈ 41.67 mm
The old SOLIDWORKS sketch (R = 1.39", r = 0.695") is ``SOLIDWORKS_SIZE``.

Torus coordinates
-----------------
    φ  (phi)   – azimuth around the main Z axis (the axis you look along in
                 the "front view" / the photo)
    θ  (theta) – angle around the tube: 0 = outer equator (rim),
                 90° = front face, 180° = inner equator (hole)
    point(θ, φ) = ((R + ρ cos θ) cos φ, (R + ρ cos θ) sin φ, ρ sin θ)

Patterns
--------
``photo`` (default, "Photo replica")
    The lattice measured from the owner's photo of a real Rodin coil frame:
    12 grooves in **each** rotational direction (24 total).  Every groove is a
    constant-pitch helix on the torus,

        φ(θ) = φ₀ ± (sweep / 180°) · θ,      θ: 0 → 360°

    so it travels ``sweep`` degrees around the axis between rim and hole
    (≈150° in the photo) and 2·sweep per full wrap.  The two families cross
    and leave raised rhombus tiles that shrink toward the hole.

``rodin`` / ``mirror``
    The earlier golden-spiral variants: one family of 12; on the front half
    (θ 0 → 180°) the path seen along the axis is an exact golden logarithmic
    spiral, φ = φ₀ + (π/2)·log_φ(q_max/q) with q = R + ρ cos θ.  The back half
    closes the Rodin 150° skip (rodin: 510° per wrap, grooves chain i → i+5)
    or mirrors the golden spiral (mirror).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

PHI = (1.0 + math.sqrt(5.0)) / 2.0  # ≈ 1.6180339887
RODIN_ADVANCE_DEG = 510.0  # 360° + 150° (skip 5 of 12 poles)
PATTERNS = ("photo", "rodin", "mirror")
PATTERN_LABELS = {
    "photo": "Photo replica — 12 + 12 crisscross lattice",
    "rodin": "Rodin golden spiral — 12 grooves, 150° skip, closed winding",
    "mirror": "Mirror golden spiral — 12 open grooves",
}
PHOTO_SWEEP_DEG = 150.0  # measured from the photo: rim → hole travel

MM_PER_IN = 25.4
# Egyptian royal cubit ≈ 52.36 cm (Petrie's measured 20.62 in; also ≈ π/6 m).
# All default torus sizes are harmonic fractions of this length.
ROYAL_CUBIT_MM = 523.6
CUBIT_FRACTIONS = {"1/4": 0.25, "1/2": 0.5, "1": 1.0}


def cubit_radius_mm(fraction: float) -> float:
    """Radius (mm) of a circle whose circumference is ``fraction`` × royal cubit."""
    return ROYAL_CUBIT_MM * fraction / (2.0 * math.pi)


def cubit_radius_in(fraction: float) -> float:
    return cubit_radius_mm(fraction) / MM_PER_IN


CUBIT_TUBE_FRACTION = 0.25  # tube cross-section circumference = C/4 (13.09 cm)
CUBIT_RING_FRACTION = 0.5  # ring centre-line circumference = C/2 (26.18 cm)
SOLIDWORKS_SIZE = (1.39, 0.695)  # (R, r) inches, the owner's original sketch


@dataclass(frozen=True)
class TorusParams:
    """Parametric inputs (inches / degrees). Defaults: royal-cubit harmonics."""

    major_radius: float = cubit_radius_in(CUBIT_RING_FRACTION)  # axis → tube centre (41.667 mm)
    tube_radius: float = cubit_radius_in(CUBIT_TUBE_FRACTION)  # minor radius (20.834 mm)
    n_grooves: int = 12  # per direction
    groove_depth: float = 0.125  # 1/8" total depth
    groove_width: float = 0.125  # 1/8" wide → U-groove (r=1/16 bottom + 1/16 walls)
    pattern: str = "photo"  # "photo" | "rodin" | "mirror"
    sweep_deg: float = PHOTO_SWEEP_DEG  # photo pattern: azimuth travelled rim → hole
    handedness: int = 1  # +1 / -1 mirrors the whole pattern
    rotation_deg: float = 0.0  # start pole of groove 0


def bounding_box_mm(p: TorusParams) -> Tuple[float, float, float]:
    """Overall (X, Y, Z) size of the exported part in mm."""
    od = 2.0 * (p.major_radius + p.tube_radius) * MM_PER_IN
    return od, od, 2.0 * p.tube_radius * MM_PER_IN


def validate(p: TorusParams) -> None:
    if p.major_radius <= 0 or p.tube_radius <= 0:
        raise ValueError("radii must be positive")
    if p.tube_radius >= p.major_radius:
        raise ValueError("tube_radius must be < major_radius (no self-intersecting torus)")
    if p.n_grooves < 1:
        raise ValueError("n_grooves must be >= 1")
    if not (0.0 < p.groove_depth < p.tube_radius):
        raise ValueError("groove_depth must be in (0, tube_radius)")
    if not (0.0 < p.groove_width < 2.0 * p.tube_radius):
        raise ValueError("groove_width must be in (0, 2·tube_radius)")
    if p.pattern not in PATTERNS:
        raise ValueError(f"pattern must be one of {PATTERNS}")
    if p.handedness not in (1, -1):
        raise ValueError("handedness must be +1 or -1")
    if not (0.0 < p.sweep_deg <= 720.0):
        raise ValueError("sweep_deg must be in (0, 720]")


def cutter_radius(p: TorusParams) -> float:
    """Radius of the circular part of the groove profile (true 3D inches).

    * depth ≥ width/2 → **U-groove**: semicircular bottom of radius width/2
      plus straight walls (depth − width/2) tall.  width = 2·depth is the pure
      semicircle; the default 1/8" × 1/8" is a U with 1/16" walls.
    * depth < width/2 → shallow circular arc of radius (w²/4 + d²)/(2d).
    """
    d, w = p.groove_depth, p.groove_width
    if d >= w / 2.0:
        return w / 2.0
    return (w * w / 4.0 + d * d) / (2.0 * d)


def wall_height(p: TorusParams) -> float:
    """Straight wall height of the U profile (0 for semicircle / shallow arc)."""
    return max(0.0, p.groove_depth - p.groove_width / 2.0)


def profile_depth(p: TorusParams, t: np.ndarray) -> np.ndarray:
    """Groove depth below the surface at true lateral distance ``t`` from the
    groove centre-line (inches).  0 outside the groove (|t| ≥ width/2)."""
    t = np.abs(np.asarray(t, dtype=float))
    rho = cutter_radius(p)
    inside = t < p.groove_width / 2.0
    dep = (p.groove_depth - rho) + np.sqrt(np.maximum(rho * rho - t * t, 0.0))
    return np.where(inside, np.clip(dep, 0.0, p.groove_depth), 0.0)


def path_radius(p: TorusParams) -> float:
    """Tube-radius of the profile's circle centre (r − depth + cutter radius)."""
    return p.tube_radius - p.groove_depth + cutter_radius(p)


def projected_limits(p: TorusParams) -> Tuple[float, float]:
    """(q_min, q_max): projected radius of the surface centre-line at hole / rim."""
    return p.major_radius - p.tube_radius, p.major_radius + p.tube_radius


def spiral_sweep(q_min: float, q_max: float) -> float:
    """Azimuth (radians) a golden spiral needs to grow from q_min to q_max."""
    return (math.pi / 2.0) * math.log(q_max / q_min) / math.log(PHI)


def golden_spiral_radius(q_max: float, dphi: float) -> float:
    """Projected radius after dphi radians of a golden spiral shrinking from q_max."""
    return q_max * PHI ** (-2.0 * dphi / math.pi)


def sweeps(p: TorusParams) -> Tuple[float, float]:
    """(front-half sweep, back-half sweep) in radians for one wrap."""
    validate(p)
    if p.pattern == "photo":
        s = math.radians(p.sweep_deg)
        return s, s
    q_min, q_max = projected_limits(p)
    top = spiral_sweep(q_min, q_max)
    if p.pattern == "rodin":
        bottom = math.radians(RODIN_ADVANCE_DEG) - top
        if bottom <= 0:
            raise ValueError("torus too fat for a 510° Rodin wrap")
    else:
        bottom = top
    return top, bottom


def wrap_advance_deg(p: TorusParams) -> float:
    top, bottom = sweeps(p)
    return math.degrees(top + bottom)


def families(p: TorusParams) -> List[int]:
    """Rotational directions present: photo has both, golden patterns one."""
    return [p.handedness, -p.handedness] if p.pattern == "photo" else [p.handedness]


def start_angles_deg(p: TorusParams) -> List[float]:
    step = 360.0 / p.n_grooves
    return [(p.rotation_deg + i * step) % 360.0 for i in range(p.n_grooves)]


def azimuth_offset(p: TorusParams, theta: np.ndarray) -> np.ndarray:
    """Azimuth travelled (radians, ≥0) at tube angle θ ∈ [0, 2π] along one wrap."""
    theta = np.asarray(theta, dtype=float)
    top, bottom = sweeps(p)
    if p.pattern == "photo":
        return theta * (top / math.pi)
    q_min, q_max = projected_limits(p)
    q = p.major_radius + p.tube_radius * np.cos(theta)
    s = np.log(q_max / q) / math.log(q_max / q_min)  # 0 at outer, 1 at inner
    s = np.clip(s, 0.0, 1.0)
    return np.where(theta <= math.pi, s * top, top + (1.0 - s) * bottom)


def groove_path(
    p: TorusParams,
    index: int,
    n: int = 241,
    direction: int | None = None,
    radius: float | None = None,
) -> np.ndarray:
    """(n, 3) points of groove ``index`` (one full wrap).

    By default the points are the profile-circle centre (tube radius
    ``path_radius``); pass ``radius=p.tube_radius`` for the groove's centre-line
    traced on the torus surface.
    """
    theta = np.linspace(0.0, 2.0 * math.pi, n)
    phi0 = math.radians(start_angles_deg(p)[index])
    hand = p.handedness if direction is None else direction
    phi = phi0 + hand * azimuth_offset(p, theta)
    rp = path_radius(p) if radius is None else radius
    q = p.major_radius + rp * np.cos(theta)
    return np.column_stack([q * np.cos(phi), q * np.sin(phi), rp * np.sin(theta)])


def all_paths(
    p: TorusParams, n: int = 241, radius: float | None = None
) -> List[np.ndarray]:
    """Every groove: n_grooves per family (family order = ``families``)."""
    return [
        groove_path(p, i, n, direction=fam, radius=radius)
        for fam in families(p)
        for i in range(p.n_grooves)
    ]


def min_centre_spacing(p: TorusParams, n: int = 721) -> Tuple[float, float]:
    """(spacing, θ_deg): closest approach of two same-direction groove centre-lines.

    Crossing grooves of the *other* direction are meant to intersect (that is
    the lattice), so only same-direction neighbours bound the tile walls.
    Samples within 4% of a groove's ends are skipped so chained grooves
    (end of i == start of j) don't count as a collision.
    """
    validate(p)
    from scipy.spatial import cKDTree

    k = max(1, int(0.04 * n))
    theta = np.linspace(0.0, 360.0, n)[k:-k]
    paths = [groove_path(p, i, n, radius=p.tube_radius)[k:-k] for i in range(p.n_grooves)]
    if len(paths) < 2:
        return float("inf"), 0.0
    others = np.vstack(paths[1:])
    d, _ = cKDTree(others).query(paths[0])
    j = int(np.argmin(d))
    return float(d[j]), float(theta[j])


def min_wall(p: TorusParams) -> Tuple[float, float]:
    """(wall, θ_deg): thinnest raised wall left between neighbouring grooves.

    wall = surface centre-line spacing − groove width (true 3D inches).
    Negative means the neighbouring grooves merge there.
    """
    s, th = min_centre_spacing(p)
    return s - p.groove_width, th


def photo_wall_analytic(p: TorusParams) -> float:
    """Closed-form wall at the hole for the photo pattern (for tests/README).

    At the inner equator neighbours are 2π/N apart in φ on a circle of radius
    q = R − ρ; the helix crosses it at angle α with tan α = ρ / (q·k),
    k = sweep/180°, so the perpendicular spacing is (2πq/N)·sin α.
    """
    rp = p.tube_radius  # centre-lines traced on the surface
    q = p.major_radius - rp
    k = p.sweep_deg / 180.0
    spacing = (2 * math.pi * q / p.n_grooves) * rp / math.hypot(rp, q * k)
    return spacing - p.groove_width


def describe_formula(p: TorusParams | None = None) -> str:
    sweep = p.sweep_deg if p else PHOTO_SWEEP_DEG
    return (
        "Units: inches internally, exports in mm.  φ = (1+√5)/2 ≈ 1.6180339887\n"
        "point(θ,φ) = ((R + ρ cos θ) cos φ, (R + ρ cos θ) sin φ, ρ sin θ)\n"
        "Profile (true 3D): depth(t) = (d − ρ) + √(ρ² − t²) for |t| < w/2, t = 3D distance\n"
        "  to the surface centre-line;  ρ = w/2 (U-groove / semicircle) or (w²/4+d²)/(2d)\n"
        f"Photo replica: φ = φ₀ ± ({sweep:.0f}°/180°)·θ, θ 0→360°, 12 grooves per sign\n"
        "  φ₀ = rotation + i·30°  → crisscross lattice, rhombus tiles\n"
        "Golden: front half φ = φ₀ + (π/2)·log_φ(q_max/q), q = R + r cos θ\n"
        "  back half rodin → 510° per wrap (150° skip), mirror → same spiral"
    )
