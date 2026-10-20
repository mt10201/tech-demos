"""Capture screenshots of the running app into media/ (headless Streamlit + Playwright).

    pip install -r requirements-dev.txt && python -m playwright install chromium
    python capture.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEDIA = ROOT / "media"
PORT = 8521
URL = f"http://127.0.0.1:{PORT}"


def wait_for_server(timeout: float = 60) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(f"{URL}/_stcore/health", timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Streamlit did not start")


def settle(page, extra: float = 2.5) -> None:
    page.wait_for_timeout(800)
    page.wait_for_selector('[data-testid="stStatusWidget"]', state="detached", timeout=120_000)
    page.wait_for_selector(".js-plotly-plot", timeout=120_000)
    page.wait_for_timeout(int(extra * 1000))


def pick(page, label_prefix: str, value: str) -> None:
    box = page.locator('[data-testid="stMultiSelect"]').filter(has_text=label_prefix).first
    box.locator("input").click()
    box.locator("input").fill(value)
    page.wait_for_timeout(400)
    page.get_by_role("option", name=value, exact=True).first.click()
    page.keyboard.press("Escape")
    settle(page, 1.5)


def main() -> None:
    from playwright.sync_api import sync_playwright

    MEDIA.mkdir(exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.port", str(PORT),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=ROOT,
    )
    try:
        wait_for_server()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            page.goto(URL)
            settle(page, 4)
            page.screenshot(path=str(MEDIA / "01_overview_equities.png"), full_page=True)

            pick(page, "Country", "United States")
            pick(page, "Sector", "Information Technology")
            pick(page, "Market cap", "Mega Cap")
            pick(page, "Market cap", "Large Cap")
            page.screenshot(path=str(MEDIA / "02_filtered_us_tech_large.png"), full_page=True)

            page.get_by_label("Search name / symbol / summary").fill("semiconductr")
            page.keyboard.press("Enter")
            settle(page, 2)
            page.screenshot(path=str(MEDIA / "03_fuzzy_search_typo.png"), full_page=True)

            page.get_by_text("ETFs", exact=True).first.click()
            page.wait_for_timeout(1500)
            settle(page, 3)
            page.screenshot(path=str(MEDIA / "04_etfs_overview.png"), full_page=True)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=20)
    for f in sorted(MEDIA.glob("*.png")):
        print("wrote", f.relative_to(ROOT))


if __name__ == "__main__":
    main()
