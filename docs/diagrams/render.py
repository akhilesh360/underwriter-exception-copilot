"""Render docs/architecture.png, architecture@2x.png and flow.png from the HTML sources here."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image

HERE = Path(__file__).parent
DOCS = HERE.parent
CHROME = "/opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell"

def shot(p, html, w, h, out):
    b = p.chromium.launch(executable_path=CHROME)
    pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
    pg.goto((HERE / html).resolve().as_uri()); pg.wait_for_timeout(1500)
    pg.evaluate("document.fonts.ready")
    pg.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h}); b.close()

with sync_playwright() as p:
    shot(p, "architecture.html", 1920, 1080, DOCS / "architecture@2x.png")
    Image.open(DOCS / "architecture@2x.png").resize((1920, 1080), Image.LANCZOS).save(DOCS / "architecture.png")
    shot(p, "flow.html", 1800, 470, DOCS / "flow.png")
