"""Generate a build123d Python snippet from CardParams."""

from __future__ import annotations

from geometry import PHI, CardParams, groove_specs


def generate_snippet(params: CardParams) -> str:
    specs = groove_specs(params)
    lines = [
        "from build123d import *",
        "import math",
        "",
        f"PHI = (1 + 5**0.5) / 2  # {PHI:.10f}",
        f"D = {params.diameter:.4f}  # mm diameter",
        f"T = {params.thickness:.4f}  # mm thickness",
        f"GROOVE_W = {params.groove_width:.4f}",
        f"GROOVE_D = {params.groove_depth:.4f}",
        f"PHI_SCALE = {params.phi_scale:.4f}",
        f"COIL = {params.coil_factor:.4f}",
        f"ROT = {params.rotation_deg:.4f}",
        "",
        "grooves = [",
    ]
    for g in specs:
        lines.append(
            f"    # i={g.index}  φ^{g.index % 4}  span={g.span:.4f} mm  "
            f"θ={g.angle_deg:.2f}°  r=[{g.r_start:.3f}, {g.r_end:.3f}]"
        )
        lines.append(
            f"    dict(angle={g.angle_deg:.6f}, r0={g.r_start:.6f}, r1={g.r_end:.6f}),"
        )
    lines += [
        "]",
        "",
        "with BuildPart() as rodin_coil_card:",
        "    with BuildSketch():",
        "        Circle(radius=D / 2)",
        "    extrude(amount=T)",
        "    for g in grooves:",
        "        span = g['r1'] - g['r0']",
        "        mid = 0.5 * (g['r0'] + g['r1'])",
        "        a = math.radians(g['angle'])",
        "        loc = Location(",
        "            (mid * math.cos(a), mid * math.sin(a), T - GROOVE_D),",
        "            (0, 0, g['angle']),",
        "        )",
        "        with BuildSketch(loc):",
        "            Rectangle(span + 0.1, GROOVE_W)",
        "        extrude(amount=GROOVE_D + 0.05, mode=Mode.SUBTRACT)",
        "",
        "part = rodin_coil_card.part",
        "# export_stl(part, 'rodin_coil_card.stl')",
        "# export_step(part, 'rodin_coil_card.step')",
        "",
    ]
    return "\n".join(lines)
