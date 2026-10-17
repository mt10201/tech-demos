"""Dev helper: `python capture.py` = demo screenshots + video; `python capture.py backtest` = Backtest tab screenshots."""
import pathlib, shutil
from playwright.sync_api import sync_playwright
URL = "http://localhost:8501"; OUT = pathlib.Path(__file__).parent / "media"
def capture_demo():
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


def capture_backtest(url: str = URL):
    """Screenshots of the Backtest tab only (no video)."""
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1400, "height": 1100})
        pg.goto(url); pg.wait_for_selector("text=Live markets", timeout=60000)
        pg.get_by_role("tab", name="Backtest").click(); pg.wait_for_selector("text=Touch model", timeout=60000)
        pg.wait_for_timeout(4000); pg.screenshot(path=str(OUT / "backtest.png"), full_page=True)
        el = pg.get_by_text("Reality check")
        if el.count():
            el.first.scroll_into_view_if_needed(); pg.wait_for_timeout(1500)
            pg.screenshot(path=str(OUT / "backtest_wallet.png"))
        br.close()


def capture_bands(url: str = URL):
    """Screenshots of the band backtest section (touch any / touch last 1m / realistic last 1m) and the wallet comparison."""
    def top(pg, text):
        pg.get_by_text(text).first.evaluate("e => e.scrollIntoView({block: 'start'})"); pg.wait_for_timeout(1500)
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1500, "height": 1400})
        pg.goto(url); pg.wait_for_selector("text=Live markets", timeout=60000)
        pg.get_by_role("tab", name="Backtest").click(); pg.wait_for_selector("text=Bands where the wallet profits", timeout=60000)
        pg.wait_for_timeout(3000); top(pg, "Bands where the wallet profits")
        pg.screenshot(path=str(OUT / "bands_touch.png"))
        def pick_window(label):
            top(pg, "Bands where the wallet profits")
            pg.get_by_role("combobox", name="Entry window (near-sure bands)").click(); pg.wait_for_timeout(800)
            pg.get_by_role("option", name=label).click(); pg.wait_for_timeout(2500)
        pick_window("last 1m"); top(pg, "Bands where the wallet profits")
        pg.screenshot(path=str(OUT / "bands_touch_last1m.png"))
        pg.get_by_text("realistic", exact=True).click(); pg.wait_for_timeout(3000); top(pg, "Bands where the wallet profits")
        pg.screenshot(path=str(OUT / "bands_realistic_last1m.png"))
        top(pg, "Low bands (5–20¢)")
        pg.screenshot(path=str(OUT / "bands_wallet.png"))
        br.close()

if __name__ == "__main__":
    import sys
    capture_bands() if "bands" in sys.argv else capture_backtest() if "backtest" in sys.argv else capture_demo()
