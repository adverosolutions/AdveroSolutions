"""Render the funnel's image assets and the design previews.

python3 src/render.py assets   -> assets/*.png (@2x, transparent) and assets/bg-*.jpg
python3 src/render.py design   -> design-desktop.png, design-mobile.png (both pages)
python3 src/render.py          -> both
"""
import io
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
ASSETS = ROOT / "assets"

# element id -> (file, display width in the build sheet). Output is always 2x the display width.
PNG_ASSETS = {
    "asset-logo": ("logo-harlow.png", 232),
    "asset-step-1": ("step-1.png", 64),
    "asset-step-2": ("step-2.png", 64),
    "asset-step-3": ("step-3.png", 64),
    "asset-phone-thread": ("phone-thread.png", 600),
    "asset-phone-received": ("phone-received.png", 420),
}
BG_ASSETS = {"bg-sky": "bg-sky.jpg", "bg-soft": "bg-soft.jpg"}


def dither_jpg(png_bytes, out):
    """Light noise so the soft gradients do not band after JPG compression."""
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    noise = Image.effect_noise(im.size, 6).convert("L")
    noise = noise.point(lambda v: v - 128)
    px, nz = im.load(), noise.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            n = (nz[x, y] if nz[x, y] < 128 else nz[x, y] - 256) * 0.35
            r, g, b = px[x, y]
            px[x, y] = (int(r + n), int(g + n), int(b + n))
    im.save(out, "JPEG", quality=88, optimize=True, progressive=True)


def render_assets(pw):
    browser = pw.chromium.launch(channel="chrome")
    for el_id, (name, display_w) in PNG_ASSETS.items():
        probe = browser.new_page(viewport={"width": 2000, "height": 1400})
        probe.goto((SRC / "assets.html").as_uri())
        src_w = probe.locator(f"#{el_id}").bounding_box()["width"]
        probe.close()
        page = browser.new_page(device_scale_factor=2 * display_w / src_w, viewport={"width": 2000, "height": 1400})
        page.goto((SRC / "assets.html").as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.locator(f"#{el_id}").screenshot(path=str(ASSETS / name), omit_background=True)
        page.close()
        print("wrote", name, Image.open(ASSETS / name).size, "display width", display_w)
    page1 = browser.new_page(device_scale_factor=1, viewport={"width": 2000, "height": 1400})
    page1.goto((SRC / "assets.html").as_uri())
    page1.wait_for_load_state("networkidle")
    for el_id, name in BG_ASSETS.items():
        data = page1.locator(f"#{el_id}").screenshot()
        dither_jpg(data, ASSETS / name)
        print("wrote", name, Image.open(ASSETS / name).size)
    browser.close()


def shot(browser, width, page_id, scale):
    page = browser.new_page(device_scale_factor=scale, viewport={"width": width, "height": 900})
    page.goto((ROOT / "design.html").as_uri() + f"?page={page_id}")
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(300)
    data = page.screenshot(full_page=True)
    page.close()
    return Image.open(io.BytesIO(data)).convert("RGB")


def side_by_side(images, gap, bg=(214, 222, 232)):
    w = sum(i.width for i in images) + gap * (len(images) + 1)
    h = max(i.height for i in images) + gap * 2
    canvas = Image.new("RGB", (w, h), bg)
    x = gap
    for i in images:
        canvas.paste(i, (x, gap))
        x += i.width + gap
    return canvas


def render_design(pw):
    browser = pw.chromium.launch(channel="chrome")
    d1, d2 = shot(browser, 1440, 1, 1), shot(browser, 1440, 2, 1)
    side_by_side([d1, d2], 60).save(ROOT / "design-desktop.png", optimize=True)
    m1, m2 = shot(browser, 390, 1, 2), shot(browser, 390, 2, 2)
    side_by_side([m1, m2], 80).save(ROOT / "design-mobile.png", optimize=True)
    browser.close()
    print("wrote design-desktop.png, design-mobile.png")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    with sync_playwright() as pw:
        if what in ("assets", "all"):
            render_assets(pw)
        if what in ("design", "all"):
            render_design(pw)
