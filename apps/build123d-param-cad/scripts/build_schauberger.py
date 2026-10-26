"""Write the default Schauberger set to assets/schauberger/ (and optionally a second folder).

    python scripts/build_schauberger.py [/extra/output/dir]
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import schauberger as S  # noqa: E402

out = ROOT / "assets" / "schauberger"
out.mkdir(parents=True, exist_ok=True)
report = {}
for name, mesh in S.build_all().items():
    (out / f"{name}.stl").write_bytes(S.stl_bytes(mesh))
    report[name] = S.check(mesh)
    print(name, report[name])
S.funnel_step(out / "Schauberger_Funnel.step")
report["horn_dims"] = S.horn_dims()
report["horn_clearance"] = S.horn_clearance()
report["adapter_dims"] = S.adapter_dims()
(out / "checks.json").write_text(json.dumps(report, indent=2))
for extra in sys.argv[1:]:
    dst = Path(extra)
    dst.mkdir(parents=True, exist_ok=True)
    for f in out.iterdir():
        shutil.copy2(f, dst / f.name)
    print("copied to", dst)
