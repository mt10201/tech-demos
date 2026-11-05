"""Export the revised 70 mm Rodin tori in mm, print pose, without touching listing files."""
from pathlib import Path
import json
import sys

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from boolean_mesh import grooved_solid  # noqa: E402
from geometry import MM_PER_IN, TorusParams, min_wall  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace/exports/rodin_70mm_v2")
OUT.mkdir(parents=True, exist_ok=True)
R = 70 / 6 / MM_PER_IN
KW = dict(chord=0.0005, ds=0.02, n_arc=20)
variants = [
    ("rodin_coil_torus_70mm_12x12_1.6mm.stl", 12, 1.6),
    ("rodin_coil_torus_70mm_pendant_6x6_2.5mm.stl", 6, 2.5),
]
report = []
for filename, count, width_mm in variants:
    p = TorusParams(major_radius=2 * R, tube_radius=R, n_grooves=count,
                    groove_width=width_mm / MM_PER_IN, groove_depth=width_mm / MM_PER_IN)
    vertices, faces = grooved_solid(p, **KW)
    mesh = trimesh.Trimesh(vertices * MM_PER_IN, faces, process=True)
    mesh.apply_translation([0, 0, -mesh.bounds[0, 2]])
    path = OUT / filename
    mesh.export(path)
    # Re-open exactly as a slicer does, then check body count and genus from topology.
    loaded = trimesh.load_mesh(path, process=True)
    bodies = loaded.split(only_watertight=False)
    wall_mm, theta_deg = min_wall(p)
    record = {
        "file": filename, "grooves_per_direction": count,
        "groove_width_mm": width_mm, "groove_depth_mm": width_mm,
        "minimum_wall_mm": wall_mm * MM_PER_IN, "minimum_wall_theta_deg": theta_deg,
        "watertight": bool(loaded.is_watertight), "winding_consistent": bool(loaded.is_winding_consistent),
        "positive_volume": bool(loaded.is_volume), "single_body": len(bodies) == 1,
        "genus": int((2 - loaded.euler_number) / 2), "extents_mm": loaded.extents.tolist(),
        "bounds_mm": loaded.bounds.tolist(), "triangles": len(loaded.faces),
    }
    assert all(record[k] for k in ("watertight", "winding_consistent", "positive_volume", "single_body"))
    assert record["genus"] == 1
    assert abs(record["bounds_mm"][0][2]) < 1e-6
    assert np.allclose(loaded.extents[:2], 70, atol=0.2)
    report.append(record)
    print(json.dumps(record), flush=True)
(OUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
