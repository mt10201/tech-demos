"""Show which edges make a build123d fillet fail (units: mm).

    python scripts/fillet_debug.py            # in the app venv (build123d 0.13): per-edge search
    /workspace/b3d-dev-venv/bin/python scripts/fillet_debug.py   # build123d dev: native PR #1525 message

Builds a 30 x 20 x 4 mm plate with a 1.5 mm step and asks for an r = 2.5 fillet on every top edge,
which is too big for the step and the plate's 4 mm thickness. Also demos filter_by_value
(build123d PR #1524) via the b3d_compat shim, selecting edges by length.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import build123d as bd  # noqa: E402

from b3d_compat import NATIVE_FILTER_BY_VALUE, faulty_fillet_edges, filter_by_value  # noqa: E402


def plate():
    p = bd.Box(30, 20, 4, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    p += bd.Pos(8, 0, 4) * bd.Box(14, 20, 1.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return p.solids()[0]


def main() -> int:
    print(f"build123d {bd.__version__}; native filter_by_value: {NATIVE_FILTER_BY_VALUE}")
    s = plate()
    top = s.edges().filter_by(bd.Axis.Z, reverse=True).filter_by_position(bd.Axis.Z, 3.9, 6)
    edges = list(top)
    long20 = filter_by_value(top, bd.Edge.length, 20.0)
    print(f"{len(edges)} non-vertical top edges; {len(long20)} of them are 20 mm long (filter_by_value)")
    r = 2.5
    try:
        s.fillet(r, edges)
        print("fillet succeeded")
        return 0
    except Exception as exc:
        print(f"\nnative error ({type(exc).__name__}):\n  {exc}")
    bad = faulty_fillet_edges(s, r, edges)
    print(f"\nper-edge search (works on any version): drop {len(bad)} edge(s) for r={r}:")
    for i in bad:
        c = edges[i].center()
        print(f"  #{i}: centre ({c.X:.1f}, {c.Y:.1f}, {c.Z:.1f}) mm, length {edges[i].length:.1f} mm")
    ok = [e for i, e in enumerate(edges) if i not in bad]
    try:
        s.fillet(r, ok)
        print(f"fillet of the other {len(ok)} edges at r={r}: OK")
    except Exception as exc:
        print(f"the remaining {len(ok)} edges still fail together: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
