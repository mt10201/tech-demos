"""Capture screenshots of the Rodin torus Streamlit app via Playwright."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEDIA = ROOT / "media"
MEDIA.mkdir(exist_ok=True)
PORT = int(os.environ.get("CAPTURE_PORT", "8511"))
URL = f"http://127.0.0.1:{PORT}"


PHOTO = os.environ.get("REFERENCE_PHOTO", "")  # optional path to the owner's photo


def compose_comparison(photo: Path, render: Path, out: Path) -> None:
    """Photo (left) and app front view (right) at the same height, labelled."""
    from PIL import Image, ImageDraw

    a = Image.open(photo).convert("RGB")
    b = Image.open(render).convert("RGB")
    # crop the render to its content (drop the flat background margin)
    bg = b.getpixel((2, 2))
    diff = Image.eval(
        Image.merge("RGB", [c.point(lambda v, k=k: 255 if abs(v - bg[k]) > 12 else 0)
                            for k, c in enumerate(b.split())]).convert("L"),
        lambda v: v,
    )
    box = diff.getbbox()
    if box:
        pad = 12
        b = b.crop((max(0, box[0] - pad), max(0, box[1] - pad),
                    min(b.width, box[2] + pad), min(b.height, box[3] + pad)))
    h = 640
    a = a.resize((int(a.width * h / a.height), h))
    b = b.resize((int(b.width * h / b.height), h))
    canvas = Image.new("RGB", (a.width + b.width + 30, h + 40), "white")
    canvas.paste(a, (0, 40))
    canvas.paste(b, (a.width + 30, 40))
    d = ImageDraw.Draw(canvas)
    d.text((10, 12), "Reference photo (real Rodin coil frame)", fill="black")
    d.text((a.width + 40, 12), "App front view: Photo replica preset (royal-cubit size, 125 mm OD)", fill="black")
    canvas.save(out)
    print(f"wrote {out}")


def ensure_browsers():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])


def main():
    ensure_browsers()
    from playwright.sync_api import sync_playwright

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "app.py"),
            "--server.port",
            str(PORT),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        # Wait for server
        import urllib.request

        for _ in range(90):
            try:
                urllib.request.urlopen(URL, timeout=1)
                break
            except Exception:
                time.sleep(1)
        else:
            out = proc.stdout.read().decode() if proc.stdout else ""
            raise RuntimeError(f"Streamlit did not start on {URL}\n{out[-2000:]}")

        # Extra settle for first CAD build + Plotly
        time.sleep(8)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(URL, wait_until="networkidle", timeout=120_000)
            # Wait for Plotly canvas / mesh
            page.wait_for_timeout(12_000)
            hero = MEDIA / "preview.png"
            page.screenshot(path=str(hero), full_page=False)
            print(f"wrote {hero}")
            shot = MEDIA / "screenshot.png"
            page.screenshot(path=str(shot), full_page=True)
            print(f"wrote {shot}")

            # Front view element + side-by-side with the reference photo
            front = page.locator(".stPlotlyChart").nth(1)
            front.scroll_into_view_if_needed()
            page.wait_for_timeout(1500)
            fv = MEDIA / "front_view.png"
            front.screenshot(path=str(fv))
            print(f"wrote {fv}")
            if PHOTO and Path(PHOTO).exists():
                compose_comparison(Path(PHOTO), fv, MEDIA / "compare_photo.png")
            # Close-up: rim vs hole patches + cross-section profiles
            hdr = page.get_by_text("Close-up: rim vs hole at the same scale", exact=False).first
            hdr.scroll_into_view_if_needed()
            page.evaluate("window.scrollBy(0, -20)")
            page.wait_for_timeout(2500)
            cu = MEDIA / "closeup_rim_vs_hole.png"
            page.screenshot(path=str(cu), full_page=False)
            print(f"wrote {cu}")
            page.evaluate("window.scrollTo(0, 0)")

            # Zoomed 3D preview across the hole (like the owner's screenshot)
            page.get_by_text("Zoom across the hole").first.click()
            page.wait_for_timeout(9000)
            page.evaluate("window.scrollTo(0, 0)")
            z = page.locator(".stPlotlyChart").nth(0)
            zp = MEDIA / "zoom_groove_walls.png"
            z.screenshot(path=str(zp))
            print(f"wrote {zp}")
            page.get_by_text("Overview").first.click()
            page.wait_for_timeout(6000)

            # Mirror-closure variant (both spiral families, like the SW top view)
            page.get_by_text("Mirror golden spiral", exact=False).first.click()
            page.wait_for_timeout(15_000)
            page.evaluate("window.scrollTo(0, 0)")
            mirror = MEDIA / "preview_mirror.png"
            page.screenshot(path=str(mirror), full_page=False)
            print(f"wrote {mirror}")

            # Second shot: scroll to groove table / snippet
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            shot2 = MEDIA / "snippet.png"
            page.screenshot(path=str(shot2), full_page=False)
            print(f"wrote {shot2}")

            # Mold master mode (back on the Photo replica preset)
            page.evaluate("window.scrollTo(0, 0)")
            page.get_by_text("Photo replica", exact=False).first.click()
            page.wait_for_timeout(8000)
            page.get_by_text("Mold master", exact=True).first.click()
            page.wait_for_timeout(25_000)
            page.evaluate("window.scrollTo(0, 0)")
            mp = MEDIA / "mold_preview.png"
            page.screenshot(path=str(mp), full_page=False)
            print(f"wrote {mp}")
            for idx, name in ((0, "mold_in_frame.png"), (1, "mold_master_B.png"), (2, "mold_section.png"),
                              (3, "mold_groove_detail.png")):
                el = page.locator(".stPlotlyChart").nth(idx)
                el.scroll_into_view_if_needed()
                page.wait_for_timeout(1500)
                el.screenshot(path=str(MEDIA / name))
                print(f"wrote {MEDIA / name}")

            # Moai statue mode: real-scan head (default), then the parametric statue
            def moai_shots(prefix, wait_ms):
                page.wait_for_timeout(wait_ms)
                page.evaluate("""() => { window.scrollTo(0, 0);
                    document.querySelectorAll('*').forEach(e => { if (e.scrollTop > 0) e.scrollTop = 0; }); }""")
                page.wait_for_timeout(1000)
                shot = MEDIA / f"{prefix}_preview.png"
                page.screenshot(path=str(shot), full_page=False)
                print(f"wrote {shot}")
                views = ((0, "front"), (1, "side"), (2, "three_quarter"))
                if prefix == "moai_head_scan":
                    views += ((3, "back"),)
                for idx, view in views:
                    el = page.locator(".stPlotlyChart").nth(idx)
                    el.scroll_into_view_if_needed()
                    page.wait_for_timeout(1500)
                    el.screenshot(path=str(MEDIA / f"{prefix}_{view}.png"))
                    print(f"wrote {MEDIA / f'{prefix}_{view}.png'}")

            page.evaluate("window.scrollTo(0, 0)")
            page.get_by_text("Moai statue", exact=True).first.click()
            moai_shots("moai_head_scan", 25_000)
            page.evaluate("window.scrollTo(0, 0)")
            page.get_by_text("Parametric (full statue)", exact=True).first.click()
            moai_shots("moai", 20_000)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def mesh_wireframe(out: Path) -> None:
    """Mesh-viewer style close-up of the actual STL triangles near the rim."""
    import numpy as np
    import plotly.graph_objects as go
    from playwright.sync_api import sync_playwright

    sys.path.insert(0, str(ROOT))
    from boolean_mesh import EXPORT_KW, drop_degenerate, grooved_solid
    from geometry import TorusParams, all_paths

    p = TorusParams()
    v, f = grooved_solid(p, **EXPORT_KW)
    g0 = all_paths(p, 3601, radius=p.tube_radius)[0]
    S = g0[int(9 / 360 * 3600)]
    f = drop_degenerate(v, f)
    keep = np.linalg.norm(v[f].mean(axis=1) - S, axis=1) < 0.2
    ff = f[keep]
    used, inv = np.unique(ff, return_inverse=True)
    vv, ff = v[used] - S, inv.reshape(-1, 3)
    e = np.concatenate([ff[:, [0, 1]], ff[:, [1, 2]], ff[:, [2, 0]]])
    seg = np.full((len(e) * 3, 3), np.nan)
    seg[0::3], seg[1::3] = vv[e[:, 0]], vv[e[:, 1]]
    N = S / np.linalg.norm(S)
    fig = go.Figure([
        go.Mesh3d(x=vv[:, 0], y=vv[:, 1], z=vv[:, 2], i=ff[:, 0], j=ff[:, 1], k=ff[:, 2],
                  color="#d9b44a", flatshading=True, lighting=dict(ambient=0.5, diffuse=0.8)),
        go.Scatter3d(x=seg[:, 0], y=seg[:, 1], z=seg[:, 2], mode="lines",
                     line=dict(color="#333", width=1)),
    ])
    eye = N * 1.2 + np.array([0, 0, 0.6])
    ax = dict(visible=False)
    fig.update_layout(
        width=1000, height=800, showlegend=False, paper_bgcolor="white",
        margin=dict(l=0, r=0, t=40, b=0),
        title="Actual STL triangles at the outer rim (10 mm patch): groove walls follow the cutter, no grid steps",
        scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data",
                   camera=dict(eye=dict(x=eye[0], y=eye[1], z=eye[2]), up=dict(x=0, y=0, z=1))),
    )
    html = MEDIA / "_wire.html"
    fig.write_html(str(html), include_plotlyjs="cdn")
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1000, "height": 800})
        pg.goto(html.as_uri(), wait_until="networkidle")
        pg.wait_for_timeout(4000)
        pg.screenshot(path=str(out))
        b.close()
    html.unlink()
    print(f"wrote {out}")


def moai_scan_only():
    """Only the real-scan moai head shots (front / side / 3/4 / back + page), without the other modes."""
    ensure_browsers()
    import urllib.request
    from playwright.sync_api import sync_playwright

    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.port",
                             str(PORT), "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(URL, timeout=1)
                break
            except Exception:
                time.sleep(1)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(URL, wait_until="networkidle", timeout=120_000)
            page.wait_for_timeout(8000)
            page.get_by_text("Moai statue", exact=True).first.click()
            page.wait_for_timeout(25_000)
            page.evaluate("""() => { window.scrollTo(0, 0);
                document.querySelectorAll('*').forEach(e => { if (e.scrollTop > 0) e.scrollTop = 0; }); }""")
            page.wait_for_timeout(1000)
            page.screenshot(path=str(MEDIA / "moai_head_scan_preview.png"), full_page=False)
            print(f"wrote {MEDIA / 'moai_head_scan_preview.png'}")
            for idx, view in ((0, "front"), (1, "side"), (2, "three_quarter"), (3, "back")):
                el = page.locator(".stPlotlyChart").nth(idx)
                el.scroll_into_view_if_needed()
                page.wait_for_timeout(1500)
                el.screenshot(path=str(MEDIA / f"moai_head_scan_{view}.png"))
                print(f"wrote {MEDIA / f'moai_head_scan_{view}.png'}")
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    if sys.argv[1:] == ["moai-scan"]:
        moai_scan_only()
    else:
        main()
        mesh_wireframe(MEDIA / "mesh_wireframe_rim.png")
