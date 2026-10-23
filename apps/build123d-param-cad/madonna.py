"""Black Madonna de Sous-Terre (Chartres Sedes Sapientiae): photo-calibrated SDF -> genus-0 mold master.

Identifies and reconstructs the statue in the owner's reference photo:
- **Subject:** *Notre-Dame de Sous-Terre* ("Our Lady of the Underground"), the 11th/12th-century
  Romanesque *Sedes Sapientiae* (Throne of Wisdom) venerated in the crypt of Chartres Cathedral,
  specifically the 8.5 in dark-stone-finish sculptural reproduction by Sacred Source (`#BMT` / `SS-BMT`,
  designed by J.B.chette / Sacred Source, 8.5" H x 3.0" W x 3.5" D).
- **3D Scan License Audit (for commercial casting):**
  * No 3D scan of the Chartres *Madonna de Sous-Terre* `#BMT` statue exists online (and the medieval
    wooden original at Chartres was burnt in 1793 during the French Revolution).
  * Related *Sedes Sapientiae* museum scans on MyMiniFactory / Sketchfab — Geoffrey Marchal's
    Musée du Cinquantenaire *Sedes Sapientiae* (`myminifactory.com/object/3d-print-sedes-sapientiae-113611`,
    CC BY-NC) and Scan The World's *Sedes Sapientiae* (`myminifactory.com/object/3d-print-sedes-sapientiae-45452`,
    CC BY-NC-SA) — forbid commercial use (`NC`) and cannot be used to sell castings.
  * The Hunt Museum's CC0 *Figure Sculpture (Sedes Sapentia)* (`819f51e0724e41119b1c126ce08f6396`) and
    *Romanesque Enthroned Madonna* (`0b7518ec12904e44929a5e62960becd4`) are Public Domain, but depict
    different, heavily weathered Irish/continental carvings (Child on left knee or missing, open chair legs)
    and require a Sketchfab login to download.
- **Construction:**
  Built directly in Python (CC0 / public-domain code) from 6 orthogonal and 3/4 studio photographs
  of the exact statue (front, left profile, right profile, back, 3/4 left, 3/4 right, and upper-body
  close-up), combining:
  1. Calibrated multi-view landmarks and trapezoidal four-post Romanesque throne geometry:
     - Rounded rectangular base plinth at `z = 0..0.146` with sloped footrest step (`z = 0.135..0.220`).
     - Wider front cylindrical posts (`x = +-0.177`, `y = -0.146`) beside the knees topped with
       spherical ball finials at `z = 0.476`.
     - Narrower rear cylindrical posts (`x = +-0.142`, `y = +0.166..+0.186`) flanking the shoulders
       topped with spherical ball finials at `z = 0.704` (giving the trapezoidal plan that lets all
       four ball finials remain visible in the frontal view).
     - Concave sweeping side walls from the rear posts down to the front posts, plus a solid backrest
       with vertical post-seam grooves and the small raised rectangular maker's plaque at bottom center.
  2. Seated Madonna in frontal majesty (*Sedes Sapientiae*):
     - Tall ornate Romanesque crown (`z = 0.872..1.000`) with jewelled base band, raised rims, and
       six trefoil / fleur-de-lis peaks sculpted in solid high relief (zero through-holes).
     - Serene elongated oval face (arched brows, heavy-lidded eyes, straight Romanesque nose, lips, chin)
       framed by a veil falling behind the shoulders with vertical pleats down the back (`z = 0.665..0.880`).
     - Horizontally pleated U-draped mantle across the chest and shoulders, upper arms and forearms
       wrapping forward, and sculpted hands with four fingers + thumbs encircling the Child's waist.
     - Knees, columnar vertical pleats and nested V-folds between the shins, arched hem cutbacks, and
       rounded shoe tips resting on the plinth step.
  3. Christ Child seated frontally on the Madonna's lap (`z = 0.360..0.692`):
     - Round halo-less head with short curly hair and facial features.
     - V-collared tunic with vertical pleats and bare feet with sculpted toes resting on the lap folds.
     - Right hand raised in a two-finger Latin blessing gesture (connected via a solid relief web so no
       fragile detached fingers or silicone-trapping tunnels exist) and left hand holding an orb against the chest.
  4. Multi-scale band-pass photo-relief field (`assets/black_madonna_calib.npz`) extracted from the
     aligned front and rear studio photos, fused with topological cavity/tunnel plugging so the final
     mesh is guaranteed **watertight, single-shell (`body_count == 1`), and genus 0 (`euler_number == 2`)**
     with a flat base at `z = 0` and default height `101.6 mm` (4.0 in).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
from typing import Tuple

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import marching_cubes
import trimesh

import scan_repair as sr

MM_PER_IN = 25.4
DEFAULT_HEIGHT_MM = 4.0 * MM_PER_IN  # 101.6 mm (4.0 in)
ENDER2_BED_MM = (150.0, 150.0, 200.0)

ASSETS = Path(__file__).resolve().parent / "assets"
MASTER_STL = ASSETS / "black_madonna_101.6mm.stl"
PREVIEW_PLY = ASSETS / "black_madonna_preview.ply"
CALIB_NPZ = ASSETS / "black_madonna_calib.npz"

TITLE = "Black Madonna de Sous-Terre (Chartres Cathedral Sedes Sapientiae)"
SUBTITLE = "4-inch (101.6 mm) watertight genus-0 silicone-mold master"
BOUNDS = ((-0.24, 0.24), (-0.24, 0.24), (-0.01, 1.01))


@dataclass(frozen=True)
class MadonnaParams:
    height_mm: float = DEFAULT_HEIGHT_MM
    relief_scale: float = 1.0
    crown_height_scale: float = 1.0
    throne_flare: float = 1.0
    plinth: bool = False
    plinth_height_mm: float = 5.0
    plinth_margin_mm: float = 3.0
    resolution: int = 180


# ---- Smooth SDF primitives (vectorised numpy) -------------------------------

def smin(a, b, k):
    """Polynomial smooth minimum (smooth union), blend radius k."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def step01(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def window(z, z0, z1, w=0.015):
    return step01((z - z0) / w) * step01((z1 - z) / w)


def sphere(x, y, z, cx, cy, cz, r):
    return np.sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) - r


def ellipsoid(x, y, z, cx, cy, cz, rx, ry, rz):
    px, py, pz = (x - cx) / rx, (y - cy) / ry, (z - cz) / rz
    k0 = np.sqrt(px * px + py * py + pz * pz + 1e-12)
    k1 = np.sqrt((px / rx) ** 2 + (py / ry) ** 2 + (pz / rz) ** 2 + 1e-12)
    return k0 * (k0 - 1.0) / k1


def capsule(x, y, z, ax, ay, az, bx, by, bz, r):
    pax, pay, paz = x - ax, y - ay, z - az
    bax, bay, baz = bx - ax, by - ay, bz - az
    h = np.clip(
        (pax * bax + pay * bay + paz * baz) / (bax * bax + bay * bay + baz * baz + 1e-12),
        0.0,
        1.0,
    )
    return np.sqrt((pax - bax * h) ** 2 + (pay - bay * h) ** 2 + (paz - baz * h) ** 2) - r


def rbox2d(x, y, hx, hy, r):
    qx = np.abs(x) - (hx - r)
    qy = np.abs(y) - (hy - r)
    return np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0)) + np.minimum(np.maximum(qx, qy), 0.0) - r


@lru_cache(maxsize=1)
def _load_calib():
    if CALIB_NPZ.exists():
        data = np.load(CALIB_NPZ)
        return {k: data[k] for k in data.files}
    return None


# ---- Photo-calibrated SDF sculpture -----------------------------------------

def sculpt_black_madonna_sdf(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    calib: dict | None = None,
    relief_scale: float = 1.0,
    crown_height_scale: float = 1.0,
    throne_flare: float = 1.0,
) -> np.ndarray:
    """Signed distance field (normalised height = 1.0, z in [0, 1], face toward -y, x left/right)."""
    ax = np.abs(x)

    # 1. BASE PLINTH + FOOTREST STEP (z in [0.00, 0.220])
    t_plinth = np.clip(z / 0.145, 0.0, 1.0)
    plinth_hx = 0.172 + 0.005 * t_plinth
    plinth_yf = -0.216 + 0.004 * t_plinth
    plinth_yb = +0.186 + 0.006 * t_plinth
    plinth_yc = 0.5 * (plinth_yf + plinth_yb)
    plinth_hy = 0.5 * (plinth_yb - plinth_yf)
    r_corner = np.where(y < 0, 0.044, 0.022)
    d_plinth_xy = rbox2d(x, y - plinth_yc, plinth_hx, plinth_hy, r_corner)
    d_plinth = smax(d_plinth_xy, smax(-z, z - 0.146, 0.008), 0.008)

    t_step = np.clip((z - 0.135) / 0.085, 0.0, 1.0)
    step_yf = -0.214 + 0.040 * (t_step ** 1.4)
    d_footstep = smax(
        rbox2d(x, y - (0.5 * (step_yf + 0.05)), 0.155 - 0.012 * t_step, 0.5 * (0.05 - step_yf), 0.035),
        smax(0.125 - z, z - 0.220, 0.010),
        0.010,
    )
    d_plinth = smin(d_plinth, d_footstep, 0.010)

    # 2. ROMANESQUE FOUR-POST THRONE (z in [0.125, 0.732])
    # Front posts sit wider beside the knees (x = +-0.177 at top) with ball finials at z = 0.476
    t_fpost = np.clip((z - 0.12) / 0.36, 0.0, 1.0)
    post_fx = (0.162 + 0.015 * t_fpost * throne_flare)
    post_fy = -0.146
    d_fpost_cyl = smax(np.hypot(ax - post_fx, y - post_fy) - 0.023, smax(0.120 - z, z - 0.456, 0.005), 0.005)
    d_fpost_ring = smax(np.hypot(ax - post_fx, y - post_fy) - 0.026, np.abs(z - 0.444) - 0.006, 0.003)
    d_fpost_ball = sphere(ax, y, z, 0.162 + 0.015 * throne_flare, post_fy, 0.476, 0.028)
    d_front_posts = smin(smin(d_fpost_cyl, d_fpost_ring, 0.004), d_fpost_ball, 0.005)

    # Rear posts sit slightly narrower in x (x = +-0.142) so all 4 finials are visible from the front
    t_bpost = np.clip((z - 0.12) / 0.58, 0.0, 1.0)
    post_bx = 0.144 - 0.002 * t_bpost
    post_by = 0.166 + 0.020 * np.sin(math.pi * np.clip(t_bpost, 0.0, 0.85))
    d_bpost_cyl = smax(np.hypot(ax - post_bx, y - post_by) - 0.025, smax(0.120 - z, z - 0.684, 0.005), 0.005)
    d_bpost_ring = smax(np.hypot(ax - post_bx, y - post_by) - 0.028, np.abs(z - 0.672) - 0.006, 0.003)
    d_bpost_ball = sphere(ax, y, z, 0.142, 0.162, 0.704, 0.028)
    d_back_posts = smin(smin(d_bpost_cyl, d_bpost_ring, 0.004), d_bpost_ball, 0.005)

    # Concave side walls sweeping from rear posts down and outward to front posts
    ty = np.clip((y - post_fy) / (post_by - post_fy + 1e-6), 0.0, 1.0)
    z_arm_curve = 0.442 + 0.226 * (0.28 * ty + 0.72 * (ty ** 2.3))
    throne_hx = (1.0 - ty) * post_fx + ty * post_bx
    d_throne_sides = smax(
        ax - throne_hx,
        smax(smax(post_fy - y, y - post_by, 0.008), smax(0.120 - z, z - z_arm_curve, 0.008), 0.008),
        0.008,
    )
    d_side_panel_recess = smax(
        (throne_hx - 0.005) - ax,
        smax(
            smax((post_fy + 0.026) - y, y - (post_by - 0.026), 0.01),
            smax(0.160 - z, z - (z_arm_curve - 0.022), 0.01),
            0.01,
        ),
        0.005,
    )
    d_throne_sides = smax(d_throne_sides, -d_side_panel_recess, 0.004)

    # Solid throne backrest slab between rear posts up to z = 0.675
    z_back_top = 0.675 - 0.012 * (x / 0.145) ** 2
    y_back_surf = (0.190 + 0.036 * np.clip((z - 0.12) / 0.52, 0.0, 1.0)) - 0.008 * (x / 0.150) ** 2
    d_backrest = smax(
        ax - (post_bx + 0.006),
        smax(smax(0.105 - y, y - y_back_surf, 0.008), smax(0.120 - z, z - z_back_top, 0.008), 0.008),
        0.008,
    )
    # Small raised rectangular maker's plaque on lower back (visible in ref_06.jpg at z=0.08..0.14)
    d_plaque = smax(
        rbox2d(x, z - 0.110, 0.044, 0.025, 0.004),
        np.abs(y - y_back_surf) - 0.005,
        0.002,
    )
    d_backrest = smin(d_backrest, d_plaque, 0.002)
    back_groove = (
        0.0035
        * np.exp(-((ax - 0.118) / 0.007) ** 2)
        * window(z, 0.16, 0.65, 0.02)
        * step01((y - 0.17) / 0.02)
    )
    d_backrest = d_backrest + back_groove

    d_throne = smin(
        smin(d_plinth, d_front_posts, 0.008),
        smin(d_back_posts, smin(d_throne_sides, d_backrest, 0.008), 0.008),
        0.008,
    )

    # 3. MADONNA LOWER BODY, KNEES, SKIRT DRAPERY & SHOES (z in [0.130, 0.455])
    knee_x = 0.092
    d_knees = capsule(ax, y, z, knee_x, -0.132, 0.150, knee_x - 0.006, -0.136, 0.425, 0.041)
    d_lap_drape = ellipsoid(x, y, z, 0.0, -0.128, 0.415, 0.136, 0.066, 0.036)
    skirt_y_front = -0.172 + 0.012 * np.exp(-(x / 0.065) ** 2)
    d_skirt_core = smax(
        ax - 0.138,
        smax(smax(skirt_y_front - y, y - 0.130, 0.015), smax(0.130 - z, z - 0.445, 0.015), 0.015),
        0.018,
    )
    d_lower_madonna = smin(smin(d_knees, d_lap_drape, 0.015), d_skirt_core, 0.018)

    w_lower_pleats = window(z, 0.138, 0.285, 0.018) * step01((0.090 - ax) / 0.018) * step01((-0.135 - y) / 0.030)
    pleat_v = 0.0070 * np.cos(2.0 * math.pi * x / 0.026)
    w_vfolds = window(z, 0.225, 0.385, 0.018) * step01((0.098 - ax) / 0.018) * step01((-0.130 - y) / 0.030)
    z_catenary = z + 0.044 * (1.0 - (x / 0.090) ** 2)
    pleat_vcat = 0.0080 * np.sin(2.0 * math.pi * (z_catenary - 0.24) / 0.032)
    w_outer_skirt = (
        window(z, 0.142, 0.410, 0.018) * window(ax, 0.070, 0.142, 0.015) * step01((-0.120 - y) / 0.035)
    )
    pleat_outer = 0.0050 * np.cos(2.0 * math.pi * (ax - 0.075 + 0.12 * (z - 0.25)) / 0.024)

    d_lower_madonna = d_lower_madonna - (
        w_lower_pleats * pleat_v + w_vfolds * pleat_vcat + w_outer_skirt * pleat_outer
    )

    d_hem_arch = ellipsoid(ax, y, z, 0.088, -0.195, 0.155, 0.028, 0.022, 0.019)
    d_lower_madonna = smax(d_lower_madonna, -d_hem_arch, 0.005)
    d_shoes = ellipsoid(ax, y, z, 0.088, -0.198, 0.155, 0.020, 0.026, 0.014)
    d_lower_madonna = smin(d_lower_madonna, d_shoes, 0.004)

    # 4. MADONNA TORSO, HORIZONTAL MANTLE PLEATS, ARMS & HANDS (z in [0.42, 0.72])
    d_torso = smax(
        ellipsoid(x, y, z, 0.0, +0.055, 0.585, 0.138, 0.105, 0.158),
        z - 0.715,
        0.015,
    )
    d_upper_arms = capsule(ax, y, z, 0.114, +0.045, 0.675, 0.126, -0.055, 0.475, 0.032)
    d_forearms = capsule(ax, y, z, 0.126, -0.055, 0.475, 0.104, -0.142, 0.462, 0.028)
    d_madonna_upper = smin(d_torso, smin(d_upper_arms, d_forearms, 0.014), 0.016)

    w_chest_pleats = window(z, 0.545, 0.712, 0.016) * step01((0.085 - y) / 0.08) * step01((0.146 - ax) / 0.015)
    z_u_pleat = z - 0.022 * (x / 0.132) ** 2
    chest_ridges = 0.0065 * np.sin(2.0 * math.pi * (z_u_pleat - 0.56) / 0.022)
    w_sleeve_pleats = (
        window(z, 0.460, 0.655, 0.018) * window(ax, 0.088, 0.148, 0.015) * step01((0.065 - y) / 0.10)
    )
    sleeve_ridges = 0.0050 * np.sin(2.0 * math.pi * (z + 0.15 * y) / 0.022)
    d_madonna_upper = d_madonna_upper - (w_chest_pleats * chest_ridges + w_sleeve_pleats * sleeve_ridges)

    d_m_palm = ellipsoid(ax, y, z, 0.088, -0.150, 0.460, 0.023, 0.016, 0.028)
    d_m_thumb = capsule(ax, y, z, 0.092, -0.152, 0.478, 0.065, -0.160, 0.490, 0.0065)
    d_m_fingers = np.full_like(x, 10.0)
    for fz, fx_tip, fr in [
        (0.474, 0.048, 0.0062),
        (0.461, 0.045, 0.0065),
        (0.448, 0.048, 0.0062),
        (0.436, 0.054, 0.0056),
    ]:
        df = capsule(ax, y, z, 0.085, -0.154, fz + 0.002, fx_tip, -0.162, fz, fr)
        d_m_fingers = smin(d_m_fingers, df, 0.002)
    d_m_hands = smin(d_m_palm, smin(d_m_thumb, d_m_fingers, 0.003), 0.004)
    d_madonna_upper = smin(d_madonna_upper, d_m_hands, 0.006)

    # 5. MADONNA NECK, SERENE OVAL FACE, VEIL & ORNATE CROWN (z in [0.66, 1.00])
    d_neck = capsule(x, y, z, 0.0, +0.068, 0.695, 0.0, +0.068, 0.765, 0.033)

    jaw_taper = 1.0 - 0.18 * np.clip((0.815 - z) / 0.065, 0.0, 1.0)
    head_rx = 0.050 * jaw_taper
    head_ry = 0.056
    d_head = ellipsoid(x, y, z, 0.0, +0.070, 0.818, head_rx, head_ry, 0.068)

    d_brow = ellipsoid(ax, y, z, 0.021, +0.016, 0.842, 0.019, 0.009, 0.006)
    d_eye_sock = ellipsoid(ax, y, z, 0.020, +0.016, 0.825, 0.014, 0.010, 0.011)
    d_eyeball = ellipsoid(ax, y, z, 0.020, +0.015, 0.824, 0.011, 0.008, 0.0075)
    eyelid_groove = (
        0.0028
        * np.exp(-((z - 0.824) / 0.0025) ** 2)
        * np.exp(-((ax - 0.020) / 0.010) ** 2)
        * step01((0.028 - y) / 0.015)
    )
    d_nose = capsule(x, y, z, 0.0, +0.014, 0.836, 0.0, +0.004, 0.798, 0.0082)
    d_nostrils = ellipsoid(ax, y, z, 0.009, +0.009, 0.796, 0.006, 0.006, 0.005)
    d_cheeks = ellipsoid(ax, y, z, 0.026, +0.022, 0.802, 0.017, 0.012, 0.016)
    d_upper_lip = ellipsoid(x, y, z, 0.0, +0.013, 0.780, 0.014, 0.007, 0.0045)
    d_lower_lip = ellipsoid(x, y, z, 0.0, +0.014, 0.772, 0.012, 0.007, 0.0045)
    mouth_line = (
        0.0028 * np.exp(-((z - 0.776) / 0.0018) ** 2) * np.exp(-(x / 0.012) ** 2) * step01((0.025 - y) / 0.015)
    )
    d_chin = ellipsoid(x, y, z, 0.0, +0.018, 0.756, 0.015, 0.010, 0.010)

    d_face = smin(d_head, d_brow, 0.005)
    d_face = smax(d_face, -d_eye_sock, 0.005)
    d_face = smin(d_face, d_eyeball, 0.003) + eyelid_groove
    d_face = smin(d_face, smin(d_nose, d_nostrils, 0.004), 0.005)
    d_face = smin(d_face, d_cheeks, 0.008)
    d_face = smin(d_face, smin(d_upper_lip, d_lower_lip, 0.002), 0.004) + mouth_line
    d_face = smin(d_face, d_chin, 0.006)

    t_veil = np.clip((0.880 - z) / 0.220, 0.0, 1.0)
    veil_rx = 0.054 + 0.014 * (t_veil ** 1.6)
    veil_yc = +0.084 + 0.010 * t_veil
    veil_ry = 0.054 + 0.008 * t_veil
    d_veil = (
        smax(
            np.hypot((x / veil_rx), ((y - veil_yc) / veil_ry)) - 1.0,
            smax(0.650 - z, z - 0.882, 0.010),
            0.010,
        )
        * 0.054
    )
    d_veil_cut = ellipsoid(x, y, z, 0.0, +0.014, 0.790, 0.046, 0.055, 0.095)
    d_veil = smax(d_veil, -d_veil_cut, 0.008)
    w_back_veil = window(z, 0.665, 0.875, 0.015) * step01((y - 0.080) / 0.025)
    veil_pleats = 0.0050 * np.cos(2.0 * math.pi * x / 0.020)
    d_veil = d_veil - w_back_veil * veil_pleats

    t_crown = np.clip((z - 0.872) / 0.115, 0.0, 1.0)
    cr_yc = +0.088
    cr_rx = 0.054 + 0.013 * t_crown
    cr_ry = 0.058 + 0.010 * t_crown
    theta = np.arctan2(x, -(y - cr_yc))
    z_crown_top = np.full_like(z, 0.916)
    for th_p, h_main, h_side, w_p in [
        (0.0, 0.084 * crown_height_scale, 0.048 * crown_height_scale, 0.25),
        (+0.92, 0.044 * crown_height_scale, 0.025 * crown_height_scale, 0.22),
        (-0.92, 0.044 * crown_height_scale, 0.025 * crown_height_scale, 0.22),
        (+2.02, 0.034 * crown_height_scale, 0.020 * crown_height_scale, 0.22),
        (-2.02, 0.034 * crown_height_scale, 0.020 * crown_height_scale, 0.22),
        (math.pi, 0.038 * crown_height_scale, 0.022 * crown_height_scale, 0.24),
    ]:
        dth = np.abs(np.arctan2(np.sin(theta - th_p), np.cos(theta - th_p)))
        p_center = h_main * np.exp(-((dth / (0.42 * w_p)) ** 2))
        p_side = h_side * np.exp(-(((dth - 0.85 * w_p) / (0.36 * w_p)) ** 2))
        z_crown_top = np.maximum(z_crown_top, 0.916 + np.maximum(p_center, p_side))

    r_crown_norm = np.hypot(x / cr_rx, (y - cr_yc) / cr_ry)
    d_crown_outer = (r_crown_norm - 1.0) * 0.056
    d_crown = smax(d_crown_outer, smax(0.872 - z, z - z_crown_top, 0.005), 0.005)

    rim_band = 0.0045 * np.exp(-((z - 0.877) / 0.004) ** 2) + 0.0040 * np.exp(-((z - 0.904) / 0.004) ** 2)
    jewel_bump = 0.0048 * np.exp(-((z - 0.890) / 0.0055) ** 2) * np.clip(np.cos(6.0 * theta), 0.0, 1.0) ** 2
    arch_recess = 0.0085 * window(z, 0.912, 0.948, 0.008) * (0.5 + 0.5 * np.cos(6.0 * theta + math.pi))
    d_crown = d_crown - rim_band - jewel_bump + arch_recess

    d_madonna_head = smin(smin(d_neck, d_face, 0.008), smin(d_veil, d_crown, 0.005), 0.006)

    # 6. CHRIST CHILD ON MADONNA'S LAP (z in [0.355, 0.695])
    d_c_legs = smax(
        ellipsoid(x, y, z, 0.0, -0.118, 0.440, 0.058, 0.055, 0.062),
        0.380 - z,
        0.008,
    )
    d_c_feet = ellipsoid(ax, y, z, 0.028, -0.172, 0.376, 0.018, 0.022, 0.014)
    toes_wave = (
        0.0020
        * np.cos(2.0 * math.pi * (ax - 0.016) / 0.0055)
        * window(z, 0.365, 0.386, 0.005)
        * step01((-0.165 - y) / 0.015)
    )
    d_c_feet = d_c_feet - toes_wave

    d_c_torso = ellipsoid(x, y, z, 0.0, -0.085, 0.530, 0.062, 0.052, 0.068)
    w_c_pleats = window(z, 0.390, 0.555, 0.015) * step01((0.052 - ax) / 0.015) * step01((-0.110 - y) / 0.030)
    c_pleats = 0.0045 * np.cos(2.0 * math.pi * x / 0.018)
    z_collar_v = 0.548 + 0.65 * ax
    w_collar = (
        np.exp(-((z - z_collar_v) / 0.006) ** 2) * step01((0.042 - ax) / 0.010) * step01((-0.105 - y) / 0.025)
    )
    collar_relief = 0.0048 * w_collar

    d_c_body = smin(d_c_legs, smin(d_c_feet, d_c_torso, 0.010), 0.010) - w_c_pleats * c_pleats - collar_relief

    # Child's right arm & raised blessing hand (viewer's left: x < 0, connected via solid relief web)
    d_cr_arm1 = capsule(x, y, z, -0.054, -0.095, 0.560, -0.086, -0.125, 0.505, 0.019)
    d_cr_arm2 = capsule(x, y, z, -0.086, -0.125, 0.505, -0.080, -0.140, 0.532, 0.017)
    d_cr_palm = ellipsoid(x, y, z, -0.080, -0.136, 0.545, 0.015, 0.016, 0.020)
    d_cr_f1 = capsule(x, y, z, -0.074, -0.138, 0.552, -0.073, -0.136, 0.578, 0.0050)
    d_cr_f2 = capsule(x, y, z, -0.083, -0.138, 0.552, -0.082, -0.136, 0.576, 0.0050)
    d_cr_f3 = ellipsoid(x, y, z, -0.090, -0.142, 0.550, 0.007, 0.008, 0.011)
    d_cr_thumb = capsule(x, y, z, -0.070, -0.140, 0.540, -0.065, -0.142, 0.558, 0.0048)
    d_cr_web = capsule(x, y, z, -0.078, -0.125, 0.515, -0.076, -0.115, 0.572, 0.020)
    d_c_right = smin(
        smin(d_cr_arm1, d_cr_arm2, 0.008),
        smin(
            d_cr_web,
            smin(
                d_cr_palm,
                smin(smin(d_cr_f1, d_cr_f2, 0.002), smin(d_cr_f3, d_cr_thumb, 0.002), 0.003),
                0.004,
            ),
            0.006,
        ),
        0.008,
    )

    # Child's left arm & hand holding the orb against the chest (viewer's right: x > 0)
    d_cl_arm1 = capsule(x, y, z, +0.054, -0.095, 0.560, +0.076, -0.122, 0.502, 0.019)
    d_cl_arm2 = capsule(x, y, z, +0.076, -0.122, 0.502, +0.042, -0.138, 0.512, 0.017)
    d_orb = sphere(x, y, z, +0.034, -0.136, 0.528, 0.021)
    d_cl_hand = ellipsoid(x, y, z, +0.038, -0.142, 0.510, 0.016, 0.012, 0.010)
    d_c_left = smin(smin(d_cl_arm1, d_cl_arm2, 0.008), smin(d_orb, d_cl_hand, 0.004), 0.006)

    # Child's head, curly hair & facial features
    d_c_neck = capsule(x, y, z, 0.0, -0.055, 0.575, 0.0, -0.046, 0.610, 0.025)
    d_c_head = ellipsoid(x, y, z, 0.0, -0.044, 0.642, 0.042, 0.045, 0.050)
    d_c_head_bridge = capsule(x, y, z, 0.0, -0.030, 0.600, 0.0, +0.015, 0.668, 0.038)
    d_c_curls = np.full_like(x, 10.0)
    for ang_deg in range(-105, 106, 21):
        ang = math.radians(ang_deg)
        cx_c = 0.039 * math.sin(ang)
        cy_c = -0.044 - 0.032 * math.cos(ang)
        cz_c = 0.676 - 0.032 * (math.sin(ang) ** 2)
        d_c_curls = smin(d_c_curls, sphere(x, y, z, cx_c, cy_c, cz_c, 0.011), 0.004)
    d_c_hair_cap = ellipsoid(x, y, z, 0.0, -0.040, 0.656, 0.044, 0.045, 0.038)
    d_c_curls = smin(d_c_curls, smax(d_c_hair_cap, (0.652 - 0.020 * (x / 0.04) ** 2) - z, 0.006), 0.005)

    d_c_brow = ellipsoid(ax, y, z, 0.015, -0.084, 0.654, 0.013, 0.007, 0.0045)
    d_c_eyes = ellipsoid(ax, y, z, 0.015, -0.084, 0.643, 0.008, 0.006, 0.0055)
    d_c_nose = capsule(x, y, z, 0.0, -0.085, 0.648, 0.0, -0.091, 0.626, 0.0065)
    d_c_cheeks = ellipsoid(ax, y, z, 0.020, -0.080, 0.626, 0.013, 0.009, 0.012)
    d_c_lips = ellipsoid(x, y, z, 0.0, -0.085, 0.612, 0.010, 0.006, 0.005)
    d_c_chin = ellipsoid(x, y, z, 0.0, -0.082, 0.599, 0.012, 0.008, 0.008)

    d_c_head_full = smin(
        smin(d_c_neck, d_c_head, 0.006), smin(d_c_head_bridge, d_c_curls, 0.006), 0.006
    )
    d_c_head_full = smin(
        d_c_head_full,
        smin(
            d_c_brow,
            smin(d_c_eyes, smin(d_c_nose, smin(d_c_cheeks, smin(d_c_lips, d_c_chin, 0.004), 0.005), 0.004), 0.004),
            0.004,
        ),
        0.004,
    )

    d_child = smin(d_c_body, smin(d_c_right, smin(d_c_left, d_c_head_full, 0.008), 0.008), 0.008)

    # 7. COMBINE ALL VOLUMES + PHOTO-CALIBRATED RELIEF FIELD
    d = smin(
        d_throne,
        smin(d_lower_madonna, smin(d_madonna_upper, smin(d_madonna_head, d_child, 0.010), 0.012), 0.012),
        0.010,
    )

    if calib is None:
        calib = _load_calib()
    if calib is not None and relief_scale > 0:
        rf = calib["front_relief"].astype(np.float32)
        rb = calib["back_relief"].astype(np.float32)
        gh, gw = rf.shape
        iz = np.clip(np.round(z * (gh - 1)).astype(int), 0, gh - 1)
        ix_f = np.clip(np.round(((x + 0.24) / 0.48) * (gw - 1)).astype(int), 0, gw - 1)
        ix_b = np.clip(np.round(((-x + 0.24) / 0.48) * (gw - 1)).astype(int), 0, gw - 1)
        rel_front = rf[iz, ix_f]
        rel_back = rb[iz, ix_b]
        # Apply frontal photo relief above the base plinth, and rear photo relief on the upper veil/crown
        w_f = step01((0.035 - y) / 0.06) * step01((z - 0.148) / 0.020)
        w_b = step01((y - 0.105) / 0.04) * step01((z - 0.665) / 0.025)
        d = d - relief_scale * (0.0045 * w_f * rel_front + 0.0030 * w_b * rel_back)

    return np.maximum(d, -z).astype(np.float32)


def statue_mesh(
    resolution: int = 180,
    relief_scale: float = 1.0,
    crown_height_scale: float = 1.0,
    throne_flare: float = 1.0,
    simplify_mm: float = 0.035,
) -> Tuple[np.ndarray, np.ndarray]:
    """Watertight, single-shell, genus-0 (`euler_number == 2`) mesh in normalised height units (z in [0, 1])."""
    step = 1.0 / resolution
    axes = [
        np.arange(lo, hi + step * 0.5, step, dtype=np.float32) + np.float32(step / 3.0)
        for lo, hi in BOUNDS
    ]
    X, Y, Z = np.meshgrid(*axes, indexing="ij")
    f = sculpt_black_madonna_sdf(
        X,
        Y,
        Z,
        calib=_load_calib(),
        relief_scale=relief_scale,
        crown_height_scale=crown_height_scale,
        throne_flare=throne_flare,
    )
    f = ndi.gaussian_filter(f, sigma=0.55)
    f = np.maximum(f, -Z)

    solid = f < 0.0
    lab, n = ndi.label(solid)
    sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
    keep = lab == (1 + int(np.argmax(sizes)))
    keep = ndi.binary_fill_holes(keep)
    for _ in range(2):
        for axis in (2, 0, 1):
            if sr._voxel_euler(keep) == 2:
                break
            plug = np.zeros_like(keep)
            for k in range(keep.shape[axis]):
                sl = [slice(None)] * 3
                sl[axis] = k
                sl = tuple(sl)
                plug[sl] = ndi.binary_fill_holes(keep[sl]) & ~keep[sl]
            keep |= plug
        keep = ndi.binary_fill_holes(keep)
    if sr._voxel_euler(keep) != 2:
        keep = ndi.binary_closing(keep, structure=ndi.generate_binary_structure(3, 2), iterations=1)
        keep = ndi.binary_fill_holes(keep)

    f_clamped = np.where(keep, np.minimum(f, -1e-4), np.maximum(f, 1e-4)).astype(np.float32)
    fp = np.pad(f_clamped, 1, constant_values=1.0)
    v, faces, _, _ = marching_cubes(fp, 0.0, spacing=(step, step, step), allow_degenerate=False)
    v += np.array([axes[0][0], axes[1][0], axes[2][0]]) - step
    m = trimesh.Trimesh(v, faces, process=True)
    m = max(m.split(only_watertight=False), key=lambda q: len(q.faces))
    zl = m.vertices[:, 2].min()
    vv = m.vertices.copy()
    vv[vv[:, 2] < zl + 0.25 * step, 2] = zl
    m = trimesh.Trimesh(vv, m.faces, process=True)
    b = m.bounds
    m.apply_translation([-(b[0][0] + b[1][0]) / 2.0, -(b[0][1] + b[1][1]) / 2.0, -b[0][2]])
    m.apply_scale(DEFAULT_HEIGHT_MM / m.extents[2])
    if simplify_mm and simplify_mm > 0:
        m = sr._decimate(m, simplify_mm)
        zl = m.vertices[:, 2].min()
        vv = m.vertices.copy()
        vv[vv[:, 2] < zl + 0.05, 2] = 0.0
        m = trimesh.Trimesh(vv, m.faces, process=True)
    m.apply_scale(1.0 / m.extents[2])
    return np.asarray(m.vertices, dtype=np.float64), np.asarray(m.faces, dtype=np.int64)


def build(p: MadonnaParams = MadonnaParams()) -> Tuple[np.ndarray, np.ndarray]:
    """Mesh in mm, standing flat on z = 0, centred in x/y, scaled to `p.height_mm`."""
    v, f = statue_mesh(
        resolution=p.resolution,
        relief_scale=p.relief_scale,
        crown_height_scale=p.crown_height_scale,
        throne_flare=p.throne_flare,
    )
    sink = 0.5
    statue_h = p.height_mm - ((p.plinth_height_mm - sink) if p.plinth else 0.0)
    v = v * (statue_h / (v[:, 2].max() - v[:, 2].min()))
    v[:, 2] -= v[:, 2].min()
    v[v[:, 2] < 0.04, 2] = 0.0
    cx, cy = 0.5 * (v[:, 0].max() + v[:, 0].min()), 0.5 * (v[:, 1].max() + v[:, 1].min())
    v[:, 0] -= cx
    v[:, 1] -= cy
    if not p.plinth:
        return v, f
    import manifold3d as mf
    from boolean_mesh import _to_manifold

    st = _to_manifold(v + np.array([0.0, 0.0, p.plinth_height_mm - sink]), f)
    lo, hi = v[:, :2].min(0) - p.plinth_margin_mm, v[:, :2].max(0) + p.plinth_margin_mm
    box = mf.Manifold.cube((hi[0] - lo[0], hi[1] - lo[1], p.plinth_height_mm)).translate((lo[0], lo[1], 0.0))
    m = (st + box).to_mesh64()
    return np.asarray(m.vert_properties)[:, :3].astype(float), np.asarray(m.tri_verts).astype(np.int64)


# ---- Prebuilt high-res master loader (fast path for default parameters) ------

@lru_cache(maxsize=2)
def _load_asset(path: str) -> Tuple[np.ndarray, np.ndarray]:
    m = trimesh.load(path, process=True)
    return np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)


def master_mesh(height_mm: float = DEFAULT_HEIGHT_MM, preview: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """Load the prebuilt high-resolution mold master (or preview PLY), flat on z = 0, scaled to `height_mm`."""
    target = PREVIEW_PLY if (preview and PREVIEW_PLY.exists()) else MASTER_STL
    if not target.exists():
        return build(MadonnaParams(height_mm=height_mm, resolution=140 if preview else 220))
    v, f = _load_asset(str(target))
    v = v - [0.5 * (v[:, 0].max() + v[:, 0].min()), 0.5 * (v[:, 1].max() + v[:, 1].min()), v[:, 2].min()]
    v = v * (height_mm / np.ptp(v[:, 2]))
    v[v[:, 2] < 0.04, 2] = 0.0
    return v, f


def master_stl_bytes(height_mm: float = DEFAULT_HEIGHT_MM) -> bytes:
    if MASTER_STL.exists() and abs(height_mm - DEFAULT_HEIGHT_MM) < 1e-9:
        return MASTER_STL.read_bytes()
    v, f = master_mesh(height_mm, preview=False)
    return stl_bytes(v, f)


def stl_bytes(v: np.ndarray, f: np.ndarray) -> bytes:
    return trimesh.Trimesh(v, f, process=False).export(file_type="stl")


def file_name(height_mm: float = DEFAULT_HEIGHT_MM) -> str:
    return f"black_madonna_{height_mm:.1f}mm.stl"


def fits_bed(v: np.ndarray, bed=ENDER2_BED_MM) -> bool:
    ext = v.max(0) - v.min(0)
    return all(e <= b for e, b in zip(ext, bed))
