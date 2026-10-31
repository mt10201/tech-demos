"""Capture screenshots + a walkthrough video of the running app.

Usage:
  streamlit run app.py --server.port 8611 --server.headless true &
  python scripts/capture.py http://localhost:8611
Set CHROME_PATH to use an installed Chrome instead of Playwright's Chromium.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8611"
MEDIA = Path(__file__).resolve().parents[1] / "media"
MEDIA.mkdir(exist_ok=True)


def settle(page, ms=2500):
    """Wait until Streamlit has finished rerunning (no spinner, no stale elements)."""
    page.wait_for_timeout(800)
    page.wait_for_function(
        """() => !document.querySelector("[data-testid='stSpinner']")
              && !document.querySelector("[data-stale='true']")
              && !document.querySelector("[data-testid='stStatusWidget'] button")""",
        timeout=90000, polling=300)
    page.wait_for_timeout(ms)


def choose(page, label, option):
    page.get_by_role("combobox", name=label).first.click()
    page.get_by_role("option", name=option, exact=False).first.click()


def search(page):
    page.get_by_role("button", name="Search").click()
    settle(page, 4000)


def shot(page, name):
    page.screenshot(path=str(MEDIA / name))
    print("saved", name)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
    ctx = b.new_context(viewport={"width": 1500, "height": 950}, record_video_dir="/tmp/ia-video",
                        record_video_size={"width": 1500, "height": 950}, accept_downloads=True)
    page = ctx.new_page()
    page.goto(URL)
    settle(page, 6000)
    shot(page, "01-prelinger-results.png")

    # Film: player + downloads
    page.get_by_role("button", name="Preview & download").first.click()
    settle(page, 6000)
    page.evaluate("() => { const v = document.querySelector('video'); if (v) { v.muted = true; v.currentTime = 95; } }")
    page.wait_for_timeout(4000)
    shot(page, "02-film-player.png")
    page.get_by_text("Download files").scroll_into_view_if_needed()
    page.mouse.wheel(0, 250)
    page.wait_for_timeout(1500)
    shot(page, "03-film-downloads.png")
    page.get_by_role("button", name="✕ Close").click()
    settle(page)

    # 78rpm, commercial OK only, 1930-1970
    choose(page, "Collection", "78rpm records")
    page.get_by_text("Commercial reuse OK only").click()
    page.get_by_role("checkbox", name="Filter by year").check(force=True)
    search(page)
    shot(page, "04-78rpm-commercial-ok.png")
    page.get_by_role("button", name="Preview & download").nth(2).click()
    settle(page, 5000)
    try:
        page.wait_for_function("() => { const a = document.querySelector('audio'); return a && a.duration > 0; }",
                               timeout=20000)
    except Exception:
        pass
    shot(page, "05-78rpm-audio-player.png")
    try:
        with page.expect_download(timeout=120000) as dl:
            page.get_by_role("button", name="Download").first.click()
        d = dl.value
        print("download ok:", d.suggested_filename, Path(d.path()).stat().st_size, "bytes")
    except Exception as e:  # report, keep capturing
        print("download FAILED:", e)
    page.get_by_role("button", name="✕ Close").click()
    settle(page)

    # Live concerts: everything flagged
    choose(page, "Collection", "Live concerts")
    page.get_by_role("checkbox", name="Filter by year").uncheck(force=True)
    page.get_by_text("All", exact=True).click()
    search(page)
    shot(page, "06-live-concerts-flagged.png")

    # Free text + table/CSV
    choose(page, "Collection", "Anything")
    page.get_by_label("Search words").fill('"mount shasta"')
    choose(page, "Media type", "Any")
    search(page)
    page.get_by_role("tab", name="Table & CSV").click()
    settle(page, 2500)
    shot(page, "07-mount-shasta-table-csv.png")
    page.wait_for_timeout(1500)
    vid = page.video.path()
    ctx.close()
    b.close()

out = MEDIA / "08-walkthrough.mp4"
if shutil.which("ffmpeg"):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-vf", "scale=1200:-2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "30", "-movflags", "+faststart", str(out)], check=True)
    print("saved", out.name)
