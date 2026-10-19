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
PORT = 8511
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
    d.text((a.width + 40, 12), "App front view: Photo replica preset (R 1.39, r 0.695 in)", fill="black")
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
            hdr = page.get_by_text("Close-up: rim vs hole at the same scale")
            hdr.scroll_into_view_if_needed()
            page.evaluate("window.scrollBy(0, -20)")
            page.wait_for_timeout(2500)
            cu = MEDIA / "closeup_rim_vs_hole.png"
            page.screenshot(path=str(cu), full_page=False)
            print(f"wrote {cu}")
            page.evaluate("window.scrollTo(0, 0)")

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
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
