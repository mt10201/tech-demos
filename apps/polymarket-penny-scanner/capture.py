"""Dev helper: record a screenshot + video of the running app (needs `pip install playwright`)."""
import pathlib, shutil
from playwright.sync_api import sync_playwright
URL = "http://localhost:8501"; OUT = pathlib.Path(__file__).parent / "media"
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 1400, "height": 1000}, record_video_dir=str(OUT / "tmp"))
    pg = ctx.new_page(); pg.goto(URL); pg.wait_for_selector("text=Live markets", timeout=60000)
    pg.wait_for_timeout(6000); pg.screenshot(path=str(OUT / "screenshot.png"), full_page=True)
    pg.mouse.wheel(0, 700); pg.wait_for_timeout(2500)
    pg.get_by_role("tab", name="Payoff calculator").click(); pg.wait_for_timeout(3000)
    pg.get_by_role("tab", name="Resolved history").click()
    pg.wait_for_selector("text=and then won", timeout=90000); pg.wait_for_timeout(5000)
    pg.screenshot(path=str(OUT / "history.png"), full_page=True)
    vid = pg.video; ctx.close(); br.close()
    shutil.move(vid.path(), OUT / "demo.webm"); shutil.rmtree(OUT / "tmp", ignore_errors=True)
