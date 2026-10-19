"""Capture screenshots of the Rodin torus Streamlit app via Playwright."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEDIA = ROOT / "media"
MEDIA.mkdir(exist_ok=True)
PORT = 8511
URL = f"http://127.0.0.1:{PORT}"


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
