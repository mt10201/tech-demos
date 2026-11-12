"""Capture real screenshots and a walkthrough of the running app."""
import os
from pathlib import Path
import subprocess
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8620"
MEDIA = Path(__file__).resolve().parents[1] / "media"

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH", "/usr/bin/google-chrome"))
    context = browser.new_context(viewport={"width":1600,"height":1050}, record_video_dir="/tmp/mpt-lab-video", record_video_size={"width":1600,"height":1050})
    page = context.new_page()
    page.goto(URL)
    page.wait_for_timeout(5000)
    page.screenshot(path=str(MEDIA / "01-lab-ready.png"))
    page.get_by_text("Optional API configuration").click()
    page.wait_for_timeout(1500)
    page.screenshot(path=str(MEDIA / "02-key-gates.png"))
    page.get_by_text("Optional API configuration").click()
    page.get_by_role("tab", name="Pre-baked sample").click()
    page.wait_for_timeout(2500)
    page.screenshot(path=str(MEDIA / "03-generated-sample.png"))
    page.get_by_text("Before you render").scroll_into_view_if_needed()
    page.wait_for_timeout(1800)
    page.screenshot(path=str(MEDIA / "04-requirements.png"))
    video = page.video.path()
    context.close()
    browser.close()
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(video),"-vf","scale=1280:-2","-c:v","libx264","-pix_fmt","yuv420p","-crf","28","-movflags","+faststart",str(MEDIA/"05-walkthrough.mp4")],check=True)
print("Captured four screenshots and walkthrough")
