"""Capture screenshots and a short video of the actual running app with Playwright."""
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8615"
MEDIA = Path(__file__).parents[1] / "media"
MEDIA.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1000},
                                  record_video_dir=str(MEDIA), record_video_size={"width": 1440, "height": 1000})
    page = context.new_page()
    page.goto(BASE)
    page.get_by_role("button", name="Build knowledge graph").click()
    page.get_by_text("Relationships", exact=True).wait_for(timeout=120_000)
    page.wait_for_timeout(6000)
    page.screenshot(path=MEDIA / "01-knowledge-graph.png", full_page=True)
    page.get_by_role("tab", name="⭐ Hubs & groups").click()
    page.wait_for_timeout(1200)
    page.screenshot(path=MEDIA / "02-hubs-groups.png", full_page=True)
    page.get_by_role("tab", name="↝ Path tracer").click()
    page.wait_for_timeout(1200)
    page.screenshot(path=MEDIA / "03-path-tracer.png", full_page=True)
    page.get_by_role("tab", name="🪙 Token report").click()
    page.wait_for_timeout(1200)
    page.screenshot(path=MEDIA / "04-token-report.png", full_page=True)
    page.get_by_role("tab", name="🕸️ Graph").click()
    page.wait_for_timeout(2000)
    video = page.video
    context.close()
    video.save_as(str(MEDIA / "05-walkthrough.mp4"))
    Path(video.path()).unlink(missing_ok=True)
    browser.close()
print(f"Saved screenshots and walkthrough to {MEDIA}")
