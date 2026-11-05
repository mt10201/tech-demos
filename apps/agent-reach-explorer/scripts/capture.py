"""Capture real screenshots and a short walkthrough of the running app."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8613"
MEDIA = Path(__file__).resolve().parents[1] / "media"
MEDIA.mkdir(exist_ok=True)


def settle(page, milliseconds=2500):
    page.wait_for_timeout(700)
    page.wait_for_function(
        """() => !document.querySelector("[data-testid='stSpinner']")
        && !document.querySelector("[data-stale='true']")""",
        timeout=120000,
    )
    page.wait_for_timeout(milliseconds)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
    context = browser.new_context(
        viewport={"width": 1600, "height": 1000},
        record_video_dir="/tmp/agent-reach-video",
        record_video_size={"width": 1600, "height": 1000},
    )
    page = context.new_page()
    page.goto(URL)
    settle(page, 3500)
    page.screenshot(path=str(MEDIA / "01-ready.png"))
    page.get_by_role("button", name="Search all three").click()
    settle(page, 6000)
    page.screenshot(path=str(MEDIA / "02-three-source-results.png"))
    page.mouse.wheel(0, 750)
    page.wait_for_timeout(1800)
    page.screenshot(path=str(MEDIA / "03-video-web-results.png"))
    page.get_by_text("Needs session / key", exact=False).scroll_into_view_if_needed()
    page.wait_for_timeout(1800)
    page.screenshot(path=str(MEDIA / "04-session-key-gates.png"))
    page.get_by_role("tab", name="Table & CSV").click()
    settle(page, 1800)
    page.get_by_text("Download combined CSV").scroll_into_view_if_needed()
    page.wait_for_timeout(1500)
    page.screenshot(path=str(MEDIA / "05-table-csv.png"))
    video = page.video.path()
    context.close()
    browser.close()

output = MEDIA / "06-walkthrough.mp4"
subprocess.run([
    "ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
    "-vf", "scale=1280:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
    "-crf", "28", "-movflags", "+faststart", str(output),
], check=True)
print(f"Saved screenshots and {output.name}")
